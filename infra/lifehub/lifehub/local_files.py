"""Privacy-safe local file connectors for LifeHub."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lifehub.lake import lake_envelope
from lifehub.sleep import load_sleep_fixture, normalize_sleep_rows, sleep_quality_events


LOCAL_KINDS = {
    "ics",
    "sleep",
    "moto_learning",
    "trade_journal",
    "personal_notes",
    "training_sessions",
    "habit_goals",
    "market_watchlist_snapshot",
    "github_project_activity",
    "learning_activity",
    "finance_event_calendar",
    "health_summary",
    "location_area_summary",
    "finance_transactions",
    "data_source_runs",
}


def import_local_file(path: Path, *, kind: str = "auto") -> list[dict]:
    selected = detect_local_kind(path) if kind == "auto" else kind
    if selected == "ics":
        return calendar_events(path)
    if selected == "sleep":
        return sleep_quality_events(normalize_sleep_rows(load_sleep_fixture(path)))
    if selected == "moto_learning":
        return moto_learning_events(load_rows(path), source_file=path.name)
    if selected == "trade_journal":
        return trade_journal_events(load_rows(path), source_file=path.name)
    if selected == "personal_notes":
        return personal_note_events(path)
    if selected in SUMMARY_IMPORTERS:
        return summary_events(selected, load_rows(path), source_file=path.name)
    raise ValueError(f"Unsupported local file kind for {path}: {selected}")


def scan_inbox(root: Path) -> list[tuple[Path, str, list[dict]]]:
    imports: list[tuple[Path, str, list[dict]]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        kind = detect_local_kind(path)
        if kind:
            imports.append((path, kind, import_local_file(path, kind=kind)))
    return imports


def detect_local_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    stem = path.stem.lower()
    name = path.name.lower()
    if suffix == ".ics":
        return "ics"
    if suffix == ".md":
        return "personal_notes"
    if suffix not in {".csv", ".json"}:
        return ""
    if "sleep" in stem:
        return "sleep"
    if "moto" in stem:
        return "moto_learning"
    if "trade" in stem or "journal" in stem:
        return "trade_journal"
    if "training" in stem or "session" in stem:
        return "training_sessions"
    if "habit" in stem or "goal" in stem:
        return "habit_goals"
    if "watchlist" in stem or "market" in stem:
        return "market_watchlist_snapshot"
    if "github" in stem or "project" in stem:
        return "github_project_activity"
    if "learning" in stem or "study" in stem:
        return "learning_activity"
    if "finance_event" in stem or "earnings" in stem:
        return "finance_event_calendar"
    if "health" in stem:
        return "health_summary"
    if "location" in stem or "area" in stem or "movement" in stem:
        return "location_area_summary"
    if "expense" in stem or "transaction" in stem or "finance" in stem:
        return "finance_transactions"
    if "source_run" in stem or "data_source" in stem or "freshness" in stem:
        return "data_source_runs"
    if "note" in name or "summary" in name:
        return "personal_notes"
    return detect_json_kind(path) if suffix == ".json" else ""


def detect_json_kind(path: Path) -> str:
    try:
        rows = load_rows(path)
    except Exception:
        return ""
    sample = rows[0] if rows else {}
    keys = {key.lower() for key in sample}
    if {"slept_at", "woke_at"} <= keys:
        return "sleep"
    if keys & {"lesson", "topic", "course", "practice_minutes", "confidence_score"}:
        return "moto_learning"
    if keys & {"symbol", "instrument", "pnl", "pnl_r", "setup", "entry_time"}:
        return "trade_journal"
    if {"activity_type", "duration_minutes", "load_score"} <= keys:
        return "training_sessions"
    if {"goal_bucket", "target_count", "done_count"} <= keys:
        return "habit_goals"
    if {"symbol_bucket", "volatility_bucket"} <= keys:
        return "market_watchlist_snapshot"
    if {"repo_bucket", "activity_count", "focus_bucket"} <= keys:
        return "github_project_activity"
    if {"topic_bucket", "duration_minutes", "progress_state"} <= keys:
        return "learning_activity"
    if {"event_date", "event_bucket", "urgency"} <= keys:
        return "finance_event_calendar"
    if {"metric_date", "metric_name", "metric_value", "unit"} <= keys:
        return "health_summary"
    if {"area_bucket", "dwell_minutes", "movement_mode"} <= keys:
        return "location_area_summary"
    if {"category_bucket", "amount_bucket", "currency"} <= keys:
        return "finance_transactions"
    if {"source_name", "status", "freshness_minutes"} <= keys:
        return "data_source_runs"
    if keys & {"summary", "title", "body", "tags"}:
        return "personal_notes"
    return ""


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix != ".json":
        raise ValueError(f"Expected CSV or JSON rows, got {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("events", "rows", "items", "nights", "notes", "trades", "sessions"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = [payload]
    else:
        raise ValueError(f"JSON source must be an object or list: {path}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Rows must be JSON objects: {path}")
    return list(rows)


def calendar_events(path: Path) -> list[dict]:
    return [
        lake_envelope(
            source_name="calendar_events",
            event_type="calendar_busy_block",
            event_time=item["started_at"],
            privacy_class="private_behavior_summary",
            source_tier="tier_2_personal_context",
            source_type="local_calendar_export",
            raw_policy="local_raw_only",
            local_policy="summarized_landing_only",
            payload_summary={
                "duration_minutes": item["duration_minutes"],
                "summary_category": item["summary_category"],
            },
            metrics={"duration_minutes": item["duration_minutes"]},
            tags=["calendar", item["summary_category"]],
            payload=item,
        )
        for item in parse_ics(path)
    ]


def parse_ics(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    lines = unfold_ics_lines(text.splitlines())
    blocks: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            blocks.append(current)
            current = None
        elif current is not None and ":" in line:
            raw_key, value = line.split(":", 1)
            key = raw_key.split(";", 1)[0].upper()
            current.setdefault(key, []).append(value.strip())

    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    for index, block in enumerate(blocks, start=1):
        raw_start = first(block, "DTSTART")
        start = parse_ics_datetime(raw_start)
        if start is None:
            raise ValueError(f"VEVENT {index} in {path} is missing DTSTART.")
        end = parse_ics_datetime(first(block, "DTEND")) or start
        duration_minutes = max(0, int((end - start).total_seconds() // 60))
        summary = first(block, "SUMMARY") or ""
        description = first(block, "DESCRIPTION") or ""
        location = first(block, "LOCATION") or ""
        events.append(
            {
                "started_at": start.isoformat(),
                "ended_at": end.isoformat(),
                "duration_minutes": duration_minutes,
                "all_day": bool(raw_start and "T" not in raw_start),
                "summary_hash": stable_hash(summary),
                "summary_category": classify_text(summary),
                "location_present": bool(location),
                "description_present": bool(description),
                "attendee_count": len(block.get("ATTENDEE", [])),
                "status": (first(block, "STATUS") or "CONFIRMED").lower(),
                "source_file_hash": stable_hash(path.name),
                "source_extension": path.suffix.lower().lstrip("."),
                "imported_at": imported_at,
            }
        )
    return events


def unfold_ics_lines(lines: Iterable[str]) -> list[str]:
    unfolded: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line.strip())
    return unfolded


def parse_ics_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if len(raw) == 8 and raw.isdigit():
        return datetime.fromisoformat(raw)
    if raw.endswith("Z"):
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" in raw:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S")
    return datetime.fromisoformat(raw)


def moto_learning_events(rows: list[dict[str, Any]], *, source_file: str) -> list[dict]:
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    for index, row in enumerate(rows, start=1):
        occurred_at = coalesce_time(row, "occurred_at", "completed_at", "started_at", "date")
        if not occurred_at:
            raise ValueError(f"Moto learning row {index} must contain occurred_at, completed_at, started_at, or date.")
        payload = {
            "occurred_at": occurred_at,
            "topic": clean_label(row.get("topic") or row.get("category") or row.get("skill")),
            "course_hash": stable_hash(row.get("course") or row.get("lesson") or row.get("title")),
            "practice_minutes": optional_int(row.get("practice_minutes") or row.get("duration_minutes")),
            "confidence_score": optional_int(row.get("confidence_score") or row.get("confidence")),
            "quiz_score": optional_float(row.get("quiz_score") or row.get("score")),
            "completed": optional_bool(row.get("completed")),
            "source_file_hash": stable_hash(source_file),
            "imported_at": imported_at,
        }
        events.append(
            lake_envelope(
                source_name="moto_learning_log",
                event_type="moto_learning_session",
                event_time=occurred_at,
                privacy_class="private_behavior_summary",
                source_tier="tier_2_personal_context",
                source_type="local_csv_json_import",
                raw_policy="local_raw_only",
                local_policy="summarized_landing_only",
                payload=drop_none(payload),
            )
        )
    return events


def trade_journal_events(rows: list[dict[str, Any]], *, source_file: str) -> list[dict]:
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    for index, row in enumerate(rows, start=1):
        occurred_at = coalesce_time(row, "occurred_at", "closed_at", "entry_time", "date")
        if not occurred_at:
            raise ValueError(f"Trade journal row {index} must contain occurred_at, closed_at, entry_time, or date.")
        payload = {
            "occurred_at": occurred_at,
            "asset_class": clean_label(row.get("asset_class") or row.get("market")),
            "instrument_hash": stable_hash(row.get("instrument") or row.get("symbol") or row.get("ticker")),
            "side": clean_label(row.get("side")),
            "setup_hash": stable_hash(row.get("setup") or row.get("strategy")),
            "result": clean_label(row.get("result") or row.get("outcome")),
            "pnl_r": optional_float(row.get("pnl_r") or row.get("r_multiple")),
            "pnl_pct": optional_float(row.get("pnl_pct") or row.get("return_pct")),
            "risk_pct": optional_float(row.get("risk_pct")),
            "duration_minutes": optional_int(row.get("duration_minutes")),
            "emotion": clean_label(row.get("emotion") or row.get("mood")),
            "notes_hash": stable_hash(row.get("notes") or row.get("comment")),
            "source_file_hash": stable_hash(source_file),
            "imported_at": imported_at,
        }
        events.append(
            lake_envelope(
                source_name="trade_journal_summary",
                event_type="trade_journal_entry",
                event_time=occurred_at,
                privacy_class="private_finance_summary",
                source_tier="tier_3_sensitive_life",
                source_type="local_trade_journal_export",
                raw_policy="local_raw_only",
                local_policy="summarized_landing_only",
                payload=drop_none(payload),
            )
        )
    return events


def personal_note_events(path: Path) -> list[dict]:
    if path.suffix.lower() == ".md":
        rows = [parse_markdown_note(path)]
    else:
        rows = load_rows(path)
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    for index, row in enumerate(rows, start=1):
        occurred_at = coalesce_time(row, "occurred_at", "created_at", "updated_at", "date") or imported_at
        title = row.get("title") or ""
        summary = row.get("summary") or row.get("body") or row.get("content") or ""
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if not isinstance(tags, list):
            tags = []
        payload = {
            "occurred_at": occurred_at,
            "title_hash": stable_hash(title),
            "summary_hash": stable_hash(summary),
            "word_count": word_count(summary),
            "tags": [clean_label(tag) for tag in tags[:12] if clean_label(tag)],
            "mood": clean_label(row.get("mood")),
            "source_file_hash": stable_hash(path.name),
            "source_extension": path.suffix.lower().lstrip("."),
            "row_number": index,
            "imported_at": imported_at,
        }
        events.append(
            lake_envelope(
                source_name="personal_notes_summary",
                event_type="personal_note_summary",
                event_time=occurred_at,
                privacy_class="private_behavior_summary",
                source_tier="tier_2_personal_context",
                source_type="local_markdown_json_summary",
                raw_policy="local_raw_only",
                local_policy="summarized_landing_only",
                payload=drop_none(payload),
            )
        )
    return events


SUMMARY_IMPORTERS = {
    "training_sessions": {
        "event_type": "training_session_summary",
        "event_time_fields": ("occurred_at", "started_at", "date"),
        "privacy_class": "private_behavior_summary",
        "source_tier": "tier_2_personal_context",
        "source_type": "derived_training_session",
        "metrics": ("duration_minutes", "load_score", "intensity", "fatigue_score"),
        "labels": ("activity_type", "result", "venue_bucket"),
    },
    "habit_goals": {
        "event_type": "habit_goal_progress",
        "event_time_fields": ("updated_at", "date"),
        "privacy_class": "private_behavior_summary",
        "source_tier": "tier_2_personal_context",
        "source_type": "local_config_and_manual_events",
        "metrics": ("target_count", "done_count", "streak_days"),
        "labels": ("goal_bucket", "status", "skipped_reason_bucket"),
    },
    "market_watchlist_snapshot": {
        "event_type": "market_watchlist_snapshot",
        "event_time_fields": ("observed_at", "date"),
        "privacy_class": "public_context",
        "source_tier": "tier_1_foundation",
        "source_type": "market_data_api",
        "metrics": ("volatility_score", "relative_volume", "change_pct"),
        "labels": ("symbol_bucket", "volatility_bucket", "direction", "attention_state"),
    },
    "github_project_activity": {
        "event_type": "github_project_activity",
        "event_time_fields": ("observed_at", "date"),
        "privacy_class": "public_context",
        "source_tier": "tier_1_foundation",
        "source_type": "public_api",
        "metrics": ("activity_count", "commit_count", "issue_count", "pr_count"),
        "labels": ("repo_bucket", "focus_bucket", "maintenance_state"),
    },
    "learning_activity": {
        "event_type": "learning_activity",
        "event_time_fields": ("occurred_at", "date"),
        "privacy_class": "private_behavior_summary",
        "source_tier": "tier_2_personal_context",
        "source_type": "local_notes_or_project_summary",
        "metrics": ("duration_minutes", "progress_pct", "artifact_count"),
        "labels": ("topic_bucket", "progress_state", "next_action_bucket"),
    },
    "finance_event_calendar": {
        "event_type": "finance_event_calendar_item",
        "event_time_fields": ("event_date", "date"),
        "privacy_class": "private_finance_summary",
        "source_tier": "tier_2_personal_context",
        "source_type": "local_calendar_or_public_finance_events",
        "metrics": ("urgency", "days_until"),
        "labels": ("event_bucket", "impact_bucket", "watchlist_bucket"),
    },
    "health_summary": {
        "event_type": "health_metric_summary",
        "event_time_fields": ("metric_date", "date"),
        "privacy_class": "private_health_summary",
        "source_tier": "tier_3_sensitive_life",
        "source_type": "wearable_or_health_export",
        "metrics": ("metric_value", "resting_hr", "hrv_ms", "steps", "active_minutes"),
        "labels": ("metric_name", "unit", "device_bucket"),
    },
    "location_area_summary": {
        "event_type": "location_area_summary",
        "event_time_fields": ("occurred_at", "date"),
        "privacy_class": "private_location_summary",
        "source_tier": "tier_3_sensitive_life",
        "source_type": "local_location_history",
        "metrics": ("dwell_minutes", "distance_km"),
        "labels": ("area_bucket", "movement_mode", "city_bucket", "precision_bucket"),
    },
    "finance_transactions": {
        "event_type": "finance_transaction_summary",
        "event_time_fields": ("occurred_at", "booked_at", "date"),
        "privacy_class": "private_finance_summary",
        "source_tier": "tier_3_sensitive_life",
        "source_type": "local_bank_or_budget_export",
        "metrics": ("transaction_count",),
        "labels": ("category_bucket", "amount_bucket", "currency", "account_bucket", "direction"),
    },
    "data_source_runs": {
        "event_type": "data_source_run",
        "event_time_fields": ("observed_at", "started_at", "date"),
        "privacy_class": "derived_context",
        "source_tier": "tier_1_foundation",
        "source_type": "pipeline_observability",
        "metrics": ("freshness_minutes", "row_count", "error_count", "duration_seconds"),
        "labels": ("source_name", "status", "quality_state"),
    },
}


def summary_events(kind: str, rows: list[dict[str, Any]], *, source_file: str) -> list[dict]:
    config = SUMMARY_IMPORTERS[kind]
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    for index, row in enumerate(rows, start=1):
        event_time = coalesce_time(row, *config["event_time_fields"])
        if not event_time:
            raise ValueError(f"{kind} row {index} is missing one of {config['event_time_fields']}.")
        labels = {field: clean_label(row.get(field)) for field in config["labels"] if clean_label(row.get(field))}
        metrics = {
            field: optional_float(row.get(field))
            for field in config["metrics"]
            if row.get(field) not in (None, "")
        }
        payload = {
            "event_time": event_time,
            "source_file_hash": stable_hash(source_file),
            "row_number": index,
            "imported_at": imported_at,
            **labels,
            **metrics,
        }
        if kind == "data_source_runs" and "source_name" in labels:
            payload["tracked_source_hash"] = stable_hash(labels["source_name"])
        events.append(
            lake_envelope(
                source_name=kind,
                event_type=config["event_type"],
                event_time=event_time,
                privacy_class=config["privacy_class"],
                source_tier=config["source_tier"],
                source_type=config["source_type"],
                raw_policy="local_raw_only" if kind != "market_watchlist_snapshot" else "public_fixture_ok",
                local_policy="summarized_landing_only",
                payload_summary={
                    "source_file_hash": stable_hash(source_file),
                    "row_number": index,
                    "labels": labels,
                },
                metrics=metrics,
                tags=[kind, str(config["source_type"]), *labels.values()],
                quality_flags=["summary_only", "raw_local_only"],
                payload=drop_none(payload),
            )
        )
    return events


def parse_markdown_note(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        _, raw_meta, body = text.split("---\n", 2)
        for line in raw_meta.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
    title = metadata.get("title") or ""
    if not title:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    metadata.setdefault("title", title)
    metadata.setdefault("summary", body)
    return metadata


def first(block: dict[str, list[str]], key: str) -> str | None:
    values = block.get(key)
    return values[0] if values else None


def coalesce_time(row: dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def stable_hash(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def classify_text(value: Any) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("doctor", "medical", "therapy", "dentist")):
        return "health"
    if any(token in text for token in ("work", "sync", "standup", "review", "meeting")):
        return "work"
    if any(token in text for token in ("train", "gym", "run", "ride", "moto")):
        return "training"
    if any(token in text for token in ("family", "friend", "dinner", "coffee")):
        return "social"
    return "personal"


def clean_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_ -]", "", text)[:48]


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value), 6)


def optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "done", "completed"}


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+\b", str(value or "")))


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "")}
