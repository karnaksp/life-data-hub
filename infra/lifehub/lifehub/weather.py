"""Weather ingestion and normalization."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lifehub.config import Location


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "snow_depth",
    "wind_speed_10m",
    "wind_gusts_10m",
    "visibility",
    "is_day",
]


@dataclass(frozen=True)
class WeatherHour:
    location_id: str
    forecast_time: str
    temperature_c: float
    precipitation_mm: float
    rain_mm: float
    snowfall_cm: float
    snow_depth_cm: float
    wind_speed_kmh: float
    wind_gust_kmh: float
    visibility_m: float
    is_day: bool
    fetched_at: str


def fetch_open_meteo(location: Location, timezone_name: str) -> dict[str, Any]:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": ",".join(HOURLY_FIELDS),
        "forecast_days": 2,
        "timezone": timezone_name,
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_weather(payload: dict[str, Any], location_id: str) -> list[WeatherHour]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: list[WeatherHour] = []
    for index, forecast_time in enumerate(times):
        rows.append(
            WeatherHour(
                location_id=location_id,
                forecast_time=str(forecast_time),
                temperature_c=float_at(hourly, "temperature_2m", index),
                precipitation_mm=float_at(hourly, "precipitation", index),
                rain_mm=float_at(hourly, "rain", index),
                snowfall_cm=float_at(hourly, "snowfall", index),
                snow_depth_cm=float_at(hourly, "snow_depth", index),
                wind_speed_kmh=float_at(hourly, "wind_speed_10m", index),
                wind_gust_kmh=float_at(hourly, "wind_gusts_10m", index),
                visibility_m=float_at(hourly, "visibility", index, default=10000.0),
                is_day=bool(int(float_at(hourly, "is_day", index, default=1.0))),
                fetched_at=fetched_at,
            )
        )
    return rows


def float_at(hourly: dict[str, Any], key: str, index: int, default: float = 0.0) -> float:
    values = hourly.get(key) or []
    if index >= len(values) or values[index] is None:
        return default
    return float(values[index])
