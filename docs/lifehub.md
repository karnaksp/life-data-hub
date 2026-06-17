# LifeHub Sports and Wellbeing Digest

LifeHub is a local only data product inside Data Forge. It keeps the retail CDC lab intact and adds a personal sports and wellbeing domain for Saint Petersburg outdoor readiness.

## Product goal

The first useful surface is a Telegram digest that answers: what should I do today?

MVP focus:

- skate, snowboard, moto lessons, volleyball and recovery logging;
- public weather context from Open-Meteo;
- public spots from OpenStreetMap/Overpass with fixture fallback for reproducible tests;
- detailed manual diary entries through Telegram commands;
- weekly review loop that summarizes goals, feedback, outcomes and next-week focus;
- daily context profile that joins weather, recommendations, diary aggregates, goals, feedback and context signals into one privacy-safe decision record;
- fixture-driven demo mode with no real Telegram token.

## Data sources

| Source | Purpose | Privacy |
| --- | --- | --- |
| Open-Meteo forecast | Hourly weather, precipitation, wind, visibility and snow conditions | Public API |
| OpenStreetMap/Overpass | Public skate, sport and park candidates around Saint Petersburg | Public API |
| Configured public spots | Offline fallback locations and activity tags | No home/work address |
| Telegram Bot API | Digest delivery and manual activity diary | Token and chat id stay in local `.env` |
| Local sleep log | Recovery quality and training readiness context | Raw exports stay local; fixtures are synthetic summaries |
| GitHub repo activity | Project focus and maintenance context | Public repo metadata by default; token optional |
| Alpaca market data | Watchlist volatility context | Optional env-gated real mode; fixtures by default |
| Fixture weather | Repeatable tests and demos | Safe to commit |

## Commands

```bash
make lifehub-tests
make lifehub-score-fixture
make lifehub-weekly-review-fixture
make lifehub-lake-export-fixture
make lifehub-sleep-fixture
make lifehub-custom-source-fixture
make lifehub-source-onboard-demo
make lifehub-lakehouse-runtime-smoke
PYTHONPATH=infra/lifehub python -m lifehub.cli activity-file-import fixtures/lifehub/activity_route_spb_public.gpx --activity-type skate
PYTHONPATH=infra/lifehub python -m lifehub.cli sleep-import fixtures/lifehub/sleep_quality.json
PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import fixtures/lifehub/custom_life_events.json --source-name custom_life_events
make lifehub-demo
docker compose --profile lifehub up -d
make lifehub-up-local
make lifehub-apply-marts
make lifehub-quality
make lifehub-lineage
make lifehub-evidence
PYTHONPATH=infra/lifehub python -m lifehub.cli context-profile --fixture fixtures/lifehub/open_meteo_clear_day.json
make lifehub-temporal-up
make lifehub-temporal-start-fixture
make lifehub-temporal-start-weekly-fixture
make lifehub-cockpit
make lifehub-cockpit-demo
make lifehub-evidence-flow-plan
make lifehub-evidence-flow
make lifehub-evidence-flow-temporal
```

Fixture context signals:

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli signal-import --fixture fixtures/lifehub/context_signals.json --output tmp/lifehub-signals.jsonl
PYTHONPATH=infra/lifehub python -m lifehub.cli github-signal-import --fixture fixtures/lifehub/github_repo_activity.json --output tmp/lifehub-github-signals.jsonl
PYTHONPATH=infra/lifehub python -m lifehub.cli market-signal-import --fixture fixtures/lifehub/market_snapshot.json --output tmp/lifehub-market-signals.jsonl
```

Telegram commands:

```text
/today
/spots
/spots skate
/spots moto_practice
/signals
/week
/review
/metrics
/goals
/coach
/done skate good
/skip snowboard thaw
/log skate 7 8 4 good dry evening session
/log activity=moto_lesson intensity=6 mood=7 fatigue=5 result=ok loc=training_ground pain=no notes=slow_turns
```

The compact `/log` shape is:

```text
/log activity intensity mood fatigue result notes
```

The detailed `/log` shape is:

```text
/log activity=skate intensity=7 mood=8 fatigue=4 result=good start=2026-06-15T19:00 end=2026-06-15T20:30 loc=public_spot pain=no notes=dry_session
```

Supported activities: `skate`, `snowboard`, `volleyball`, `moto_lesson`, `gym`, `walk`, `rest`.

Supported results: `good`, `ok`, `bad`, `skipped`.

## Scoring contract

- `skate_score` penalizes rain, wet pavement, strong wind and freezing/slush risk.
- `snowboard_score` rewards snow depth or snowfall and penalizes thaw, rain and high wind.
- `moto_score` penalizes precipitation, wind gusts, poor visibility and cold road-surface risk.
- `volleyball_score` is mostly diary/consistency based; weather only adjusts outdoor sessions.
- `recommendation_score` adjusts outdoor readiness using weekly fatigue, mood, pain flags, sleep recovery and activity load.

Scores map to:

- `go`: 75-100
- `caution`: 50-74
- `recover`: 0-49 or when diary signals suggest recovery

## Saint Petersburg preset

`config/lifehub/locations.yaml` contains a public, non-private preset for Saint Petersburg:

- city baseline: Saint Petersburg center;
- skate and walking: Sevkabel Port, New Holland, Park 300 letiya, Primorsky Victory Park;
- volleyball and recovery walks: Primorsky Victory Park, Krestovsky island;
- moto practice and day rides: Pulkovo Heights, Pushkin, Sestroretsky Razliv;
- snowboard and winter day trips: Toksovo, Okhta Park, Igora, Krasnoe Ozero, Snezhny.

Add personal favorites only as public labels or broad areas. Do not store home, work, garage, or private training addresses in committed config.

## Weekly goals and preferences

`config/lifehub/preferences.yaml` stores privacy-safe weekly targets and activity priorities. These are local recommendation policy inputs, not raw personal history:

- skate: 2 sessions per week;
- volleyball: 1 session per week;
- moto lesson/practice: 1 session per week;
- gym: 1 session per week;
- walk/recovery: 2 sessions per week.

LifeHub uses these targets to add small, explainable recommendation boosts when an activity is under target, for example `weekly goal gap 0/2` or `high priority activity`. `/goals` shows current weekly target progress, `/coach` reports goal gaps in context, and LifeHub Cockpit shows weekly goal progress from aggregate activity counts.

## Storage

Postgres operational tables:

- `life_activity_log`
- `life_decision_feedback`
- `life_digest_runs`
- `life_recommendation_events`
- `life_signal_events`
- `life_user_preferences`
- `life_spots`

ClickHouse analytical tables:

- `analytics.life_weather_hourly`
- `analytics.life_readiness_scores`
- `analytics.life_activity_events`
- `analytics.life_decision_feedback_events`
- `analytics.life_recommendation_events`
- `analytics.life_signal_events`
- `analytics.life_daily_context_profiles`

Iceberg lakehouse tables:

- `iceberg.bronze.lifehub_events`
- `iceberg.silver.lifehub_events`
- `iceberg.gold.lifehub_decision_events`

## Daily context profile

The new product-level object is the daily context profile. It is intentionally compact and privacy-safe: it stores the top recommended action, decision state, seven-day diary aggregates, useful decision metrics, weekly goal gaps and active context signal counts, but not raw diary notes, pain text, Telegram chat ids, home/work addresses or credentials.

Runtime commands:

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli context-profile \
  --fixture fixtures/lifehub/open_meteo_clear_day.json \
  --sleep-fixture fixtures/lifehub/sleep_quality.json

PYTHONPATH=infra/lifehub python -m lifehub.cli context-profile \
  --fixture fixtures/lifehub/open_meteo_clear_day.json \
  --sleep-fixture fixtures/lifehub/sleep_quality.json \
  --write-postgres \
  --write-clickhouse
```

Storage:

- Postgres operational state: `life_daily_context_profiles`.
- ClickHouse analytical events: `analytics.life_daily_context_profiles`.
- Latest mart: `analytics.life_daily_context_latest_v`.
- dbt-compatible models: `stg_lifehub_daily_context_profiles` and `mart_lifehub_daily_context_latest`.

This is the first step toward the Personal Context Graph: LifeHub can now treat the day itself as a measurable product artifact, not just a rendered Telegram message.

## LifeHub services

- `lifehub-weather-ingest`: fetches Open-Meteo forecast rows.
- `lifehub-place-sync`: syncs Overpass spots when available and falls back to local public placeholders.
- `lifehub-score`: computes readiness scores and diary-aware recommendation events.
- `lifehub-score context-profile`: builds the Personal Context Graph daily profile from recommendations, diary aggregates, goals, feedback and context signals.
- `lifehub-signal-import`: imports synthetic local context signals for future market/GitHub/career domains.
- `lifehub-github-signal-import`: imports public GitHub repo activity signals into the shared signal contract.
- `lifehub-market-signal-import`: imports fixture or Alpaca-compatible market volatility signals into the shared signal contract.
- `lifehub-telegram-bot`: polls Telegram and sends the daily digest at `LIFEHUB_DIGEST_TIME`.
- `lifehub-temporal-worker`: runs the durable daily decision workflow on the `lifehub-daily-decision` task queue.
- `temporal`: local Temporal dev server for workflow testing and retry/replay semantics.
- `scripts/capture_lifehub_evidence.py`: writes redacted runtime counts to `docs/evidence/lifehub-evidence.md`.
- `scripts/build_lifehub_cockpit.py`: writes the local LifeHub Cockpit to `docs/lifehub-cockpit.html`.

## Lakehouse and DWH foundation

LifeHub now has a real data engineering path beyond operational Postgres and analytical ClickHouse:

- object storage: MinIO/S3-compatible lake;
- table format: Iceberg;
- metadata: Hive Metastore;
- compute/load: Spark job `infra/airflow/processing/spark/jobs/lifehub_jsonl_to_iceberg.py`;
- orchestration: Airflow DAG `infra/airflow/dags/lifehub_lakehouse_pipeline_dag.py`;
- query/DWH access: Trino SQL in `sql/lifehub/trino_lifehub_lakehouse.sql`;
- source onboarding contract: `config/lifehub/source_registry.yaml`.

Local fixture export:

```bash
make lifehub-lake-export-fixture
```

Full local lakehouse runtime smoke:

```bash
make lifehub-lakehouse-runtime-smoke
```

This starts the Docker lakehouse services, runs Spark against the landing files, writes Iceberg Bronze/Silver/Gold tables, queries them via Trino, and stores redacted proof in `docs/evidence/lifehub-lakehouse-runtime-evidence.md`.

This writes privacy-safe JSONL envelopes to:

```text
tmp/lake/lifehub/landing/<source_name>/dt=<date>/events.jsonl
```

The Airflow lakehouse DAG loads the same contract into:

```text
iceberg.bronze.lifehub_events
iceberg.silver.lifehub_events
iceberg.gold.lifehub_decision_events
```

To add a new real-life source, add it to `config/lifehub/source_registry.yaml`, normalize it into the LifeHub lake envelope, export landing JSONL, and reuse the same Spark loader. This makes future sources such as Strava/GPX, moto-school schedules, broker exports, calendar events, sleep metrics, or new GitHub telemetry extensions a data engineering onboarding task rather than a one-off app integration.

The first implemented extensibility proof is `activity_files`: a local GPX route file can be parsed into a privacy-safe activity summary and exported through the same lakehouse path.

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli activity-file-import \
  fixtures/lifehub/activity_route_spb_public.gpx \
  --activity-type skate \
  --output-root tmp/lake \
  --dt 2026-06-16
```

Real GPX/route files stay local. Public repo fixtures must use broad public routes only.

The first first-class life source extension is `sleep_quality`: a local sleep log can be normalized into night-level recovery summaries, exported to the same landing path, and loaded into Iceberg Bronze/Silver by the lakehouse runtime.

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli sleep-import \
  fixtures/lifehub/sleep_quality.json \
  --output-root tmp/lake \
  --dt 2026-06-16
```

Real sleep or health exports stay local. Committed fixtures contain synthetic aggregate fields only: sleep/wake timestamps, duration, quality score, recovery score and efficiency.

The generic source onboarding path is `custom_life_events`: a local JSON file can be imported without writing a new connector first, as long as the source exists in `config/lifehub/source_registry.yaml`.

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import \
  fixtures/lifehub/custom_life_events.json \
  --source-name custom_life_events \
  --output-root tmp/lake \
  --dt 2026-06-16
```

The importer writes the same lake envelope and redacts notes, addresses, tokens and raw personal text before landing. This is the practical path for trying a new life source first, then promoting it to a dedicated connector and DWH mart once the event shape is stable.

To bootstrap a new source contract, generate an onboarding package first:

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli source-onboard sleep_quality \
  --domain recovery \
  --source-type local_json_event \
  --event-type sleep_metric \
  --required-fields occurred_at,domain,metric_name,metric_value \
  --output-dir tmp/lifehub/source_onboarding
```

The package contains:

- `source_registry_entry.yaml` for the LifeHub source registry;
- a synthetic fixture JSON safe for tests and demos;
- `README.md` with import and lakehouse smoke commands.

After review, apply the registry entry with `--apply-registry` or copy it manually, import the generated fixture through `custom-source-import`, and run `make lifehub-lakehouse-runtime-smoke`. This keeps source onboarding repeatable for sleep metrics, moto-school schedules, broker exports, calendar events, or any future life domain.

## Data engineering controls

- Contract: `contracts/lifehub/data_contract.yaml`.
- Data catalog: `catalog/lifehub/datasets.yaml`.
- Expectations: `expectations/lifehub/expectations.yaml`.
- dbt-compatible analytics layer: `dbt/lifehub`.
- Orchestration: Airflow DAG `infra/airflow/dags/lifehub_daily_pipeline_dag.py`.
- Lakehouse orchestration: Airflow DAG `infra/airflow/dags/lifehub_lakehouse_pipeline_dag.py`.
- Durable orchestration: Temporal workflow `LifeHubDailyDecisionWorkflow`, including daily context profile generation.
- Runtime quality gate: `scripts/lifehub_quality_check.py`.
- Lineage event: `scripts/emit_lifehub_lineage.py`.
- SQL checks: `sql/lifehub/lifehub_quality_checks.sql`.
- ClickHouse marts: `sql/lifehub/clickhouse_lifehub_marts.sql`.
- Trino observability examples: `sql/lifehub/trino_lifehub_observability.sql`.

## Temporal daily decision workflow

Temporal is optional for the MVP runtime and useful when the daily decision pipeline needs production-style retries, durable progress and replay-safe orchestration.

Workflow:

1. ingest weather into ClickHouse;
2. sync public places into Postgres;
3. import context signals into Postgres and ClickHouse;
4. compute readiness scores and diary-aware recommendations;
5. build the daily context profile for the Personal Context Graph;
6. expose workflow progress through the `status` query.

Weekly review workflow:

1. build an aggregate weekly review from diary summary, feedback profile, readiness and context signals;
2. build the progress scorecard for `useful_decision_days_per_week`, follow rate and goal coverage;
3. expose workflow progress through the same `status` query shape.

Run locally:

```bash
make lifehub-temporal-up
make lifehub-temporal-start-fixture
make lifehub-temporal-start-weekly-fixture
```

Temporal Web UI is exposed at `http://localhost:8233` when the `temporal` profile is running. The workflow code stays deterministic: network calls, database writes and file reads live in activities, while the workflow only orders the steps and records progress.

## Runtime evidence

After the local stack is running and `.env` contains Telegram credentials:

```bash
docker compose --profile lifehub up -d
make lifehub-evidence
```

For a reproducible local product run, use the one-command evidence flow. It starts Postgres and ClickHouse, loads fixture weather/spots/signals, seeds synthetic diary and feedback events, computes recommendations, applies ClickHouse marts, runs quality checks, captures evidence and rebuilds the cockpit:

```bash
make lifehub-evidence-flow-plan
make lifehub-evidence-flow
```

To include durable orchestration, run the Temporal variant. It additionally starts Temporal and executes both daily and weekly fixture workflows:

```bash
make lifehub-evidence-flow-temporal
```

The flow uses synthetic fixture events only. It does not require Telegram credentials and does not write real personal history into the repository.

The Temporal variant also writes `docs/evidence/lifehub-temporal-evidence.md` with redacted workflow-level proof for the daily decision and weekly review workflows.

If host ports such as `5432` or `8123` are already used on the machine, use:

```bash
make lifehub-up-local
make lifehub-evidence
```

The evidence file stores only operational counts. It does not include tokens, chat ids, personal notes, pain text, or raw diary rows.

## LifeHub Cockpit

LifeHub Cockpit is the first local visual product surface. It is a static HTML dashboard generated from ClickHouse marts and designed for quick daily review:

- best action today and readiness score;
- useful decision days and follow rate;
- weekly goal progress;
- recommendation score trend;
- context signals from market/GitHub/system domains;
- weather aggregates for configured Saint Petersburg locations.

Generate it from local runtime data:

```bash
make lifehub-apply-marts
make lifehub-cockpit
```

Generate a privacy-safe synthetic preview:

```bash
make lifehub-cockpit-demo
```

Open `docs/lifehub-cockpit.html` in a browser. The cockpit intentionally uses aggregate marts only and does not render raw diary notes, Telegram identifiers, pain text, or secrets.

## Weekly summary

`/week` reads `life_activity_log` for the last seven days and reports session count, average intensity, mood, fatigue, pain-flagged sessions, activities, and results.

`/review` is the weekly intelligence report. It combines the same seven-day diary summary with weekly goals, recommendation feedback, readiness, and recent context signals. The output is intentionally aggregate-only: it reports activity mix, open and covered goals, learning signals such as follow rate, context watches, and one next-week focus. It does not render raw diary notes, Telegram identifiers, private locations, pain text, or token values.

Fixture-only smoke:

```bash
make lifehub-weekly-review-fixture
```

## Coach and decision metrics

`/today` returns the current diary-aware recommendation. `/coach` summarizes the week and explains whether to push, keep it light, or recover.

`/metrics` returns the LifeHub progress scorecard:

- North Star: `useful_decision_days_per_week`;
- logged sessions per week;
- followed/skipped feedback and follow rate;
- weekly goal coverage;
- best learned activity from feedback profile;
- next metric move.

Fixture-only smoke:

```bash
make lifehub-metrics-fixture
```

Use `/done activity [result] [note]` after following a recommendation and `/skip activity [reason]` when you ignore it. These feedback events power `useful_decision_days_per_week` and follow-rate metrics.

When `/today` is sent through Telegram, the digest includes inline feedback buttons for the top recommendation: `Done`, `Skip`, and `Bad fit`. Button callbacks write the same `life_decision_feedback` records as typed commands, so the learning loop works even when feedback is captured with one tap.

Feedback also personalizes future recommendations. LifeHub builds a thirty-day aggregate profile per activity from followed/skipped/good/bad outcomes. Activities with strong follow-through and good outcomes get a small score boost; activities that are repeatedly skipped or produce bad outcomes get a small penalty. Raw feedback notes are not used in public evidence or cockpit output.

`/signals` shows recent context signals. The public MVP includes synthetic fixture signals and optional importers for public GitHub repo activity and Alpaca-compatible market data. Real GitHub/Alpaca mode writes the same `life_signal_events` contract without committing credentials or raw private payloads.

Real GitHub mode reads compact repository metadata from the GitHub REST `repos/{owner}/{repo}` endpoint. Real Alpaca mode reads stock latest bars from `https://data.alpaca.markets/v2/stocks/bars/latest`; the default real watchlist is stock-only (`SPY,QQQ`). Crypto symbols in fixtures are synthetic examples until a separate crypto endpoint adapter is added.

Reference docs:

- GitHub REST repository endpoints: https://docs.github.com/rest/repos/repos
- Alpaca stock latest bars: https://docs.alpaca.markets/us/reference/stocklatestbars-1

North Star metric:

- `useful_decision_days_per_week`: days with at least one generated recommendation that the user can act on.

Supporting metrics:

- `logged_sessions_per_week`
- `recommendation_events_per_day`
- `activity_feedback_profile_follow_rate`
- `weekly_review_generated`
- `high_fatigue_recovery_recommendations`
- `pain_flag_recovery_recommendations`
- `weekly_activity_balance`

## Future integrations

Do not merge market projects into this MVP. The signal layer is intentionally narrow: it imports only compact context events, not raw trading payloads or private repository data. Later LifeHub domains can subscribe to or import outputs from:

- `investment-signals` for market anomaly events and trading context;
- `investment-signals-analytics` for signal quality and delivery diagnostics;
- `stock-prices` for generated market video artifacts and watchlist narratives;
- GitHub activity for career/portfolio consistency;
- GPX/Strava exports for route and training history, if explicit local consent is added.

## Boundaries

- No real personal data is committed.
- No home or work address is stored in defaults.
- Real Telegram secrets live only in `.env`.
- Fixture mode is the default path for automated checks.
