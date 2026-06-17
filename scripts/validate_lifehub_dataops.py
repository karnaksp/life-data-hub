#!/usr/bin/env python3
"""Validate LifeHub DataOps metadata artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


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
    "infra/lifehub/lifehub/source_subscriptions.py",
    "infra/lifehub/lifehub/runtime_sources.py",
    "config/lifehub/source_subscriptions.example.json",
    "fixtures/lifehub/source_subscriptions.json",
    "fixtures/lifehub/rss_feed.xml",
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

ACTIVE_FIXTURE_SOURCES = {
    "weather_forecast": ["fixtures/lifehub/open_meteo_clear_day.json"],
    "place_spots": ["fixtures/lifehub/overpass_spots.json"],
    "activity_diary": ["fixtures/lifehub/week_summary.json"],
    "activity_files": ["fixtures/lifehub/activity_route_spb_public.gpx"],
    "decision_feedback": ["fixtures/lifehub/decision_metrics.json", "fixtures/lifehub/feedback_profile.json"],
    "context_signals": ["fixtures/lifehub/context_signals.json"],
    "external_source_items": ["fixtures/lifehub/source_subscriptions.json", "fixtures/lifehub/rss_feed.xml"],
    "daily_context_profile": [
        "fixtures/lifehub/open_meteo_clear_day.json",
        "fixtures/lifehub/week_summary.json",
        "fixtures/lifehub/decision_metrics.json",
        "fixtures/lifehub/context_signals.json",
    ],
    "sleep_quality": ["fixtures/lifehub/sleep_quality.json"],
    "custom_life_events": ["fixtures/lifehub/custom_life_events.json"],
    "calendar_events": ["fixtures/lifehub/local_calendar.ics"],
    "moto_learning_log": ["fixtures/lifehub/moto_learning.csv", "fixtures/lifehub/moto_learning.json"],
    "trade_journal_summary": ["fixtures/lifehub/trade_journal.csv", "fixtures/lifehub/trade_journal.json"],
    "personal_notes_summary": ["fixtures/lifehub/personal_notes.md", "fixtures/lifehub/personal_notes.json"],
    "training_sessions": ["fixtures/lifehub/training_sessions.json"],
    "habit_goals": ["fixtures/lifehub/habit_goals.json"],
    "market_watchlist_snapshot": ["fixtures/lifehub/market_watchlist_snapshot.json"],
    "github_project_activity": ["fixtures/lifehub/github_project_activity_summary.json"],
    "learning_activity": ["fixtures/lifehub/learning_activity.json"],
    "finance_event_calendar": ["fixtures/lifehub/finance_event_calendar.json"],
    "health_summary": ["fixtures/lifehub/health_summary.json"],
    "location_area_summary": ["fixtures/lifehub/location_area_summary.json"],
    "finance_transactions": ["fixtures/lifehub/finance_transactions_summary.json"],
    "data_source_runs": ["fixtures/lifehub/data_source_runs.json"],
    "browser_and_app_usage": ["fixtures/lifehub/digital_activity.json"],
    "tasks_and_projects": ["fixtures/lifehub/tasks_projects.json"],
    "communications_metadata": ["fixtures/lifehub/communications_summary.json"],
    "location_visits": ["fixtures/lifehub/location_visits.json"],
    "health_metrics": ["fixtures/lifehub/health_metrics.json"],
    "identity_documents": ["fixtures/lifehub/identity_pointers.json"],
    "secrets_inventory": ["fixtures/lifehub/credential_rotation.json"],
}

REQUIRED_SOURCE_FIELDS = [
    "tier",
    "domain",
    "source_type",
    "privacy_class",
    "raw_policy",
    "local_policy",
    "producer",
    "landing_path",
    "bronze_table",
    "silver_table",
    "consumers",
    "pii",
    "onboarding_contract",
]

REQUIRED_CONTRACT_FIELDS = ["required_fields", "event_time_field", "idempotency_key"]

FORBIDDEN_PAYLOAD_KEYS = {
    "address",
    "api_key",
    "chat_id",
    "email",
    "home",
    "home_address",
    "note",
    "notes",
    "pain_text",
    "phone",
    "raw_diary_notes",
    "secret",
    "telegram_bot_token",
    "token",
    "work_address",
}

FORBIDDEN_LANDING_KEYS = FORBIDDEN_PAYLOAD_KEYS | {"raw_payload", "message_body", "document_number"}

DISALLOWED_TRACKED_RAW_PATTERNS = [
    "fixtures/lifehub/raw",
    "fixtures/lifehub/private",
    "fixtures/lifehub/export",
    "fixtures/lifehub/token",
    "fixtures/lifehub/secret",
    "fixtures/lifehub/home_address",
    "fixtures/lifehub/raw_diary",
    "fixtures/lifehub/pain_text",
]

DISALLOWED_TRACKED_SUFFIXES = {".fit", ".tcx"}

LANDING_ENVELOPE_FIELDS = [
    "lake_version",
    "event_id",
    "source_name",
    "source_tier",
    "source_type",
    "event_type",
    "event_time",
    "ingested_at",
    "privacy_class",
    "consent_scope",
    "subject_id",
    "idempotency_key",
    "raw_policy",
    "local_policy",
    "payload_summary",
    "metrics",
    "tags",
    "quality_flags",
    "payload",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--landing-root",
        type=Path,
        help="Validate generated LifeHub lake landing files under this root, for example tmp/lake.",
    )
    parser.add_argument(
        "--write-source-map",
        type=Path,
        help="Write a markdown source registry map for demo/evidence review.",
    )
    args = parser.parse_args(argv)
    failures: list[str] = []
    failures.extend(validate_required_files())
    failures.extend(validate_catalog())
    failures.extend(validate_expectations())
    failures.extend(validate_source_registry())
    failures.extend(validate_fixture_coverage())
    failures.extend(validate_privacy_sanitizer_and_tracked_files())
    if args.landing_root:
        failures.extend(validate_landing_root(args.landing_root))
    failures.extend(validate_lakehouse_artifacts())
    failures.extend(validate_dbt())
    failures.extend(validate_lineage_event_shape())
    if failures:
        print("LifeHub DataOps validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    if args.write_source_map:
        write_source_map(args.write_source_map)
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
    failures = [f"Source registry missing phrase: {phrase}" for phrase in required if phrase not in text]
    registry = load_source_registry()
    sources = registry.get("sources")
    if not isinstance(sources, dict) or not sources:
        return failures + ["Source registry must define non-empty sources"]
    privacy_classes = set((registry.get("source_architecture") or {}).get("privacy_classes") or {})
    raw_policies = set((registry.get("source_architecture") or {}).get("raw_local_policies") or {})
    medallion_layers = registry.get("medallion_layers") or {}
    for layer in ["landing", "bronze", "silver", "gold"]:
        if layer not in medallion_layers:
            failures.append(f"Source registry missing medallion layer {layer}")
    for source_name, source in sources.items():
        if not isinstance(source, dict):
            failures.append(f"Source registry entry {source_name} must be a mapping")
            continue
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in source:
                failures.append(f"Source registry entry {source_name} missing {field}")
        if source.get("privacy_class") not in privacy_classes:
            failures.append(f"Source registry entry {source_name} has unknown privacy_class {source.get('privacy_class')}")
        if source.get("raw_policy") not in raw_policies:
            failures.append(f"Source registry entry {source_name} has unknown raw_policy {source.get('raw_policy')}")
        if source.get("local_policy") not in raw_policies and source.get("local_policy") != "explicit_opt_in_pointer_only":
            failures.append(f"Source registry entry {source_name} has unknown local_policy {source.get('local_policy')}")
        if source.get("pii") is True and not source.get("commit_policy"):
            failures.append(f"Source registry entry {source_name} handles PII but has no commit_policy")
        landing_path = str(source.get("landing_path", ""))
        if f"/{source_name}/" not in landing_path:
            failures.append(f"Source registry entry {source_name} landing_path must include source name")
        if not str(source.get("bronze_table", "")).startswith("iceberg.bronze."):
            failures.append(f"Source registry entry {source_name} bronze_table must be an Iceberg bronze table")
        if not str(source.get("silver_table", "")).startswith("iceberg.silver."):
            failures.append(f"Source registry entry {source_name} silver_table must be an Iceberg silver table")
        if not isinstance(source.get("consumers"), list) or not source.get("consumers"):
            failures.append(f"Source registry entry {source_name} must list consumers")
        contract = source.get("onboarding_contract") or {}
        for field in REQUIRED_CONTRACT_FIELDS:
            if field not in contract:
                failures.append(f"Source registry entry {source_name} onboarding_contract missing {field}")
        if not isinstance(contract.get("required_fields"), list) or not contract.get("required_fields"):
            failures.append(f"Source registry entry {source_name} required_fields must be a non-empty list")
        if contract.get("event_time_field") not in (contract.get("required_fields") or []):
            failures.append(f"Source registry entry {source_name} event_time_field must be required")
        if not isinstance(contract.get("idempotency_key"), list) or not contract.get("idempotency_key"):
            failures.append(f"Source registry entry {source_name} idempotency_key must be a non-empty list")
    return failures


def load_source_registry() -> dict[str, Any]:
    return parse_yaml_subset((ROOT / "config/lifehub/source_registry.yaml").read_text(encoding="utf-8"))


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the simple YAML subset used by the source registry.

    This keeps repository validation dependency-free while still checking the
    structured source metadata. It supports nested mappings, inline lists, and
    scalar strings/booleans/numbers; block lists are not needed by the checks.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.lstrip().startswith("- "):
            continue
        if ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, value = raw.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = value.strip()
        if not value:
            nested: dict[str, Any] = {}
            parent[key] = nested
            stack.append((indent, nested))
        else:
            parent[key] = parse_yaml_scalar(value)
    return root


def parse_yaml_scalar(value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        return value.strip("\"'")


def validate_fixture_coverage() -> list[str]:
    failures: list[str] = []
    registry = load_source_registry()
    sources = set((registry.get("sources") or {}).keys())
    for source_name, fixture_paths in ACTIVE_FIXTURE_SOURCES.items():
        if source_name not in sources:
            failures.append(f"Active fixture source {source_name} is missing from source registry")
        for relative in fixture_paths:
            path = ROOT / relative
            if not path.exists():
                failures.append(f"Fixture coverage for {source_name} missing {relative}")
                continue
            if path.suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload in ({}, []):
                    failures.append(f"Fixture coverage for {source_name} has empty JSON fixture {relative}")
            elif path.suffix == ".gpx" and "<gpx" not in path.read_text(encoding="utf-8")[:500].lower():
                failures.append(f"Fixture coverage for {source_name} GPX fixture is not a GPX document: {relative}")
    missing_fixture_policy = sources.difference(ACTIVE_FIXTURE_SOURCES)
    for source_name in sorted(missing_fixture_policy):
        source = registry["sources"][source_name]
        producer = str(source.get("producer", ""))
        if not producer.startswith("planned-"):
            failures.append(f"Source {source_name} has no fixture coverage and is not marked with a planned producer")
    return failures


def validate_privacy_sanitizer_and_tracked_files() -> list[str]:
    failures: list[str] = []
    generic_source = (ROOT / "infra/lifehub/lifehub/generic_sources.py").read_text(encoding="utf-8")
    for key in sorted(FORBIDDEN_PAYLOAD_KEYS):
        if f'"{key}"' not in generic_source:
            failures.append(f"Generic source sanitizer missing forbidden key {key}")
    try:
        tracked_files = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        return failures + [f"Cannot inspect tracked files for raw LifeHub payloads: {exc}"]
    failures.extend(validate_fixture_payload_privacy(tracked_files))
    for relative in tracked_files:
        normalized = relative.lower()
        if any(pattern in normalized for pattern in DISALLOWED_TRACKED_RAW_PATTERNS):
            failures.append(f"Tracked LifeHub file looks like raw/private payload and must stay local: {relative}")
        if Path(relative).suffix.lower() in DISALLOWED_TRACKED_SUFFIXES and relative.startswith("fixtures/lifehub/"):
            failures.append(f"Tracked LifeHub route/device raw file must stay local: {relative}")
        if relative.startswith("tmp/"):
            failures.append(f"Generated tmp file must not be tracked: {relative}")
    return failures


def validate_fixture_payload_privacy(tracked_files: list[str]) -> list[str]:
    failures: list[str] = []
    allowed_redacted_keys = {"fixtures/lifehub/custom_life_events.json": {"note", "home_address"}}
    fixture_files = [
        ROOT / relative
        for relative in tracked_files
        if relative.startswith("fixtures/lifehub/") and relative.endswith(".json")
    ]
    for path in sorted(fixture_files):
        relative = str(path.relative_to(ROOT))
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key_path, value in iter_forbidden_payload_values(payload, FORBIDDEN_PAYLOAD_KEYS):
            leaf = key_path.rsplit(".", 1)[-1]
            if leaf in allowed_redacted_keys.get(relative, set()) and str(value).lower().startswith("redacted"):
                continue
            failures.append(f"Fixture {relative} contains forbidden raw field {key_path}")
    return failures


def iter_forbidden_payload_values(value: Any, forbidden: set[str], prefix: str = ""):
    if isinstance(value, dict):
        for key, nested in value.items():
            key_name = str(key)
            normalized = key_name.lower().replace("-", "_")
            path = f"{prefix}.{key_name}" if prefix else key_name
            if normalized in forbidden:
                yield path, nested
            yield from iter_forbidden_payload_values(nested, forbidden, path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from iter_forbidden_payload_values(nested, forbidden, f"{prefix}[{index}]")


def validate_landing_root(root: Path) -> list[str]:
    failures: list[str] = []
    landing_root = root if root.is_absolute() else ROOT / root
    landing_dir = landing_root / "lifehub" / "landing"
    if not landing_dir.exists():
        return [f"Landing root has no LifeHub landing directory: {landing_dir.relative_to(ROOT)}"]
    registry_sources = set((load_source_registry().get("sources") or {}).keys())
    files = sorted(landing_dir.glob("*/dt=*/events.jsonl"))
    if not files:
        return [f"Landing root contains no events.jsonl files: {landing_dir.relative_to(ROOT)}"]
    observed_sources: set[str] = set()
    for path in files:
        source_name = path.parent.parent.name
        observed_sources.add(source_name)
        if source_name not in registry_sources:
            failures.append(f"Landing file uses unregistered source {source_name}: {path.relative_to(ROOT)}")
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                failures.append(f"{path.relative_to(ROOT)}:{line_number} is not valid JSON: {exc}")
                continue
            failures.extend(validate_landing_event(path, line_number, source_name, event))
    for source_name in ACTIVE_FIXTURE_SOURCES:
        if source_name not in observed_sources:
            failures.append(f"Landing root missing active source output: {source_name}")
    return failures


def validate_landing_event(path: Path, line_number: int, source_name: str, event: Any) -> list[str]:
    location = f"{path.relative_to(ROOT)}:{line_number}"
    failures: list[str] = []
    if not isinstance(event, dict):
        return [f"{location} landing event must be a JSON object"]
    for field in LANDING_ENVELOPE_FIELDS:
        if field not in event:
            failures.append(f"{location} landing event missing {field}")
    if event.get("lake_version") != "lifehub.lake.v1":
        failures.append(f"{location} landing event has unexpected lake_version {event.get('lake_version')}")
    if event.get("source_name") != source_name:
        failures.append(f"{location} source_name does not match landing path source {source_name}")
    if not isinstance(event.get("payload"), dict) or not event.get("payload"):
        failures.append(f"{location} payload must be a non-empty object")
    for key_path, _value in iter_forbidden_payload_values(event.get("payload"), FORBIDDEN_LANDING_KEYS):
        failures.append(f"{location} payload contains forbidden raw field {key_path}")
    return failures


def write_source_map(path: Path) -> None:
    registry = load_source_registry()
    output = path if path.is_absolute() else ROOT / path
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LifeHub Source Map Demo",
        "",
        "| Source | Tier | Domain | Privacy class | Raw policy | Fixture coverage | Bronze | Silver |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source_name, source in sorted((registry.get("sources") or {}).items()):
        fixtures = ACTIVE_FIXTURE_SOURCES.get(source_name)
        fixture_label = ", ".join(fixtures) if fixtures else "planned/no committed raw fixture"
        lines.append(
            "| "
            + " | ".join(
                [
                    source_name,
                    str(source.get("tier", "")),
                    str(source.get("domain", "")),
                    str(source.get("privacy_class", "")),
                    str(source.get("raw_policy", "")),
                    fixture_label,
                    str(source.get("bronze_table", "")),
                    str(source.get("silver_table", "")),
                ]
            )
            + " |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    for phrase in [
        'sub.add_parser("source-add")',
        'sub.add_parser("source-list")',
        'sub.add_parser("source-sync")',
        "handle_source_subscription_command",
        "external_source_items",
        "runtime-log-import",
    ]:
        if phrase not in cli:
            failures.append(f"LifeHub CLI missing source subscription phrase: {phrase}")
    runtime_sources = (ROOT / "infra/lifehub/lifehub/runtime_sources.py").read_text(encoding="utf-8")
    for phrase in ["runtime_log_source_events", "data_source_runs", "render_source_run_status", "sanitize_message"]:
        if phrase not in runtime_sources:
            failures.append(f"LifeHub runtime source importer missing phrase: {phrase}")
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
