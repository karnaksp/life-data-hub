"""Start LifeHub Temporal workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from temporalio.client import Client
except ImportError:  # pragma: no cover - keeps --help usable outside the worker image.
    Client = None

TASK_QUEUE = "lifehub-daily-decision"


def build_params(args: argparse.Namespace) -> dict[str, object]:
    params: dict[str, object] = {
        "weather_fixture": args.weather_fixture,
        "places_fixture": args.places_fixture,
        "signal_fixture": args.signal_fixture,
        "places_source": args.places_source,
        "places_radius_m": args.places_radius_m,
        "write_postgres": not args.no_write,
        "write_clickhouse": not args.no_write,
    }
    if args.workflow == "weekly":
        params.update(
            {
                "summary_fixture": args.summary_fixture,
                "feedback_fixture": args.feedback_fixture,
                "metrics_fixture": args.metrics_fixture,
            }
        )
    return {key: value for key, value in params.items() if value not in {None, ""}}


async def run(args: argparse.Namespace) -> dict[str, object]:
    if Client is None:
        raise RuntimeError("Temporal SDK is not installed. Run this command inside the lifehub-temporal-worker image.")
    address = os.getenv("LIFEHUB_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.getenv("LIFEHUB_TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(address, namespace=namespace)
    timezone = os.getenv("LIFEHUB_TIMEZONE", "Europe/Moscow")
    today = datetime.now(ZoneInfo(timezone)).date().isoformat()
    if args.workflow == "weekly":
        from lifehub.temporal.workflows import LifeHubWeeklyReviewWorkflow

        workflow_id = args.workflow_id or f"lifehub-weekly-review-{today}"
        workflow_run = LifeHubWeeklyReviewWorkflow.run
    else:
        from lifehub.temporal.workflows import LifeHubDailyDecisionWorkflow

        workflow_id = args.workflow_id or f"lifehub-daily-decision-{today}"
        workflow_run = LifeHubDailyDecisionWorkflow.run
    return await client.execute_workflow(
        workflow_run,
        build_params(args),
        id=workflow_id,
        task_queue=os.getenv("LIFEHUB_TEMPORAL_TASK_QUEUE", TASK_QUEUE),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start LifeHub Temporal workflows.")
    parser.add_argument("--workflow", default="daily", choices=["daily", "weekly"])
    parser.add_argument("--workflow-id", default="")
    parser.add_argument("--weather-fixture", default="")
    parser.add_argument("--places-fixture", default="")
    parser.add_argument("--signal-fixture", default="fixtures/lifehub/context_signals.json")
    parser.add_argument("--summary-fixture", default="")
    parser.add_argument("--feedback-fixture", default="")
    parser.add_argument("--metrics-fixture", default="")
    parser.add_argument("--places-source", default="auto", choices=["auto", "overpass"])
    parser.add_argument("--places-radius-m", type=int, default=30_000)
    parser.add_argument("--no-write", action="store_true", help="Run activities without Postgres/ClickHouse writes.")
    return parser.parse_args()


def main() -> int:
    result = asyncio.run(run(parse_args()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
