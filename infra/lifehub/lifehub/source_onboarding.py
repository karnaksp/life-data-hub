"""Generate onboarding artifacts for new LifeHub data sources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SOURCE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SourceOnboardingSpec:
    source_name: str
    domain: str
    source_type: str
    producer: str
    consumers: list[str]
    required_fields: list[str]
    event_time_field: str
    idempotency_key: list[str]
    pii: bool
    privacy_class: str
    event_type: str


def csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def validate_source_name(source_name: str) -> None:
    if not SOURCE_RE.match(source_name):
        raise ValueError("source_name must be snake_case and start with a letter.")


def registry_entry(spec: SourceOnboardingSpec) -> str:
    consumers = "[" + ", ".join(spec.consumers) + "]"
    required_fields = "[" + ", ".join(spec.required_fields) + "]"
    idempotency_key = "[" + ", ".join(spec.idempotency_key) + "]"
    pii = "true" if spec.pii else "false"
    return f"""  {spec.source_name}:
    domain: {spec.domain}
    source_type: {spec.source_type}
    producer: {spec.producer}
    landing_path: s3a://iceberg/lifehub/landing/{spec.source_name}/dt={{dt}}/events.jsonl
    bronze_table: iceberg.bronze.lifehub_{spec.source_name}_events
    silver_table: iceberg.silver.lifehub_{spec.source_name}
    gold_table: iceberg.gold.lifehub_{spec.source_name}_mart
    consumers: {consumers}
    pii: {pii}
    commit_policy: keep real source files local; write only privacy-safe summaries to landing
    onboarding_contract:
      required_fields: {required_fields}
      event_time_field: {spec.event_time_field}
      idempotency_key: {idempotency_key}
"""


def sample_fixture(spec: SourceOnboardingSpec) -> dict:
    occurred_at = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc).isoformat()
    event: dict[str, object] = {
        spec.event_time_field: occurred_at,
        "event_type": spec.event_type,
        "domain": spec.domain,
        "metric_name": "demo_metric",
        "metric_value": 1,
        "fixture_kind": "synthetic_demo",
    }
    for field in spec.required_fields:
        event.setdefault(field, demo_value(field, occurred_at))
    return {"events": [event]}


def demo_value(field: str, occurred_at: str) -> object:
    normalized = field.lower()
    if normalized.endswith("_at") or normalized.endswith("_time") or normalized == "occurred_at":
        return occurred_at
    if "count" in normalized or "minutes" in normalized or "score" in normalized:
        return 1
    if "value" in normalized or "amount" in normalized:
        return 1.0
    if normalized in {"domain", "source"}:
        return "demo"
    return f"demo_{field}"


def runbook(spec: SourceOnboardingSpec, fixture_path: Path) -> str:
    fields = ", ".join(spec.required_fields)
    return f"""# LifeHub Source Onboarding: {spec.source_name}

Purpose: connect `{spec.source_name}` as a local-only LifeHub source and send it through the shared lakehouse path.

## Contract

- domain: `{spec.domain}`
- source_type: `{spec.source_type}`
- event_type: `{spec.event_type}`
- event_time_field: `{spec.event_time_field}`
- required_fields: `{fields}`
- privacy_class: `{spec.privacy_class}`
- pii: `{str(spec.pii).lower()}`

## Commands

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import \\
  {fixture_path} \\
  --source-name {spec.source_name} \\
  --event-type {spec.event_type} \\
  --event-time-field {spec.event_time_field} \\
  --privacy-class {spec.privacy_class} \\
  --output-root tmp/lake \\
  --dt 2026-06-16

make lifehub-lakehouse-runtime-smoke
```

## Promotion Checklist

- Add or apply the registry entry to `config/lifehub/source_registry.yaml`.
- Keep real raw exports under ignored local paths, not in git.
- Use the generated fixture only as a synthetic contract example.
- Add source-specific normalization when raw payloads become complex.
- Add Silver/Gold SQL or dbt models only after Bronze events are stable.
- Extend `scripts/validate_lifehub_contract.py` when this becomes a first-class source.
"""


def write_onboarding_package(spec: SourceOnboardingSpec, output_dir: Path) -> dict[str, Path]:
    validate_source_name(spec.source_name)
    target = output_dir / spec.source_name
    target.mkdir(parents=True, exist_ok=True)
    registry_path = target / "source_registry_entry.yaml"
    fixture_path = target / f"{spec.source_name}.json"
    runbook_path = target / "README.md"
    registry_path.write_text(registry_entry(spec), encoding="utf-8")
    fixture_path.write_text(json.dumps(sample_fixture(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runbook_path.write_text(runbook(spec, fixture_path), encoding="utf-8")
    return {
        "registry_entry": registry_path,
        "fixture": fixture_path,
        "runbook": runbook_path,
    }


def apply_registry_entry(registry_path: Path, entry: str, source_name: str) -> None:
    text = registry_path.read_text(encoding="utf-8")
    if f"  {source_name}:" in text:
        raise ValueError(f"Source {source_name!r} already exists in {registry_path}.")
    marker = "\nnew_source_template:"
    if marker not in text:
        raise ValueError(f"Cannot find new_source_template marker in {registry_path}.")
    updated = text.replace(marker, "\n" + entry.rstrip() + "\n" + marker, 1)
    registry_path.write_text(updated, encoding="utf-8")
