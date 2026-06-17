"""Temporal activities for the LifeHub daily decision pipeline."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from temporalio import activity
except ImportError:  # pragma: no cover - lets fixture tests run without Temporal installed.
    activity = None

from lifehub.cli import build_context_profile, compute_scores
from lifehub.config import env_config, load_locations, load_preferences
from lifehub.places import fetch_overpass_spots, load_spot_fixture
from lifehub.recommendations import (
    build_recommendations,
    render_personal_digest,
    render_progress_scorecard,
    render_weekly_intelligence_report,
)
from lifehub.signals import load_signal_fixture, summarize_signals
from lifehub.storage import (
    fetch_recent_signals_postgres,
    fetch_decision_metrics_postgres,
    fetch_feedback_profile_postgres,
    fetch_week_summary_postgres,
    insert_recommendations_clickhouse,
    insert_recommendations_postgres,
    insert_scores_clickhouse,
    insert_signals_clickhouse,
    insert_weather_clickhouse,
    insert_daily_context_clickhouse,
    upsert_daily_context_postgres,
    upsert_spots_postgres,
    upsert_signals_postgres,
)
from lifehub.weather import fetch_open_meteo, load_fixture, normalize_weather


def temporal_activity(fn):
    if activity is None:
        return fn
    return activity.defn(fn)


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _load_json_fixture(value: str | None) -> dict | None:
    path = _path(value)
    if not path:
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@temporal_activity
def ingest_weather(fixture: str | None = None, write_clickhouse: bool = True) -> dict[str, Any]:
    cfg = env_config()
    locations = load_locations(cfg.locations_path)
    fixture_path = _path(fixture) or cfg.fixture_weather_path
    rows = []
    for location in locations:
        payload = load_fixture(fixture_path) if fixture_path else fetch_open_meteo(location, cfg.timezone)
        rows.extend(normalize_weather(payload, location.id))
    if write_clickhouse:
        insert_weather_clickhouse(cfg.clickhouse_url, rows)
    return {"weather_rows": len(rows), "locations": len(locations), "fixture": str(fixture_path or "")}


@temporal_activity
def sync_places(source: str = "auto", fixture: str | None = None, radius_m: int = 30_000) -> dict[str, Any]:
    cfg = env_config()
    locations = load_locations(cfg.locations_path)
    spots = []
    if fixture:
        spots = load_spot_fixture(Path(fixture))
    elif source in {"auto", "overpass"}:
        center = locations[0]
        try:
            spots = fetch_overpass_spots(center.latitude, center.longitude, radius_m)
        except Exception:
            if source == "overpass":
                raise
    if not spots:
        spots = locations
        source = "configured_fallback"
    upsert_spots_postgres(cfg.postgres_dsn, spots)
    return {"spots": len(spots), "source": source}


@temporal_activity
def import_context_signals(fixture: str, write_postgres: bool = True, write_clickhouse: bool = True) -> dict[str, Any]:
    cfg = env_config()
    signals = load_signal_fixture(Path(fixture))
    if write_postgres:
        upsert_signals_postgres(cfg.postgres_dsn, signals)
    if write_clickhouse:
        insert_signals_clickhouse(cfg.clickhouse_url, signals)
    return {"signals": len(signals), "fixture": fixture}


@temporal_activity
def compute_daily_recommendations(
    fixture: str | None = None,
    write_postgres: bool = True,
    write_clickhouse: bool = True,
) -> dict[str, Any]:
    cfg = env_config()
    scores = compute_scores(cfg, _path(fixture))
    try:
        week_summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception:
        week_summary = {}
    try:
        feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
    except Exception:
        feedback_profile = {}
    preferences = load_preferences(cfg.preferences_path)
    recommendations = build_recommendations(scores, week_summary, feedback_profile, preferences)
    if write_clickhouse:
        insert_scores_clickhouse(cfg.clickhouse_url, scores)
        insert_recommendations_clickhouse(cfg.clickhouse_url, recommendations)
    if write_postgres:
        insert_recommendations_postgres(cfg.postgres_dsn, recommendations)
    signals = fetch_recent_signals_postgres(cfg.postgres_dsn)
    digest = render_personal_digest(recommendations)
    signal_lines = summarize_signals(signals)
    if signal_lines:
        digest = f"{digest}\n\nContext signals:\n" + "\n".join(f"- {line}" for line in signal_lines)
    top = recommendations[0] if recommendations else None
    return {
        "recommendations": len(recommendations),
        "top": asdict(top) if top else None,
        "digest_preview": digest[:1000],
        "signal_lines": signal_lines,
    }


@temporal_activity
def build_daily_context(
    weather_fixture: str | None = None,
    summary_fixture: str | None = None,
    feedback_fixture: str | None = None,
    metrics_fixture: str | None = None,
    signal_fixture: str | None = None,
    write_postgres: bool = True,
    write_clickhouse: bool = True,
) -> dict[str, Any]:
    cfg = env_config()
    profile = build_context_profile(
        cfg,
        _path(weather_fixture),
        summary_fixture=_path(summary_fixture),
        feedback_fixture=_path(feedback_fixture),
        metrics_fixture=_path(metrics_fixture),
        signal_fixture=_path(signal_fixture),
    )
    if write_postgres:
        upsert_daily_context_postgres(cfg.postgres_dsn, profile)
    if write_clickhouse:
        insert_daily_context_clickhouse(cfg.clickhouse_url, profile)
    return {
        "profile_date": profile.profile_date,
        "top_activity": profile.top_activity,
        "top_score": profile.top_score,
        "readiness_state": profile.readiness_state,
        "open_goal_count": profile.open_goal_count,
        "signal_count_7d": profile.signal_count_7d,
    }


@temporal_activity
def build_weekly_review(
    weather_fixture: str | None = None,
    summary_fixture: str | None = None,
    feedback_fixture: str | None = None,
    signal_fixture: str | None = None,
) -> dict[str, Any]:
    cfg = env_config()
    summary = _load_json_fixture(summary_fixture)
    if summary is None:
        summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    feedback_profile = _load_json_fixture(feedback_fixture)
    if feedback_profile is None:
        try:
            feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
        except Exception:
            feedback_profile = {}
    if signal_fixture:
        signals = load_signal_fixture(Path(signal_fixture))
    else:
        signals = fetch_recent_signals_postgres(cfg.postgres_dsn)
    scores = compute_scores(cfg, _path(weather_fixture))
    preferences = load_preferences(cfg.preferences_path)
    recommendations = build_recommendations(scores, summary, feedback_profile, preferences)
    report = render_weekly_intelligence_report(summary, recommendations, feedback_profile, preferences, signals)
    top = recommendations[0] if recommendations else None
    return {
        "sessions": int(summary.get("sessions") or 0),
        "recommendations": len(recommendations),
        "top": asdict(top) if top else None,
        "report_preview": report[:1000],
    }


@temporal_activity
def build_progress_metrics(
    summary_fixture: str | None = None,
    feedback_fixture: str | None = None,
    metrics_fixture: str | None = None,
) -> dict[str, Any]:
    cfg = env_config()
    summary = _load_json_fixture(summary_fixture)
    if summary is None:
        summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    feedback_profile = _load_json_fixture(feedback_fixture)
    if feedback_profile is None:
        try:
            feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
        except Exception:
            feedback_profile = {}
    decision_metrics = _load_json_fixture(metrics_fixture)
    if decision_metrics is None:
        try:
            decision_metrics = fetch_decision_metrics_postgres(cfg.postgres_dsn)
        except Exception:
            decision_metrics = {}
    preferences = load_preferences(cfg.preferences_path)
    scorecard = render_progress_scorecard(summary, decision_metrics, feedback_profile, preferences)
    return {
        "useful_decision_days": int(decision_metrics.get("useful_decision_days") or 0),
        "follow_rate": float(decision_metrics.get("follow_rate") or 0),
        "sessions": int(summary.get("sessions") or 0),
        "scorecard_preview": scorecard[:1000],
    }
