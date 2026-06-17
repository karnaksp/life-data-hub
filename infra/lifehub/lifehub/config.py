"""Configuration loading for LifeHub."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def discover_repo_root() -> Path:
    configured = os.getenv("LIFEHUB_REPO_ROOT")
    if configured:
        return Path(configured)

    workspace = Path("/workspace")
    if workspace.exists():
        return workspace

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "lifehub").exists():
            return parent
    return current.parents[1]


ROOT = discover_repo_root()
DEFAULT_LOCATIONS = ROOT / "config" / "lifehub" / "locations.yaml"
DEFAULT_SCORING = ROOT / "config" / "lifehub" / "scoring.yaml"
DEFAULT_PREFERENCES = ROOT / "config" / "lifehub" / "preferences.yaml"


@dataclass(frozen=True)
class Location:
    id: str
    label: str
    latitude: float
    longitude: float
    tags: tuple[str, ...]


@dataclass(frozen=True)
class LifeHubConfig:
    timezone: str
    digest_time: str
    locations_path: Path
    scoring_path: Path
    preferences_path: Path
    postgres_dsn: str
    clickhouse_url: str
    telegram_token: str
    telegram_chat_id: str
    fixture_weather_path: Path | None


def env_config() -> LifeHubConfig:
    fixture = os.getenv("LIFEHUB_WEATHER_FIXTURE")
    return LifeHubConfig(
        timezone=os.getenv("LIFEHUB_TIMEZONE", "Europe/Moscow"),
        digest_time=os.getenv("LIFEHUB_DIGEST_TIME", "08:00"),
        locations_path=Path(os.getenv("LIFEHUB_LOCATIONS", DEFAULT_LOCATIONS)),
        scoring_path=Path(os.getenv("LIFEHUB_SCORING", DEFAULT_SCORING)),
        preferences_path=Path(os.getenv("LIFEHUB_PREFERENCES", DEFAULT_PREFERENCES)),
        postgres_dsn=os.getenv(
            "LIFEHUB_POSTGRES_DSN",
            "host=postgres port=5432 dbname=demo user=admin password=admin",
        ),
        clickhouse_url=os.getenv(
            "LIFEHUB_CLICKHOUSE_URL",
            "http://clickhouse:8123/?user=admin&password=admin",
        ),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        fixture_weather_path=Path(fixture) if fixture else None,
    )


def load_locations(path: Path = DEFAULT_LOCATIONS) -> list[Location]:
    data = parse_simple_yaml(path)
    locations = data.get("locations", [])
    result: list[Location] = []
    for item in locations:
        result.append(
            Location(
                id=str(item["id"]),
                label=str(item["label"]),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                tags=tuple(str(tag) for tag in item.get("tags", [])),
            )
        )
    return result


def load_scoring(path: Path = DEFAULT_SCORING) -> dict[str, Any]:
    return parse_simple_yaml(path)


def load_preferences(path: Path = DEFAULT_PREFERENCES) -> dict[str, Any]:
    if not path.exists():
        return {}
    return parse_simple_yaml(path)


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the small YAML subset used by LifeHub config files.

    Supported shape: top-level maps, lists of maps, scalar strings/numbers,
    inline arrays such as [a, b], and one-level nested maps.
    """

    lines = [
        raw.split("#", 1)[0].rstrip()
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.split("#", 1)[0].strip()
    ]
    root: dict[str, Any] = {}
    current_key: str | None = None
    current_item: dict[str, Any] | None = None
    current_map: dict[str, Any] | None = None
    current_map_indent = 0

    for raw in lines:
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.endswith(":"):
            current_key = line[:-1]
            root[current_key] = []
            current_item = None
            current_map = None
            continue
        if indent == 0 and ":" in line:
            key, value = split_pair(line)
            root[key] = parse_scalar(value)
            current_key = None
            current_item = None
            current_map = None
            continue
        if current_key is None:
            continue
        if line.startswith("- "):
            payload = line[2:]
            current_item = {}
            root[current_key].append(current_item)
            current_map = None
            if payload:
                key, value = split_pair(payload)
                current_item[key] = parse_scalar(value)
            continue
        if current_item is not None and ":" in line:
            key, value = split_pair(line)
            if value == "":
                nested: dict[str, Any] = {}
                current_item[key] = nested
                current_map = nested
                current_map_indent = indent
            elif current_map is not None and indent > current_map_indent:
                current_map[key] = parse_scalar(value)
            else:
                current_item[key] = parse_scalar(value)
                current_map = None
            continue
        if isinstance(root.get(current_key), list) and ":" in line:
            # Convert top-level list placeholder to a map on first map-like child.
            if root[current_key] == []:
                root[current_key] = {}
            key, value = split_pair(line)
            root[current_key][key] = parse_scalar(value)
            continue
        if isinstance(root.get(current_key), dict) and ":" in line:
            key, value = split_pair(line)
            root[current_key][key] = parse_scalar(value)

    return root


def split_pair(text: str) -> tuple[str, str]:
    key, value = text.split(":", 1)
    return key.strip(), value.strip().strip('"')


def parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [part.strip().strip('"') for part in inner.split(",") if part.strip()]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"')
