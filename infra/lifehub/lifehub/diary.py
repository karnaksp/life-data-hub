"""Telegram diary command parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


ACTIVITY_TYPES = {
    "skate",
    "snowboard",
    "volleyball",
    "moto_lesson",
    "gym",
    "walk",
    "rest",
}
RESULTS = {"good", "ok", "bad", "skipped"}


@dataclass(frozen=True)
class ActivityLog:
    activity_type: str
    start_time: str | None
    end_time: str | None
    location_label: str | None
    intensity: int
    mood: int
    fatigue: int
    pain_flag: bool
    pain_text: str | None
    result: str
    notes: str
    logged_at: str


def parse_log_command(text: str) -> ActivityLog:
    """Parse compact and detailed Telegram diary entries.

    Compact form:
    /log skate 7 8 4 good dry session

    Detailed form:
    /log activity=skate intensity=7 mood=8 fatigue=4 result=good loc=spot pain=no notes=dry
    """

    parts = text.strip().split(maxsplit=6)
    if len(parts) < 6 or parts[0] != "/log":
        raise ValueError(
            "Use: /log activity intensity mood fatigue result notes; "
            "or /log activity=skate intensity=7 mood=8 fatigue=4 result=good loc=spot pain=no notes=text"
        )
    if "=" in parts[1]:
        return parse_key_value_log(text)

    activity, intensity, mood, fatigue, result = parts[1:6]
    notes = parts[6] if len(parts) > 6 else ""
    return build_log(
        activity=activity,
        intensity=intensity,
        mood=mood,
        fatigue=fatigue,
        result=result,
        notes=notes,
    )


def parse_key_value_log(text: str) -> ActivityLog:
    payload = text.strip()[len("/log") :].strip()
    values: dict[str, str] = {}
    for token in payload.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip().lower()] = value.strip()
    missing = [key for key in ["activity", "intensity", "mood", "fatigue", "result"] if key not in values]
    if missing:
        raise ValueError(f"Missing /log fields: {', '.join(missing)}")
    pain_value = values.get("pain", values.get("pain_flag", "no"))
    pain_flag = pain_value.lower() in {"1", "yes", "true", "y", "pain"}
    notes = values.get("notes", "")
    return build_log(
        activity=values["activity"],
        intensity=values["intensity"],
        mood=values["mood"],
        fatigue=values["fatigue"],
        result=values["result"],
        notes=notes.replace("_", " "),
        start_time=values.get("start"),
        end_time=values.get("end"),
        location_label=values.get("loc", values.get("location")),
        pain_flag=pain_flag,
        pain_text=values.get("pain_text"),
    )


def build_log(
    *,
    activity: str,
    intensity: str,
    mood: str,
    fatigue: str,
    result: str,
    notes: str,
    start_time: str | None = None,
    end_time: str | None = None,
    location_label: str | None = None,
    pain_flag: bool = False,
    pain_text: str | None = None,
) -> ActivityLog:
    if activity not in ACTIVITY_TYPES:
        raise ValueError(f"Unknown activity: {activity}")
    if result not in RESULTS:
        raise ValueError(f"Unknown result: {result}")
    return ActivityLog(
        activity_type=activity,
        start_time=start_time,
        end_time=end_time,
        location_label=location_label.replace("_", " ") if location_label else None,
        intensity=bounded_int("intensity", intensity),
        mood=bounded_int("mood", mood),
        fatigue=bounded_int("fatigue", fatigue),
        pain_flag=pain_flag,
        pain_text=pain_text.replace("_", " ") if pain_text else None,
        result=result,
        notes=notes,
        logged_at=datetime.now(timezone.utc).isoformat(),
    )


def bounded_int(label: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer from 1 to 10") from exc
    if parsed < 1 or parsed > 10:
        raise ValueError(f"{label} must be from 1 to 10")
    return parsed


def command_name(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return ""
    return stripped.split(maxsplit=1)[0]
