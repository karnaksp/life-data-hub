# Retail CDC Evidence Bundle

This bundle is generated from repository contracts so reviewers can inspect the intended end-to-end path without starting the full Docker stack. It is not a substitute for live screenshots; it is the static evidence contract that live runs must satisfy.

## Generator Runtime Contract

| Contract | Evidence |
| --- | --- |
| Kafka bootstrap | `${KAFKA_BOOTSTRAP:-kafka:9092}` |
| Schema Registry | `${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}` |
| Postgres DSN | `${PG_DSN:-host=postgres port=5432 dbname=demo user=admin password=admin}` |
| Target event rate | `${DATA_GEN_TARGET_EPS:-40}` events/sec |
| Business topic weights | orders `${DATA_GEN_WEIGHT_ORDERS:-0.35}`, interactions `${DATA_GEN_WEIGHT_INTERACTIONS:-0.45}`, inventory `${DATA_GEN_WEIGHT_INVENTORY_CHG:-0.20}` |

## Business Event Topics

These topics are aligned across generator defaults, Airflow Bronze DAG params, Schema Registry subjects, and the Kafka validation checklist.

- `customer-interactions.v1`
- `inventory-changes.v1`
- `orders.v1`
- `payments.v1`
- `shipments.v1`

## Debezium CDC Topics

These CDC topics are aligned across generator defaults, Airflow CDC streams, Debezium/Postgres source tables, and the Kafka validation checklist.

- `demo.public.customer_segments`
- `demo.public.inventory`
- `demo.public.product_suppliers`
- `demo.public.products`
- `demo.public.suppliers`
- `demo.public.users`
- `demo.public.warehouse_inventory`
- `demo.public.warehouses`

## Schema Registry Subjects

- `customer-interactions.v1-value`
- `inventory-changes.v1-value`
- `orders.v1-value`
- `payments.v1-value`
- `shipments.v1-value`

## Postgres Source Tables

The local Postgres bootstrap creates the following source tables. Debezium streams the configured CDC subset through the `demo` topic prefix.

- `customer_segments`
- `inventory`
- `life_activity_log`
- `life_daily_context_profiles`
- `life_decision_feedback`
- `life_digest_runs`
- `life_recommendation_events`
- `life_signal_events`
- `life_spots`
- `life_user_preferences`
- `product_suppliers`
- `products`
- `suppliers`
- `users`
- `warehouse_inventory`
- `warehouses`

## Airflow Bronze Targets

Business topics from DAG params:

- `customer-interactions.v1`
- `inventory-changes.v1`
- `orders.v1`
- `payments.v1`
- `shipments.v1`

CDC topics from DAG streams:

- `demo.public.customer_segments`
- `demo.public.inventory`
- `demo.public.product_suppliers`
- `demo.public.products`
- `demo.public.suppliers`
- `demo.public.users`
- `demo.public.warehouse_inventory`
- `demo.public.warehouses`

## ClickHouse Analytics Contract

ClickHouse init tables:

- `inventory_changes`
- `orders`
- `payments`

Kafka ingestion tables and materialized view targets:

| Contract | Evidence |
| --- | --- |
| `analytics.kafka_inventory_changes` | topic `inventory-changes.v1`, group `clickhouse_inventory_changes_sink_v1`, MV target `analytics.inventory_changes` |
| `analytics.kafka_orders` | topic `orders.v1`, group `clickhouse_orders_sink_v1`, MV target `analytics.orders` |
| `analytics.kafka_payments` | topic `payments.v1`, group `clickhouse_payments_sink_v1`, MV target `analytics.payments` |

Tables referenced by the realtime analytics SQL example:

- `inventory_changes`
- `orders`
- `payments`

## Validation Commands

| Contract | Evidence |
| --- | --- |
| Static runtime contract | `python scripts/validate_runtime_contract.py` (passed) |
| Project quality gate | `python scripts/validate_project.py` |
| Compose config | `docker compose --env-file .env.example config --quiet` |
| Evidence compose config | `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml config --quiet` |
| Postgres checks | `docker compose exec -T postgres psql -U admin -d demo < sql/validation/postgres_retail_seed_checks.sql` |
| Kafka checks | `sql/validation/kafka_topic_inventory.md` |
| ClickHouse ingestion checks | `sql/validation/clickhouse_ingestion_contract.md` |
| ClickHouse live evidence | `python scripts/capture_clickhouse_evidence.py --duration 60 --cleanup` (uses `docker-compose.evidence.yml` without host port bindings) |

## Live Evidence Still Required

- Kafka UI topic screenshot after `core` and `datagen` profiles are running.
- Data generator logs showing seed counts and event rate.
- Postgres validation output from `sql/validation/postgres_retail_seed_checks.sql`.
- ClickHouse query output after generator events are produced; use `python scripts/capture_clickhouse_evidence.py --duration 60 --cleanup` to write diffable text evidence under `docs/assets/` with the host-port-free evidence compose override.
- Trino query output after lakehouse ingestion jobs are finalized.
