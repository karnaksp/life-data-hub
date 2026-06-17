# LifeHub Runtime Evidence

Generated at: `2026-06-15T22:14:28.891330+00:00`

This file intentionally captures only counts and operational proof. It does not include Telegram tokens, chat ids, personal notes, pain text, or raw diary rows.

## Postgres Operational Tables

| Metric | Value |
| --- | --- |
| activity rows | `12` |
| decision feedback rows | `14` |
| digest rows | `6` |
| recommendation rows | `76` |
| signal rows | `7` |
| daily context profile rows | `1` |
| spot rows | `69` |

## ClickHouse Analytical Tables

| Metric | Value |
| --- | --- |
| weather rows | `4416` |
| readiness rows | `1040` |
| recommendation event rows | `68` |
| decision feedback event rows | `14` |
| signal event rows | `7` |
| activity event rows | `12` |
| daily context profile rows | `3` |

## Manual Checks

- Send `/today` to the configured Telegram bot and confirm a readiness digest arrives.
- Send `/signals` to confirm context signals are available.
- Send `/done skate good` after following a recommendation; feedback counts should increase.
- Send `/log skate 7 8 4 good dry session` and rerun this capture; activity counts should increase.
- Send `/coach` after at least one log entry and confirm the coaching summary uses diary aggregates.
