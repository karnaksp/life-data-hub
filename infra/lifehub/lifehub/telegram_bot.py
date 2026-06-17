"""Telegram Bot API helpers for LifeHub."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from lifehub.observability import get_logger, record_event


LOG = get_logger(__name__)


def send_message(token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    if not token or not chat_id:
        record_event(
            component="lifehub.telegram",
            action="send_message",
            status="skipped",
            message="Telegram token or chat id is not configured; printed to stdout.",
            metrics={"chars": len(text)},
            fields={"chat_id": chat_id},
        )
        print(text)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.URLError as exc:
        LOG.warning("Telegram send failed: %s", exc)
        record_event(
            component="lifehub.telegram",
            action="send_message",
            status="failure",
            message=str(exc),
            metrics={"chars": len(text)},
            fields={"chat_id": chat_id},
        )
        return False
    record_event(
        component="lifehub.telegram",
        action="send_message",
        status="success",
        metrics={"chars": len(text), "reply_markup": bool(reply_markup)},
        fields={"chat_id": chat_id},
    )
    return True


def answer_callback_query(token: str, callback_query_id: str, text: str = "") -> bool:
    if not token or not callback_query_id:
        return False
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.URLError as exc:
        LOG.warning("Telegram callback answer failed: %s", exc)
        record_event(
            component="lifehub.telegram",
            action="answer_callback_query",
            status="failure",
            message=str(exc),
        )
        return False
    record_event(component="lifehub.telegram", action="answer_callback_query", status="success")
    return True


def get_updates(token: str, offset: int | None = None) -> list[dict]:
    if not token:
        return []
    params = {"timeout": 20}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        LOG.warning("Telegram updates skipped: %s", exc)
        record_event(
            component="lifehub.telegram",
            action="get_updates",
            status="failure",
            message=str(exc),
        )
        return []
    updates = payload.get("result", [])
    record_event(
        component="lifehub.telegram",
        action="get_updates",
        status="success",
        metrics={"updates": len(updates)},
    )
    return updates
