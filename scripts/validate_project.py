#!/usr/bin/env python3
"""Lightweight quality checks for the Life Data Hub platform."""

from __future__ import annotations

import re
from pathlib import Path

from validate_bronze_contract import validate_bronze_contract
from generate_evidence_bundle import EVIDENCE_PATH, render_evidence_bundle
from validate_lifehub_dataops import main as validate_lifehub_dataops_main
from validate_lifehub_contract import main as validate_lifehub_main
from validate_runtime_contract import validate_runtime_contract


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "README.md",
    "CHANGELOG.md",
    ".github/workflows/package.yml",
    "CASE_STUDY.md",
    "docker-compose.evidence.yml",
    "docker-compose.lakehouse-smoke.yml",
    "docs/retail-cdc-runbook.md",
    "docs/assets/README.md",
    "docs/assets/life-data-hub-stack.svg",
    "docs/data-engineering-stack.md",
    "docs/evidence/retail-cdc-evidence.md",
    "scripts/capture_clickhouse_evidence.py",
    "sql/validation/postgres_retail_seed_checks.sql",
    "sql/validation/kafka_topic_inventory.md",
    "sql/validation/clickhouse_ingestion_contract.md",
    "sql/examples/postgres_retail_profile.sql",
    "sql/examples/clickhouse_realtime_sales.sql",
    "sql/examples/trino_lakehouse_quality.sql",
    "docs/lifehub.md",
    "config/lifehub/locations.yaml",
    "config/lifehub/scoring.yaml",
    "catalog/lifehub/datasets.yaml",
    "expectations/lifehub/expectations.yaml",
    "fixtures/lifehub/open_meteo_clear_day.json",
    "infra/lifehub/README.md",
    "infra/airflow/dags/lifehub_daily_pipeline_dag.py",
    "contracts/lifehub/data_contract.yaml",
    "sql/lifehub/clickhouse_lifehub_marts.sql",
    "sql/lifehub/lifehub_quality_checks.sql",
    "sql/lifehub/trino_lifehub_observability.sql",
    "scripts/lifehub_quality_check.py",
    "scripts/emit_lifehub_lineage.py",
    "scripts/validate_lifehub_dataops.py",
    "scripts/validate_lifehub_contract.py",
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
        (readme, "Локальная data engineering платформа", "README.md"),
        (readme, "LifeHub", "README.md"),
        (readme, "Retail CDC сценарий", "README.md"),
        (readme, "сохранен как инженерная лаборатория", "README.md"),
        (readme, "ghcr.io/karnaksp/life-data-hub/lifehub", "README.md"),
    ]
    for text, phrase, file_name in required_phrases:
        if phrase not in text:
            failures.append(f"{file_name} is missing required CDC/lakehouse framing: {phrase}")
    return failures


def validate_evidence_bundle() -> list[str]:
    expected = render_evidence_bundle()
    actual = EVIDENCE_PATH.read_text(encoding="utf-8") if EVIDENCE_PATH.exists() else ""
    if actual != expected:
        return [
            "docs/evidence/retail-cdc-evidence.md is stale; "
            "run python scripts/generate_evidence_bundle.py"
        ]
    return []


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_required_files())
    failures.extend(validate_markdown_links())
    failures.extend(validate_sql_files())
    failures.extend(validate_case_study_framing())
    failures.extend(validate_evidence_bundle())
    failures.extend(validate_bronze_contract())
    failures.extend(validate_runtime_contract())
    if validate_lifehub_main() != 0:
        failures.append("LifeHub contract validation failed")
    if validate_lifehub_dataops_main() != 0:
        failures.append("LifeHub DataOps validation failed")

    if failures:
        print("Project validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Project validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
