# Assets

Store README diagrams and runtime evidence captured from local smoke runs here.

## Product diagrams

- `life-data-hub-stack.svg` - visual stack map embedded in the main README.

## Runtime evidence

Recommended files:

- `kafka-topics.png` - Kafka UI topic list with generator and CDC topics.
- `generator-logs.png` - data generator logs showing seed counts and target EPS.
- `postgres-validation.png` - output from `sql/validation/postgres_retail_seed_checks.sql`.
- `analytics-query.png` - Trino or ClickHouse query output after ingestion jobs are wired.
- `clickhouse-show-tables.txt` - `SHOW TABLES FROM analytics` after ClickHouse starts.
- `clickhouse-orders-count.txt` - row count for `analytics.orders` after generator events.
- `clickhouse-payments-count.txt` - row count for `analytics.payments` after generator events.
- `clickhouse-inventory-count.txt` - row count for `analytics.inventory_changes` after generator events.
- `clickhouse-ingestion-log.txt` - relevant ClickHouse or Docker logs for ingestion review.

Generate these text artifacts with:

```bash
python scripts/capture_clickhouse_evidence.py --duration 60 --cleanup
```

The capture script uses `docker-compose.evidence.yml`, which disables host port bindings for Postgres, Kafka, Schema Registry, and ClickHouse. This keeps the smoke run isolated from local services that may already use ports such as `5432`, `8081`, or `8123`.

Text logs are preferred for PR review because they are diffable. Do not commit screenshots or logs containing secrets, local tokens, private URLs, or personal data.
