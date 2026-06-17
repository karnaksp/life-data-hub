"""Generic LifeHub local JSON source import.

This is the low-friction onboarding path for a new personal source before it
deserves a dedicated connector. It keeps raw files local, checks the source is
registered, and writes privacy-safe lake envelopes for the common Bronze job.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from lifehub.lake import lake_envelope, load_source_registry


FORBIDDEN_PAYLOAD_KEYS = {
    "address",
    "api_key",
    "chat_id",
    "email",
    "home",
    "home_address",
    "note",
    "notes",
    "pain_text",
    "phone",
    "raw_diary_notes",
    "secret",
    "telegram_bot_token",
    "token",
    "work_address",
}


def load_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        rows = payload["events"]
    elif isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = [payload]
    else:
        raise ValueError("Custom LifeHub source must be a JSON object, list, or {'events': [...]} object.")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Custom LifeHub source rows must be JSON objects.")
    return list(rows)


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in FORBIDDEN_PAYLOAD_KEYS:
                continue
            redacted[key] = redact_payload(nested)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def custom_source_events(
    *,
    source_name: str,
    rows: Iterable[dict[str, Any]],
    registry_path: Path,
    event_type: str = "custom_life_event",
    event_time_field: str = "occurred_at",
    privacy_class: str = "custom_local_summary",
) -> list[dict]:
    registry = load_source_registry(registry_path)
    if source_name not in registry["sources"]:
        known = ", ".join(sorted(registry["sources"]))
        raise ValueError(f"Source {source_name!r} is not registered in {registry_path}. Known sources: {known}")

    events = []
    for index, row in enumerate(rows, start=1):
        event_time = str(row.get(event_time_field) or row.get("event_time") or "")
        if not event_time:
            raise ValueError(f"Row {index} has no {event_time_field!r} or 'event_time' field.")
        payload = redact_payload(row)
        events.append(
            lake_envelope(
                source_name=source_name,
                event_type=str(row.get("event_type") or event_type),
                event_time=event_time,
                privacy_class=privacy_class,
                payload=payload,
            )
        )
    return events
