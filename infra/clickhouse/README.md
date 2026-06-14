# 🧩 ClickHouse

Why: Columnar analytics database for fast OLAP queries.

## ⚙️ Profile

- `core`

## 🔗 Dependencies

- None (used by other services)

## 🚀 How

- Start service:
  - `docker compose --profile core up -d clickhouse`

- HTTP: `http://localhost:8123`
- Native port: `9000` (mapped to `9002` on host)
- Credentials: from `.env` (`CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD`)

## 📝 Notes

- Config files mounted: [config.xml](config.xml), [users.xml](users.xml).
- Init SQL mounted from [init/](init/) creates the `analytics` database, retail event sink tables for `orders`, `payments`, and `inventory_changes`, plus Kafka Engine source tables and materialized views for the matching retail event topics.
- Validate the ingestion contract with [../../sql/validation/clickhouse_ingestion_contract.md](../../sql/validation/clickhouse_ingestion_contract.md).
- Data persisted in `clickhouse-data` volume.
