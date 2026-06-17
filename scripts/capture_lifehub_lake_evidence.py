#!/usr/bin/env python3
"""Capture redacted evidence for LifeHub lake landing files."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "tmp" / "lake" / "lifehub" / "landing"
OUTPUT = ROOT / "docs" / "evidence" / "lifehub-lakehouse-evidence.md"
FORBIDDEN = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "pain_text",
    "raw_diary_notes",
    "raw_sleep_notes",
    "home_address",
]


def collect() -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = defaultdict(int)
    failures: list[str] = []
    if not LANDING.exists():
        return counts, [f"Missing landing path: {LANDING.relative_to(ROOT)}"]
    for path in sorted(LANDING.glob("*/dt=*/events.jsonl")):
        source = path.parts[-3]
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            for forbidden in FORBIDDEN:
                if forbidden in line:
                    failures.append(f"{path.relative_to(ROOT)}:{line_no} contains forbidden phrase {forbidden}")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                failures.append(f"{path.relative_to(ROOT)}:{line_no} invalid JSON: {exc}")
                continue
            if payload.get("source_name") != source:
                failures.append(f"{path.relative_to(ROOT)}:{line_no} source_name mismatch")
            counts[source] += 1
    return dict(counts), failures


def render(counts: dict[str, int], failures: list[str]) -> str:
    rows = "\n".join(f"| {source} | `{count}` |" for source, count in sorted(counts.items()))
    if not rows:
        rows = "| none | `0` |"
    status = "passed" if not failures else "failed"
    failure_text = "\n".join(f"- {failure}" for failure in failures) if failures else "- none"
    return f"""# LifeHub Lakehouse Evidence

Generated at: `{datetime.now(timezone.utc).isoformat()}`

This file captures redacted local evidence for the LifeHub lake landing layer. It reports source-level counts only and checks that landing JSONL files do not contain Telegram tokens, chat ids, raw diary notes, raw sleep notes, or pain text.

## Landing Rows

| Source | Rows |
| --- | --- |
{rows}

## Privacy Check

Status: `{status}`

{failure_text}
"""


def main() -> int:
    counts, failures = collect()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(counts, failures), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    if failures:
        for failure in failures:
            print(failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
