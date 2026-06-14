# ClickHouse Ingestion Contract

This checklist validates the Kafka-to-ClickHouse wiring for the retail CDC case study. The static contract is covered by `python scripts/validate_project.py`; the commands below are for a short local runtime proof when Docker is available.

## Static Contract

The ClickHouse init SQL defines:

- Kafka Engine source tables for `orders.v1`, `payments.v1`, and `inventory-changes.v1`.
- Materialized views into `analytics.orders`, `analytics.payments`, and `analytics.inventory_changes`.
- Dedicated consumer groups: `clickhouse_orders_sink_v1`, `clickhouse_payments_sink_v1`, and `clickhouse_inventory_changes_sink_v1`.
- Avro Confluent decoding through the local Schema Registry at `http://schema-registry:8081`.

Run:

```bash
python scripts/validate_runtime_contract.py
python scripts/validate_project.py
```

## Runtime Smoke

Start the minimal services needed for ClickHouse ingestion review:

```bash
docker compose --profile core up -d postgres kafka schema-registry clickhouse
docker compose --profile datagen up -d data-generator
```

Inspect the ClickHouse tables:

```bash
docker compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
```

Check that rows arrive after the generator has produced events:

```bash
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.orders"
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.payments"
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.inventory_changes"
```

Run the example analytical queries:

```bash
docker compose exec -T clickhouse clickhouse-client --multiquery < sql/examples/clickhouse_realtime_sales.sql
```

## Evidence to Capture Later

Prefer text logs for PR review because they are diffable and easy to search:

- `docs/assets/clickhouse-show-tables.txt`
- `docs/assets/clickhouse-orders-count.txt`
- `docs/assets/clickhouse-payments-count.txt`
- `docs/assets/clickhouse-inventory-count.txt`
- `docs/assets/clickhouse-ingestion-log.txt`

Static validation proves the wiring is present and aligned with repository contracts. Runtime proof still requires a short local run that shows non-zero row counts after events are produced.
