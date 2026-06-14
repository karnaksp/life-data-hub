#!/usr/bin/env python3
"""Lightweight quality checks for the Data Forge portfolio case study."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "README.md",
    "CASE_STUDY.md",
    "docs/retail-cdc-runbook.md",
    "docs/assets/README.md",
    "sql/validation/postgres_retail_seed_checks.sql",
    "sql/validation/kafka_topic_inventory.md",
    "sql/examples/postgres_retail_profile.sql",
    "sql/examples/clickhouse_realtime_sales.sql",
    "sql/examples/trino_lakehouse_quality.sql",
]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def validate_required_files() -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.exists():
            failures.append(f"Missing required case-study file: {relative}")
        elif path.is_file() and not path.read_text(encoding="utf-8").strip():
            failures.append(f"Required case-study file is empty: {relative}")
    return failures


def iter_markdown_files() -> list[Path]:
    candidates = [ROOT / "README.md", ROOT / "CASE_STUDY.md"]
    candidates.extend((ROOT / "docs").rglob("*.md"))
    candidates.extend((ROOT / "sql").rglob("*.md"))
    return sorted(path for path in candidates if path.exists())


def validate_markdown_links() -> list[str]:
    failures: list[str] = []
    for path in iter_markdown_files():
        text = path.read_text(encoding="utf-8")
        if text.count("```") % 2:
            failures.append(f"{path.relative_to(ROOT)} has an unbalanced fenced code block")
        for match in LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if (
                not target
                or target.startswith(("http://", "https://", "mailto:", "#"))
                or target.startswith("<")
            ):
                continue
            target_path = (path.parent / target.split("#", 1)[0]).resolve()
            try:
                target_path.relative_to(ROOT.resolve())
            except ValueError:
                failures.append(f"{path.relative_to(ROOT)} links outside repository: {target}")
                continue
            if not target_path.exists():
                failures.append(f"{path.relative_to(ROOT)} has a broken local link: {target}")
    return failures


def validate_sql_files() -> list[str]:
    failures: list[str] = []
    for path in sorted((ROOT / "sql").rglob("*.sql")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            failures.append(f"{path.relative_to(ROOT)} is empty")
            continue
        if ";" not in text:
            failures.append(f"{path.relative_to(ROOT)} does not contain a SQL statement terminator")
    return failures


def validate_case_study_framing() -> list[str]:
    failures: list[str] = []
    case_study = (ROOT / "CASE_STUDY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_phrases = [
        (case_study, "My Contribution in This Fork", "CASE_STUDY.md"),
        (case_study, "Validation Contract", "CASE_STUDY.md"),
        (readme, "Portfolio Case Study", "README.md"),
        (readme, "retail CDC", "README.md"),
    ]
    for text, phrase, file_name in required_phrases:
        if phrase not in text:
            failures.append(f"{file_name} is missing required portfolio framing: {phrase}")
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_required_files())
    failures.extend(validate_markdown_links())
    failures.extend(validate_sql_files())
    failures.extend(validate_case_study_framing())

    if failures:
        print("Project validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Project validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
