#!/usr/bin/env python3
"""Generate a static evidence bundle for the retail CDC case study."""

from __future__ import annotations

from pathlib import Path

from validate_runtime_contract import (
    clickhouse_example_tables,
    clickhouse_init_tables,
    clickhouse_kafka_ingestion_contract,
    clickhouse_materialized_view_targets,
    config_business_topics,
    config_cdc_topics,
    config_env_defaults,
    compose_generator_env,
    dag_topics,
    postgres_tables,
    schema_registry_topics,
    validate_runtime_contract,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs/evidence/retail-cdc-evidence.md"


def bullet_list(values: list[str]) -> str:
    return "\n".join(f"- `{value}`" for value in values)


def table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Contract | Evidence |", "| --- | --- |"]
    lines.extend(f"| {key} | {value} |" for key, value in rows)
    return "\n".join(lines)


def render_evidence_bundle() -> str:
    defaults = config_env_defaults()
    generator_env = compose_generator_env()
    business_dag, cdc_dag = dag_topics()
    business_topics = sorted(config_business_topics(defaults))
    cdc_topics = sorted(config_cdc_topics(defaults))
    schema_subjects = sorted(f"{topic}-value" for topic in schema_registry_topics())
    clickhouse_tables = sorted(clickhouse_init_tables())
    example_tables = sorted(clickhouse_example_tables())
    clickhouse_ingestion = clickhouse_kafka_ingestion_contract()
    clickhouse_views = clickhouse_materialized_view_targets()
    postgres_source_tables = sorted(postgres_tables())
    runtime_failures = validate_runtime_contract()
    runtime_status = "passed" if not runtime_failures else "failed"

    env_rows = [
        ("Kafka bootstrap", f"`{generator_env['KAFKA_BOOTSTRAP']}`"),
        ("Schema Registry", f"`{generator_env['SCHEMA_REGISTRY_URL']}`"),
        ("Postgres DSN", f"`{generator_env['PG_DSN']}`"),
        ("Target event rate", f"`{generator_env['TARGET_EPS']}` events/sec"),
        (
            "Business topic weights",
            ", ".join(
                [
                    f"orders `{generator_env['WEIGHT_ORDERS']}`",
                    f"interactions `{generator_env['WEIGHT_INTERACTIONS']}`",
                    f"inventory `{generator_env['WEIGHT_INVENTORY_CHG']}`",
                ]
            ),
        ),
    ]
    validation_rows = [
        ("Static runtime contract", f"`python scripts/validate_runtime_contract.py` ({runtime_status})"),
        ("Project quality gate", "`python scripts/validate_project.py`"),
        ("Compose config", "`docker compose --env-file .env.example config --quiet`"),
        (
            "Postgres checks",
            "`docker compose exec -T postgres psql -U admin -d demo < sql/validation/postgres_retail_seed_checks.sql`",
        ),
        ("Kafka checks", "`sql/validation/kafka_topic_inventory.md`"),
        ("ClickHouse ingestion checks", "`sql/validation/clickhouse_ingestion_contract.md`"),
    ]
    clickhouse_rows = [
        (
            f"`analytics.kafka_{table}`",
            f"topic `{contract['topic']}`, group `{contract['group']}`, "
            f"MV target `analytics.{clickhouse_views.get(table, 'missing')}`",
        )
        for table, contract in sorted(clickhouse_ingestion.items())
    ]

    content = f"""# Retail CDC Evidence Bundle

This bundle is generated from repository contracts so reviewers can inspect the intended end-to-end path without starting the full Docker stack. It is not a substitute for live screenshots; it is the static evidence contract that live runs must satisfy.

## Generator Runtime Contract

{table(env_rows)}

## Business Event Topics

These topics are aligned across generator defaults, Airflow Bronze DAG params, Schema Registry subjects, and the Kafka validation checklist.

{bullet_list(business_topics)}

## Debezium CDC Topics

These CDC topics are aligned across generator defaults, Airflow CDC streams, Debezium/Postgres source tables, and the Kafka validation checklist.

{bullet_list(cdc_topics)}

## Schema Registry Subjects

{bullet_list(schema_subjects)}

## Postgres Source Tables

The local Postgres bootstrap creates the following source tables. Debezium streams the configured CDC subset through the `demo` topic prefix.

{bullet_list(postgres_source_tables)}

## Airflow Bronze Targets

Business topics from DAG params:

{bullet_list(sorted(business_dag))}

CDC topics from DAG streams:

{bullet_list(sorted(cdc_dag))}

## ClickHouse Analytics Contract

ClickHouse init tables:

{bullet_list(clickhouse_tables)}

Kafka ingestion tables and materialized view targets:

{table(clickhouse_rows)}

Tables referenced by the realtime analytics SQL example:

{bullet_list(example_tables)}

## Validation Commands

{table(validation_rows)}

## Live Evidence Still Required

- Kafka UI topic screenshot after `core` and `datagen` profiles are running.
- Data generator logs showing seed counts and event rate.
- Postgres validation output from `sql/validation/postgres_retail_seed_checks.sql`.
- ClickHouse query output after generator events are produced.
- Trino query output after lakehouse ingestion jobs are finalized.
"""
    if runtime_failures:
        content += "\n## Runtime Contract Failures\n\n"
        content += "\n".join(f"- {failure}" for failure in runtime_failures)
        content += "\n"
    return content


def main() -> int:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(render_evidence_bundle(), encoding="utf-8")
    print(f"Wrote {EVIDENCE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
