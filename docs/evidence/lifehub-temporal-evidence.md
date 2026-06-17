# LifeHub Temporal Runtime Evidence

Generated at: `2026-06-15T22:14:25.595613+00:00`

This file captures redacted workflow-level proof from the local fixture run. It does not include Telegram tokens, chat ids, raw diary notes, pain text, or private locations.

## Workflows

| Workflow | Status | Key proof |
| --- | --- | --- |
| daily decision | `completed` | `weather_rows=112, recommendations=4, top=skate, context=act_on_open_goal` |
| weekly review | `completed` | `sessions=5, useful_decision_days=3, follow_rate=0.8` |

## Commands

- `make lifehub-evidence-flow-temporal`
- `python -m lifehub.temporal.starter --weather-fixture ...`
- `python -m lifehub.temporal.starter --workflow weekly ...`
