#!/usr/bin/env python3
"""Run redacted LifeHub data quality checks against local Docker services."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.evidence.yml",
    "--profile",
    "lifehub",
]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    observed: str
    expectation: str


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def compose(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = run([*COMPOSE, *args], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def postgres_scalar(query: str) -> str:
    if os.getenv("LIFEHUB_QUALITY_DIRECT") == "1":
        import psycopg2

        dsn = os.getenv(
            "LIFEHUB_POSTGRES_DSN",
            "host=postgres port=5432 dbname=demo user=admin password=admin",
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                value = cur.fetchone()[0]
        return str(value)

    result = compose(
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "admin",
            "-d",
            "demo",
            "-At",
            "-c",
            query,
        ],
        timeout=60,
    )
    return result.stdout.strip()


def clickhouse_scalar(query: str) -> str:
    if os.getenv("LIFEHUB_QUALITY_DIRECT") == "1":
        clickhouse_url = os.getenv(
            "LIFEHUB_CLICKHOUSE_URL",
            "http://clickhouse:8123/?user=admin&password=admin",
        )
        parsed = urllib.parse.urlsplit(clickhouse_url)
        params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        params["query"] = query
        path = parsed.path or "/"
        url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(params), parsed.fragment)
        )
        request = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8").strip()

    result = compose(
        ["exec", "-T", "clickhouse", "clickhouse-client", "--query", query],
        timeout=60,
    )
    return result.stdout.strip()


def int_value(value: str) -> int:
    return int(value.splitlines()[-1].strip() or "0")


def iso_datetime(value: str) -> datetime | None:
    cleaned = value.splitlines()[-1].strip()
    if not cleaned:
        return None
    normalized = cleaned.replace(" ", "T").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_minutes(value: datetime | None) -> float | None:
    if value is None:
        return None
    return (datetime.now(timezone.utc) - value).total_seconds() / 60


def collect_checks() -> list[Check]:
    checks: list[Check] = []

    spot_rows = int_value(postgres_scalar("SELECT count(*) FROM life_spots;"))
    checks.append(Check("postgres.life_spots.count", spot_rows > 0, str(spot_rows), "> 0"))

    bad_spot_coords = int_value(
        postgres_scalar(
            """
            SELECT count(*)
            FROM life_spots
            WHERE latitude NOT BETWEEN -90 AND 90
               OR longitude NOT BETWEEN -180 AND 180;
            """
        )
    )
    checks.append(Check("postgres.life_spots.coordinates", bad_spot_coords == 0, str(bad_spot_coords), "0 bad rows"))

    empty_spot_labels = int_value(
        postgres_scalar("SELECT count(*) FROM life_spots WHERE label IS NULL OR btrim(label) = '';")
    )
    checks.append(Check("postgres.life_spots.labels", empty_spot_labels == 0, str(empty_spot_labels), "0 empty labels"))

    bad_activity_scores = int_value(
        postgres_scalar(
            """
            SELECT count(*)
            FROM life_activity_log
            WHERE intensity NOT BETWEEN 1 AND 10
               OR mood NOT BETWEEN 1 AND 10
               OR fatigue NOT BETWEEN 1 AND 10;
            """
        )
    )
    checks.append(
        Check("postgres.life_activity_log.score_ranges", bad_activity_scores == 0, str(bad_activity_scores), "0 bad rows")
    )

    weather_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_weather_hourly"))
    checks.append(Check("clickhouse.life_weather_hourly.count", weather_rows > 0, str(weather_rows), "> 0"))

    latest_weather_fetch = iso_datetime(clickhouse_scalar("SELECT max(fetched_at) FROM analytics.life_weather_hourly"))
    weather_age = age_minutes(latest_weather_fetch)
    checks.append(
        Check(
            "clickhouse.life_weather_hourly.freshness",
            weather_age is not None and weather_age <= 360,
            "missing" if weather_age is None else f"{weather_age:.1f} minutes",
            "<= 360 minutes",
        )
    )

    bad_weather = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_weather_hourly
            WHERE temperature_c NOT BETWEEN -60 AND 45
               OR precipitation_mm < 0
               OR wind_speed_kmh < 0
               OR wind_gust_kmh < 0
            """
        )
    )
    checks.append(Check("clickhouse.life_weather_hourly.ranges", bad_weather == 0, str(bad_weather), "0 bad rows"))

    readiness_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_readiness_scores"))
    checks.append(Check("clickhouse.life_readiness_scores.count", readiness_rows > 0, str(readiness_rows), "> 0"))

    latest_readiness = iso_datetime(clickhouse_scalar("SELECT max(computed_at) FROM analytics.life_readiness_scores"))
    readiness_age = age_minutes(latest_readiness)
    checks.append(
        Check(
            "clickhouse.life_readiness_scores.freshness",
            readiness_age is not None and readiness_age <= 360,
            "missing" if readiness_age is None else f"{readiness_age:.1f} minutes",
            "<= 360 minutes",
        )
    )

    bad_scores = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_readiness_scores
            WHERE score NOT BETWEEN 0 AND 100
               OR decision NOT IN ('go', 'caution', 'skip')
               OR explanation = ''
            """
        )
    )
    checks.append(Check("clickhouse.life_readiness_scores.contract", bad_scores == 0, str(bad_scores), "0 bad rows"))

    recommendation_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_recommendation_events"))
    checks.append(Check("clickhouse.life_recommendation_events.count", recommendation_rows > 0, str(recommendation_rows), "> 0"))

    latest_recommendation = iso_datetime(
        clickhouse_scalar("SELECT max(generated_at) FROM analytics.life_recommendation_events")
    )
    recommendation_age = age_minutes(latest_recommendation)
    checks.append(
        Check(
            "clickhouse.life_recommendation_events.freshness",
            recommendation_age is not None and recommendation_age <= 360,
            "missing" if recommendation_age is None else f"{recommendation_age:.1f} minutes",
            "<= 360 minutes",
        )
    )

    bad_recommendations = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_recommendation_events
            WHERE score NOT BETWEEN 0 AND 100
               OR decision NOT IN ('go', 'caution', 'recover')
               OR reasons = ''
            """
        )
    )
    checks.append(
        Check(
            "clickhouse.life_recommendation_events.contract",
            bad_recommendations == 0,
            str(bad_recommendations),
            "0 bad rows",
        )
    )

    feedback_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_decision_feedback_events"))
    checks.append(Check("clickhouse.life_decision_feedback_events.count", feedback_rows >= 0, str(feedback_rows), ">= 0"))

    bad_feedback = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_decision_feedback_events
            WHERE action NOT IN ('followed', 'skipped', 'changed')
               OR (result IS NOT NULL AND result NOT IN ('good', 'ok', 'bad', 'skipped'))
            """
        )
    )
    checks.append(
        Check(
            "clickhouse.life_decision_feedback_events.contract",
            bad_feedback == 0,
            str(bad_feedback),
            "0 bad rows",
        )
    )

    signal_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_signal_events"))
    checks.append(Check("clickhouse.life_signal_events.count", signal_rows >= 0, str(signal_rows), ">= 0"))

    bad_signals = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_signal_events
            WHERE domain NOT IN ('market', 'github', 'career', 'wellbeing', 'system')
               OR direction NOT IN ('positive', 'negative', 'neutral')
               OR urgency NOT BETWEEN 1 AND 10
               OR confidence NOT BETWEEN 1 AND 100
               OR title = ''
            """
        )
    )
    checks.append(Check("clickhouse.life_signal_events.contract", bad_signals == 0, str(bad_signals), "0 bad rows"))

    context_rows = int_value(clickhouse_scalar("SELECT count() FROM analytics.life_daily_context_profiles"))
    checks.append(Check("clickhouse.life_daily_context_profiles.count", context_rows > 0, str(context_rows), "> 0"))

    bad_context = int_value(
        clickhouse_scalar(
            """
            SELECT count()
            FROM analytics.life_daily_context_profiles
            WHERE top_score NOT BETWEEN 0 AND 100
               OR top_decision NOT IN ('go', 'caution', 'recover')
               OR sessions_7d < 0
               OR avg_mood_7d NOT BETWEEN 0 AND 10
               OR avg_fatigue_7d NOT BETWEEN 0 AND 10
               OR useful_decision_days_7d NOT BETWEEN 0 AND 7
               OR follow_rate_7d NOT BETWEEN 0 AND 1
               OR highest_signal_urgency NOT BETWEEN 0 AND 10
               OR context_summary = ''
            """
        )
    )
    checks.append(
        Check("clickhouse.life_daily_context_profiles.contract", bad_context == 0, str(bad_context), "0 bad rows")
    )

    return checks


def main() -> int:
    checks = collect_checks()
    payload = {
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "observed": check.observed,
                "expectation": check.expectation,
            }
            for check in checks
        ]
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
