#!/usr/bin/env python3
"""Validate the LifeHub MVP contract without external services."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "config/lifehub/locations.yaml",
    "config/lifehub/preferences.yaml",
    "config/lifehub/scoring.yaml",
    "config/lifehub/source_registry.yaml",
    "fixtures/lifehub/open_meteo_clear_day.json",
    "fixtures/lifehub/open_meteo_rain_day.json",
    "fixtures/lifehub/open_meteo_snow_day.json",
    "fixtures/lifehub/context_signals.json",
    "fixtures/lifehub/activity_route_spb_public.gpx",
    "fixtures/lifehub/sleep_quality.json",
    "fixtures/lifehub/custom_life_events.json",
    "fixtures/lifehub/decision_metrics.json",
    "fixtures/lifehub/feedback_profile.json",
    "fixtures/lifehub/github_repo_activity.json",
    "fixtures/lifehub/market_snapshot.json",
    "fixtures/lifehub/overpass_spots.json",
    "fixtures/lifehub/week_summary.json",
    "infra/lifehub/Dockerfile",
    "infra/lifehub/lifehub/cli.py",
    "infra/lifehub/lifehub/activity_files.py",
    "infra/lifehub/lifehub/sleep.py",
    "infra/lifehub/lifehub/generic_sources.py",
    "infra/lifehub/lifehub/source_onboarding.py",
    "infra/lifehub/lifehub/context.py",
    "infra/lifehub/lifehub/feedback.py",
    "infra/lifehub/lifehub/places.py",
    "infra/lifehub/lifehub/signals.py",
    "infra/lifehub/lifehub/temporal/activities.py",
    "infra/lifehub/lifehub/temporal/starter.py",
    "infra/lifehub/lifehub/temporal/worker.py",
    "infra/lifehub/lifehub/temporal/workflows.py",
    "infra/clickhouse/init/003_lifehub_tables.sql",
    "infra/clickhouse/init/004_lifehub_marts.sql",
    "infra/airflow/dags/lifehub_daily_pipeline_dag.py",
    "infra/airflow/dags/lifehub_lakehouse_pipeline_dag.py",
    "infra/airflow/processing/spark/jobs/lifehub_jsonl_to_iceberg.py",
    "contracts/lifehub/data_contract.yaml",
    "catalog/lifehub/datasets.yaml",
    "expectations/lifehub/expectations.yaml",
    "dbt/lifehub/dbt_project.yml",
    "dbt/lifehub/models/marts/mart_lifehub_activity_feedback_profile.sql",
    "dbt/lifehub/models/marts/mart_lifehub_daily_context_latest.sql",
    "dbt/lifehub/models/staging/stg_lifehub_daily_context_profiles.sql",
    "sql/lifehub/clickhouse_lifehub_marts.sql",
    "sql/lifehub/lifehub_quality_checks.sql",
    "sql/lifehub/trino_lifehub_observability.sql",
    "sql/lifehub/trino_lifehub_lakehouse.sql",
    "scripts/capture_lifehub_evidence.py",
    "scripts/capture_lifehub_lake_evidence.py",
    "scripts/build_lifehub_cockpit.py",
    "scripts/lifehub_quality_check.py",
    "scripts/run_lifehub_evidence_flow.py",
    "scripts/run_lifehub_lakehouse_runtime_smoke.py",
    "scripts/emit_lifehub_lineage.py",
    "scripts/validate_lifehub_dataops.py",
    "docs/data-engineering-stack.md",
    "docs/evidence/lifehub-lakehouse-evidence.md",
    "docs/evidence/lifehub-temporal-evidence.md",
    "docs/lifehub.md",
    "docs/lifehub-cockpit.html",
]

REQUIRED_ENV = [
    "LIFEHUB_TIMEZONE",
    "LIFEHUB_DIGEST_TIME",
    "LIFEHUB_POSTGRES_DSN",
    "LIFEHUB_CLICKHOUSE_URL",
    "LIFEHUB_PLACES_SOURCE",
    "LIFEHUB_PREFERENCES",
    "LIFEHUB_TEMPORAL_ADDRESS",
    "LIFEHUB_TEMPORAL_NAMESPACE",
    "LIFEHUB_TEMPORAL_TASK_QUEUE",
    "LIFEHUB_GITHUB_REPO",
    "GITHUB_TOKEN",
    "LIFEHUB_MARKET_SYMBOLS",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
    "ALPACA_MARKET_DATA_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

REQUIRED_COMPOSE_SERVICES = [
    "lifehub-weather-ingest",
    "lifehub-place-sync",
    "lifehub-score",
    "lifehub-github-signal-import",
    "lifehub-market-signal-import",
    "lifehub-telegram-bot",
    "temporal",
    "lifehub-temporal-worker",
]

REQUIRED_POSTGRES_TABLES = [
    "life_activity_log",
    "life_decision_feedback",
    "life_digest_runs",
    "life_recommendation_events",
    "life_signal_events",
    "life_daily_context_profiles",
    "life_user_preferences",
    "life_spots",
]

REQUIRED_CLICKHOUSE_TABLES = [
    "analytics.life_weather_hourly",
    "analytics.life_readiness_scores",
    "analytics.life_activity_events",
    "analytics.life_decision_feedback_events",
    "analytics.life_recommendation_events",
    "analytics.life_signal_events",
    "analytics.life_daily_context_profiles",
]


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_required_files())
    failures.extend(validate_env())
    failures.extend(validate_compose())
    failures.extend(validate_postgres_tables())
    failures.extend(validate_clickhouse_tables())
    failures.extend(validate_data_contract())
    failures.extend(validate_weather_fixtures())
    failures.extend(validate_place_fixture())
    failures.extend(validate_preferences())
    failures.extend(validate_signal_fixture())
    failures.extend(validate_github_fixture())
    failures.extend(validate_market_fixture())
    failures.extend(validate_weekly_review_fixtures())
    failures.extend(validate_decision_metrics_fixture())
    failures.extend(validate_docs())
    failures.extend(validate_cockpit())
    if failures:
        print("LifeHub contract validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("LifeHub contract validation passed.")
    return 0


def validate_required_files() -> list[str]:
    failures = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.exists():
            failures.append(f"Missing required LifeHub file: {relative}")
        elif path.is_file() and not path.read_text(encoding="utf-8").strip():
            failures.append(f"Required LifeHub file is empty: {relative}")
    return failures


def validate_env() -> list[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return [f".env.example missing {key}" for key in REQUIRED_ENV if f"{key}=" not in text]


def validate_compose() -> list[str]:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    failures = []
    for service in REQUIRED_COMPOSE_SERVICES:
        if not re.search(rf"^\s{{2}}{re.escape(service)}:", text, re.MULTILINE):
            failures.append(f"docker-compose.yml missing service {service}")
    if "profiles: [core,airflow,lifehub,temporal]" not in text:
        failures.append("postgres service must include lifehub and temporal profiles")
    if "profiles: [core,lifehub,temporal]" not in text:
        failures.append("clickhouse service must include lifehub and temporal profiles")
    return failures


def validate_postgres_tables() -> list[str]:
    text = (ROOT / "infra/postgres/init-databases.sh").read_text(encoding="utf-8")
    return [
        f"Postgres init missing {table}"
        for table in REQUIRED_POSTGRES_TABLES
        if f"CREATE TABLE IF NOT EXISTS {table}" not in text
    ]


def validate_clickhouse_tables() -> list[str]:
    text = (ROOT / "infra/clickhouse/init/003_lifehub_tables.sql").read_text(encoding="utf-8")
    return [
        f"ClickHouse LifeHub init missing {table}"
        for table in REQUIRED_CLICKHOUSE_TABLES
        if f"CREATE TABLE IF NOT EXISTS {table}" not in text
    ]


def validate_data_contract() -> list[str]:
    text = (ROOT / "contracts/lifehub/data_contract.yaml").read_text(encoding="utf-8")
    required = [
        "privacy: local_only",
        "postgres.life_spots",
        "postgres.life_activity_log",
        "clickhouse.analytics.life_weather_hourly",
        "clickhouse.analytics.life_readiness_scores",
        "life_recommendation_events",
        "life_decision_feedback",
        "life_activity_feedback_profile_v",
        "recommendation personalization",
        "life_signal_events",
        "life_daily_context_profiles",
        "daily context profile",
        "lifehub lakehouse",
        "iceberg.bronze.lifehub_events",
        "github_repo_activity",
        "alpaca_market_snapshot",
        "compact_context_events_only",
        "lifehub_preferences",
        "privacy_safe_weekly_targets",
        "weekly_review",
        "telegram_token",
        "raw_diary_notes",
    ]
    return [f"LifeHub data contract missing phrase: {phrase}" for phrase in required if phrase not in text]


def validate_weather_fixtures() -> list[str]:
    failures = []
    for path in sorted((ROOT / "fixtures/lifehub").glob("open_meteo_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            failures.append(f"{path.relative_to(ROOT)} has no hourly.time values")
        for key in ["temperature_2m", "precipitation", "rain", "snowfall", "wind_gusts_10m", "is_day"]:
            if len(hourly.get(key, [])) != len(times):
                failures.append(f"{path.relative_to(ROOT)} field {key} length must match hourly.time")
    return failures


def validate_place_fixture() -> list[str]:
    payload = json.loads((ROOT / "fixtures/lifehub/overpass_spots.json").read_text(encoding="utf-8"))
    elements = payload.get("elements", [])
    failures = []
    if not elements:
        failures.append("fixtures/lifehub/overpass_spots.json has no elements")
    for element in elements:
        if "lat" not in element or "lon" not in element:
            failures.append("Overpass fixture element missing lat/lon")
        if not element.get("tags"):
            failures.append("Overpass fixture element missing tags")
    return failures


def validate_preferences() -> list[str]:
    text = (ROOT / "config/lifehub/preferences.yaml").read_text(encoding="utf-8")
    required = ["weekly_goals:", "skate:", "moto_lesson:", "priority_activities:", "recommendation_policy:"]
    return [f"LifeHub preferences missing phrase: {phrase}" for phrase in required if phrase not in text]


def validate_signal_fixture() -> list[str]:
    payload = json.loads((ROOT / "fixtures/lifehub/context_signals.json").read_text(encoding="utf-8"))
    signals = payload.get("signals", [])
    failures = []
    if not signals:
        failures.append("fixtures/lifehub/context_signals.json has no signals")
    for signal in signals:
        if signal.get("domain") not in {"market", "github", "career", "wellbeing", "system"}:
            failures.append("Context signal has unknown domain")
        if signal.get("direction") not in {"positive", "negative", "neutral"}:
            failures.append("Context signal has unknown direction")
        if not 1 <= int(signal.get("urgency", 0)) <= 10:
            failures.append("Context signal urgency must be 1..10")
    return failures


def validate_github_fixture() -> list[str]:
    payload = json.loads((ROOT / "fixtures/lifehub/github_repo_activity.json").read_text(encoding="utf-8"))
    repos = payload.get("repositories", [])
    failures = []
    if not repos:
        failures.append("fixtures/lifehub/github_repo_activity.json has no repositories")
    for repo in repos:
        if "/" not in str(repo.get("full_name", "")):
            failures.append("GitHub fixture repository full_name must use owner/repo")
        for key in ["pushed_at", "open_issues_count", "archived"]:
            if key not in repo:
                failures.append(f"GitHub fixture repository missing {key}")
    return failures


def validate_market_fixture() -> list[str]:
    payload = json.loads((ROOT / "fixtures/lifehub/market_snapshot.json").read_text(encoding="utf-8"))
    symbols = payload.get("symbols", [])
    failures = []
    if not symbols:
        failures.append("fixtures/lifehub/market_snapshot.json has no symbols")
    for symbol in symbols:
        if not symbol.get("symbol"):
            failures.append("Market fixture symbol is missing symbol")
        for key in ["open", "high", "low", "close", "timestamp"]:
            if key not in symbol:
                failures.append(f"Market fixture symbol missing {key}")
    return failures


def validate_weekly_review_fixtures() -> list[str]:
    week = json.loads((ROOT / "fixtures/lifehub/week_summary.json").read_text(encoding="utf-8"))
    feedback = json.loads((ROOT / "fixtures/lifehub/feedback_profile.json").read_text(encoding="utf-8"))
    failures = []
    if int(week.get("sessions", 0)) <= 0:
        failures.append("fixtures/lifehub/week_summary.json must include positive sessions")
    for key in ["avg_intensity", "avg_mood", "avg_fatigue", "pain_sessions", "by_activity", "by_result"]:
        if key not in week:
            failures.append(f"Weekly summary fixture missing {key}")
    if not feedback:
        failures.append("fixtures/lifehub/feedback_profile.json must include at least one activity")
    for activity, profile in feedback.items():
        if "follow_rate" not in profile or "feedback_events" not in profile:
            failures.append(f"Feedback profile fixture for {activity} missing learning metrics")
    return failures


def validate_decision_metrics_fixture() -> list[str]:
    payload = json.loads((ROOT / "fixtures/lifehub/decision_metrics.json").read_text(encoding="utf-8"))
    failures = []
    for key in ["useful_decision_days", "followed_events", "skipped_events", "follow_rate"]:
        if key not in payload:
            failures.append(f"Decision metrics fixture missing {key}")
    if not 0 <= float(payload.get("follow_rate", 0)) <= 1:
        failures.append("Decision metrics fixture follow_rate must be 0..1")
    if not 0 <= int(payload.get("useful_decision_days", 0)) <= 7:
        failures.append("Decision metrics fixture useful_decision_days must be 0..7")
    return failures


def validate_docs() -> list[str]:
    text = (ROOT / "docs/lifehub.md").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    required = [
        "Open-Meteo",
        "OpenStreetMap",
        "Overpass",
        "Telegram",
        "local only",
        "Future integrations",
        "investment-signals",
        "stock-prices",
        "Temporal",
        "Weekly review workflow",
        "lifehub-temporal-start-weekly-fixture",
        "LifeHub Cockpit",
        "one-command evidence flow",
        "lifehub-evidence-flow",
        "lifehub-evidence-flow-temporal",
        "lifehub-temporal-evidence.md",
        "inline feedback buttons",
        "life_decision_feedback",
        "/goals",
        "/review",
        "/metrics",
        "weekly review",
        "progress scorecard",
        "GitHub",
        "Alpaca",
        "Lakehouse and DWH foundation",
        "lifehub_lakehouse_pipeline_dag.py",
        "lifehub_jsonl_to_iceberg.py",
        "lifehub-lakehouse-runtime-smoke",
        "lifehub-lakehouse-runtime-evidence.md",
        "iceberg.bronze.lifehub_events",
        "source_registry.yaml",
        "activity-file-import",
        "activity_files",
        "sleep-import",
        "sleep_quality",
        "sleep recovery",
        "sleep-fixture",
        "custom-source-import",
        "custom_life_events",
        "source-onboard",
        "source_registry_entry.yaml",
    ]
    failures = [f"docs/lifehub.md missing phrase: {phrase}" for phrase in required if phrase not in text]
    if "lifehub-temporal-start-weekly-fixture" not in makefile:
        failures.append("Makefile missing lifehub-temporal-start-weekly-fixture")
    for target in [
        "lifehub-evidence-flow",
        "lifehub-evidence-flow-temporal",
        "lifehub-evidence-flow-plan",
        "lifehub-lake-export-fixture",
        "lifehub-sleep-fixture",
        "lifehub-custom-source-fixture",
        "lifehub-source-onboard-demo",
        "lifehub-source-map-demo",
        "lifehub-full-source-demo",
        "lifehub-lakehouse-runtime-smoke",
    ]:
        if target not in makefile:
            failures.append(f"Makefile missing {target}")
    return failures


def validate_cockpit() -> list[str]:
    text = (ROOT / "docs/lifehub-cockpit.html").read_text(encoding="utf-8")
    required = [
        "LifeHub Cockpit",
        "Today Decision",
        "Readiness By Activity",
        "Recommendation Score Trend",
        "Weekly Review",
        "Weekly Goal Progress",
        "Activity Learning Profile",
        "Context Signals",
        "DataOps Health",
        "Weather Aggregates",
    ]
    forbidden = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "raw_diary_notes",
        "pain_text",
        "feedback note",
    ]
    failures = [f"LifeHub Cockpit missing phrase: {phrase}" for phrase in required if phrase not in text]
    failures.extend(f"LifeHub Cockpit contains forbidden sensitive phrase: {phrase}" for phrase in forbidden if phrase in text)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
