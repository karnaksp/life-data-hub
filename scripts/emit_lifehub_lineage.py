#!/usr/bin/env python3
"""Emit a redacted OpenLineage-compatible event for the LifeHub pipeline."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "lifehub-openlineage-event.json"


def dataset(namespace: str, name: str) -> dict:
    return {"namespace": namespace, "name": name}


def build_event() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "eventType": "COMPLETE",
        "eventTime": now,
        "run": {
            "runId": str(uuid.uuid4()),
            "facets": {
                "dataForge": {
                    "_producer": "https://github.com/karnaksp/data-forge",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/BaseFacet.json",
                    "domain": "lifehub",
                    "privacy": "local_only",
                    "redacted": True,
                }
            },
        },
        "job": {
            "namespace": "data-forge.local",
            "name": "lifehub_daily_pipeline",
        },
        "inputs": [
            dataset("https://api.open-meteo.com", "forecast"),
            dataset("https://overpass-api.de", "public_spots"),
            dataset("postgres://demo/public", "life_activity_log"),
            dataset("postgres://demo/public", "life_decision_feedback"),
            dataset("fixture://lifehub", "context_signals.json"),
            dataset("config://lifehub", "locations.yaml"),
            dataset("config://lifehub", "scoring.yaml"),
        ],
        "outputs": [
            dataset("clickhouse://analytics", "life_weather_hourly"),
            dataset("postgres://demo/public", "life_spots"),
            dataset("clickhouse://analytics", "life_readiness_scores"),
            dataset("postgres://demo/public", "life_recommendation_events"),
            dataset("clickhouse://analytics", "life_recommendation_events"),
            dataset("clickhouse://analytics", "life_decision_feedback_events"),
            dataset("postgres://demo/public", "life_signal_events"),
            dataset("clickhouse://analytics", "life_signal_events"),
            dataset("clickhouse://analytics", "life_latest_readiness_v"),
            dataset("clickhouse://analytics", "life_location_weather_daily_v"),
            dataset("clickhouse://analytics", "life_activity_daily_v"),
            dataset("clickhouse://analytics", "life_recommendation_daily_v"),
            dataset("clickhouse://analytics", "life_decision_feedback_daily_v"),
            dataset("clickhouse://analytics", "life_useful_decision_days_v"),
            dataset("clickhouse://analytics", "life_signal_daily_v"),
        ],
        "producer": "https://github.com/OpenLineage/OpenLineage/tree/main/spec",
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_event(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
