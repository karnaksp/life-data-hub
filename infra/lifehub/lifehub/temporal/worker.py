"""Temporal worker for LifeHub workflows."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os

from temporalio.client import Client
from temporalio.worker import Worker

from lifehub.temporal.activities import (
    build_daily_context,
    build_progress_metrics,
    build_weekly_review,
    compute_daily_recommendations,
    import_context_signals,
    ingest_weather,
    sync_places,
)
from lifehub.temporal.workflows import LifeHubDailyDecisionWorkflow, LifeHubWeeklyReviewWorkflow


TASK_QUEUE = os.getenv("LIFEHUB_TEMPORAL_TASK_QUEUE", "lifehub-daily-decision")


async def main() -> None:
    address = os.getenv("LIFEHUB_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.getenv("LIFEHUB_TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(address, namespace=namespace)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[LifeHubDailyDecisionWorkflow, LifeHubWeeklyReviewWorkflow],
            activities=[
                ingest_weather,
                sync_places,
                import_context_signals,
                compute_daily_recommendations,
                build_daily_context,
                build_weekly_review,
                build_progress_metrics,
            ],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
