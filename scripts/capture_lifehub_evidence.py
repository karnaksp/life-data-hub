#!/usr/bin/env python3
"""Capture redacted LifeHub runtime evidence from local Docker services."""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "lifehub-evidence.md"
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


POSTGRES_QUERIES = {
    "activity rows": "SELECT count(*) FROM life_activity_log;",
    "decision feedback rows": "SELECT count(*) FROM life_decision_feedback;",
    "digest rows": "SELECT count(*) FROM life_digest_runs;",
    "recommendation rows": "SELECT count(*) FROM life_recommendation_events;",
    "signal rows": "SELECT count(*) FROM life_signal_events;",
    "daily context profile rows": "SELECT count(*) FROM life_daily_context_profiles;",
    "spot rows": "SELECT count(*) FROM life_spots;",
}

CLICKHOUSE_QUERIES = {
    "weather rows": "SELECT count() FROM analytics.life_weather_hourly",
    "readiness rows": "SELECT count() FROM analytics.life_readiness_scores",
    "recommendation event rows": "SELECT count() FROM analytics.life_recommendation_events",
    "decision feedback event rows": "SELECT count() FROM analytics.life_decision_feedback_events",
    "signal event rows": "SELECT count() FROM analytics.life_signal_events",
    "activity event rows": "SELECT count() FROM analytics.life_activity_events",
    "daily context profile rows": "SELECT count() FROM analytics.life_daily_context_profiles",
}


def run(args: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def compose(args: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([*COMPOSE, *args], timeout=timeout, check=check)


def postgres_scalar(query: str) -> str:
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
    result = compose(
        ["exec", "-T", "clickhouse", "clickhouse-client", "--query", query],
        timeout=60,
    )
    return result.stdout.strip()


def render_evidence() -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    pg_rows = [(label, postgres_scalar(query)) for label, query in POSTGRES_QUERIES.items()]
    ch_rows = [(label, clickhouse_scalar(query)) for label, query in CLICKHOUSE_QUERIES.items()]
    return f"""# LifeHub Runtime Evidence

Generated at: `{generated_at}`

This file intentionally captures only counts and operational proof. It does not include Telegram tokens, chat ids, personal notes, pain text, or raw diary rows.

## Postgres Operational Tables

{table(pg_rows)}

## ClickHouse Analytical Tables

{table(ch_rows)}

## Manual Checks

- Send `/today` to the configured Telegram bot and confirm a readiness digest arrives.
- Send `/signals` to confirm context signals are available.
- Send `/done skate good` after following a recommendation; feedback counts should increase.
- Send `/log skate 7 8 4 good dry session` and rerun this capture; activity counts should increase.
- Send `/coach` after at least one log entry and confirm the coaching summary uses diary aggregates.
"""


def table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Metric | Value |", "| --- | --- |"]
    lines.extend(f"| {label} | `{value}` |" for label, value in rows)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_evidence(), encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
