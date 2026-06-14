# 🔥 Data Forge — Data Engineering Playground

Локальная площадка для современного data stack. Здесь можно поднять основные компоненты реальной data platform и отработать end-to-end workflows без облачных счетов и production-риска.

> Portfolio Case Study: этот репозиторий — fork, который я использую как Data Engineering lab. Я превращаю его в applied retail CDC/lakehouse case study с воспроизводимым runbook, validation SQL и явным описанием моего вклада. См. [CASE_STUDY.md](CASE_STUDY.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2.0+-blue.svg)](https://docs.docker.com/compose/)

Вместо того чтобы только читать про "data lakes" и "lakehouses", здесь их можно реально запустить. Это инженерный тренажёр для data engineers: локально, прозрачно и без риска сломать production.

---

## 🎯 Что внутри

Data Forge включает полный современный data stack на привычных индустриальных инструментах:

### 🗄️ Storage & Catalog
- **MinIO** → S3-compatible object storage для data lakes
- **Hive Metastore** → централизованный metadata catalog для таблиц и схем

### ⚡ Compute Engines
- **Trino** → interactive SQL query engine для federated analytics
- **Apache Spark** → distributed processing для batch и streaming workloads

### 🌊 Streaming & CDC
- **Apache Kafka** → event streaming platform
- **Schema Registry** → schema evolution and compatibility
- **Debezium** → change data capture из баз данных

### 🗃️ Databases
- **PostgreSQL** → primary OLTP database (source system)
- **ClickHouse** → columnar analytics database (sink)

### 🔄 Orchestration
- **Apache Airflow 3** → workflow orchestration

### 📊 Visualization & Exploration
- **Apache Superset** → modern BI и data visualization
- **JupyterLab** → interactive data science environment

### 🏭 Data Generation
- **Data Generator** → реалистичный retail data producer для Kafka topics и Postgres tables (см. [infra/data-generator/README.md](infra/data-generator/README.md))

---

## 🚀 Быстрый старт

### Требования

- **Docker** 20.10+ 
- **Docker Compose** 2.0+
- **8GB+ RAM** рекомендуется
- **20GB+ disk space** для всех сервисов

### 1. Склонировать и настроить

```bash
git clone https://github.com/karnaksp/data-forge.git
cd data-forge

# Copy environment template
cp .env.example .env

# Review and adjust settings
nano .env
```

### 2. Запустить core services

```bash
# Start essential data stack (MinIO, Postgres, ClickHouse, etc.)
docker compose --profile core up -d

# Wait for services to be healthy
docker compose ps
```

### 3. Добавить compute и orchestration

```bash
# Add Airflow for orchestration
docker compose --profile airflow up -d

# Add exploration tools
docker compose --profile explore up -d

# Add realistic data generation
docker compose --profile datagen up -d
```

### 4. Открыть сервисы

| Service | URL | Default Login |
|---------|-----|---------------|
|**Kafka UI**|http://localhost:8082 |No auth|
| **Airflow** | http://localhost:8085 | `airflow` / `airflow` |
| **Superset** | http://localhost:8089 | `admin` / `admin` |
| **MinIO Console** | http://localhost:9001 | `minio` / `minio123` |
| **Trino** | http://localhost:8080 | No auth |

---

## 🧩 Architecture profiles

Подробности по профилям и командам — в [docs/architecture.md](docs/architecture.md).

## 🧪 Portfolio case study

Applied scenario: **retail CDC to lakehouse and realtime analytics**.

- source tables: `users`, `products`, `warehouses`, `suppliers`, `inventory`, `warehouse_inventory`, `customer_segments`, `product_suppliers`;
- business-event topics: `orders.v1`, `payments.v1`, `shipments.v1`, `inventory-changes.v1`, `customer-interactions.v1`;
- CDC topics: `demo.public.*` из Postgres через Debezium;
- validation: source counts, duplicate keys, referential integrity, Kafka topic inventory, ClickHouse ingestion wiring и analytical query examples.

Начинать лучше отсюда:

- [CASE_STUDY.md](CASE_STUDY.md) - scope fork, мой вклад и acceptance criteria.
- [docs/retail-cdc-runbook.md](docs/retail-cdc-runbook.md) - воспроизводимый локальный сценарий.
- [sql/validation/postgres_retail_seed_checks.sql](sql/validation/postgres_retail_seed_checks.sql) - source-system data quality checks.
- [sql/validation/kafka_topic_inventory.md](sql/validation/kafka_topic_inventory.md) - streaming validation checklist.
- [sql/validation/clickhouse_ingestion_contract.md](sql/validation/clickhouse_ingestion_contract.md) - Kafka-to-ClickHouse ingestion contract и runtime smoke commands.
- [docs/evidence/retail-cdc-evidence.md](docs/evidence/retail-cdc-evidence.md) - сгенерированный static evidence bundle для удобной reviewer-проверки.
- [sql/examples/](sql/examples/) - SQL-примеры для Postgres, ClickHouse и Trino.

---

## 📚 Learning path

Короткая воспроизводимая последовательность notebooks описана в [docs/learning-path.md](docs/learning-path.md).

---

## 🛠️ Разработка

Project layout, env vars и советы по изменениям — в [docs/development.md](docs/development.md).

Portfolio quality checks:

```bash
python scripts/validate_project.py
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml config --quiet
```

---

## 🤝 Contributing

- Открывайте issues или PRs с понятным scope и шагами проверки.
- Соблюдайте docs style: [docs/guidelines.md](docs/guidelines.md).
- Проверяйте изменения через релевантные compose profiles.

---

## 📄 License

MIT — см. `LICENSE`. Лицензии сторонних сервисов указаны в их документации.

---

## 🌟 Resources

- Docs entrypoint: [docs/](docs/)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Learning Path: [docs/learning-path.md](docs/learning-path.md)
- Development: [docs/development.md](docs/development.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Service docs index: [docs/services.md](docs/services.md)
- Guidelines (please read): [docs/guidelines.md](docs/guidelines.md)

Service docs (direct links):
- MinIO: [infra/minio/README.md](infra/minio/README.md)
- Trino: [infra/trino/README.md](infra/trino/README.md)
- Spark: [infra/spark/README.md](infra/spark/README.md)
- Airflow: [infra/airflow/README.md](infra/airflow/README.md)
- ClickHouse: [infra/clickhouse/README.md](infra/clickhouse/README.md)
- Kafka: [infra/kafka/README.md](infra/kafka/README.md)
- Schema Registry: [infra/schema-registry/README.md](infra/schema-registry/README.md)
- Hive Metastore: [infra/hive-metastore/README.md](infra/hive-metastore/README.md)
- JupyterLab: [infra/jupyterlab/README.md](infra/jupyterlab/README.md)
- Superset: [infra/superset/README.md](infra/superset/README.md)
- Postgres: [infra/postgres/README.md](infra/postgres/README.md)
- Redis: [infra/redis/README.md](infra/redis/README.md)
- Debezium: [infra/debezium/README.md](infra/debezium/README.md)
- Kafka UI: [infra/kafka-ui/README.md](infra/kafka-ui/README.md)

---

## 🙏 Acknowledgments

Проект опирается на open-source communities: Apache (Airflow, Spark, Kafka, Trino), ClickHouse, MinIO, Jupyter, Superset, Redis.

---

*Название "Forge" подходит проекту: это место, где сырой материал (data) превращается во что-то структурированное и полезное, а разработчик оттачивает ремесло.* ⚒️

---

## 🏭 Data Generation

Usage и configuration описаны в [infra/data-generator/README.md](infra/data-generator/README.md).
