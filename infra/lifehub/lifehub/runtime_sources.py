"""Convert LifeHub runtime logs into source freshness events."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Iterable

from lifehub.lake import lake_envelope
from lifehub.observability import default_log_path, read_events, sanitize


FAILURE_STATUSES = {"error", "failed", "failure", "skipped"}


def runtime_log_source_events(
    path: Path | None = None,
    *,
    observed_at: str | None = None,
    limit: int = 5000,
) -> list[dict]:
    """Summarize local runtime JSONL into `data_source_runs` landing events."""

    target = path or default_log_path()
    now = observed_at or datetime.now(timezone.utc).isoformat()
    events = read_events(target, limit=limit)
    if not events:
        return [runtime_source_event("runtime_log", "missing", now, 0, 1, "no_runtime_events", target)]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        component = str(event.get("component") or "unknown_component")
        grouped[component].append(event)

    rows = []
    for component, component_events in sorted(grouped.items()):
        rows.append(component_source_event(component, component_events, now, target))
    rows.append(overall_source_event(events, now, target))
    return rows


def load_source_run_status(landing_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    """Read latest `data_source_runs` landing events as source health rows."""

    landing_dir = landing_root / "lifehub" / "landing" / "data_source_runs"
    if not landing_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(landing_dir.glob("dt=*/events.jsonl")):
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "source_name": payload.get("source_name") or event.get("source_name") or "unknown",
                    "status": payload.get("status") or "unknown",
                    "quality_state": payload.get("quality_state") or "",
                    "freshness_minutes": int(float(payload.get("freshness_minutes") or 0)),
                    "row_count": int(float(payload.get("row_count") or 0)),
                    "error_count": int(float(payload.get("error_count") or 0)),
                    "latest_event_time": payload.get("latest_event_time") or event.get("event_time") or "",
                    "observed_at": payload.get("observed_at") or event.get("event_time") or "",
                    "last_error": payload.get("last_error") or "",
                }
            )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["source_name"])
        if key not in latest or str(row.get("observed_at", "")) >= str(latest[key].get("observed_at", "")):
            latest[key] = row
    ordered = sorted(
        latest.values(),
        key=lambda row: (int(row.get("error_count") or 0) == 0, str(row.get("source_name") or "")),
    )
    return ordered[:limit]


def render_source_run_status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "\n".join(
            [
                "LifeHub source health",
                "No data_source_runs landing events yet.",
                "Run: PYTHONPATH=infra/lifehub python -m lifehub.cli runtime-log-import",
            ]
        )
    lines = ["LifeHub source health"]
    for row in rows:
        status = str(row.get("status") or "unknown")
        errors = int(row.get("error_count") or 0)
        freshness = int(row.get("freshness_minutes") or 0)
        suffix = f"{status}; fresh {freshness}m; rows {int(row.get('row_count') or 0)}"
        if errors:
            suffix += f"; errors {errors}"
        if row.get("last_error"):
            suffix += f"; last: {row['last_error']}"
        lines.append(f"- {row.get('source_name')}: {suffix}")
    return "\n".join(lines)


def component_source_event(component: str, events: list[dict[str, Any]], observed_at: str, path: Path) -> dict:
    latest_event = latest_by_time(events)
    failures = [event for event in events if str(event.get("status", "")).lower() in FAILURE_STATUSES]
    status = "failed" if failures else "ok"
    quality_state = "has_failures" if failures else "fresh"
    return runtime_source_event(
        source_label=component,
        status=status,
        observed_at=observed_at,
        row_count=len(events),
        error_count=len(failures),
        quality_state=quality_state,
        path=path,
        latest_event=latest_event,
        status_counts=dict(Counter(str(event.get("status", "unknown")) for event in events)),
        last_error=last_error_message(failures),
    )


def overall_source_event(events: list[dict[str, Any]], observed_at: str, path: Path) -> dict:
    failures = [event for event in events if str(event.get("status", "")).lower() in FAILURE_STATUSES]
    status = "failed" if failures else "ok"
    quality_state = "has_failures" if failures else "fresh"
    return runtime_source_event(
        source_label="lifehub_runtime",
        status=status,
        observed_at=observed_at,
        row_count=len(events),
        error_count=len(failures),
        quality_state=quality_state,
        path=path,
        latest_event=latest_by_time(events),
        status_counts=dict(Counter(str(event.get("status", "unknown")) for event in events)),
        last_error=last_error_message(failures),
    )


def runtime_source_event(
    source_label: str,
    status: str,
    observed_at: str,
    row_count: int,
    error_count: int,
    quality_state: str,
    path: Path,
    *,
    latest_event: dict[str, Any] | None = None,
    status_counts: dict[str, int] | None = None,
    last_error: str = "",
) -> dict:
    latest_time = str((latest_event or {}).get("event_time") or observed_at)
    freshness_minutes = minutes_between(latest_time, observed_at)
    payload = {
        "observed_at": observed_at,
        "source_name": source_label,
        "status": status,
        "quality_state": quality_state,
        "freshness_minutes": freshness_minutes,
        "row_count": row_count,
        "error_count": error_count,
        "latest_event_time": latest_time,
        "status_counts": status_counts or {},
        "last_error": sanitize_message(last_error),
        "runtime_log_hash": stable_path_hash(path),
    }
    return lake_envelope(
        source_name="data_source_runs",
        event_type="data_source_run",
        event_time=observed_at,
        privacy_class="derived_context",
        source_tier="tier_1_foundation",
        source_type="pipeline_observability",
        raw_policy="local_raw_only",
        local_policy="summarized_landing_only",
        payload_summary={
            "source_name": source_label,
            "status": status,
            "quality_state": quality_state,
            "latest_event_time": latest_time,
        },
        metrics={
            "freshness_minutes": freshness_minutes,
            "row_count": row_count,
            "error_count": error_count,
        },
        tags=["runtime_log", source_label, status, quality_state],
        quality_flags=["summary_only", "runtime_log_import", quality_state],
        payload=payload,
        idempotency_key=f"runtime-log:{source_label}:{observed_at}",
    )


def latest_by_time(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return max(events, key=lambda event: str(event.get("event_time") or ""))


def last_error_message(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    latest = latest_by_time(events)
    return str(latest.get("message") or latest.get("action") or latest.get("status") or "")


def minutes_between(start: str, end: str) -> int:
    started = parse_time(start)
    ended = parse_time(end)
    if started is None or ended is None:
        return 0
    return max(0, int((ended - started).total_seconds() // 60))


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sanitize_message(value: str) -> str:
    sanitized = sanitize({"message": value}).get("message", "")
    text = str(sanitized)
    text = re.sub(r"(?i)telegram token or chat id is not configured", "Telegram credentials missing", text)
    text = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[redacted-token]", text)
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)=\S+", r"\1=[redacted]", text)
    text = re.sub(r"(?i)(bot)[A-Za-z0-9:_-]{20,}", r"\1[redacted]", text)
    text = re.sub(r"(?i)chat id", "chat identifier", text)
    text = re.sub(r"(?i)token", "credential", text)
    return text[:180]


def stable_path_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
