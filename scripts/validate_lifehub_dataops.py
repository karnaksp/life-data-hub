#!/usr/bin/env python3
"""Validate LifeHub DataOps metadata artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "catalog/lifehub/datasets.yaml",
    "config/lifehub/source_registry.yaml",
    "expectations/lifehub/expectations.yaml",
    "dbt/lifehub/dbt_project.yml",
    "dbt/lifehub/profiles.example.yml",
    "dbt/lifehub/models/sources.yml",
    "dbt/lifehub/models/schema.yml",
    "dbt/lifehub/models/staging/stg_lifehub_weather_hourly.sql",
    "dbt/lifehub/models/staging/stg_lifehub_readiness_scores.sql",
    "dbt/lifehub/models/staging/stg_lifehub_recommendation_events.sql",
    "dbt/lifehub/models/staging/stg_lifehub_decision_feedback_events.sql",
    "dbt/lifehub/models/staging/stg_lifehub_signal_events.sql",
    "dbt/lifehub/models/staging/stg_lifehub_spots.sql",
    "dbt/lifehub/models/marts/mart_lifehub_daily_weather.sql",
    "dbt/lifehub/models/marts/mart_lifehub_latest_readiness.sql",
    "dbt/lifehub/models/marts/mart_lifehub_recommendation_daily.sql",
    "dbt/lifehub/models/marts/mart_lifehub_decision_feedback_daily.sql",
    "dbt/lifehub/models/marts/mart_lifehub_useful_decision_days.sql",
    "dbt/lifehub/models/marts/mart_lifehub_signal_daily.sql",
    "scripts/emit_lifehub_lineage.py",
    "scripts/run_lifehub_lakehouse_runtime_smoke.py",
    "infra/airflow/dags/lifehub_lakehouse_pipeline_dag.py",
    "infra/airflow/processing/spark/jobs/lifehub_jsonl_to_iceberg.py",
    "infra/lifehub/lifehub/sleep.py",
    "infra/lifehub/lifehub/generic_sources.py",
    "infra/lifehub/lifehub/source_onboarding.py",
    "fixtures/lifehub/sleep_quality.json",
    "sql/lifehub/trino_lifehub_lakehouse.sql",
]

REQUIRED_DATASETS = [
    "postgres.public.life_spots",
    "postgres.public.life_activity_log",
    "clickhouse.analytics.life_weather_hourly",
    "clickhouse.analytics.life_readiness_scores",
    "clickhouse.analytics.life_activity_events",
    "clickhouse.analytics.life_latest_readiness_v",
    "clickhouse.analytics.life_recommendation_events",
    "postgres.public.life_recommendation_events",
    "clickhouse.analytics.life_decision_feedback_events",
    "postgres.public.life_decision_feedback",
    "clickhouse.analytics.life_signal_events",
    "postgres.public.life_signal_events",
    "iceberg.bronze.lifehub_events",
    "iceberg.silver.lifehub_events",
    "iceberg.gold.lifehub_decision_events",
    "source_registry.custom_life_events",
    "lake.landing.lifehub.custom_life_events",
    "source_registry.sleep_quality",
    "lake.landing.lifehub.sleep_quality",
]


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_required_files())
    failures.extend(validate_catalog())
    failures.extend(validate_expectations())
    failures.extend(validate_source_registry())
    failures.extend(validate_lakehouse_artifacts())
    failures.extend(validate_dbt())
    failures.extend(validate_lineage_event_shape())
    if failures:
        print("LifeHub DataOps validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("LifeHub DataOps validation passed.")
    return 0


def validate_required_files() -> list[str]:
    failures = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.exists():
            failures.append(f"Missing DataOps file: {relative}")
        elif path.is_file() and not path.read_text(encoding="utf-8").strip():
            failures.append(f"DataOps file is empty: {relative}")
    return failures


def validate_catalog() -> list[str]:
    text = (ROOT / "catalog/lifehub/datasets.yaml").read_text(encoding="utf-8")
    failures = [f"Catalog missing dataset {name}" for name in REQUIRED_DATASETS if name not in text]
    for phrase in ["privacy: local_only", "private_diary", "freshness_slo", "commit_policy"]:
        if phrase not in text:
            failures.append(f"Catalog missing phrase: {phrase}")
    return failures


def validate_expectations() -> list[str]:
    text = (ROOT / "expectations/lifehub/expectations.yaml").read_text(encoding="utf-8")
    required = [
        "spots_have_rows",
        "weather_has_recent_fetch",
        "readiness_has_recent_compute",
        "readiness_scores_are_valid",
        "recommendations_are_valid",
        "feedback_actions_are_valid",
        "context_signals_are_valid",
        "severity: error",
    ]
    return [f"Expectations missing phrase: {phrase}" for phrase in required if phrase not in text]


def validate_source_registry() -> list[str]:
    text = (ROOT / "config/lifehub/source_registry.yaml").read_text(encoding="utf-8")
    required = [
        "medallion_layers:",
        "landing:",
        "bronze:",
        "silver:",
        "gold:",
        "weather_forecast:",
        "activity_diary:",
        "activity_files:",
        "sleep_quality:",
        "custom_life_events:",
        "decision_feedback:",
        "context_signals:",
        "daily_context_profile:",
        "new_source_template:",
        "never_export_raw_notes_or_pain_text",
        "real route files stay local",
        "custom-source-import",
        "redact notes, addresses, tokens",
    ]
    return [f"Source registry missing phrase: {phrase}" for phrase in required if phrase not in text]


def validate_lakehouse_artifacts() -> list[str]:
    failures = []
    dag = (ROOT / "infra/airflow/dags/lifehub_lakehouse_pipeline_dag.py").read_text(encoding="utf-8")
    job = (ROOT / "infra/airflow/processing/spark/jobs/lifehub_jsonl_to_iceberg.py").read_text(encoding="utf-8")
    sql = (ROOT / "sql/lifehub/trino_lifehub_lakehouse.sql").read_text(encoding="utf-8")
    for phrase in [
        "lifehub_lakehouse_pipeline",
        "export_lifehub_landing_jsonl",
        "load_lifehub_jsonl_to_iceberg",
        "custom-source-import",
        "activity_route_spb_public.gpx",
        "sleep_quality.json",
        "iceberg.bronze.lifehub_events",
        "iceberg.silver.lifehub_events",
        "iceberg.gold.lifehub_decision_events",
    ]:
        if phrase not in dag:
            failures.append(f"LifeHub lakehouse DAG missing phrase: {phrase}")
    for phrase in ["read_landing", "ensure_iceberg_table", "privacy_class", "json_payload"]:
        if phrase not in job:
            failures.append(f"LifeHub Spark lakehouse job missing phrase: {phrase}")
    onboarding = (ROOT / "infra/lifehub/lifehub/source_onboarding.py").read_text(encoding="utf-8")
    cli = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
    recommendations = (ROOT / "infra/lifehub/lifehub/recommendations.py").read_text(encoding="utf-8")
    context = (ROOT / "infra/lifehub/lifehub/context.py").read_text(encoding="utf-8")
    for phrase in ["SourceOnboardingSpec", "source_registry_entry.yaml", "make lifehub-lakehouse-runtime-smoke"]:
        if phrase not in onboarding:
            failures.append(f"LifeHub source onboarding generator missing phrase: {phrase}")
    for phrase in ['sub.add_parser("source-onboard")', "cmd_source_onboard", "--apply-registry"]:
        if phrase not in cli:
            failures.append(f"LifeHub CLI missing source onboarding phrase: {phrase}")
    for phrase in ["recovery_summary", "sleep recovery is low", "sleep duration was short"]:
        if phrase not in recommendations:
            failures.append(f"LifeHub recommendation engine missing recovery phrase: {phrase}")
    for phrase in ["recovery_summary", "sleep_recovery=", "sleep_minutes="]:
        if phrase not in context:
            failures.append(f"LifeHub daily context profile missing recovery phrase: {phrase}")
    smoke = (ROOT / "scripts/run_lifehub_lakehouse_runtime_smoke.py").read_text(encoding="utf-8")
    for phrase in [
        "spark-submit",
        "iceberg.bronze.lifehub_events",
        "iceberg.silver.lifehub_events",
        "iceberg.gold.lifehub_decision_events",
        "trino",
        "lifehub-lakehouse-runtime-evidence.md",
    ]:
        if phrase not in smoke:
            failures.append(f"LifeHub lakehouse runtime smoke missing phrase: {phrase}")
    for phrase in [
        "iceberg.bronze.lifehub_events",
        "iceberg.silver.lifehub_events",
        "forbidden_payload_rows",
        "source_name = 'sleep_quality'",
        "avg_recovery_score",
    ]:
        if phrase not in sql:
            failures.append(f"LifeHub Trino lakehouse SQL missing phrase: {phrase}")
    return failures


def validate_dbt() -> list[str]:
    failures = []
    project = (ROOT / "dbt/lifehub/dbt_project.yml").read_text(encoding="utf-8")
    sources = (ROOT / "dbt/lifehub/models/sources.yml").read_text(encoding="utf-8")
    schema = (ROOT / "dbt/lifehub/models/schema.yml").read_text(encoding="utf-8")
    if "profile: lifehub" not in project:
        failures.append("dbt project must use the lifehub profile")
    for phrase in ["clickhouse_lifehub", "postgres_lifehub", "freshness"]:
        if phrase not in sources:
            failures.append(f"dbt sources missing phrase: {phrase}")
    for phrase in [
        "accepted_values",
        "not_null",
        "mart_lifehub_latest_readiness",
        "stg_lifehub_recommendation_events",
        "stg_lifehub_decision_feedback_events",
        "mart_lifehub_useful_decision_days",
        "stg_lifehub_signal_events",
    ]:
        if phrase not in schema:
            failures.append(f"dbt schema missing phrase: {phrase}")
    return failures


def validate_lineage_event_shape() -> list[str]:
    import importlib.util

    script = ROOT / "scripts/emit_lifehub_lineage.py"
    spec = importlib.util.spec_from_file_location("emit_lifehub_lineage", script)
    if spec is None or spec.loader is None:
        return ["Cannot import scripts/emit_lifehub_lineage.py"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    event = module.build_event()
    failures = []
    for key in ["eventType", "eventTime", "run", "job", "inputs", "outputs"]:
        if key not in event:
            failures.append(f"Lineage event missing key: {key}")
    serialized = json.dumps(event)
    for forbidden in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "pain_text", "raw_diary_notes"]:
        if forbidden in serialized:
            failures.append(f"Lineage event contains forbidden phrase: {forbidden}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
