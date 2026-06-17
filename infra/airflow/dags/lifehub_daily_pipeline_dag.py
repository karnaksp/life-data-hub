import os

from airflow import DAG
from airflow.datasets import Dataset
from airflow.providers.standard.operators.bash import BashOperator


default_args = {"owner": "DataForge", "depends_on_past": False, "retries": 1}

WORKSPACE = os.getenv("DATAFORGE_WORKSPACE", "/workspace")
LIFEHUB_ENV = (
    "PYTHONPATH=/workspace/infra/lifehub "
    "LIFEHUB_LOCATIONS=/workspace/config/lifehub/locations.yaml "
    "LIFEHUB_SCORING=/workspace/config/lifehub/scoring.yaml "
    "LIFEHUB_POSTGRES_DSN='host=postgres port=5432 dbname=demo user=admin password=admin' "
    "LIFEHUB_CLICKHOUSE_URL='http://clickhouse:8123/?user=admin&password=admin' "
)


def lifehub_command(command: str) -> str:
    return f"cd {WORKSPACE} && {LIFEHUB_ENV} {command}"


with DAG(
    dag_id="lifehub_daily_pipeline",
    description="Daily LifeHub public data ingest, scoring, and data quality checks",
    doc_md="""\
        #### LifeHub Daily Pipeline

        Orchestrates the local-only LifeHub domain:

        - fetch Open-Meteo hourly forecast into ClickHouse;
        - sync public OSM/configured spots into Postgres;
        - compute outdoor readiness scores into ClickHouse;
        - run redacted quality checks for operational and analytical tables.

        The DAG does not read or print Telegram secrets. Telegram delivery remains handled
        by the long-running `lifehub-telegram-bot` service.
        """,
    start_date=None,
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["lifehub", "data-quality", "clickhouse", "postgres"],
) as dag:
    weather_ingest = BashOperator(
        task_id="weather_ingest_clickhouse",
        bash_command=lifehub_command("python -m lifehub.cli weather-ingest --write-clickhouse"),
        outlets=[Dataset("clickhouse://analytics/life_weather_hourly")],
    )

    place_sync = BashOperator(
        task_id="place_sync_postgres",
        bash_command=lifehub_command("python -m lifehub.cli place-sync --source auto"),
        outlets=[Dataset("postgres://demo/public/life_spots")],
    )

    score_readiness = BashOperator(
        task_id="recommendation_engine",
        bash_command=lifehub_command("python -m lifehub.cli recommend --write-clickhouse --write-postgres"),
        outlets=[
            Dataset("clickhouse://analytics/life_readiness_scores"),
            Dataset("clickhouse://analytics/life_recommendation_events"),
            Dataset("postgres://demo/public/life_recommendation_events"),
        ],
    )

    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=f"cd {WORKSPACE} && LIFEHUB_QUALITY_DIRECT=1 {LIFEHUB_ENV} python scripts/lifehub_quality_check.py",
    )

    [weather_ingest, place_sync] >> score_readiness >> quality_gate
