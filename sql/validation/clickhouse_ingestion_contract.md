# Контракт загрузки в ClickHouse

Этот чеклист проверяет связку Kafka -> ClickHouse для retail CDC контура. Статический контракт покрывается командой `python scripts/validate_project.py`; команды ниже нужны для короткой runtime-проверки, когда доступен Docker.

## Статический контракт

ClickHouse init SQL определяет:

- Kafka Engine source tables для `orders.v1`, `payments.v1` и `inventory-changes.v1`.
- Materialized views в `analytics.orders`, `analytics.payments` и `analytics.inventory_changes`.
- Отдельные consumer groups: `clickhouse_orders_sink_v1`, `clickhouse_payments_sink_v1` и `clickhouse_inventory_changes_sink_v1`.
- Avro Confluent decoding через локальный Schema Registry по адресу `http://schema-registry:8081`.

Запуск:

```bash
python scripts/validate_runtime_contract.py
python scripts/validate_project.py
```

## Runtime smoke

Используйте capture script, чтобы поднять только сервисы, нужные для проверки ClickHouse ingestion, немного подождать события генератора и записать diffable evidence files в `docs/assets/`:

```bash
python scripts/capture_clickhouse_evidence.py --duration 60 --cleanup
```

Скрипт применяет `docker-compose.evidence.yml` поверх основного compose-файла. Override убирает host port bindings, поэтому smoke run может выполняться на машинах разработчиков, где порты Postgres, Kafka, Schema Registry или ClickHouse уже заняты.

Скрипт записывает:

- `docs/assets/clickhouse-show-tables.txt`
- `docs/assets/clickhouse-orders-count.txt`
- `docs/assets/clickhouse-payments-count.txt`
- `docs/assets/clickhouse-inventory-count.txt`
- `docs/assets/clickhouse-ingestion-log.txt`

Ручной эквивалент:

```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml --profile core up -d postgres kafka schema-registry clickhouse
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml --profile datagen up -d data-generator
```

Проверить таблицы ClickHouse:

```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
```

Проверить, что строки появляются после генерации событий:

```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.orders"
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.payments"
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml exec clickhouse clickhouse-client --query "SELECT count() FROM analytics.inventory_changes"
```

Запустить пример аналитического запроса:

```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml exec -T clickhouse clickhouse-client --multiquery < sql/examples/clickhouse_realtime_sales.sql
```

Сохранить лог генератора как evidence:

```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml logs --no-color --tail 200 data-generator > docs/assets/clickhouse-ingestion-log.txt
```

## Evidence для сохранения

Для ревью предпочтительны текстовые логи: они diffable и по ним удобно искать:

- `docs/assets/clickhouse-show-tables.txt`
- `docs/assets/clickhouse-orders-count.txt`
- `docs/assets/clickhouse-payments-count.txt`
- `docs/assets/clickhouse-inventory-count.txt`
- `docs/assets/clickhouse-ingestion-log.txt`

Статическая проверка доказывает, что wiring присутствует и совпадает с контрактами репозитория. Runtime-доказательство требует короткого локального запуска, где row-count files появляются после генерации событий.
