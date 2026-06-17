"""Public place discovery for LifeHub."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@dataclass(frozen=True)
class Spot:
    id: str
    label: str
    latitude: float
    longitude: float
    tags: tuple[str, ...]
    source: str


def load_spot_fixture(path: Path) -> list[Spot]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_overpass(payload)


def fetch_overpass_spots(latitude: float, longitude: float, radius_m: int) -> list[Spot]:
    query = overpass_query(latitude, longitude, radius_m)
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "data-forge-lifehub/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return normalize_overpass(payload)


def overpass_query(latitude: float, longitude: float, radius_m: int) -> str:
    selectors = [
        'node["leisure"="sports_centre"]',
        'way["leisure"="sports_centre"]',
        'node["leisure"="pitch"]',
        'way["leisure"="pitch"]',
        'node["sport"="skateboard"]',
        'way["sport"="skateboard"]',
        'node["sport"="volleyball"]',
        'way["sport"="volleyball"]',
        'node["leisure"="park"]',
        'way["leisure"="park"]',
    ]
    body = "\n".join(f"  {selector}(around:{radius_m},{latitude},{longitude});" for selector in selectors)
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout center tags 50;"


def normalize_overpass(payload: dict[str, Any]) -> list[Spot]:
    spots: list[Spot] = []
    seen: set[str] = set()
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        if lat is None or lon is None:
            continue
        source_id = f"osm_{element.get('type', 'node')}_{element.get('id')}"
        if source_id in seen:
            continue
        seen.add(source_id)
        label = tags.get("name") or tags.get("leisure") or tags.get("sport") or source_id
        spots.append(
            Spot(
                id=source_id,
                label=str(label),
                latitude=float(lat),
                longitude=float(lon),
                tags=spot_tags(tags),
                source="overpass",
            )
        )
    return spots


def spot_tags(tags: dict[str, Any]) -> tuple[str, ...]:
    result = ["public"]
    for key in ["sport", "leisure"]:
        value = tags.get(key)
        if value:
            result.append(str(value))
    if tags.get("sport") == "skateboard":
        result.append("skate")
    if tags.get("sport") == "volleyball":
        result.append("volleyball")
    return tuple(dict.fromkeys(result))
