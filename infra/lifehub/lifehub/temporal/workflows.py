"""Temporal workflows for LifeHub."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from lifehub.temporal.activities import (
        build_daily_context,
        build_progress_metrics,
        build_weekly_review,
        compute_daily_recommendations,
        import_context_signals,
        ingest_weather,
        sync_places,
    )


@workflow.defn
class LifeHubDailyDecisionWorkflow:
    """Durable orchestration for a complete daily recommendation run."""

    def __init__(self) -> None:
        self._status = "pending"
        self._completed_steps: list[str] = []

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {"status": self._status, "completed_steps": self._completed_steps}

    @workflow.run
    async def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        fixture = params.get("weather_fixture")
        places_fixture = params.get("places_fixture")
        signal_fixture = params.get("signal_fixture", "fixtures/lifehub/context_signals.json")
        write_clickhouse = bool(params.get("write_clickhouse", True))
        write_postgres = bool(params.get("write_postgres", True))

        results: dict[str, Any] = {}
        self._status = "ingesting_weather"
        results["weather"] = await workflow.execute_activity(
            ingest_weather,
            args=[fixture, write_clickhouse],
            start_to_close_timeout=timedelta(minutes=3),
        )
        self._completed_steps.append("weather")

        self._status = "syncing_places"
        results["places"] = await workflow.execute_activity(
            sync_places,
            args=[params.get("places_source", "auto"), places_fixture, int(params.get("places_radius_m", 30_000))],
            start_to_close_timeout=timedelta(minutes=3),
        )
        self._completed_steps.append("places")

        self._status = "importing_signals"
        results["signals"] = await workflow.execute_activity(
            import_context_signals,
            args=[signal_fixture, write_postgres, write_clickhouse],
            start_to_close_timeout=timedelta(minutes=1),
        )
        self._completed_steps.append("signals")

        self._status = "computing_recommendations"
        results["recommendations"] = await workflow.execute_activity(
            compute_daily_recommendations,
            args=[fixture, write_postgres, write_clickhouse],
            start_to_close_timeout=timedelta(minutes=3),
        )
        self._completed_steps.append("recommendations")

        self._status = "building_daily_context"
        results["daily_context"] = await workflow.execute_activity(
            build_daily_context,
            args=[fixture, None, None, None, signal_fixture, write_postgres, write_clickhouse],
            start_to_close_timeout=timedelta(minutes=3),
        )
        self._completed_steps.append("daily_context")

        self._status = "completed"
        return results


@workflow.defn
class LifeHubWeeklyReviewWorkflow:
    """Durable orchestration for weekly progress review and measurement."""

    def __init__(self) -> None:
        self._status = "pending"
        self._completed_steps: list[str] = []

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {"status": self._status, "completed_steps": self._completed_steps}

    @workflow.run
    async def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        results: dict[str, Any] = {}

        self._status = "building_weekly_review"
        results["weekly_review"] = await workflow.execute_activity(
            build_weekly_review,
            args=[
                params.get("weather_fixture"),
                params.get("summary_fixture"),
                params.get("feedback_fixture"),
                params.get("signal_fixture"),
            ],
            start_to_close_timeout=timedelta(minutes=3),
        )
        self._completed_steps.append("weekly_review")

        self._status = "building_metrics"
        results["metrics"] = await workflow.execute_activity(
            build_progress_metrics,
            args=[
                params.get("summary_fixture"),
                params.get("feedback_fixture"),
                params.get("metrics_fixture"),
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )
        self._completed_steps.append("metrics")

        self._status = "completed"
        return results
