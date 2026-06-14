#!/usr/bin/env python3
"""Static Bronze ingestion contract checks.

The checks intentionally use only stdlib parsing so they can run in CI without
Airflow, PySpark, or project service dependencies installed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAG_PATH = ROOT / "infra/airflow/dags/bronze_events_kafka_stream_dag.py"
SPARK_JOBS = [
    ROOT / "infra/airflow/processing/spark/jobs/bronze_events_kafka_stream.py",
    ROOT / "infra/airflow/processing/spark/jobs/bronze_cdc_stream.py",
]

CDC_REQUIRED_KEYS = {"name", "topic", "table", "checkpoint"}
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOPIC_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
TABLE_PATTERN = re.compile(r"^iceberg\.bronze\.[a-z][a-z0-9_]*$")
CHECKPOINT_PATTERN = re.compile(r"^s3a://checkpoints/[A-Za-z0-9._/-]+$")


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _parse_python(path: Path) -> tuple[ast.Module | None, list[str]]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path)), []
    except SyntaxError as exc:
        return None, [f"{_relative(path)} has invalid Python syntax: {exc}"]


def _literal_assignment(module: ast.Module, name: str) -> Any:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"{name} must be a literal value: {exc}") from exc
    raise ValueError(f"{name} assignment not found")


def _find_function(module: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _constant_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _called_function_names(function: ast.FunctionDef) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return calls


def _argparse_flags(function: ast.FunctionDef) -> set[str]:
    flags: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        for arg in node.args:
            flag = _constant_string(arg)
            if flag and flag.startswith("--"):
                flags.add(flag)
    return flags


def _validate_unique(streams: list[dict[str, Any]], key: str) -> list[str]:
    failures: list[str] = []
    seen: dict[str, str] = {}
    for stream in streams:
        value = str(stream.get(key, ""))
        name = str(stream.get("name", "<unknown>"))
        if value in seen:
            failures.append(
                f"CDC_STREAMS has duplicate {key}={value!r} in {seen[value]!r} and {name!r}"
            )
        else:
            seen[value] = name
    return failures


def validate_cdc_streams() -> list[str]:
    failures: list[str] = []
    module, parse_failures = _parse_python(DAG_PATH)
    if module is None:
        return parse_failures

    try:
        streams = _literal_assignment(module, "CDC_STREAMS")
    except ValueError as exc:
        return [f"{_relative(DAG_PATH)}: {exc}"]

    if not isinstance(streams, list) or not streams:
        return [f"{_relative(DAG_PATH)}: CDC_STREAMS must be a non-empty list"]

    typed_streams: list[dict[str, Any]] = []
    for index, stream in enumerate(streams):
        if not isinstance(stream, dict):
            failures.append(f"CDC_STREAMS[{index}] must be a dict")
            continue

        typed_streams.append(stream)
        missing = CDC_REQUIRED_KEYS - set(stream)
        if missing:
            failures.append(f"CDC_STREAMS[{index}] is missing keys: {', '.join(sorted(missing))}")

        for key in CDC_REQUIRED_KEYS:
            value = stream.get(key)
            if not isinstance(value, str) or not value.strip():
                failures.append(f"CDC_STREAMS[{index}].{key} must be a non-empty string")

        name = stream.get("name")
        topic = stream.get("topic")
        table = stream.get("table")
        checkpoint = stream.get("checkpoint")

        if isinstance(name, str) and not NAME_PATTERN.fullmatch(name):
            failures.append(f"CDC_STREAMS[{index}].name is not a snake_case identifier: {name!r}")
        if isinstance(topic, str) and not TOPIC_PATTERN.fullmatch(topic):
            failures.append(f"CDC_STREAMS[{index}].topic has invalid Kafka topic syntax: {topic!r}")
        if isinstance(table, str) and not TABLE_PATTERN.fullmatch(table):
            failures.append(
                f"CDC_STREAMS[{index}].table must target iceberg.bronze.<table>: {table!r}"
            )
        if isinstance(checkpoint, str) and not CHECKPOINT_PATTERN.fullmatch(checkpoint):
            failures.append(
                "CDC_STREAMS"
                f"[{index}].checkpoint must live under s3a://checkpoints/: {checkpoint!r}"
            )
        if isinstance(table, str) and isinstance(checkpoint, str):
            table_leaf = table.rsplit(".", 1)[-1]
            if f"/{table_leaf}" not in checkpoint:
                failures.append(
                    f"CDC_STREAMS[{index}].checkpoint should include table leaf {table_leaf!r}"
                )

    for key in sorted(CDC_REQUIRED_KEYS):
        failures.extend(_validate_unique(typed_streams, key))

    return failures


def validate_spark_jobs() -> list[str]:
    failures: list[str] = []
    for path in SPARK_JOBS:
        module, parse_failures = _parse_python(path)
        if module is None:
            failures.extend(parse_failures)
            continue

        functions = {node.name for node in module.body if isinstance(node, ast.FunctionDef)}
        missing_functions = {"build_stream", "parse_args", "main"} - functions
        if missing_functions:
            failures.append(
                f"{_relative(path)} is missing functions: {', '.join(sorted(missing_functions))}"
            )
            continue

        parse_args = _find_function(module, "parse_args")
        main = _find_function(module, "main")
        if parse_args is None or main is None:
            continue

        flags = _argparse_flags(parse_args)
        required_flags = {"--checkpoint", "--table"}
        required_flags.add("--topics" if path.name == "bronze_events_kafka_stream.py" else "--topic")
        missing_flags = required_flags - flags
        if missing_flags:
            failures.append(
                f"{_relative(path)} parse_args is missing flags: {', '.join(sorted(missing_flags))}"
            )

        main_calls = _called_function_names(main)
        if "parse_args" not in main_calls:
            failures.append(f"{_relative(path)} main() does not call parse_args()")
        if "build_stream" not in main_calls:
            failures.append(f"{_relative(path)} main() does not call build_stream()")

    return failures


def validate_bronze_contract() -> list[str]:
    failures: list[str] = []
    failures.extend(validate_cdc_streams())
    failures.extend(validate_spark_jobs())
    return failures


def main() -> int:
    failures = validate_bronze_contract()
    if failures:
        print("Bronze contract validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Bronze contract validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
