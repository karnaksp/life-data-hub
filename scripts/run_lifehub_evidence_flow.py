#!/usr/bin/env python3
"""Run the full local LifeHub fixture evidence flow."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    "--profile",
    "temporal",
]


def run(
    args: list[str],
    dry_run: bool = False,
    timeout: int = 600,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str] | None:
    printable = " ".join(args)
    print(f"+ {printable}")
    if dry_run:
        return None
    result = subprocess.run(
        args,
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {printable}\nstderr:\n{result.stderr}")
    return result


def compose(
    args: list[str],
    dry_run: bool = False,
    timeout: int = 600,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str] | None:
    return run([*COMPOSE, *args], dry_run=dry_run, timeout=timeout, input_text=input_text)


def service_run(
    service: str,
    command: list[str],
    dry_run: bool = False,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str] | None:
    return compose(["run", "--build", "--rm", service, *command], dry_run=dry_run, timeout=timeout)


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run

    compose(["up", "-d", "--build", "postgres", "clickhouse"], dry_run=dry_run, timeout=900)

    service_run(
        "lifehub-place-sync",
        ["python", "-m", "lifehub.cli", "place-sync", "--fixture", "/workspace/fixtures/lifehub/overpass_spots.json"],
        dry_run=dry_run,
    )
    service_run(
        "lifehub-weather-ingest",
        [
            "python",
            "-m",
            "lifehub.cli",
            "weather-ingest",
            "--fixture",
            "/workspace/fixtures/lifehub/open_meteo_clear_day.json",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )
    service_run(
        "lifehub-signal-import",
        [
            "python",
            "-m",
            "lifehub.cli",
            "signal-import",
            "--fixture",
            "/workspace/fixtures/lifehub/context_signals.json",
            "--write-postgres",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )
    service_run(
        "lifehub-github-signal-import",
        [
            "python",
            "-m",
            "lifehub.cli",
            "github-signal-import",
            "--fixture",
            "/workspace/fixtures/lifehub/github_repo_activity.json",
            "--write-postgres",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )
    service_run(
        "lifehub-market-signal-import",
        [
            "python",
            "-m",
            "lifehub.cli",
            "market-signal-import",
            "--fixture",
            "/workspace/fixtures/lifehub/market_snapshot.json",
            "--write-postgres",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )
    for text in [
        "/log skate 7 8 4 good dry fixture session",
        "/log moto_lesson 6 7 5 ok slow turns fixture session",
        "/done skate good fixture_followed",
        "/skip snowboard thaw_fixture",
    ]:
        service_run(
            "lifehub-score",
            ["python", "-m", "lifehub.cli", "log" if text.startswith("/log") else "feedback", text, "--write-clickhouse"],
            dry_run=dry_run,
        )
    service_run(
        "lifehub-score",
        [
            "python",
            "-m",
            "lifehub.cli",
            "recommend",
            "--fixture",
            "/workspace/fixtures/lifehub/open_meteo_clear_day.json",
            "--write-postgres",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )
    service_run(
        "lifehub-score",
        [
            "python",
            "-m",
            "lifehub.cli",
            "context-profile",
            "--fixture",
            "/workspace/fixtures/lifehub/open_meteo_clear_day.json",
            "--write-postgres",
            "--write-clickhouse",
        ],
        dry_run=dry_run,
    )

    if args.include_temporal:
        compose(["up", "-d", "--build", "temporal", "lifehub-temporal-worker"], dry_run=dry_run, timeout=900)
        daily_temporal = service_run(
            "lifehub-temporal-worker",
            [
                "python",
                "-m",
                "lifehub.temporal.starter",
                "--weather-fixture",
                "/workspace/fixtures/lifehub/open_meteo_clear_day.json",
                "--places-fixture",
                "/workspace/fixtures/lifehub/overpass_spots.json",
                "--signal-fixture",
                "/workspace/fixtures/lifehub/context_signals.json",
            ],
            dry_run=dry_run,
            timeout=300,
        )
        weekly_temporal = service_run(
            "lifehub-temporal-worker",
            [
                "python",
                "-m",
                "lifehub.temporal.starter",
                "--workflow",
                "weekly",
                "--weather-fixture",
                "/workspace/fixtures/lifehub/open_meteo_clear_day.json",
                "--summary-fixture",
                "/workspace/fixtures/lifehub/week_summary.json",
                "--feedback-fixture",
                "/workspace/fixtures/lifehub/feedback_profile.json",
                "--metrics-fixture",
                "/workspace/fixtures/lifehub/decision_metrics.json",
                "--signal-fixture",
                "/workspace/fixtures/lifehub/context_signals.json",
            ],
            dry_run=dry_run,
            timeout=300,
        )
        if not dry_run:
            write_temporal_evidence(daily_temporal, weekly_temporal)

    marts_sql = (ROOT / "sql" / "lifehub" / "clickhouse_lifehub_marts.sql").read_text(encoding="utf-8")
    compose(
        ["exec", "-T", "clickhouse", "clickhouse-client", "--multiquery"],
        dry_run=dry_run,
        input_text=marts_sql,
    )
    run(["python", "scripts/lifehub_quality_check.py"], dry_run=dry_run, timeout=180)
    run(["python", "scripts/capture_lifehub_evidence.py"], dry_run=dry_run, timeout=180)
    run(["python", "scripts/build_lifehub_cockpit.py"], dry_run=dry_run, timeout=180)
    run(["python", "scripts/validate_lifehub_contract.py"], dry_run=dry_run, timeout=180)
    print("LifeHub evidence flow completed.")
    return 0


def write_temporal_evidence(
    daily_result: subprocess.CompletedProcess[str] | None,
    weekly_result: subprocess.CompletedProcess[str] | None,
) -> None:
    output = ROOT / "docs" / "evidence" / "lifehub-temporal-evidence.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    daily_payload = extract_json_with_keys(
        daily_result.stdout if daily_result else "",
        {"weather", "recommendations", "daily_context"},
    )
    weekly_payload = extract_json_with_keys(weekly_result.stdout if weekly_result else "", {"weekly_review", "metrics"})
    lines = [
        "# LifeHub Temporal Runtime Evidence",
        "",
        f"Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "This file captures redacted workflow-level proof from the local fixture run. It does not include Telegram tokens, chat ids, raw diary notes, pain text, or private locations.",
        "",
        "## Workflows",
        "",
        "| Workflow | Status | Key proof |",
        "| --- | --- | --- |",
        f"| daily decision | `completed` | `{daily_summary(daily_payload)}` |",
        f"| weekly review | `completed` | `{weekly_summary(weekly_payload)}` |",
        "",
        "## Commands",
        "",
        "- `make lifehub-evidence-flow-temporal`",
        "- `python -m lifehub.temporal.starter --weather-fixture ...`",
        "- `python -m lifehub.temporal.starter --workflow weekly ...`",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)}")


def extract_json_with_keys(text: str, required_keys: set[str]) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    fallback: dict[str, Any] = {}
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            fallback = value
            if required_keys.issubset(value.keys()):
                return value
    return fallback


def daily_summary(payload: dict[str, Any]) -> str:
    weather = payload.get("weather") or {}
    recommendations = payload.get("recommendations") or {}
    daily_context = payload.get("daily_context") or {}
    top = recommendations.get("top") or {}
    return (
        f"weather_rows={weather.get('weather_rows', 'n/a')}, "
        f"recommendations={recommendations.get('recommendations', 'n/a')}, "
        f"top={top.get('activity', 'n/a')}, "
        f"context={daily_context.get('readiness_state', 'n/a')}"
    )


def weekly_summary(payload: dict[str, Any]) -> str:
    review = payload.get("weekly_review") or {}
    metrics = payload.get("metrics") or {}
    return (
        f"sessions={review.get('sessions', 'n/a')}, "
        f"useful_decision_days={metrics.get('useful_decision_days', 'n/a')}, "
        f"follow_rate={metrics.get('follow_rate', 'n/a')}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the ordered command plan without running Docker.")
    parser.add_argument("--include-temporal", action="store_true", help="Also run daily and weekly Temporal fixture workflows.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
