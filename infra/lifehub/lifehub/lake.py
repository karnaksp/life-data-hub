"""LifeHub lakehouse landing exports.

The lake contract uses privacy-safe JSONL envelopes so new life sources can be
added without changing the downstream Bronze ingestion job.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lifehub.activity_files import ActivityFileSummary, summary_payload
from lifehub.context import DailyContextProfile
from lifehub.recommendations import RecommendationEvent
from lifehub.signals import ContextSignal
from lifehub.weather import WeatherHour


LAKE_VERSION = "lifehub.lake.v1"


def load_source_registry(path: Path) -> dict:
    """Load the source registry with a tiny YAML subset parser.

    The registry is mostly validated as text elsewhere. For runtime we only need
    source names and configured landing paths, so a dependency-free parser keeps
    the LifeHub image small.
    """

    sources: dict[str, dict[str, str]] = {}
    current: str | None = None
    in_sources = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "sources:":
            in_sources = True
            continue
        if in_sources and line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            current = line.strip()[:-1]
            sources[current] = {}
            continue
        if in_sources and current and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            sources[current][key] = value.strip().strip('"')
        elif in_sources and not line.startswith(" "):
            break
    return {"sources": sources}


def lake_envelope(
    *,
    source_name: str,
    event_type: str,
    event_time: str,
    payload: dict,
    privacy_class: str = "derived",
) -> dict:
    return {
        "lake_version": LAKE_VERSION,
        "source_name": source_name,
        "event_type": event_type,
        "event_time": event_time,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "privacy_class": privacy_class,
        "payload": payload,
    }


def weather_events(rows: Iterable[WeatherHour]) -> list[dict]:
    return [
        lake_envelope(
            source_name="weather_forecast",
            event_type="weather_hour",
            event_time=row.forecast_time,
            privacy_class="public_weather",
            payload=asdict(row),
        )
        for row in rows
    ]


def recommendation_events(rows: Iterable[RecommendationEvent]) -> list[dict]:
    return [
        lake_envelope(
            source_name="daily_context_profile",
            event_type="recommendation",
            event_time=row.generated_at,
            privacy_class="derived_recommendation",
            payload=asdict(row),
        )
        for row in rows
    ]


def signal_events(rows: Iterable[ContextSignal]) -> list[dict]:
    return [
        lake_envelope(
            source_name="context_signals",
            event_type="context_signal",
            event_time=row.occurred_at,
            privacy_class="context_signal",
            payload=asdict(row),
        )
        for row in rows
    ]


def week_summary_events(summary: dict) -> list[dict]:
    event_time = datetime.now(timezone.utc).isoformat()
    safe_summary = {
        "sessions": int(summary.get("sessions") or 0),
        "avg_intensity": float(summary.get("avg_intensity") or 0),
        "avg_mood": float(summary.get("avg_mood") or 0),
        "avg_fatigue": float(summary.get("avg_fatigue") or 0),
        "pain_sessions": int(summary.get("pain_sessions") or 0),
        "by_activity": summary.get("by_activity") or [],
        "by_result": summary.get("by_result") or [],
    }
    return [
        lake_envelope(
            source_name="activity_diary",
            event_type="activity_week_summary",
            event_time=event_time,
            privacy_class="private_diary_aggregate",
            payload=safe_summary,
        )
    ]


def decision_metrics_events(metrics: dict) -> list[dict]:
    event_time = datetime.now(timezone.utc).isoformat()
    safe_metrics = {
        "useful_decision_days": int(metrics.get("useful_decision_days") or 0),
        "followed_events": int(metrics.get("followed_events") or 0),
        "skipped_events": int(metrics.get("skipped_events") or 0),
        "follow_rate": float(metrics.get("follow_rate") or 0),
    }
    return [
        lake_envelope(
            source_name="decision_feedback",
            event_type="decision_metrics_7d",
            event_time=event_time,
            privacy_class="behavioral_feedback_aggregate",
            payload=safe_metrics,
        )
    ]


def daily_context_events(profile: DailyContextProfile) -> list[dict]:
    return [
        lake_envelope(
            source_name="daily_context_profile",
            event_type="daily_context_profile",
            event_time=profile.generated_at,
            privacy_class="derived_personal_context",
            payload=asdict(profile),
        )
    ]


def activity_file_events(rows: Iterable[ActivityFileSummary]) -> list[dict]:
    return [
        lake_envelope(
            source_name="activity_files",
            event_type="activity_file_summary",
            event_time=row.started_at or row.imported_at,
            privacy_class="private_activity_aggregate",
            payload=summary_payload(row),
        )
        for row in rows
    ]


def write_landing_events(events: Iterable[dict], output_root: Path, dt: str | None = None) -> dict:
    event_list = list(events)
    date_part = dt or datetime.now(timezone.utc).date().isoformat()
    written: dict[str, int] = {}
    for event in event_list:
        source_name = event["source_name"]
        path = output_root / "lifehub" / "landing" / source_name / f"dt={date_part}" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        written[str(path)] = written.get(str(path), 0) + 1
    return written


def write_landing_manifest(written: dict[str, int], output_root: Path) -> Path:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lake_version": LAKE_VERSION,
        "files": [{"path": path, "rows": rows} for path, rows in sorted(written.items())],
    }
    path = output_root / "lifehub" / "_manifests" / "latest_landing_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
