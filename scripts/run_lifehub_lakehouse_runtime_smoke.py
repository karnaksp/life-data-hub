#!/usr/bin/env python3
"""Run a real local LifeHub lakehouse smoke through Spark, Iceberg and Trino.

This script is intentionally Docker-based: it proves the LifeHub landing
contract is loadable into Iceberg tables and queryable through the DWH layer.
It uses `.env.example` and fixture data only.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "evidence" / "lifehub-lakehouse-runtime-evidence.md"

COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env.example",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.lakehouse-smoke.yml",
]
CORE_SERVICES = ["postgres", "redis", "minio", "hive-metastore", "clickhouse", "trino"]

SPARK_PACKAGES = ",".join(
    [
        "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.9.2",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
    ]
)

SPARK_CONF = [
    "--conf",
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "--conf",
    "spark.sql.defaultCatalog=iceberg",
    "--conf",
    "spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog",
    "--conf",
    "spark.sql.catalog.iceberg.type=hive",
    "--conf",
    "spark.sql.catalog.iceberg.uri=thrift://hive-metastore:9083",
    "--conf",
    "spark.sql.catalog.iceberg.warehouse=s3a://iceberg/warehouse",
    "--conf",
    "spark.jars.ivy=/home/spark/.ivy2",
    "--conf",
    "spark.hadoop.fs.s3a.endpoint=http://minio:9000",
    "--conf",
    "spark.hadoop.fs.s3a.path.style.access=true",
    "--conf",
    "spark.hadoop.fs.s3a.connection.ssl.enabled=false",
    "--conf",
    "spark.hadoop.fs.s3a.aws.credentials.provider=org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    "--conf",
    "spark.hadoop.fs.s3a.access.key=minio",
    "--conf",
    "spark.hadoop.fs.s3a.secret.key=minio123",
]

TRINO_QUERIES = {
    "bronze_by_source": """
        SELECT source_name, count(*) AS rows
        FROM iceberg.bronze.lifehub_events
        GROUP BY source_name
        ORDER BY source_name
    """,
    "silver_valid_rows": """
        SELECT count(*) AS rows
        FROM iceberg.silver.lifehub_events
        WHERE source_name IS NOT NULL
          AND event_type IS NOT NULL
          AND event_time IS NOT NULL
    """,
    "gold_decision_rows": """
        SELECT event_type, count(*) AS rows
        FROM iceberg.gold.lifehub_decision_events
        GROUP BY event_type
        ORDER BY event_type
    """,
    "forbidden_payload_rows": """
        SELECT count(*) AS rows
        FROM iceberg.bronze.lifehub_events
        WHERE regexp_like(json_payload, '(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|pain_text|raw_diary_notes|raw_sleep_notes|home_address)')
    """,
}


def run(cmd: list[str], *, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output_lines: list[str] = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            output_lines.append(line)
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise

    stdout = "".join(output_lines)
    if check and return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd, output=stdout, stderr="")
    return subprocess.CompletedProcess(cmd, return_code, stdout, "")


def trino_query(sql: str) -> str:
    result = run(
        COMPOSE
        + [
            "exec",
            "-T",
            "trino",
            "trino",
            "--output-format",
            "CSV_HEADER",
            "--execute",
            " ".join(sql.split()),
        ],
        timeout=180,
    )
    return result.stdout.strip()


def render_evidence(query_outputs: dict[str, str]) -> str:
    sections = "\n\n".join(
        f"## {name}\n\n```csv\n{output or 'no rows'}\n```"
        for name, output in query_outputs.items()
    )
    return f"""# LifeHub Lakehouse Runtime Evidence

Generated at: `{datetime.now(timezone.utc).isoformat()}`

This evidence is produced by `scripts/run_lifehub_lakehouse_runtime_smoke.py`.
It uses fixture data, loads LifeHub landing JSONL with Spark into Iceberg
Bronze/Silver/Gold tables, and queries those tables through Trino.

{sections}
"""


def main() -> int:
    run(["make", "lifehub-lake-export-fixture"], timeout=300)
    run(COMPOSE + ["--profile", "core", "up", "-d", "--build", *CORE_SERVICES], timeout=1200)
    run(COMPOSE + ["build", "spark-master"], timeout=1200)
    run(
        COMPOSE
        + [
            "--profile",
            "core",
            "run",
            "--rm",
            "--no-deps",
            "spark-master",
            "/opt/spark/bin/spark-submit",
            "--master",
            "local[2]",
            "--packages",
            SPARK_PACKAGES,
            *SPARK_CONF,
            "/opt/spark/jobs/lifehub_jsonl_to_iceberg.py",
            "--input",
            "/workspace/tmp/lake/lifehub/landing/*/dt=*/events.jsonl",
            "--bronze-table",
            "iceberg.bronze.lifehub_events",
            "--silver-table",
            "iceberg.silver.lifehub_events",
            "--gold-table",
            "iceberg.gold.lifehub_decision_events",
        ],
        timeout=1200,
    )
    outputs = {name: trino_query(sql) for name, sql in TRINO_QUERIES.items()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_evidence(outputs), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    if '"0"' not in outputs["forbidden_payload_rows"] and "\n0" not in outputs["forbidden_payload_rows"]:
        print(outputs["forbidden_payload_rows"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
