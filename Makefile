.PHONY: validate lifehub-tests lifehub-score-fixture lifehub-weekly-review-fixture lifehub-metrics-fixture lifehub-lake-export-fixture lifehub-sleep-fixture lifehub-custom-source-fixture lifehub-source-onboard-demo lifehub-source-subscription-demo lifehub-source-map-demo lifehub-full-source-demo lifehub-lakehouse-runtime-smoke lifehub-demo lifehub-evidence-flow lifehub-evidence-flow-temporal lifehub-evidence-flow-plan lifehub-up-local lifehub-temporal-up lifehub-temporal-start-fixture lifehub-temporal-start-weekly-fixture lifehub-apply-marts lifehub-quality lifehub-lineage lifehub-evidence lifehub-cockpit lifehub-cockpit-demo

validate:
	python scripts/validate_project.py
	docker compose --env-file .env.example config --quiet
	docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.evidence.yml config --quiet
	docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.lakehouse-smoke.yml config --quiet

lifehub-tests:
	PYTHONPATH=infra/lifehub python scripts/run_lifehub_tests.py

lifehub-score-fixture:
	PYTHONPATH=infra/lifehub python -m lifehub.cli score --fixture fixtures/lifehub/open_meteo_clear_day.json

lifehub-weekly-review-fixture:
	PYTHONPATH=infra/lifehub python -m lifehub.cli weekly-report --fixture fixtures/lifehub/open_meteo_clear_day.json --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --signal-fixture fixtures/lifehub/context_signals.json --sleep-fixture fixtures/lifehub/sleep_quality.json

lifehub-metrics-fixture:
	PYTHONPATH=infra/lifehub python -m lifehub.cli metrics --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --metrics-fixture fixtures/lifehub/decision_metrics.json

lifehub-lake-export-fixture:
	rm -rf tmp/lake/lifehub
	PYTHONPATH=infra/lifehub python -m lifehub.cli lake-export --fixture fixtures/lifehub/open_meteo_clear_day.json --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --metrics-fixture fixtures/lifehub/decision_metrics.json --signal-fixture fixtures/lifehub/context_signals.json --activity-file fixtures/lifehub/activity_route_spb_public.gpx --activity-type skate --sleep-fixture fixtures/lifehub/sleep_quality.json --output-root tmp/lake --dt 2026-06-16
	PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import fixtures/lifehub/custom_life_events.json --source-name custom_life_events --output-root tmp/lake --dt 2026-06-16
	python scripts/capture_lifehub_lake_evidence.py

lifehub-sleep-fixture:
	rm -rf tmp/sleep-quality
	PYTHONPATH=infra/lifehub python -m lifehub.cli sleep-import fixtures/lifehub/sleep_quality.json --output-root tmp/sleep-quality --dt 2026-06-16

lifehub-custom-source-fixture:
	rm -rf tmp/custom-source
	PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import fixtures/lifehub/custom_life_events.json --source-name custom_life_events --output-root tmp/custom-source --dt 2026-06-16

lifehub-source-onboard-demo:
	rm -rf tmp/lifehub/source_onboarding/sleep_quality
	PYTHONPATH=infra/lifehub python -m lifehub.cli source-onboard sleep_quality --domain recovery --source-type local_json_event --event-type sleep_metric --required-fields occurred_at,domain,metric_name,metric_value --output-dir tmp/lifehub/source_onboarding

lifehub-source-subscription-demo:
	rm -rf tmp/lake/lifehub/landing/external_source_items
	PYTHONPATH=infra/lifehub python -m lifehub.cli source-list --subscriptions fixtures/lifehub/source_subscriptions.json
	PYTHONPATH=infra/lifehub python -m lifehub.cli source-sync --subscriptions fixtures/lifehub/source_subscriptions.json --fixture fixtures/lifehub/rss_feed.xml --output-root tmp/lake --dt 2026-06-16
	python scripts/validate_lifehub_dataops.py --landing-root tmp/lake --write-source-map docs/evidence/lifehub-source-map-demo.md

lifehub-source-map-demo:
	python scripts/validate_lifehub_dataops.py --write-source-map docs/evidence/lifehub-source-map-demo.md

lifehub-full-source-demo: lifehub-lake-export-fixture
	PYTHONPATH=infra/lifehub python -m lifehub.cli place-sync --fixture fixtures/lifehub/overpass_spots.json --output-root tmp/lake --dt 2026-06-16 --output-only
	PYTHONPATH=infra/lifehub python -m lifehub.cli inbox-scan fixtures/lifehub/local_inbox --output-root tmp/lake --dt 2026-06-16
	PYTHONPATH=infra/lifehub python -m lifehub.cli source-sync --subscriptions fixtures/lifehub/source_subscriptions.json --fixture fixtures/lifehub/rss_feed.xml --output-root tmp/lake --dt 2026-06-16
	python scripts/capture_lifehub_lake_evidence.py
	python scripts/validate_lifehub_dataops.py --landing-root tmp/lake --write-source-map docs/evidence/lifehub-source-map-demo.md

lifehub-lakehouse-runtime-smoke:
	python scripts/run_lifehub_lakehouse_runtime_smoke.py

lifehub-demo: lifehub-tests lifehub-score-fixture
	PYTHONPATH=infra/lifehub python -m lifehub.cli weather-ingest --fixture fixtures/lifehub/open_meteo_clear_day.json --output tmp/lifehub-weather.jsonl
	PYTHONPATH=infra/lifehub python -m lifehub.cli place-sync --fixture fixtures/lifehub/overpass_spots.json --output tmp/lifehub-spots.jsonl --output-only
	PYTHONPATH=infra/lifehub python -m lifehub.cli signal-import --fixture fixtures/lifehub/context_signals.json --output tmp/lifehub-signals.jsonl
	PYTHONPATH=infra/lifehub python -m lifehub.cli github-signal-import --fixture fixtures/lifehub/github_repo_activity.json --output tmp/lifehub-github-signals.jsonl
	PYTHONPATH=infra/lifehub python -m lifehub.cli market-signal-import --fixture fixtures/lifehub/market_snapshot.json --output tmp/lifehub-market-signals.jsonl
	PYTHONPATH=infra/lifehub python -m lifehub.cli weekly-report --fixture fixtures/lifehub/open_meteo_clear_day.json --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --signal-fixture fixtures/lifehub/context_signals.json --sleep-fixture fixtures/lifehub/sleep_quality.json
	PYTHONPATH=infra/lifehub python -m lifehub.cli metrics --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --metrics-fixture fixtures/lifehub/decision_metrics.json
	PYTHONPATH=infra/lifehub python -m lifehub.cli lake-export --fixture fixtures/lifehub/open_meteo_clear_day.json --summary-fixture fixtures/lifehub/week_summary.json --feedback-fixture fixtures/lifehub/feedback_profile.json --metrics-fixture fixtures/lifehub/decision_metrics.json --signal-fixture fixtures/lifehub/context_signals.json --activity-file fixtures/lifehub/activity_route_spb_public.gpx --activity-type skate --sleep-fixture fixtures/lifehub/sleep_quality.json --output-root tmp/lake --dt 2026-06-16
	PYTHONPATH=infra/lifehub python -m lifehub.cli custom-source-import fixtures/lifehub/custom_life_events.json --source-name custom_life_events --output-root tmp/lake --dt 2026-06-16
	python scripts/validate_lifehub_contract.py

lifehub-evidence-flow:
	python scripts/run_lifehub_evidence_flow.py

lifehub-evidence-flow-temporal:
	python scripts/run_lifehub_evidence_flow.py --include-temporal

lifehub-evidence-flow-plan:
	python scripts/run_lifehub_evidence_flow.py --dry-run --include-temporal

lifehub-up-local:
	docker compose --env-file .env -f docker-compose.yml -f docker-compose.evidence.yml --profile lifehub up -d --build postgres clickhouse lifehub-place-sync lifehub-weather-ingest lifehub-score lifehub-signal-import lifehub-github-signal-import lifehub-market-signal-import lifehub-telegram-bot

lifehub-temporal-up:
	docker compose --env-file .env -f docker-compose.yml -f docker-compose.evidence.yml --profile temporal up -d --build postgres clickhouse temporal lifehub-temporal-worker

lifehub-temporal-start-fixture:
	docker compose --env-file .env -f docker-compose.yml -f docker-compose.evidence.yml --profile temporal run --rm lifehub-temporal-worker python -m lifehub.temporal.starter --weather-fixture /workspace/fixtures/lifehub/open_meteo_clear_day.json --places-fixture /workspace/fixtures/lifehub/overpass_spots.json --signal-fixture /workspace/fixtures/lifehub/context_signals.json

lifehub-temporal-start-weekly-fixture:
	docker compose --env-file .env -f docker-compose.yml -f docker-compose.evidence.yml --profile temporal run --rm lifehub-temporal-worker python -m lifehub.temporal.starter --workflow weekly --weather-fixture /workspace/fixtures/lifehub/open_meteo_clear_day.json --summary-fixture /workspace/fixtures/lifehub/week_summary.json --feedback-fixture /workspace/fixtures/lifehub/feedback_profile.json --metrics-fixture /workspace/fixtures/lifehub/decision_metrics.json --signal-fixture /workspace/fixtures/lifehub/context_signals.json

lifehub-apply-marts:
	docker compose --env-file .env -f docker-compose.yml -f docker-compose.evidence.yml --profile lifehub exec -T clickhouse clickhouse-client --multiquery < sql/lifehub/clickhouse_lifehub_marts.sql

lifehub-quality:
	python scripts/lifehub_quality_check.py

lifehub-lineage:
	python scripts/emit_lifehub_lineage.py

lifehub-evidence:
	python scripts/capture_lifehub_evidence.py

lifehub-cockpit:
	python scripts/build_lifehub_cockpit.py

lifehub-cockpit-demo:
	python scripts/build_lifehub_cockpit.py --demo
