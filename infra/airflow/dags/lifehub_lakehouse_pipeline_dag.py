import os

from airflow import DAG
from airflow.datasets import Dataset
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator


default_args = {"owner": "DataForge", "depends_on_past": False, "retries": 1}

WORKSPACE = os.getenv("DATAFORGE_WORKSPACE", "/workspace")
SPARK_JOB_BASE = os.getenv("SPARK_JOB_BASE", "/opt/spark/jobs")
LIFEHUB_ENV = (
    "PYTHONPATH=/workspace/infra/lifehub "
    "LIFEHUB_LOCATIONS=/workspace/config/lifehub/locations.yaml "
    "LIFEHUB_SCORING=/workspace/config/lifehub/scoring.yaml "
    "LIFEHUB_PREFERENCES=/workspace/config/lifehub/preferences.yaml "
    "LIFEHUB_POSTGRES_DSN='host=postgres port=5432 dbname=demo user=admin password=admin' "
    "LIFEHUB_CLICKHOUSE_URL='http://clickhouse:8123/?user=admin&password=admin' "
)
PACKAGES = ",".join(
    [
        "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.9.2",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
    ]
)
BASE_CONF = {
    "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.sql.defaultCatalog": "iceberg",
    "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.iceberg.type": "hive",
    "spark.sql.catalog.iceberg.uri": "thrift://hive-metastore:9083",
    "spark.sql.catalog.iceberg.warehouse": "s3a://iceberg/warehouse",
    "spark.hadoop.fs.s3a.endpoint": "http://minio:9000",
    "spark.hadoop.fs.s3a.path.style.access": "true",
    "spark.hadoop.fs.s3a.connection.ssl.enabled": "false",
    "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    "spark.hadoop.fs.s3a.access.key": os.getenv("MINIO_ROOT_USER", "minio"),
    "spark.hadoop.fs.s3a.secret.key": os.getenv("MINIO_ROOT_PASSWORD", "minio123"),
}


def lifehub_command(command: str) -> str:
    return f"cd {WORKSPACE} && {LIFEHUB_ENV} {command}"


def iceberg_maintenance(table: str, expire_days: str = "7d") -> None:
    import trino

    conn = trino.dbapi.connect(host="trino", port=8080, user="airflow")
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} EXECUTE optimize")
    _ = cur.fetchall()
    cur.execute(f"ALTER TABLE {table} EXECUTE expire_snapshots(retention_threshold => '{expire_days}')")
    _ = cur.fetchall()
    cur.execute(f"ALTER TABLE {table} EXECUTE remove_orphan_files")
    _ = cur.fetchall()


with DAG(
    dag_id="lifehub_lakehouse_pipeline",
    description="Export LifeHub decision signals to lake landing and load Bronze/Silver/Gold Iceberg tables",
    doc_md="""\
        #### LifeHub Lakehouse Pipeline

        This DAG makes LifeHub an extensible data engineering product:

        - exports privacy-safe LifeHub source envelopes to `s3a://iceberg/lifehub/landing`;
        - loads the same JSONL contract into Iceberg Bronze;
        - filters typed valid events into Silver;
        - publishes decision-oriented events into Gold;
        - runs Iceberg maintenance through Trino.

        New real-life sources should be added through `config/lifehub/source_registry.yaml`
        and the same landing JSONL envelope, then ingested by this DAG.
        """,
    start_date=None,
    schedule="30 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["lifehub", "lakehouse", "iceberg", "medallion"],
) as dag:
    export_landing = BashOperator(
        task_id="export_lifehub_landing_jsonl",
        bash_command=lifehub_command(
            "python -m lifehub.cli lake-export "
            "--output-root /workspace/tmp/lake "
            "--fixture /workspace/fixtures/lifehub/open_meteo_clear_day.json "
            "--summary-fixture /workspace/fixtures/lifehub/week_summary.json "
            "--feedback-fixture /workspace/fixtures/lifehub/feedback_profile.json "
            "--metrics-fixture /workspace/fixtures/lifehub/decision_metrics.json "
            "--signal-fixture /workspace/fixtures/lifehub/context_signals.json "
            "--activity-file /workspace/fixtures/lifehub/activity_route_spb_public.gpx "
            "--activity-type skate "
            "--sleep-fixture /workspace/fixtures/lifehub/sleep_quality.json && "
            "python -m lifehub.cli custom-source-import "
            "/workspace/fixtures/lifehub/custom_life_events.json "
            "--source-name custom_life_events "
            "--output-root /workspace/tmp/lake"
        ),
        outlets=[Dataset("file:///workspace/tmp/lake/lifehub/landing/")],
    )

    load_iceberg = SparkSubmitOperator(
        task_id="load_lifehub_jsonl_to_iceberg",
        conn_id="spark_default",
        application=os.path.join(SPARK_JOB_BASE, "lifehub_jsonl_to_iceberg.py"),
        py_files=os.path.join(SPARK_JOB_BASE, "spark_utils.py"),
        packages=PACKAGES,
        conf=BASE_CONF,
        application_args=[
            "--input",
            "/workspace/tmp/lake/lifehub/landing/*/dt=*/events.jsonl",
            "--bronze-table",
            "iceberg.bronze.lifehub_events",
            "--silver-table",
            "iceberg.silver.lifehub_events",
            "--gold-table",
            "iceberg.gold.lifehub_decision_events",
        ],
        verbose=True,
        outlets=[
            Dataset("s3://iceberg/warehouse/bronze.db/lifehub_events/"),
            Dataset("s3://iceberg/warehouse/silver.db/lifehub_events/"),
            Dataset("s3://iceberg/warehouse/gold.db/lifehub_decision_events/"),
        ],
    )

    bronze_maintenance = PythonOperator(
        task_id="iceberg_maintenance_bronze_lifehub_events",
        python_callable=iceberg_maintenance,
        op_kwargs={"table": "iceberg.bronze.lifehub_events"},
    )

    silver_maintenance = PythonOperator(
        task_id="iceberg_maintenance_silver_lifehub_events",
        python_callable=iceberg_maintenance,
        op_kwargs={"table": "iceberg.silver.lifehub_events"},
    )

    gold_maintenance = PythonOperator(
        task_id="iceberg_maintenance_gold_lifehub_decision_events",
        python_callable=iceberg_maintenance,
        op_kwargs={"table": "iceberg.gold.lifehub_decision_events"},
    )

    export_landing >> load_iceberg >> [bronze_maintenance, silver_maintenance, gold_maintenance]
