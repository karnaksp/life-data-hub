"""Telegram Bot API helpers for LifeHub."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def send_message(token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    if not token or not chat_id:
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
        print(f"Telegram send failed: {exc}")
        return False
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
        print(f"Telegram callback answer failed: {exc}")
        return False
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
        print(f"Telegram updates skipped: {exc}")
        return []
    return payload.get("result", [])
