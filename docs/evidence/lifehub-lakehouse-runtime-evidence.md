# LifeHub Lakehouse Runtime Evidence

Generated at: `2026-06-17T11:19:21.948407+00:00`

This evidence is produced by `scripts/run_lifehub_lakehouse_runtime_smoke.py`.
It uses fixture data, loads LifeHub landing JSONL with Spark into Iceberg
Bronze/Silver/Gold tables, and queries those tables through Trino.

## bronze_by_source

```csv
"source_name","rows"
"activity_diary","1"
"activity_files","1"
"context_signals","3"
"custom_life_events","2"
"daily_context_profile","5"
"decision_feedback","1"
"sleep_quality","2"
"weather_forecast","112"
```

## silver_valid_rows

```csv
"rows"
"127"
```

## gold_decision_rows

```csv
"event_type","rows"
"daily_context_profile","1"
"decision_metrics_7d","1"
"recommendation","4"
```

## forbidden_payload_rows

```csv
"rows"
"0"
```
