"""Context signal events for future LifeHub domains such as trading and GitHub."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SIGNAL_DOMAINS = {"market", "github", "career", "wellbeing", "system"}
SIGNAL_DIRECTIONS = {"positive", "negative", "neutral"}


@dataclass(frozen=True)
class ContextSignal:
    signal_id: str
    domain: str
    source: str
    title: str
    direction: str
    urgency: int
    confidence: int
    summary: str
    occurred_at: str
    ingested_at: str


def load_signal_fixture(path: Path) -> list[ContextSignal]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_signals(payload)


def load_github_fixture(path: Path) -> list[ContextSignal]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_github_repo_activity(payload)


def load_market_fixture(path: Path) -> list[ContextSignal]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_market_snapshot(payload)


def fetch_github_repo_activity(owner: str, repo: str, token: str | None = None) -> list[ContextSignal]:
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "data-forge-lifehub",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repo_payload = http_json(url, headers=headers)
    return normalize_github_repo_activity({"repositories": [repo_payload]})


def normalize_github_repo_activity(payload: dict[str, Any]) -> list[ContextSignal]:
    now = datetime.now(timezone.utc).isoformat()
    signals = []
    for item in payload.get("repositories", []):
        full_name = str(item.get("full_name") or item.get("name") or "unknown/repo")
        pushed_at = str(item.get("pushed_at") or item.get("updated_at") or now)
        open_issues = int(item.get("open_issues_count") or item.get("open_issues") or 0)
        stars = int(item.get("stargazers_count") or item.get("stars") or 0)
        archived = bool(item.get("archived", False))
        if archived:
            direction = "neutral"
            urgency = 2
            title = "Archived repo"
            summary = f"{full_name} is archived; keep it out of active focus decisions."
        elif open_issues >= 10:
            direction = "negative"
            urgency = min(10, 4 + open_issues // 5)
            title = "Issue backlog needs attention"
            summary = f"{full_name} has {open_issues} open issues; schedule focused maintenance."
        else:
            direction = "positive"
            urgency = 5 if stars else 4
            title = "Project focus window"
            summary = f"{full_name} is active enough to use as a career/project context signal."
        signals.append(
            ContextSignal(
                signal_id=f"github_{slug(full_name)}_{pushed_at[:10]}",
                domain="github",
                source="github_api",
                title=title,
                direction=direction,
                urgency=urgency,
                confidence=75,
                summary=summary,
                occurred_at=pushed_at,
                ingested_at=now,
            )
        )
    return signals


def fetch_alpaca_market_snapshot(symbols: list[str], api_key: str, api_secret: str, base_url: str) -> list[ContextSignal]:
    if not symbols:
        return []
    latest_bars_url = base_url.rstrip("/") + "/v2/stocks/bars/latest?" + urllib.parse.urlencode(
        [("symbols", ",".join(symbols))]
    )
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
        "User-Agent": "data-forge-lifehub",
    }
    payload = http_json(latest_bars_url, headers=headers)
    return normalize_market_snapshot({"provider": "alpaca", "symbols": payload.get("bars", {})})


def normalize_market_snapshot(payload: dict[str, Any]) -> list[ContextSignal]:
    now = datetime.now(timezone.utc).isoformat()
    provider = str(payload.get("provider", "fixture"))
    signals = []
    symbols = payload.get("symbols", {})
    if isinstance(symbols, list):
        iterator = ((item.get("symbol", "UNKNOWN"), item) for item in symbols)
    else:
        iterator = symbols.items()
    for raw_symbol, item in iterator:
        symbol = str(raw_symbol).upper()
        open_price = float(item.get("open") or item.get("o") or 0)
        close_price = float(item.get("close") or item.get("c") or open_price or 0)
        high_price = float(item.get("high") or item.get("h") or close_price or 0)
        low_price = float(item.get("low") or item.get("l") or close_price or 0)
        occurred_at = str(item.get("timestamp") or item.get("t") or now)
        move_pct = percent_change(open_price, close_price)
        range_pct = percent_change(low_price, high_price)
        if abs(move_pct) >= 2.5 or range_pct >= 4:
            direction = "negative"
            urgency = min(10, max(6, int(abs(move_pct) + range_pct)))
            title = "Market volatility watch"
            summary = f"{symbol} moved {move_pct:.1f}% with {range_pct:.1f}% intraday range; keep trading context separate from recovery decisions."
        elif move_pct >= 0.8:
            direction = "positive"
            urgency = 5
            title = "Positive market context"
            summary = f"{symbol} is up {move_pct:.1f}%; useful for watchlist review, not for impulsive action."
        else:
            direction = "neutral"
            urgency = 3
            title = "Calm market context"
            summary = f"{symbol} has no large move in the latest snapshot."
        signals.append(
            ContextSignal(
                signal_id=f"market_{slug(symbol)}_{occurred_at[:10]}",
                domain="market",
                source=provider,
                title=title,
                direction=direction,
                urgency=urgency,
                confidence=70,
                summary=summary,
                occurred_at=occurred_at,
                ingested_at=now,
            )
        )
    return signals


def normalize_signals(payload: dict[str, Any]) -> list[ContextSignal]:
    signals = []
    now = datetime.now(timezone.utc).isoformat()
    for item in payload.get("signals", []):
        domain = str(item.get("domain", "")).lower()
        direction = str(item.get("direction", "neutral")).lower()
        if domain not in SIGNAL_DOMAINS:
            raise ValueError(f"Unknown signal domain: {domain}")
        if direction not in SIGNAL_DIRECTIONS:
            raise ValueError(f"Unknown signal direction: {direction}")
        urgency = bounded_int("urgency", item.get("urgency", 1), 1, 10)
        confidence = bounded_int("confidence", item.get("confidence", 1), 1, 100)
        signal_id = str(item.get("signal_id") or f"{domain}_{item.get('source', 'manual')}_{len(signals) + 1}")
        signals.append(
            ContextSignal(
                signal_id=signal_id,
                domain=domain,
                source=str(item.get("source", "manual")),
                title=str(item.get("title", signal_id)),
                direction=direction,
                urgency=urgency,
                confidence=confidence,
                summary=str(item.get("summary", "")),
                occurred_at=str(item.get("occurred_at") or now),
                ingested_at=now,
            )
        )
    return signals


def bounded_int(label: str, value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{label} must be from {minimum} to {maximum}")
    return parsed


def percent_change(start: float, end: float) -> float:
    if start == 0:
        return 0
    return (end - start) / start * 100


def slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "unknown"


def http_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def env_symbols(default: str = "SPY,QQQ") -> list[str]:
    raw = os.getenv("LIFEHUB_MARKET_SYMBOLS", default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def summarize_signals(signals: list[ContextSignal], limit: int = 3) -> list[str]:
    ranked = sorted(signals, key=lambda item: (item.urgency, item.confidence), reverse=True)
    return [
        f"{item.domain}/{item.source}: {item.title} ({item.direction}, urgency {item.urgency}/10)"
        for item in ranked[:limit]
    ]
