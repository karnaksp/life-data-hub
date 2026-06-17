#!/usr/bin/env python3
"""Load LifeHub JSONL landing files into Iceberg medallion tables."""

from __future__ import annotations

import argparse
import logging

from pyspark.sql import DataFrame, SparkSession, functions as F

from spark_utils import build_spark, ensure_iceberg_table


APP_NAME = "lifehub_jsonl_to_iceberg"
LOG = logging.getLogger(__name__)


def read_landing(spark: SparkSession, input_path: str) -> DataFrame:
    raw = spark.read.json(input_path)
    return raw.select(
        F.col("lake_version").cast("string").alias("lake_version"),
        F.col("source_name").cast("string").alias("source_name"),
        F.col("event_type").cast("string").alias("event_type"),
        F.to_timestamp("event_time").alias("event_time"),
        F.to_timestamp("ingested_at").alias("ingested_at"),
        F.col("privacy_class").cast("string").alias("privacy_class"),
        F.to_json("payload").alias("json_payload"),
        F.input_file_name().alias("landing_file"),
        F.current_timestamp().alias("loaded_at"),
    )


def write_table(df: DataFrame, table: str) -> int:
    ensure_iceberg_table(
        df.sparkSession,
        table,
        columns_sql="""
            lake_version STRING,
            source_name STRING,
            event_type STRING,
            event_time TIMESTAMP,
            ingested_at TIMESTAMP,
            privacy_class STRING,
            json_payload STRING,
            landing_file STRING,
            loaded_at TIMESTAMP
        """,
        partition_field="source_name",
    )
    df.writeTo(table).append()
    return df.count()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Landing JSONL path, local or s3a://")
    parser.add_argument("--bronze-table", default="iceberg.bronze.lifehub_events")
    parser.add_argument("--silver-table", default="iceberg.silver.lifehub_events")
    parser.add_argument("--gold-table", default="iceberg.gold.lifehub_decision_events")
    parser.add_argument("--skip-silver", action="store_true")
    parser.add_argument("--skip-gold", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    spark = build_spark(APP_NAME)
    spark.sparkContext.setLogLevel("INFO")
    bronze = read_landing(spark, args.input)
    bronze_count = write_table(bronze, args.bronze_table)
    LOG.info("Wrote %s rows to %s", bronze_count, args.bronze_table)

    if not args.skip_silver:
        silver = bronze.where("event_time IS NOT NULL AND source_name IS NOT NULL AND event_type IS NOT NULL")
        silver_count = write_table(silver, args.silver_table)
        LOG.info("Wrote %s rows to %s", silver_count, args.silver_table)

    if not args.skip_gold:
        gold = bronze.where("source_name = 'daily_context_profile' OR event_type LIKE 'decision_%'")
        gold_count = write_table(gold, args.gold_table)
        LOG.info("Wrote %s rows to %s", gold_count, args.gold_table)


if __name__ == "__main__":
    main()
