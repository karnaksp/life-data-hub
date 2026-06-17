"""Managed external source subscriptions for LifeHub.

This layer is for user-managed URLs: Telegram channels, RSS feeds, news pages,
public API/event streams, and other links that should not require editing the
static source registry for every new subscription.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lifehub.lake import lake_envelope


SUPPORTED_SOURCE_TYPES = {
    "telegram_channel",
    "rss_feed",
    "news_url",
    "event_stream",
    "web_page",
    "api_json",
}

URL_COMMANDS = {"/source_add", "/source_list", "/source_pause", "/source_resume", "/source_remove", "/source_sync"}


@dataclass(frozen=True)
class SourceSubscription:
    subscription_id: str
    source_type: str
    reference: str
    label: str
    domain: str
    tags: tuple[str, ...]
    enabled: bool
    privacy_class: str
    cadence: str
    created_at: str
    updated_at: str


def infer_source_type(reference: str) -> str:
    parsed = urllib.parse.urlparse(reference)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    lower = reference.lower()
    if host in {"t.me", "telegram.me"} or host.endswith(".t.me"):
        return "telegram_channel"
    if lower.startswith(("ws://", "wss://")) or "stream" in path or "events" in path:
        return "event_stream"
    if path.endswith((".rss", ".xml", ".atom")) or "rss" in lower or "feed" in lower:
        return "rss_feed"
    if path.endswith(".json") or "api" in path:
        return "api_json"
    if parsed.scheme in {"http", "https"}:
        return "news_url"
    raise ValueError("Source reference must be an http(s), ws(s), Telegram, RSS, API, or event stream URL.")


def load_subscriptions(path: Path) -> list[SourceSubscription]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("subscriptions", payload if isinstance(payload, list) else [])
    result = []
    for row in rows:
        result.append(
            SourceSubscription(
                subscription_id=str(row["subscription_id"]),
                source_type=str(row["source_type"]),
                reference=str(row["reference"]),
                label=str(row["label"]),
                domain=str(row.get("domain") or "context"),
                tags=tuple(str(tag) for tag in row.get("tags", [])),
                enabled=bool(row.get("enabled", True)),
                privacy_class=str(row.get("privacy_class") or "public_context"),
                cadence=str(row.get("cadence") or "manual"),
                created_at=str(row.get("created_at") or now_utc()),
                updated_at=str(row.get("updated_at") or now_utc()),
            )
        )
    return result


def save_subscriptions(path: Path, subscriptions: list[SourceSubscription]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": now_utc(),
        "subscriptions": [asdict(item) | {"tags": list(item.tags)} for item in subscriptions],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_subscription(
    path: Path,
    reference: str,
    *,
    source_type: str = "auto",
    label: str = "",
    domain: str = "",
    tags: list[str] | None = None,
    cadence: str = "manual",
    privacy_class: str = "public_context",
) -> tuple[SourceSubscription, bool]:
    selected_type = infer_source_type(reference) if source_type == "auto" else source_type
    if selected_type not in SUPPORTED_SOURCE_TYPES:
        known = ", ".join(sorted(SUPPORTED_SOURCE_TYPES))
        raise ValueError(f"Unsupported source type {selected_type!r}. Known: {known}")
    normalized_reference = normalize_reference(reference)
    now = now_utc()
    existing = load_subscriptions(path)
    subscription_id = stable_subscription_id(selected_type, normalized_reference)
    subscription = SourceSubscription(
        subscription_id=subscription_id,
        source_type=selected_type,
        reference=normalized_reference,
        label=clean_label(label) or default_label(normalized_reference),
        domain=clean_label(domain) or default_domain(selected_type),
        tags=tuple(clean_label(tag) for tag in (tags or []) if clean_label(tag)),
        enabled=True,
        privacy_class=privacy_class,
        cadence=clean_label(cadence) or "manual",
        created_at=now,
        updated_at=now,
    )
    replaced = False
    updated = []
    for item in existing:
        if item.subscription_id == subscription_id:
            updated.append(subscription)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(subscription)
    save_subscriptions(path, updated)
    return subscription, not replaced


def set_subscription_enabled(path: Path, selector: str, enabled: bool) -> SourceSubscription:
    subscriptions = load_subscriptions(path)
    selected = find_subscription(subscriptions, selector)
    now = now_utc()
    updated = [
        SourceSubscription(**(asdict(item) | {"enabled": enabled, "updated_at": now}))
        if item.subscription_id == selected.subscription_id
        else item
        for item in subscriptions
    ]
    save_subscriptions(path, updated)
    return find_subscription(updated, selected.subscription_id)


def remove_subscription(path: Path, selector: str) -> SourceSubscription:
    subscriptions = load_subscriptions(path)
    selected = find_subscription(subscriptions, selector)
    save_subscriptions(path, [item for item in subscriptions if item.subscription_id != selected.subscription_id])
    return selected


def find_subscription(subscriptions: list[SourceSubscription], selector: str) -> SourceSubscription:
    matches = [item for item in subscriptions if item.subscription_id.startswith(selector)]
    if not matches:
        raise ValueError(f"Source subscription {selector!r} was not found.")
    if len(matches) > 1:
        ids = ", ".join(item.subscription_id for item in matches[:5])
        raise ValueError(f"Source subscription selector {selector!r} is ambiguous: {ids}")
    return matches[0]


def render_subscriptions(path: Path) -> str:
    subscriptions = load_subscriptions(path)
    if not subscriptions:
        return "\n".join(
            [
                "LifeHub source subscriptions",
                "No managed sources yet.",
                "Add one: /source_add https://example.com/feed.xml label=Example tags=news,market",
            ]
        )
    lines = ["LifeHub source subscriptions"]
    for item in subscriptions:
        state = "on" if item.enabled else "paused"
        tags = f" tags={','.join(item.tags)}" if item.tags else ""
        lines.append(f"- {item.subscription_id[:8]} [{state}] {item.source_type} {item.label} domain={item.domain}{tags}")
    return "\n".join(lines)


def parse_source_add_command(text: str) -> dict[str, Any]:
    parts = text.strip().split()
    if not parts or parts[0] != "/source_add":
        raise ValueError("Use: /source_add [type] <url> label=Name domain=context tags=a,b")
    if len(parts) < 2:
        raise ValueError("Use: /source_add [type] <url> label=Name domain=context tags=a,b")
    source_type = "auto"
    reference_index = 1
    if parts[1] in SUPPORTED_SOURCE_TYPES or parts[1] == "auto":
        source_type = parts[1]
        reference_index = 2
    if len(parts) <= reference_index:
        raise ValueError("Source URL is missing.")
    reference = parts[reference_index]
    pairs, tags = parse_pairs(parts[reference_index + 1 :])
    if "tags" in pairs:
        tags.extend(tag.strip() for tag in pairs["tags"].split(","))
    return {
        "source_type": source_type,
        "reference": reference,
        "label": pairs.get("label", ""),
        "domain": pairs.get("domain", ""),
        "tags": [tag for tag in tags if tag],
        "cadence": pairs.get("cadence", "manual"),
        "privacy_class": pairs.get("privacy", "public_context"),
    }


def source_command_selector(text: str, command: str) -> str:
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0] != command:
        raise ValueError(f"Use: {command} <subscription_id_prefix>")
    return parts[1].strip()


def subscription_events(
    subscriptions: list[SourceSubscription],
    *,
    fixture: Path | None = None,
    fetch: bool = False,
    limit: int = 20,
) -> list[dict]:
    events: list[dict] = []
    for subscription in subscriptions:
        if not subscription.enabled:
            continue
        content = fixture.read_text(encoding="utf-8") if fixture else ""
        if not content and fetch:
            content = fetch_reference(subscription.reference)
        events.extend(events_for_subscription(subscription, content, limit=limit))
    return events


def events_for_subscription(subscription: SourceSubscription, content: str, *, limit: int = 20) -> list[dict]:
    if subscription.source_type == "rss_feed" and content.strip():
        return [item_event(subscription, item) for item in parse_rss_items(content)[:limit]]
    if subscription.source_type in {"api_json", "event_stream"} and content.strip():
        return [item_event(subscription, item) for item in parse_json_items(content)[:limit]]
    return [
        item_event(
            subscription,
            {
                "event_type": "source_seen",
                "event_time": now_utc(),
                "title": subscription.label,
                "url": subscription.reference,
                "summary": "subscription registered or checked",
            },
        )
    ]


def item_event(subscription: SourceSubscription, item: dict[str, Any]) -> dict:
    event_time = str(item.get("event_time") or item.get("published_at") or item.get("updated_at") or now_utc())
    title = clean_preview(str(item.get("title") or item.get("name") or subscription.label))
    item_url = str(item.get("url") or item.get("link") or subscription.reference)
    summary = clean_preview(str(item.get("summary") or item.get("description") or ""))
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    payload = {
        "subscription_id": subscription.subscription_id,
        "source_type": subscription.source_type,
        "domain": subscription.domain,
        "label": subscription.label,
        "reference_host": reference_host(subscription.reference),
        "reference_hash": stable_hash(subscription.reference),
        "item_url_hash": stable_hash(item_url),
        "title_hash": stable_hash(title),
        "summary_hash": stable_hash(summary) if summary else "",
        "published_at": event_time,
    }
    return lake_envelope(
        source_name="external_source_items",
        event_type=str(item.get("event_type") or f"{subscription.source_type}_item"),
        event_time=event_time,
        privacy_class=subscription.privacy_class,
        source_tier="tier_1_foundation",
        source_type="managed_url_subscription",
        raw_policy="local_raw_only",
        local_policy="summarized_landing_only",
        payload_summary={
            "subscription_id": subscription.subscription_id,
            "source_type": subscription.source_type,
            "label": subscription.label,
            "title_preview": title,
        },
        metrics=metrics,
        tags=["managed_source", subscription.source_type, subscription.domain, *subscription.tags],
        quality_flags=["fixture_or_manual_check" if not item.get("url") else "parsed_item"],
        provenance={"connector": "lifehub-source-subscriptions", "reference_host": reference_host(subscription.reference)},
        idempotency_key=f"{subscription.subscription_id}:{event_time}:{stable_hash(item_url + title)}",
        payload={key: value for key, value in payload.items() if value != ""},
    )


def parse_rss_items(content: str) -> list[dict[str, Any]]:
    root = ET.fromstring(content.encode("utf-8"))
    rows = []
    for item in root.findall(".//item"):
        rows.append(
            {
                "title": text_of(item, "title"),
                "url": text_of(item, "link"),
                "published_at": text_of(item, "pubDate") or text_of(item, "date"),
                "summary": text_of(item, "description"),
            }
        )
    if rows:
        return rows
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for item in root.findall(".//atom:entry", ns):
        link = item.find("atom:link", ns)
        rows.append(
            {
                "title": text_of(item, "atom:title", ns),
                "url": link.attrib.get("href", "") if link is not None else "",
                "published_at": text_of(item, "atom:published", ns) or text_of(item, "atom:updated", ns),
                "summary": text_of(item, "atom:summary", ns),
            }
        )
    return rows


def parse_json_items(content: str) -> list[dict[str, Any]]:
    stripped = content.strip()
    if not stripped:
        return []
    if "\n" in stripped and not stripped.startswith(("[", "{")):
        return [json.loads(line) for line in stripped.splitlines() if line.strip()]
    payload = json.loads(stripped)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    for key in ("events", "items", "rows", "entries"):
        if isinstance(payload, dict) and isinstance(payload.get(key), list):
            return [item for item in payload[key] if isinstance(item, dict)]
    return [payload] if isinstance(payload, dict) else []


def fetch_reference(reference: str) -> str:
    request = urllib.request.Request(reference, headers={"User-Agent": "lifehub-source-subscriptions/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read(2_000_000).decode("utf-8", errors="replace")


def parse_pairs(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    pairs: dict[str, str] = {}
    tags: list[str] = []
    for token in tokens:
        if "=" in token:
            key, value = token.split("=", 1)
            pairs[key.strip().lower()] = value.strip().replace("_", " ")
        else:
            tags.append(token.replace("_", " "))
    return pairs, tags


def normalize_reference(reference: str) -> str:
    parsed = urllib.parse.urlparse(reference.strip())
    if not parsed.scheme:
        raise ValueError("Source reference must include a URL scheme such as https://")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def default_domain(source_type: str) -> str:
    return {
        "telegram_channel": "telegram",
        "rss_feed": "news",
        "news_url": "news",
        "event_stream": "events",
        "web_page": "web",
        "api_json": "api",
    }.get(source_type, "context")


def default_label(reference: str) -> str:
    parsed = urllib.parse.urlparse(reference)
    path = parsed.path.strip("/").split("/")
    tail = path[-1] if path and path[-1] else parsed.netloc
    return clean_label(tail.replace("-", " ").replace("_", " ")) or parsed.netloc


def reference_host(reference: str) -> str:
    return urllib.parse.urlparse(reference).netloc.lower()


def stable_subscription_id(source_type: str, reference: str) -> str:
    return f"{source_type[:3]}_{stable_hash(source_type + ':' + reference)[:12]}"


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def clean_label(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ ._:/-]+", "", str(value)).strip()
    return re.sub(r"\s+", " ", cleaned)[:80]


def clean_preview(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:160]


def text_of(item: ET.Element, name: str, ns: dict[str, str] | None = None) -> str:
    found = item.find(name, ns or {})
    return (found.text or "").strip() if found is not None else ""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
