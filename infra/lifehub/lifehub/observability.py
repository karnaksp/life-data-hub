"""Local-first observability helpers for LifeHub.

The CLI should keep human-readable stdout for scripts and Make targets, while
runtime evidence needs structured events that can be analyzed later. This module
writes privacy-safe JSONL under data/private by default.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lifehub.config import ROOT


DEFAULT_LOG_PATH = ROOT / "data" / "private" / "logs" / "lifehub" / "events.jsonl"
SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "chat_id",
    "cookie",
    "authorization",
    "api_key",
    "dsn",
    "credential",
)


def configure_logging(level: str | None = None) -> None:
    """Configure standard logging once for services that use logging.Logger."""

    configured_level = (level or os.getenv("LIFEHUB_LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, configured_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def default_log_path() -> Path:
    return Path(os.getenv("LIFEHUB_LOG_PATH", DEFAULT_LOG_PATH))


def run_id() -> str:
    configured = os.getenv("LIFEHUB_RUN_ID")
    if configured:
        return configured
    generated = str(uuid.uuid4())
    os.environ["LIFEHUB_RUN_ID"] = generated
    return generated


def record_event(
    *,
    component: str,
    action: str,
    status: str = "ok",
    message: str = "",
    metrics: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Append one sanitized operational event and return the stored payload."""

    event = {
        "event_time": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id(),
        "component": component,
        "action": action,
        "status": status,
        "message": message,
        "metrics": sanitize(metrics or {}),
        "fields": sanitize(fields or {}),
    }
    target = log_path or default_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def sanitize(value: Any) -> Any:
    """Remove direct secrets and raw free text from log fields."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def read_events(
    path: Path | None = None,
    *,
    limit: int = 100,
    component: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    target = path or default_log_path()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if component and event.get("component") != component:
            continue
        if status and event.get("status") != status:
            continue
        rows.append(event)
    if limit <= 0:
        return rows
    return rows[-limit:]


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    by_status = Counter(str(row.get("status", "")) for row in rows)
    by_component = Counter(str(row.get("component", "")) for row in rows)
    failures = [
        row
        for row in rows
        if str(row.get("status", "")).lower() in {"error", "failed", "failure", "skipped"}
    ]
    return {
        "events": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_component": dict(sorted(by_component.items())),
        "latest_event_time": rows[-1].get("event_time", "") if rows else "",
        "recent_failures": failures[-5:],
    }


def render_log_summary(events: Iterable[dict[str, Any]]) -> str:
    summary = summarize_events(events)
    lines = [
        "LifeHub runtime logs",
        f"Events: {summary['events']}",
        f"Latest event: {summary['latest_event_time'] or 'none'}",
    ]
    if summary["by_status"]:
        statuses = ", ".join(f"{key} {value}" for key, value in summary["by_status"].items())
        lines.append(f"Status: {statuses}")
    if summary["by_component"]:
        components = ", ".join(f"{key} {value}" for key, value in summary["by_component"].items())
        lines.append(f"Components: {components}")
    failures = summary["recent_failures"]
    if failures:
        lines.append("Recent failures:")
        for item in failures:
            lines.append(
                f"- {item.get('event_time', '')} {item.get('component', '')} "
                f"{item.get('action', '')}: {item.get('message', '')}"
            )
    return "\n".join(lines)
