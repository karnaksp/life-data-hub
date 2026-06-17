"""Sleep quality source normalization for LifeHub."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lifehub.lake import lake_envelope


@dataclass(frozen=True)
class SleepQualityEvent:
    slept_at: str
    woke_at: str
    duration_minutes: int
    quality_score: int
    recovery_score: int
    sleep_efficiency: float
    source: str
    imported_at: str


def load_sleep_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("nights"), list):
        rows = payload["nights"]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("Sleep quality source must be a JSON list or {'nights': [...]} object.")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Sleep quality rows must be JSON objects.")
    return list(rows)


def normalize_sleep_rows(rows: list[dict[str, Any]], *, source: str = "local_sleep_log") -> list[SleepQualityEvent]:
    events = []
    imported_at = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(rows, start=1):
        slept_at = str(row.get("slept_at") or "")
        woke_at = str(row.get("woke_at") or "")
        if not slept_at or not woke_at:
            raise ValueError(f"Sleep row {index} must contain slept_at and woke_at.")
        start = datetime.fromisoformat(slept_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(woke_at.replace("Z", "+00:00"))
        duration_minutes = int((end - start).total_seconds() // 60)
        if duration_minutes <= 0:
            raise ValueError(f"Sleep row {index} duration must be positive.")
        quality_score = bounded_int(row.get("quality_score", 0), "quality_score", 1, 100)
        recovery_score = bounded_int(row.get("recovery_score", quality_score), "recovery_score", 1, 100)
        in_bed_minutes = int(row.get("in_bed_minutes") or duration_minutes)
        if in_bed_minutes < duration_minutes:
            raise ValueError(f"Sleep row {index} in_bed_minutes must be >= duration_minutes.")
        sleep_efficiency = round(duration_minutes / in_bed_minutes, 3)
        events.append(
            SleepQualityEvent(
                slept_at=slept_at,
                woke_at=woke_at,
                duration_minutes=duration_minutes,
                quality_score=quality_score,
                recovery_score=recovery_score,
                sleep_efficiency=sleep_efficiency,
                source=str(row.get("source") or source),
                imported_at=imported_at,
            )
        )
    return events


def bounded_int(value: Any, field: str, lower: int, upper: int) -> int:
    number = int(value)
    if not lower <= number <= upper:
        raise ValueError(f"{field} must be between {lower} and {upper}.")
    return number


def sleep_quality_events(rows: list[SleepQualityEvent]) -> list[dict]:
    return [
        lake_envelope(
            source_name="sleep_quality",
            event_type="sleep_quality_night",
            event_time=row.woke_at,
            privacy_class="private_recovery_summary",
            payload=asdict(row),
        )
        for row in rows
    ]


def summarize_sleep(rows: list[SleepQualityEvent]) -> dict[str, float | int | str]:
    if not rows:
        return {}
    ordered = sorted(rows, key=lambda row: row.woke_at)
    latest = ordered[-1]
    nights = len(ordered)
    avg_duration = sum(row.duration_minutes for row in ordered) / nights
    avg_quality = sum(row.quality_score for row in ordered) / nights
    avg_recovery = sum(row.recovery_score for row in ordered) / nights
    avg_efficiency = sum(row.sleep_efficiency for row in ordered) / nights
    return {
        "nights": nights,
        "latest_woke_at": latest.woke_at,
        "latest_duration_minutes": latest.duration_minutes,
        "latest_quality_score": latest.quality_score,
        "latest_recovery_score": latest.recovery_score,
        "avg_duration_minutes": round(avg_duration, 1),
        "avg_quality_score": round(avg_quality, 1),
        "avg_recovery_score": round(avg_recovery, 1),
        "avg_sleep_efficiency": round(avg_efficiency, 3),
    }
