# LifeHub Personal Data Sources

LifeHub uses a local-first source architecture. Every source is registered in `config/lifehub/source_registry.yaml`, described in `contracts/lifehub/data_contract.yaml`, and normalized into a privacy-safe event envelope before it can feed shared lakehouse or DWH layers.

The registry is intentionally broader than the current runnable fixtures. Tier 1 sources are active MVP inputs or public/synthetic fixtures. Tier 2-4 entries are the coverage plan for future personal domains and define what is allowed before connector work starts.

## Source Tiers

| Tier | Meaning | Raw Policy | Landing Policy |
| --- | --- | --- | --- |
| Tier 1 foundation | Public, synthetic, derived, or low-risk summary sources. | Synthetic fixtures and public API examples may be committed. | Privacy-safe envelopes may land in the local lakehouse. |
| Tier 2 personal context | Behavior, planning, productivity, and preference data that is useful after summarization. | Real raw exports stay on ignored local paths. | Land summaries, buckets, and redacted metrics only. |
| Tier 3 sensitive life | Health, finance, precise location, and communications data. | Raw exports stay local and require source-specific redaction. | No exact identifiers, private coordinates, raw device payloads, account data, or message content. |
| Tier 4 private core | Secrets, identity documents, legal/tax/insurance records, and irreversible identifiers. | No raw payloads in shared bronze. | Pointer-only events with status, due dates, buckets, and local pointer ids. |

## Coverage Map

| Source | Tier | Domain | Privacy Class | Status | Allowed Payload |
| --- | --- | --- | --- | --- | --- |
| `weather_forecast` | Tier 1 | Weather | `public_context` | Active fixture/API | Forecast facts by configured location id. |
| `place_spots` | Tier 1 | Places | `public_context` | Active fixture/API | Public OSM/config spot candidates for skate, volleyball, parks and outdoor decisions. |
| `context_signals` | Tier 1 | Context | `public_context` | Active fixture/API | Compact market, GitHub, career, wellbeing, or system signals. |
| `external_source_items` | Tier 1 | Managed links | `public_context` | Active fixture/local subscriptions | Telegram channel, RSS, news URL, API JSON, and event stream items from local subscriptions. |
| `decision_feedback` | Tier 1 | Decision quality | `private_behavior_summary` | Active | Follow/skip/change feedback without raw notes. |
| `daily_context_profile` | Tier 1 | Decision intelligence | `derived_context` | Active | Daily aggregate recommendation context. |
| `activity_diary` | Tier 2 | Wellbeing | `private_behavior_summary` | Active local input | Activity, intensity, mood, fatigue, result; no raw notes or pain text. |
| `activity_files` | Tier 2 | Sports/location | `private_location_summary` | Active synthetic GPX fixture | Route and training summaries; real route files stay local. |
| `sleep_quality` | Tier 2 | Recovery | `private_health_summary` | Active synthetic fixture | Night-level sleep and recovery summaries. |
| `custom_life_events` | Tier 2 | Extensibility | `private_behavior_summary` | Active generic importer | Redacted generic metrics for new source experiments. |
| `calendar_events` | Tier 2 | Schedule | `private_behavior_summary` | Active local fixture | Busy windows, duration, commitment bucket; no titles, attendees, or locations. |
| `moto_learning_log` | Tier 2 | Moto learning | `private_behavior_summary` | Active local fixture | Lesson type, exercise bucket, confidence, errors count, next focus tag; no raw instructor notes. |
| `training_sessions` | Tier 2 | Sports | `private_behavior_summary` | Active local fixture | Activity type, duration, intensity, load, result, and coarse venue bucket. |
| `habit_goals` | Tier 2 | Habits | `private_behavior_summary` | Active local fixture | Weekly target, status, streak, skipped reason bucket, and review date. |
| `personal_notes_summary` | Tier 2 | Notes/learning | `private_behavior_summary` | Active local fixture | Redacted note topic, sentiment bucket, action count, and source file bucket; no raw note body. |
| `trade_journal_summary` | Tier 3 | Trading journal | `private_finance_summary` | Active local fixture | Synthetic or redacted trade setup, risk bucket, result, and lessons; no broker account ids. |
| `market_watchlist_snapshot` | Tier 1 | Market context | `public_context` | Active local fixture | Watchlist symbol bucket, volatility state, and public context signals. |
| `github_project_activity` | Tier 1 | Career/projects | `public_context` | Active local fixture | Repo activity counts, focus area, maintenance gaps, and open-source signals. |
| `learning_activity` | Tier 2 | Learning | `private_behavior_summary` | Active local fixture | Study session duration, topic bucket, progress, and next action. |
| `finance_event_calendar` | Tier 2 | Finance calendar | `private_finance_summary` | Active local fixture | Event buckets and dates from public or local finance calendars; no broker account or position identifiers. |
| `health_summary` | Tier 3 | Health | `private_health_summary` | Active local fixture | Daily aggregate recovery, load, and wellness summaries. |
| `location_area_summary` | Tier 3 | Location | `private_location_summary` | Active local fixture | Broad area bucket, dwell minutes, movement mode, and precision bucket. |
| `data_source_runs` | Tier 1 | DataOps | `derived_context` | Active validator output | Run status, freshness, record counts, quality flags, and missing source gaps. |
| `browser_and_app_usage` | Tier 2 | Digital activity | `private_behavior_summary` | Active local fixture | Category-duration buckets; no URLs, titles, or search queries. |
| `tasks_and_projects` | Tier 2 | Productivity | `private_behavior_summary` | Active local fixture | Status, priority, effort, and project buckets; no task text or client names. |
| `location_visits` | Tier 3 | Location | `private_location_summary` | Active local fixture | Coarse place buckets, dwell time, movement mode, precision bucket. |
| `health_metrics` | Tier 3 | Health | `private_health_summary` | Active local fixture | Daily metric summaries and device class, not raw device exports. |
| `finance_transactions` | Tier 3 | Finance | `private_finance_summary` | Active local fixture | Category, currency, amount bucket, and account bucket. |
| `communications_metadata` | Tier 3 | Communications | `private_communications_summary` | Active local fixture | Channel, direction, contact bucket, and counts only. |
| `identity_documents` | Tier 4 | Identity | `private_identity_document` | Active pointer-only fixture | Document bucket, status, expiry month, reminder bucket, local pointer bucket. |
| `secrets_inventory` | Tier 4 | Security | `secret_credential` | Active pointer-only fixture | Rotation due month, age bucket, vault bucket; never secret material. |

## Universal Envelope

All source exports should converge on the same event envelope:

```yaml
lake_version: lifehub.lake.v1
event_id: deterministic event hash
source_name: source id from source_registry.yaml
source_tier: tier_1_foundation | tier_2_personal_context | tier_3_sensitive_life | tier_4_private_core
source_type: connector or import type
event_type: source-specific event kind
event_time: source event time or aggregate date
ingested_at: local ingestion timestamp
privacy_class: registry privacy class
consent_scope: local_personal_use
subject_id: self or another local pseudonymous subject id
schema_version: source payload version
idempotency_key: deterministic non-secret source key
provenance: connector, fixture, export bucket, and transform version
raw_policy: public_fixture_ok | local_raw_only | no_shared_bronze_raw
local_policy: summarized_landing_only | explicit_opt_in_pointer_only
payload_summary: compact redacted facts safe for evidence
metrics: numeric measures extracted from payload
tags: controlled labels for routing and analysis
quality_flags: validation, freshness, redaction, and completeness flags
payload: privacy-safe source payload
```

Existing runtime code writes the full `lifehub.lake.v1` envelope. New connectors should keep payloads privacy-safe and put evidence-friendly facts into `payload_summary`, `metrics`, `tags`, and `quality_flags` instead of copying raw private text.

## Onboarding Rules

1. Add the source to `config/lifehub/source_registry.yaml` with tier, privacy class, raw policy, local policy, landing path, tables, consumers, commit policy, and onboarding contract.
2. Add or update contract metadata in `contracts/lifehub/data_contract.yaml`.
3. Use synthetic fixtures for public examples. Keep real raw exports outside git.
4. Normalize raw data into the universal envelope before landing.
5. For Tier 2 and Tier 3, remove direct identifiers, raw free text, private coordinates, account numbers, message bodies, and device payloads before landing.
6. For Tier 4, land only pointer metadata after explicit opt-in. Do not copy raw files or secret values into shared Bronze.
7. Public evidence may report counts, schema presence, freshness, and aggregate status only.

## Current Fixture Boundary

Committed fixtures remain synthetic or public-safe:

- Weather, place, market, GitHub, managed URL subscriptions, decision metrics, feedback, weekly review, sleep, calendar, moto learning, trade journal, personal notes, custom events, and context signals use compact fixture payloads.
- `activity_route_spb_public.gpx` is a public synthetic route example. Real GPX/FIT/TCX files stay local.
- No fixture should contain Telegram tokens, chat ids, raw diary notes, pain text, private addresses, bank data, message bodies, document numbers, or secret values.
