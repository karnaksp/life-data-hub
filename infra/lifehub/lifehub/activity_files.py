"""Local activity-file imports for LifeHub."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ActivityFileSummary:
    source_file: str
    activity_type: str
    started_at: str
    ended_at: str
    duration_minutes: float
    distance_km: float
    elevation_gain_m: float
    point_count: int
    city_hint: str
    imported_at: str


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lon: float
    ele: float
    time: str


def parse_gpx(path: Path, activity_type: str = "walk", city_hint: str = "Saint Petersburg") -> ActivityFileSummary:
    tree = ET.parse(path)
    root = tree.getroot()
    points: list[TrackPoint] = []
    for trkpt in root.findall(".//{*}trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        ele_node = trkpt.find("{*}ele")
        time_node = trkpt.find("{*}time")
        points.append(
            TrackPoint(
                lat=lat,
                lon=lon,
                ele=float(ele_node.text) if ele_node is not None and ele_node.text else 0.0,
                time=time_node.text if time_node is not None and time_node.text else "",
            )
        )
    if not points:
        raise ValueError(f"GPX file has no track points: {path}")

    started_at = points[0].time
    ended_at = points[-1].time
    duration_minutes = duration_between(started_at, ended_at)
    distance_km = sum(distance_km_between(prev, cur) for prev, cur in zip(points, points[1:]))
    elevation_gain_m = sum(max(0.0, cur.ele - prev.ele) for prev, cur in zip(points, points[1:]))
    return ActivityFileSummary(
        source_file=path.name,
        activity_type=activity_type,
        started_at=started_at,
        ended_at=ended_at,
        duration_minutes=round(duration_minutes, 2),
        distance_km=round(distance_km, 3),
        elevation_gain_m=round(elevation_gain_m, 1),
        point_count=len(points),
        city_hint=city_hint,
        imported_at=datetime.now(timezone.utc).isoformat(),
    )


def duration_between(start: str, end: str) -> float:
    if not start or not end:
        return 0.0
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return max(0.0, (end_dt - start_dt).total_seconds() / 60)


def distance_km_between(a: TrackPoint, b: TrackPoint) -> float:
    radius_km = 6371.0088
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def summary_payload(summary: ActivityFileSummary) -> dict:
    return asdict(summary)
