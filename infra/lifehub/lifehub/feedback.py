"""Decision feedback parsing for LifeHub recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from lifehub.diary import ACTIVITY_TYPES, RESULTS


FEEDBACK_ACTIONS = {"followed", "skipped", "changed"}
CALLBACK_PREFIX = "lhfb"


@dataclass(frozen=True)
class DecisionFeedback:
    activity: str
    action: str
    result: str | None
    note: str
    created_at: str


def parse_feedback_command(text: str) -> DecisionFeedback:
    """Parse Telegram feedback commands.

    Supported shapes:
    /done skate good
    /skip moto_lesson rain
    /feedback skate followed good dry_session
    """

    parts = text.strip().split(maxsplit=4)
    command = parts[0] if parts else ""
    if command == "/done":
        if len(parts) < 2:
            raise ValueError("Use: /done activity [result] [note]")
        activity = parts[1]
        result = parts[2] if len(parts) >= 3 and parts[2] in RESULTS else "good"
        note = parts[3] if len(parts) >= 4 else ""
        return build_feedback(activity, "followed", result, note)
    if command == "/skip":
        if len(parts) < 2:
            raise ValueError("Use: /skip activity [reason]")
        activity = parts[1]
        note = parts[2] if len(parts) >= 3 else ""
        return build_feedback(activity, "skipped", "skipped", note)
    if command == "/feedback":
        if len(parts) < 3:
            raise ValueError("Use: /feedback activity followed|skipped|changed [result] [note]")
        activity = parts[1]
        action = parts[2]
        result = parts[3] if len(parts) >= 4 and parts[3] in RESULTS else None
        note = parts[4] if len(parts) >= 5 else ""
        return build_feedback(activity, action, result, note)
    raise ValueError("Use: /done, /skip, or /feedback")


def parse_feedback_callback(data: str) -> DecisionFeedback:
    """Parse compact Telegram callback data.

    Supported shapes:
    lhfb:done:skate:good
    lhfb:skip:skate:skipped
    """

    parts = data.split(":", maxsplit=3)
    if len(parts) < 3 or parts[0] != CALLBACK_PREFIX:
        raise ValueError("Unknown LifeHub callback")
    action_token = parts[1]
    activity = parts[2]
    result = parts[3] if len(parts) >= 4 else None
    if action_token == "done":
        return build_feedback(activity, "followed", result if result in RESULTS else "good", "telegram button")
    if action_token == "skip":
        return build_feedback(activity, "skipped", "skipped", "telegram button")
    raise ValueError(f"Unknown callback action: {action_token}")


def feedback_keyboard(activity: str) -> dict:
    if activity not in ACTIVITY_TYPES:
        raise ValueError(f"Unknown activity: {activity}")
    return {
        "inline_keyboard": [
            [
                {"text": "Done", "callback_data": f"{CALLBACK_PREFIX}:done:{activity}:good"},
                {"text": "Skip", "callback_data": f"{CALLBACK_PREFIX}:skip:{activity}:skipped"},
            ],
            [
                {"text": "Bad fit", "callback_data": f"{CALLBACK_PREFIX}:done:{activity}:bad"},
            ],
        ]
    }


def build_feedback(
    activity: str,
    action: str,
    result: str | None,
    note: str,
) -> DecisionFeedback:
    if activity not in ACTIVITY_TYPES:
        raise ValueError(f"Unknown activity: {activity}")
    if action not in FEEDBACK_ACTIONS:
        raise ValueError(f"Unknown feedback action: {action}")
    if result is not None and result not in RESULTS:
        raise ValueError(f"Unknown result: {result}")
    return DecisionFeedback(
        activity=activity,
        action=action,
        result=result,
        note=note.replace("_", " "),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
