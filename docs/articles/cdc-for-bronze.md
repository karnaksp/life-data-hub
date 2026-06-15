# Почему Bronze-слою нужен CDC

В [Bronze как зона ответственности](bronze-is-the-battlefield.md) основная идея простая: Bronze - не polished warehouse, а журнал raw facts. Offsets, schemas и late events должны сохраняться, иначе downstream truth становится недоказуемой. Но журнал бесполезен, если source changes не доходят до него. Поэтому Bronze нужен CDC.

---

## Why We Pick CDC Over Replicas

Реплики выглядят удобно: подключить Trino, query, назвать это pipeline. Но replicas плохо подходят для Bronze playbook:

- **Freshness** - replicas могут отставать во время `VACUUM` или checkpoints; WAL decoding стримит intent по мере commit.
- **History** - replica это snapshot; CDC сохраняет каждый insert, update, delete и порядок поступления.
- **Isolation** - OLTP не нагружается аналитическими queries. Debezium читает WAL один раз и отправляет firehose в Kafka.
- **Schema fidelity** - каждое изменение несет Schema Registry ID; replica не хранит историю schema shifts.
- **Selective capture** - publications позволяют стримить только нужные tables: `demo.public.*`.

С change log в Bronze команде не нужно строить bloating audit tables в OLTP, чтобы отвечать на вопросы по истории. Trino читает CDC-backed Iceberg tables напрямую. Если спрашивают “зачем CDC, если events уже идут через Kafka?”, ответ - coverage: domain events отражают то, что producers решили emit-ить; CDC фиксирует тихие mutations: price fixes, admin toggles, backfills.

Цена: включить logical decoding, правильно настроить WAL retention и обслуживать Debezium. Выигрыш: Bronze действительно покрывает source truth.

```text
Postgres
     │
     ▼
Debezium
     │
     ▼
Kafka + Schema Registry
     │
     ▼
Spark
     │
     ▼
Iceberg Bronze Tables
     │
     ▼
Trino / Analytics
```

Postgres здесь source of operational truth, WAL - журнал committed changes, Debezium - reader, Kafka - transport, Bronze - durable analytical landing.

---

## Data Forge: CDC Ingestion Reference

Data Forge включает Postgres, Debezium, Kafka, Schema Registry и Spark, чтобы локально проверить WAL-to-Kafka-to-Bronze behavior без production risk. Начинайте с [project README](../../README.md): там есть схема сервисов и то, как publication `demo.public.*` проходит через stack. Затем смотрите [Trino walkthrough](../../infra/trino/README.md), где Iceberg tables доступны через SQL, и [data generator guide](../../infra/data-generator/README.md), где описано, как demo changes попадают в Kafka и Postgres.

---

## How Data Forge Streams CDC

### Postgres: prepare the source

`infra/postgres/init-databases.sh` выполняется при старте container и:

- sets `wal_level=logical`, `max_replication_slots=16`, `max_wal_senders=16`, `wal_keep_size=256MB`;
- создает или обновляет role `cdc_reader` с `REPLICATION` и `SELECT` на `demo.public` tables;
- держит `demo_publication` синхронизированной со всеми tables в `demo.public`.

Две Postgres primitives важны для CDC:

- **Replication slot** - logical slot, здесь `demo_slot`, привязывает database к LSN для конкретного consumer. Postgres хранит WAL segments, пока slot не подтвердит consumption. Debezium использует slot, чтобы продолжать с той же позиции после restart.
- **Publication** - named list tables, которые публикуют change events. `demo_publication` объявляет каждую table в `demo.public`; Debezium подписывается на нее, поэтому новые tables можно добавлять без rebuilding connector.

Credentials лежат в `.env`, а `docker-compose.yml` передает их в Postgres и Debezium. Logical replication декодирует WAL в inserts, updates и deletes. One publication дает schema-by-schema control без пересоздания slots.

Предупреждение из replication guides: slots продвигаются только после acknowledgement LSN consumer-ом. LSN - Postgres 64-bit pointer в write-ahead log; каждое committed change получает более высокий LSN. Debezium сохраняет этот pointer в offsets topic и на restart просит Postgres продолжить с него, чтобы не было gaps или duplicates. Если Debezium остановлен, slot's restart LSN не движется, а WAL segments копятся. Monitor slot lag:

```sql
SELECT slot_name, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots;
SELECT pid, state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication;
```

Держите `wal_keep_size` под ваш downtime window и используйте `pg_slot_advance` только как last resort.

Дополнительные практические правила:

- Snapshot strategy matters. `snapshot.mode=initial` делает repeatable-read snapshot, `initial_only` captures and stops, `never` предполагает, что initial state восстановлен другим способом.
- Schema evolution happens. Schema Registry + Iceberg помогают не ломать consumers при additions/drops.
- Lag metrics tell the story. Compare `pg_replication_slots.restart_lsn` and `pg_stat_replication.write_lsn`; alert when the gap grows.
- Security scope stays tight. `cdc_reader` has `REPLICATION` but no write privileges, and row-level security still applies.

### Debezium: capture and publish

[`infra/debezium/Dockerfile`](../../infra/debezium/Dockerfile) устанавливает Confluent Avro converters и копирует [`start-with-connectors.sh`](../../infra/debezium/start-with-connectors.sh). При старте launcher ждет Kafka Connect и делает `PUT` для каждого connector JSON из [`infra/debezium/config/`](../../infra/debezium/config/). Default config ([`demo-postgres.json`](../../infra/debezium/config/demo-postgres.json)) переиспользует `demo_slot`, слушает `demo_publication`, делает initial snapshot и stream-ит Avro payloads с Schema Registry metadata. Deletes остаются update-style events, потому что `tombstones.on.delete` is `false`; переключайте на `true`, если нужны Kafka tombstones для log compaction.

### Kafka and Schema Registry

CDC topics имеют формат `demo.public.<table>`. Каждый record несет partition, offset, schema ID и decoded payload, чтобы provenance можно было записать в Bronze. Internal topics (`schema-changes.demo`, `my_connect_*`) хранят schema history и connector state.

### Orchestration and Bronze Writes

Airflow DAG ([`infra/airflow/dags/bronze_events_kafka_stream_dag.py`](../../infra/airflow/dags/bronze_events_kafka_stream_dag.py)) запускает два пути:

- **`bounded_ingest`** - batches generator topics в общую table `iceberg.bronze.raw_events`. Job находится в [`infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py`](../../infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py). Generator feeds уже смешивают несколько event types, поэтому одна Bronze table хранит raw bus.
- **`ingest_<table>` tasks** - по одной task на CDC topic через [`infra/airflow/processing/spark/jobs/bronze_cdc_stream.py`](../../infra/airflow/processing/spark/jobs/bronze_cdc_stream.py). Каждая job читает один topic через `AvailableNow`, пишет в отдельную Iceberg table и сохраняет `event_source`, `event_time`, schema IDs, payload sizes, partitions и offsets.

CDC tasks явно перечислены в `CDC_STREAMS` внутри DAG ([`infra/airflow/dags/bronze_events_kafka_stream_dag.py`](../../infra/airflow/dags/bronze_events_kafka_stream_dag.py#L69)). Чтобы onboard-ить новую Postgres table, добавьте ее topic, target table и checkpoint path туда, чтобы Airflow scheduled matching ingest job.

#### Example: `iceberg.bronze.demo_public_warehouse_inventory`

CDC table для `demo.public.warehouse_inventory` использует общую Bronze schema: `event_source`, `event_time`, `schema_id`, `payload_size`, `json_payload`, `partition`, `offset`. Payload хранит полный Debezium envelope, чтобы можно было replay, reprocess или audit каждое изменение без повторного Avro decoding. Реальный update выглядит так:

```json
{"before":null,"after":{"warehouse_id":"WH002","product_id":"P000040","qty":598,"reserved_qty":22,"updated_at":"2025-09-26T07:33:47.178366Z"},"source":{"version":"3.0.0.Final","connector":"postgresql","name":"demo","ts_ms":1758872027178,"snapshot":"false","db":"demo","sequence":"[\"1152784920\",\"1152784976\"]","ts_us":1758872027178519,"ts_ns":1758872027178519000,"schema":"public","table":"warehouse_inventory","txId":2460848,"lsn":1152784976,"xmin":null},"transaction":null,"op":"u","ts_ms":1758872027457,"ts_us":1758872027457782,"ts_ns":1758872027457782333}
```

- `event_source` - Kafka topic (`demo.public.warehouse_inventory`), поэтому lineage к publication очевиден.
- `event_time` - момент, когда Kafka observed event; `json_payload.ts_*` сохраняют исходные Debezium timestamps.
- `json_payload.after` содержит row image, который чаще всего читают analytics teams; `json_payload.before` появляется на deletes/updates и нужен для SCD или audit trails.
- `json_payload.source.lsn` отражает replay position slot; используйте его, чтобы подтверждать progress ingestion и сопоставлять gaps с Postgres logs.
- Offsets и partitions остаются рядом с payload, поэтому можно re-seek конкретную Kafka record при rebuild Bronze.

Каждая ingest task ведет к Iceberg maintenance step: optimize, expire snapshots, remove orphans через Trino. Shared Spark helpers лежат в [`infra/airflow/processing/spark/jobs/spark_utils.py`](../../infra/airflow/processing/spark/jobs/spark_utils.py). CDC streams разделены per table, поэтому каждый Iceberg dataset mirrors one OLTP table, что удобно для deterministic upserts и history tracking.

---

## Operating Checklist

- **Start services** - `docker compose --profile core up -d` поднимает Postgres, Kafka, Schema Registry, Debezium, Spark, Trino и зависимые сервисы.
- **Bring up Airflow** - `docker compose --profile airflow up -d`. Откройте `http://localhost:8085`, чтобы monitor runs.
- **Verify connector** - `curl http://localhost:8083/connectors/demo-postgres/status` должен показать `RUNNING`.
- **Seed changes** - `docker compose --profile datagen up -d data-generator` или direct inserts в Postgres.
- **Inspect topics** - `docker compose exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --list` и проверьте `demo.public.*` topics.
- **Trigger the Bronze DAG** - запустите `bronze_events_kafka_stream` в Airflow и дождитесь success для `bounded_ingest` и per-table CDC tasks.
- **Check Iceberg tables** - в Trino выполните `SELECT * FROM iceberg.bronze.demo_public_users LIMIT 5;`, чтобы подтвердить payloads и provenance.

---

## Troubleshooting

- **Only heartbeat topic** - проверьте, что в tables есть rows. Snapshot mode создает topics только при наличии данных; logs могут содержать “no changes will be captured”, если include lists неверны.
- **WAL retention warnings** - увеличьте `wal_keep_size` или подтвердите, что Debezium running; slots держат WAL, пока consumption не продвинется.
- **Checkpoint cleanup** - остановите data generator; он очищает Kafka topics и MinIO checkpoints, чтобы повторные runs стартовали clean ([`infra/data-generator/adapters/minio/checkpoints.py`](../../infra/data-generator/adapters/minio/checkpoints.py)).

---

## For Practitioners

<details>
<summary>Key files</summary>

- Postgres init: [`infra/postgres/init-databases.sh`](../../infra/postgres/init-databases.sh)
- Debezium image and launcher: [`infra/debezium/Dockerfile`](../../infra/debezium/Dockerfile), [`infra/debezium/start-with-connectors.sh`](../../infra/debezium/start-with-connectors.sh)
- Debezium connector config: [`infra/debezium/config/demo-postgres.json`](../../infra/debezium/config/demo-postgres.json)
- Airflow DAG: [`infra/airflow/dags/bronze_events_kafka_stream_dag.py`](../../infra/airflow/dags/bronze_events_kafka_stream_dag.py)
- Spark jobs: [`infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py`](../../infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py), [`infra/airflow/processing/spark/jobs/bronze_cdc_stream.py`](../../infra/airflow/processing/spark/jobs/bronze_cdc_stream.py), [`infra/airflow/processing/spark/jobs/spark_utils.py`](../../infra/airflow/processing/spark/jobs/spark_utils.py)
- Checkpoint cleaner: [`infra/data-generator/adapters/minio/checkpoints.py`](../../infra/data-generator/adapters/minio/checkpoints.py)

</details>

---

## Further Reading

- [Bronze как зона ответственности](bronze-is-the-battlefield.md)
- [A Guide to Logical Replication and CDC in PostgreSQL](https://airbyte.com/blog/a-guide-to-logical-replication-and-cdc-in-postgresql)
- [Debezium Postgres connector docs](https://debezium.io/documentation/reference/stable/connectors/postgresql.html)
- Service references: [`infra/postgres/README.md`](../../infra/postgres/README.md), [`infra/debezium/README.md`](../../infra/debezium/README.md)

Data Forge показывает, как retail CDC, Debezium, Iceberg Bronze и ClickHouse/Trino validation собираются в одну воспроизводимую локальную platform.
