# ⚙️ Development Setup

Why: Set up, extend, and debug the stack efficiently.

## 🚀 How

- Clone and configure env:
  - `git clone https://github.com/fortiql/data-forge.git && cd data-forge`
  - `cp .env.example .env` and adjust to your machine.

- Project structure (high level):
  - [infra/](../infra/) → service configs and Dockerfiles
  - [notebooks/](../notebooks/) → examples and lessons
  - [docs/](./) → documentation
  - [`docker-compose.yml`](../docker-compose.yml) → services and profiles

- Build and run (example):
  - `docker compose --profile core up -d`
  - `docker compose ps` to check health

- Validate the CDC/lakehouse smoke contracts before changing runtime wiring:
  - `python scripts/validate_runtime_contract.py`
  - `python scripts/validate_lifehub_contract.py`
  - `python scripts/validate_project.py`
  - `make lifehub-demo`
  - `docker compose --env-file .env.example config --quiet`
  - `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml config --quiet`

- Environment variables (common):
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  - `POSTGRES_CDC_USER`, `POSTGRES_CDC_PASSWORD`
  - `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DB`
  - `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
  - Airflow/Superset admin credentials

## 📝 Notes

- Keep changes minimal and tested with the compose profiles you affect.
- Keep Compose env names aligned with `infra/data-generator/config.py`; the runtime contract validator checks this without starting containers.
- For docs, follow [guidelines.md](guidelines.md).
- Open an issue for substantial changes or new services.
