# Evidence Assets

Store portfolio evidence captured from the retail CDC run here.

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

Text logs are preferred for PR review because they are diffable. Do not commit screenshots or logs containing secrets, local tokens, private URLs, or personal data.
