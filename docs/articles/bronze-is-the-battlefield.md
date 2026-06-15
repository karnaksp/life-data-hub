# Bronze как зона ответственности: почему data engineers начинают с источника

Не ограничивайтесь downstream tables. Надежный data pipeline начинается там, где события впервые попадают в систему: offsets, schemas, timestamps, payloads и checkpoints должны сохраняться до любых чисток и агрегаций.

Bronze - это raw layer. В нем данные еще не приведены к удобной аналитической форме, но уже сохранены с provenance, достаточным для replay, audit и reprocessing.

---

## The Trap of SQL Modeling

Многие junior data engineers начинают с SQL: читают tables, строят views, моделируют downstream data. Это полезный навык, но если остановиться только на нем, upstream-проблемы становятся невидимыми: потерянный lineage, late data, хрупкие backfills и непонятные gaps.

Как это выглядит на практике:

- вы оптимизируете queries на данных, которые сами не ingest-или, поэтому не можете объяснить gaps, duplicates или странные timestamps;
- deduplication строится на эвристиках вместо offsets и event time, поэтому результаты начинают drift-ить при росте volumes;
- backfill делается ad hoc SQL, потому что исходные offsets и checkpoints неизвестны;
- на вопрос “откуда пришла эта запись и какая schema была на момент ingestion” нет авторитетного ответа.

Почему это бьет по командам:

- debugging замедляется, потому что никто не владеет первым километром данных;
- lineage неполный, доверие к витринам падает;
- reprocessing становится рискованным и дорогим без authoritative checkpoints.

Как выйти из ловушки:

- начинайте с источника: забирайте raw events из Kafka / CDC вместе с offsets, partitions, schema identifiers и event time;
- пишите Bronze table так, чтобы provenance fields сохранялись без потерь;
- используйте durable checkpoint для ingestion jobs и относитесь к нему как к журналу истины;
- учите downstream models читать из Bronze или из curated Silver, который построен напрямую на Bronze.

Практическая data engineering работа начинается на шаг раньше SQL-моделей: на raw ingestion layer.

---

## The Question

Задайте себе простой вопрос: “Я действительно понимаю, откуда берутся данные, с которыми работаю каждый день?”

- Event streams: clicks, payments, shipments?
- Operational databases: CDC feeds?
- Third-party APIs: ads, SaaS, partners?

Если вы впервые видите данные уже в transformed tables, вы не контролируете их origins.

---

## What Data Forge Validates

[Data Forge](../../README.md) - локальный modern data stack, который можно поднять на laptop: Spark, Trino, ClickHouse, Iceberg, Kafka, Airflow, MinIO через Docker Compose. Его задача не в том, чтобы “показать набор инструментов”, а в том, чтобы проверять реальные ingestion flows: retail events, CDC lineage, Bronze-to-analytics contracts и runtime evidence.

Один из ключевых компонентов - data generator. Он создает live retail stream: orders, payments, shipments, customers и пишет события в Kafka.

- Data Generator: [infra/data-generator/README.md](../../infra/data-generator/README.md)

Эта статья объясняет, зачем нужен Bronze layer и как Data Forge проверяет bounded ingestion pattern.

---

## Medallion Logic

- Bronze: raw events with offsets, schema IDs, timestamps, payloads. Forensic truth.
- Silver: deduplicated, validated, enriched data. Analyst-friendly layer.
- Gold: metrics/models for decisions.

Без Bronze слой Silver строится на предположениях; без Silver слой Gold легко вводит в заблуждение.

---

## What Is Bronze

Одна Bronze row для teaching-oriented JSON payload может выглядеть так:

```text
(event_source=orders.v1,
 partition=3,
 offset=12847,
 schema_id=17,
 event_time=2025-09-15 14:22:00,
 payload_size=512,
 json_payload='{...}')
```

Каждое поле - часть provenance. Если нужно replay, reprocess или debug, Bronze остается logbook.

### Почему события стоит копировать в lake

Нормальный вопрос от non technical stakeholder: зачем дублировать events в lake, если они уже есть в Kafka или source systems. Короткий ответ: reliability и independence for analytics.

- Durability beyond retention: Kafka - conveyor belt с ограниченным retention; lake хранит историю дольше.
- Replay and reproducibility: полная история events плюс checkpoints позволяют пересобрать tables, исправить bugs и audit-ить decisions.
- Decoupling from producers: analytics не зависит от producer SLAs, outages или schema churn.
- Governance and access control: проще централизованно применять PII policies, masking и lineage.
- Cost and performance: columnar tables и snapshots дешевле и безопаснее для аналитики, чем постоянная нагрузка на operational systems.
- Multi team enablement: новые use cases могут стартовать от Bronze без изменения producers.

В этом repo correctness держится на двух механизмах:

- Checkpoints: `--checkpoint` задает authoritative offset state для каждого run.
- ACID writes: Iceberg commits атомарны. Вместе с offsets это дает exactly-once ingestion.

Storage не должен расти бесконтрольно. DAG maintenance выполняет compact, optimize и expire snapshots, чтобы Bronze оставался управляемым.

---

## Bounded Streaming Orchestration

Airflow часто воспринимается как batch orchestrator, а Spark Structured Streaming - как always-on streaming engine. `availableNow` объединяет эти режимы: streaming query обрабатывает все доступные на текущий момент данные, продвигает state/watermarks, commits и останавливается. Infinite stream превращается в bounded catch-up run.

В этом pattern Airflow владеет lifecycle: schedule, retries, observability. Spark отвечает за streaming correctness: offsets, watermarks, exactly-once writes. Checkpoint переносит continuity в следующий run.

Важно: `availableNow` не равен обычному batch job. Это streaming query с checkpoints и streaming semantics, но он завершается после catch-up.

### Как это работает в repo

- Airflow запускает bounded Spark Structured Streaming job через `SparkSubmitOperator` с `trigger(availableNow=True)`.
- Job читает Kafka с `startingOffsets` и `maxOffsetsPerTrigger`, чтобы контролировать объем catch-up.
- Offsets и streaming state лежат в настроенном `checkpointLocation` в S3/MinIO.
- Writes попадают в Iceberg как atomic commits. На retry Spark продолжает с последнего успешного offset и Iceberg snapshot.

Key DAG params:

- `topics`: `orders.v1,payments.v1,shipments.v1,inventory-changes.v1,customer-interactions.v1`
- `checkpoint`: `s3a://checkpoints/spark/iceberg/bronze/raw_events`
- `starting_offsets`: `latest` или `earliest` для backfills
- `batch_size`: maps to `maxOffsetsPerTrigger`
- `table`: `iceberg.bronze.raw_events`

### Что это дает

- Bounded runs со streaming semantics: каждый run забирает “новое”, commits и останавливается.
- Offset-driven correctness: Kafka offsets в checkpoints, Iceberg ACID snapshots на записи.
- Predictable late data handling: watermarks/TTL живут между runs.
- Stateful logic survives across runs: checkpoint хранит state для joins/aggregations.
- Operational fit: backpressure через `batch_size`, простые retries, capacity scales per run.

### Replay and backfill

- Full rebuild: поставьте `starting_offsets=earliest` и пишите в fresh `checkpoint` path.
- Targeted catch-up: запускайте AvailableNow повторно, пока offsets/time range не догонятся; затем возвращайтесь к `latest`.
- Idempotency: offsets + Iceberg commits authoritative; reruns не должны дублировать rows.

### Почему это может казаться странным

- Airflow запускает и останавливает job, что похоже на batch. Сам job остается streaming query с checkpoints и watermarks.
- Always-on cluster не нужен. Capacity используется per run, а continuity хранится в checkpoint.
- Recovery делается rerun-ом; offsets и Iceberg snapshots защищают от duplicates и gaps.

### Почему не только batch и не always-on

- Classic batch: offsets, overlaps и idempotency приходится вести вручную.
- Always-on streaming: хорош для sub-second SLAs, но требует 24/7 resources и ops.
- AvailableNow: streaming correctness без 24/7 cluster; удобно для hourly Bronze ingestion.

### Common pitfalls

- Удаление checkpoints ломает replay guarantees. Version/rotate intentionally.
- Schema changes могут требовать новый checkpoint path; migrations нужно планировать.
- Не обходите Iceberg прямой записью files, иначе теряется ACID lineage.

---

## Architecture

Для общего обзора services и profiles см. [docs/architecture.md](../../docs/architecture.md).

Markdown diagram:

```text
+------------------+        Avro events         +--------+
| Data Generator   | ----------------------->   | Kafka  |
+------------------+                            +--------+
                                                ^
                         schemas                |
+------------------+  <-------------------------+
| Schema Registry  |
+------------------+


+------------------+      triggers       +-----------------------------------+
| Airflow (DAG)    | ------------------> | Spark Structured Streaming         |
| bronze_events... |                     | Trigger: AvailableNow              |
+------------------+                     +-----------------------------------+
                                                |
                                   append writes (exactly once)
                                                v
                                 +-----------------------------+
                                 | Iceberg (Bronze tables)     |
                                 +-----------------------------+
                                                |
                                  S3 object storage and paths
                                                v
                                 +-----------------------------+
                                 | MinIO                       |
                                 +-----------------------------+
                                                ^
                         checkpointLocation     |
                         s3a://checkpoints/...  |
                                                |
                                 +-----------------------------+
                                 | Checkpoints                 |
                                 +-----------------------------+


+--------+       maintenance + SQL          +-----------------------------+
| Trino  | --------------------------------> Iceberg Catalog & Tables     |
+--------+                                  (OPTIMIZE, EXPIRE, ORPHANS)   |
                                            +-----------------------------+
```

## What's Next

Чтобы связать Bronze mindset с CDC, переходите к [Bronze Needs CDC](cdc-for-bronze.md): там разобраны replication slots, publication `demo.public.*`, Debezium и landing в Iceberg.

---

## Step 1: Boot the Local Stack

```bash
# Clone and configure
git clone https://github.com/fortiql/data-forge.git
cd data-forge && cp .env.example .env

# Start core services (MinIO, Trino, Spark, Kafka, etc.)
docker compose --profile core up -d

# Orchestration (Airflow)
docker compose --profile airflow up -d

# Live retail stream (Kafka + Postgres)
docker compose --profile datagen up -d
```

После этого идут events: orders, payments, shipments, customer interactions.

- Quick start and ports: [README.md](../../README.md)
- Kafka topics and config: [infra/data-generator/README.md](../../infra/data-generator/README.md)

---

## Step 2: Orchestrate with Airflow

- Open Airflow: http://localhost:8085
- DAG: `bronze_events_kafka_stream`
- Path: [infra/airflow/dags/bronze_events_kafka_stream_dag.py](../../infra/airflow/dags/bronze_events_kafka_stream_dag.py)

Key pieces:

```python
with DAG(
    dag_id="bronze_events_kafka_stream",
    description="Manage Bronze raw_events via streaming from Kafka",
    params={
        "topics": ["orders.v1","payments.v1","shipments.v1","inventory-changes.v1","customer-interactions.v1"],
        "batch_size": 10000,
        "checkpoint": "s3a://checkpoints/spark/iceberg/bronze/raw_events",
        "starting_offsets": "latest",
        "table": "iceberg.bronze.raw_events",
        "expire_days": "7d",
    },
):
    bounded_ingest = SparkSubmitOperator(
        application="/opt/spark/jobs/bronze_events_kafka_stream.py",
        conf={
            "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "spark.sql.defaultCatalog": "iceberg",
            # ... S3/MinIO + Iceberg + Kafka
        },
        application_args=["--topics","{{ params.topics | join(',') }}",
                          "--batch-size","{{ params.batch_size }}",
                          "--checkpoint","{{ params.checkpoint }}",
                          "--starting-offsets","{{ params.starting_offsets }}",
                          "--table","{{ params.table }}"],
    )
```

После ingestion DAG запускает Iceberg maintenance: `OPTIMIZE`, `EXPIRE_SNAPSHOTS`, `REMOVE_ORPHANS` через Trino.

---

## Step 3: The Spark Job

Path: [infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py](../../infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py)

Job читает Kafka с AvailableNow, извлекает provenance и пишет exactly-once в Iceberg:

```python
src = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", kafka_bootstrap)
    .option("subscribe", topics)
    .option("startingOffsets", starting_offsets)
    .option("maxOffsetsPerTrigger", str(batch_size))
    .option("failOnDataLoss", "false")
    .load().withWatermark("timestamp", "1 minute")
)

ordered = src.select(
    F.col("topic").alias("event_source"),
    F.col("timestamp").alias("event_time"),
    F.col("partition"),
    F.col("offset"),
    F.col("value"),
).withColumn(
    "schema_id",
    F.when(F.length("value") >= 5,
           F.conv(F.hex(F.expr("substring(value, 2, 4)")), 16, 10).cast("int"))
     .otherwise(F.lit(None).cast("int"))
).withColumn(
    "payload_size",
    F.when(F.col("value").isNotNull(), F.length("value") - F.lit(5))
     .otherwise(F.lit(None))
).drop("value")

# Exactly-once to Iceberg with AvailableNow
(
  ordered.writeStream.format("iceberg")
  .option("path", table)
  .option("checkpointLocation", checkpoint)
  .outputMode("append")
  .trigger(availableNow=True)
  .start()
  .awaitTermination()
)
```

Checkpoint - authoritative resume state. Удалите его, и exactly-once resumption потеряется. Для replay используйте fresh checkpoint и rebuild table или пишите в new table from earliest.

Production best practice vs demo note:

- Production best practice: хранить byte-for-byte copy Kafka value с provenance metadata: topic, partition, offset, schema_id, event_time. Не трансформировать payload на ingestion step.
  - Reproducibility: можно rebuild downstream layers после decoding bugs или schema changes.
  - Auditability: есть точная запись полученного события.
  - Flexibility: future re-decoding для analytics или ML не требует повторного чтения producers.
- Demo note: для exploration repo раскрывает `json_payload`, decoded from Avro, чтобы быстро inspect/query через Trino или Superset.

---

## Step 4: Watch the Flow

Подключите SQL client, например DBeaver, к Trino (`http://localhost:8080`) и выполните:

```sql
SELECT *
FROM iceberg.bronze.raw_events
ORDER BY event_time DESC
LIMIT 20;
```

Каждая row связана с Kafka offset и partition.

---

## When Not to Use This Pattern

- <1s latency fraud detection
- High-volume ad-tech clickstreams: millions/sec
- Always-on pipelines, где bounded catch-up unacceptable

Для таких случаев лучше подходят Flink, always-on Spark или dedicated stream processor.

---

## Step 5: Validate in Notebooks

Откройте JupyterLab (`docker compose --profile explore up -d`, затем http://localhost:8888) и пройдите notebooks:

- [Streaming Fundamentals: checkpoints, offsets, Avro wire format](../../notebooks/lessons/streaming/streaming-fundamentals-lesson.ipynb)
- [Multi-Topic Streaming: schema metadata, unified checkpoints](../../notebooks/lessons/streaming/multi-topic-streaming-lesson.ipynb)
- [Bronze on Iceberg: time travel, snapshot cleanup](../../notebooks/lessons/streaming/bronze-layer-iceberg-example.ipynb)

Они помогают проверить assumptions руками: offsets, checkpoints, Avro wire format, Iceberg snapshots и cleanup.

---

## Failure Lesson

Представьте Kafka -> Spark ingestion job, где offsets лежат не в checkpoints, а в fragile side table или вообще нигде.

Airflow DAG настроен с 0 retries, чтобы “избежать duplicates”. Кто-то нажимает Clear Task в UI. Spark reruns, перечитывает те же offsets и вставляет сотни миллионов rows повторно. Команда тратит дни на cleanup.

**Offsets belong in checkpoints, not spreadsheets.** С AvailableNow reruns и retries безопаснее: Spark продолжает с сохраненного state, а Bronze остается clean.

---

## Operational Discipline

- Checkpoints are sacred. Version them. Don’t casually delete.
- Maintenance is daily discipline. Run `OPTIMIZE` and `EXPIRE SNAPSHOTS`.
- Observability is required. Emit metrics: offsets caught, rows written, batch duration.

## Cleanup After Experiments

После экспериментов избегайте accidental double-appends: остановите generator, очистите table и checkpoint.

- Stop the data generator

```bash
docker compose stop data-generator
```

- Drop the Bronze table

Run in any Trino client:

```sql
DROP TABLE IF EXISTS iceberg.bronze.raw_events;
```

- Remove the checkpoint prefix in MinIO

Use MinIO Console at http://localhost:9001 and delete:

```text
checkpoints/spark/iceberg/bronze/raw_events/
```

---

## Extensible Ingestion Reference

Data Forge - локальная reference-платформа, которую можно расширять под другие ingestion contracts.

- Нужно сравнить Flink с Spark AvailableNow? Добавьте отдельный profile и одинаковые evidence checks.
- Нужен Delta вместо Iceberg? Добавьте параллельный sink и сравните maintenance semantics.
- Видите более простой DAG? Оформите PR с теми же validation guarantees.

Start here: [Data Forge repo](../../README.md)

---

## What’s Next

- Part 1.1: [Bronze Needs CDC](cdc-for-bronze.md) - change data capture из Postgres в Kafka и Bronze через Debezium, schema evolution, delete tombstones и replay strategy.
- Part 2: Silver - cleaning, dedupe, shaping raw events.
- Part 3: Gold - metrics and models in ClickHouse.

Запустите DAG, проверьте Trino, посмотрите flow и затем адаптируйте topics, sinks и maintenance policies под свои ingestion requirements.

---

This article is part of the [Data Forge](https://github.com/fortiql/data-forge) project.  
> Published also on Medium: [link](https://medium.com/@thedatainsight/bronze-is-the-battlefield-why-real-data-engineers-start-at-the-source-6eaa16730f0a)
