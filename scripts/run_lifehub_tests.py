#!/usr/bin/env python3
"""Dependency-free unit tests for LifeHub core logic."""

from __future__ import annotations

import unittest
import json
import os
import subprocess
import sys
import importlib.util
import tempfile
from pathlib import Path

from lifehub.activity_files import parse_gpx
from lifehub.config import load_locations, load_preferences, load_scoring
from lifehub.context import build_daily_context_profile, extract_confidence_and_gaps, render_daily_context_profile
from lifehub.diary import capture_to_activity_log, command_name, parse_capture_command, parse_log_command
from lifehub.feedback import feedback_keyboard, parse_feedback_callback, parse_feedback_command
from lifehub.generic_sources import custom_source_events, load_json_rows
from lifehub.local_files import detect_local_kind, import_local_file, scan_inbox
from lifehub.places import load_spot_fixture, place_spot_events
from lifehub.recommendations import (
    build_recommendations,
    render_coach_summary,
    render_goal_summary,
    render_weekly_intelligence_report,
    render_progress_scorecard,
    weekly_activity_counts,
)
from lifehub.scoring import score_readiness
from lifehub.signals import load_github_fixture, load_market_fixture, load_signal_fixture, normalize_signals
from lifehub.sleep import load_sleep_fixture, normalize_sleep_rows, sleep_quality_events, summarize_sleep
from lifehub.source_onboarding import (
    SourceOnboardingSpec,
    apply_registry_entry,
    registry_entry,
    write_onboarding_package,
)
from lifehub.source_subscriptions import (
    add_subscription,
    infer_source_type,
    load_subscriptions,
    parse_source_add_command,
    remove_subscription,
    render_subscriptions,
    set_subscription_enabled,
    subscription_events,
)
from lifehub.storage import clickhouse_datetime
from lifehub.weather import load_fixture, normalize_weather
from lifehub.lake import activity_file_events, lake_envelope, write_landing_events


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "lifehub"


class WeatherTests(unittest.TestCase):
    def test_normalizes_open_meteo_fixture(self) -> None:
        payload = load_fixture(FIXTURES / "open_meteo_clear_day.json")
        rows = normalize_weather(payload, "spb_center")
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0].location_id, "spb_center")
        self.assertEqual(rows[0].temperature_c, 16.0)
        self.assertTrue(rows[0].is_day)


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_scoring(ROOT / "config" / "lifehub" / "scoring.yaml")

    def score_fixture(self, name: str):
        payload = load_fixture(FIXTURES / name)
        return score_readiness(normalize_weather(payload, "spb_center"), self.config)

    def by_activity(self, scores):
        return {score.activity: score for score in scores}

    def test_clear_day_rewards_skate_and_moto(self) -> None:
        scores = self.by_activity(self.score_fixture("open_meteo_clear_day.json"))
        self.assertGreaterEqual(scores["skate"].score, 75)
        self.assertGreaterEqual(scores["moto_lesson"].score, 75)

    def test_rain_day_penalizes_skate_and_moto(self) -> None:
        scores = self.by_activity(self.score_fixture("open_meteo_rain_day.json"))
        self.assertLess(scores["skate"].score, 60)
        self.assertLess(scores["moto_lesson"].score, 60)

    def test_snow_day_rewards_snowboard(self) -> None:
        scores = self.by_activity(self.score_fixture("open_meteo_snow_day.json"))
        self.assertGreaterEqual(scores["snowboard"].score, 70)


class RecommendationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_scoring(ROOT / "config" / "lifehub" / "scoring.yaml")

    def scores(self):
        payload = load_fixture(FIXTURES / "open_meteo_clear_day.json")
        return score_readiness(normalize_weather(payload, "spb_center"), self.config)

    def test_high_fatigue_turns_go_into_caution_or_recover(self) -> None:
        recommendations = build_recommendations(
            self.scores(),
            {"sessions": 4, "avg_fatigue": 8, "avg_mood": 7, "pain_sessions": 0},
        )
        skate = next(item for item in recommendations if item.activity == "skate")
        self.assertIn(skate.decision, {"caution", "recover"})
        self.assertIn("recent fatigue is high", skate.reasons)

    def test_low_sleep_recovery_penalizes_high_impact_recommendations(self) -> None:
        baseline = next(item for item in build_recommendations(self.scores()) if item.activity == "skate")
        adjusted = next(
            item
            for item in build_recommendations(
                self.scores(),
                recovery_summary={"latest_recovery_score": 50, "latest_duration_minutes": 360},
            )
            if item.activity == "skate"
        )
        self.assertLess(adjusted.score, baseline.score)
        self.assertIn(adjusted.decision, {"caution", "recover"})
        self.assertIn("sleep recovery is low", adjusted.reasons)
        self.assertIn("sleep duration was short", adjusted.reasons)

    def test_pain_signal_affects_recommendation(self) -> None:
        recommendations = build_recommendations(
            self.scores(),
            {"sessions": 2, "avg_fatigue": 4, "avg_mood": 7, "pain_sessions": 1},
        )
        self.assertTrue(any("pain was logged this week" in item.reasons for item in recommendations))

    def test_positive_feedback_boosts_recommendation(self) -> None:
        baseline = next(item for item in build_recommendations(self.scores()) if item.activity == "skate")
        learned = next(
            item
            for item in build_recommendations(
                self.scores(),
                feedback_profile={
                    "skate": {
                        "feedback_events": 3,
                        "follow_rate": 1.0,
                        "good_results": 2,
                        "bad_results": 0,
                        "skipped_events": 0,
                    }
                },
            )
            if item.activity == "skate"
        )
        self.assertGreaterEqual(learned.score, baseline.score)
        self.assertIn("recent feedback says this is usually followed", learned.reasons)

    def test_weekly_goal_gap_boosts_recommendation(self) -> None:
        recommendations = build_recommendations(
            self.scores(),
            {"sessions": 1, "by_activity": [{"activity_type": "skate", "sessions": 0}]},
            preferences={
                "weekly_goals": {"skate": 2},
                "priority_activities": {"skate": 9},
                "recommendation_policy": {"under_target_boost": 7, "high_priority_boost": 3, "max_goal_boost": 10},
            },
        )
        skate = next(item for item in recommendations if item.activity == "skate")
        self.assertIn("weekly goal gap 0/2", skate.reasons)
        self.assertIn("high priority activity", skate.reasons)

    def test_coach_summary_reports_goal_gaps(self) -> None:
        text = render_coach_summary(
            {"sessions": 1, "avg_fatigue": 4, "avg_mood": 7, "pain_sessions": 0, "by_activity": []},
            [],
            {"weekly_goals": {"skate": 2}},
        )
        self.assertIn("Goal gaps: skate 0/2", text)

    def test_goal_summary_reports_open_and_covered_goals(self) -> None:
        text = render_goal_summary(
            {"by_activity": [{"activity_type": "skate", "sessions": 2}]},
            {"weekly_goals": {"skate": 2, "volleyball": 1}},
        )
        self.assertIn("skate: 2/2 (covered)", text)
        self.assertIn("volleyball: 0/1 (open)", text)

    def test_negative_feedback_penalizes_recommendation(self) -> None:
        learned = next(
            item
            for item in build_recommendations(
                self.scores(),
                feedback_profile={
                    "moto_lesson": {
                        "feedback_events": 3,
                        "follow_rate": 0.0,
                        "good_results": 0,
                        "bad_results": 1,
                        "skipped_events": 3,
                    }
                },
            )
            if item.activity == "moto_lesson"
        )
        self.assertLess(learned.score, 100)
        self.assertIn("recent feedback says this is often skipped", learned.reasons)

    def test_coach_summary_without_sessions(self) -> None:
        text = render_coach_summary({"sessions": 0}, [])
        self.assertIn("no sessions logged", text)

    def test_weekly_intelligence_report_closes_decision_loop(self) -> None:
        recommendations = build_recommendations(
            self.scores(),
            {
                "sessions": 3,
                "avg_fatigue": 5,
                "avg_mood": 7,
                "pain_sessions": 0,
                "by_activity": [{"activity_type": "skate", "sessions": 1}],
                "by_result": [{"result": "good", "sessions": 2}],
            },
            feedback_profile={
                "skate": {
                    "feedback_events": 4,
                    "follow_rate": 0.75,
                    "good_results": 2,
                    "bad_results": 0,
                    "skipped_events": 1,
                }
            },
            preferences={"weekly_goals": {"skate": 2, "volleyball": 1}},
        )
        text = render_weekly_intelligence_report(
            {
                "sessions": 3,
                "avg_fatigue": 5,
                "avg_mood": 7,
                "pain_sessions": 0,
                "by_activity": [{"activity_type": "skate", "sessions": 1}],
                "by_result": [{"result": "good", "sessions": 2}],
            },
            recommendations,
            {"skate": {"feedback_events": 4, "follow_rate": 0.75, "good_results": 2}},
            {"weekly_goals": {"skate": 2, "volleyball": 1}},
            [],
        )
        self.assertIn("LifeHub weekly review", text)
        self.assertIn("Open goals: skate 1/2, volleyball 0/1", text)
        self.assertIn("Learning: skate has follow rate 0.75", text)
        self.assertIn("Best next action now:", text)

    def test_progress_scorecard_reports_north_star_and_next_move(self) -> None:
        text = render_progress_scorecard(
            {
                "sessions": 5,
                "by_activity": [{"activity_type": "skate", "sessions": 2}],
            },
            {"useful_decision_days": 3, "followed_events": 4, "skipped_events": 1, "follow_rate": 0.8},
            {"skate": {"feedback_events": 4, "follow_rate": 0.75}},
            {"weekly_goals": {"skate": 2, "volleyball": 1}},
        )
        self.assertIn("North Star: useful decision days 3/7", text)
        self.assertIn("Feedback: 4 followed, 1 skipped, follow rate 80%", text)
        self.assertIn("Weekly goals covered: 1/2", text)
        self.assertIn("Open goal gaps: volleyball 0/1", text)


class DailyContextProfileTests(unittest.TestCase):
    def test_builds_privacy_safe_daily_context_profile(self) -> None:
        scoring = load_scoring(ROOT / "config" / "lifehub" / "scoring.yaml")
        scores = score_readiness(
            normalize_weather(load_fixture(FIXTURES / "open_meteo_clear_day.json"), "spb_center"),
            scoring,
        )
        week_summary = {
            "sessions": 5,
            "avg_mood": 7,
            "avg_fatigue": 5,
            "pain_sessions": 0,
            "by_activity": [{"activity_type": "skate", "sessions": 1}],
        }
        preferences = {"weekly_goals": {"skate": 2, "volleyball": 1}}
        recommendations = build_recommendations(scores, week_summary, {}, preferences)
        profile = build_daily_context_profile(
            recommendations,
            week_summary,
            {"useful_decision_days": 3, "follow_rate": 0.8},
            load_signal_fixture(FIXTURES / "context_signals.json"),
            preferences,
        )

        self.assertEqual(profile.top_activity, "skate")
        self.assertEqual(profile.useful_decision_days_7d, 3)
        self.assertEqual(profile.open_goal_count, 2)
        self.assertGreater(profile.signal_count_7d, 0)
        self.assertNotIn("pain_text", profile.context_summary)

    def test_daily_context_profile_names_sleep_recovery(self) -> None:
        scoring = load_scoring(ROOT / "config" / "lifehub" / "scoring.yaml")
        scores = score_readiness(
            normalize_weather(load_fixture(FIXTURES / "open_meteo_clear_day.json"), "spb_center"),
            scoring,
        )
        recovery = summarize_sleep(normalize_sleep_rows(load_sleep_fixture(FIXTURES / "sleep_quality.json")))
        recommendations = build_recommendations(scores, recovery_summary=recovery)
        profile = build_daily_context_profile(recommendations, {}, {}, [], {}, recovery_summary=recovery)
        self.assertIn("sleep_recovery=", profile.context_summary)
        self.assertIn("sleep_minutes=", profile.context_summary)

    def test_daily_context_render_names_decision_loop(self) -> None:
        profile = build_daily_context_profile([], {}, {}, [], {})
        text = render_daily_context_profile(profile)
        self.assertIn("LifeHub daily context profile", text)
        self.assertIn("Decision quality", text)
        self.assertIn("Profile confidence:", text)
        self.assertIn("Data gaps:", text)

    def test_daily_context_profiles_data_gaps_from_missing_sources(self) -> None:
        profile = build_daily_context_profile([], {}, {}, [], {})
        confidence, gaps = extract_confidence_and_gaps(profile.context_summary)
        self.assertLess(confidence, 100)
        self.assertIn("activity_diary_empty", gaps)
        self.assertIn("sleep_recovery_missing", gaps)


class LakeExportTests(unittest.TestCase):
    def test_lake_envelope_is_privacy_classed(self) -> None:
        event = lake_envelope(
            source_name="context_signals",
            event_type="context_signal",
            event_time="2026-06-16T08:00:00+00:00",
            privacy_class="context_signal",
            payload={"signal_id": "demo"},
        )
        self.assertEqual(event["lake_version"], "lifehub.lake.v1")
        self.assertEqual(event["privacy_class"], "context_signal")
        self.assertNotIn("TELEGRAM_BOT_TOKEN", str(event))

    def test_write_landing_events_uses_medallion_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            written = write_landing_events(
                [
                    lake_envelope(
                        source_name="daily_context_profile",
                        event_type="daily_context_profile",
                        event_time="2026-06-16T08:00:00+00:00",
                        payload={"top_activity": "skate"},
                    )
                ],
                Path(tmpdir),
                "2026-06-16",
            )
            paths = list(written)
            self.assertEqual(len(paths), 1)
            self.assertIn("lifehub/landing/daily_context_profile/dt=2026-06-16/events.jsonl", paths[0])
            self.assertTrue(Path(paths[0]).exists())

    def test_gpx_activity_file_becomes_lake_event(self) -> None:
        summary = parse_gpx(FIXTURES / "activity_route_spb_public.gpx", activity_type="skate")
        self.assertEqual(summary.activity_type, "skate")
        self.assertGreater(summary.distance_km, 0.5)
        self.assertEqual(summary.point_count, 5)
        events = activity_file_events([summary])
        self.assertEqual(events[0]["source_name"], "activity_files")
        self.assertEqual(events[0]["event_type"], "activity_file_summary")
        self.assertNotIn("home_address", str(events[0]))

    def test_custom_source_import_redacts_sensitive_fields(self) -> None:
        rows = load_json_rows(FIXTURES / "custom_life_events.json")
        events = custom_source_events(
            source_name="custom_life_events",
            rows=rows,
            registry_path=ROOT / "config" / "lifehub" / "source_registry.yaml",
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["source_name"], "custom_life_events")
        serialized = str(events)
        self.assertNotIn("home_address", serialized)
        self.assertNotIn("note", serialized)
        self.assertNotIn("redacted by importer", serialized)

    def test_custom_source_import_requires_registered_source(self) -> None:
        rows = load_json_rows(FIXTURES / "custom_life_events.json")
        with self.assertRaises(ValueError):
            custom_source_events(
                source_name="unregistered_source",
                rows=rows,
                registry_path=ROOT / "config" / "lifehub" / "source_registry.yaml",
            )

    def test_source_onboarding_package_can_feed_custom_import(self) -> None:
        spec = SourceOnboardingSpec(
            source_name="sleep_quality",
            domain="recovery",
            source_type="local_json_event",
            producer="lifehub-sleep-quality-import",
            consumers=["daily_context_profile"],
            required_fields=["occurred_at", "domain", "metric_name", "metric_value"],
            event_time_field="occurred_at",
            idempotency_key=["domain", "metric_name", "occurred_at"],
            pii=False,
            privacy_class="custom_local_summary",
            event_type="sleep_metric",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = write_onboarding_package(spec, tmp)
            registry = tmp / "source_registry.yaml"
            registry.write_text(
                "version: 1\nsources:\nnew_source_template:\n  steps: []\n",
                encoding="utf-8",
            )
            apply_registry_entry(registry, registry_entry(spec), spec.source_name)
            rows = load_json_rows(paths["fixture"])
            events = custom_source_events(
                source_name=spec.source_name,
                rows=rows,
                registry_path=registry,
                event_type=spec.event_type,
                privacy_class=spec.privacy_class,
            )
            self.assertEqual(events[0]["source_name"], "sleep_quality")
            self.assertEqual(events[0]["event_type"], "sleep_metric")
            self.assertTrue(paths["runbook"].exists())
            self.assertIn("make lifehub-lakehouse-runtime-smoke", paths["runbook"].read_text(encoding="utf-8"))

    def test_sleep_quality_fixture_becomes_lake_events(self) -> None:
        rows = normalize_sleep_rows(load_sleep_fixture(FIXTURES / "sleep_quality.json"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].duration_minutes, 475)
        self.assertGreater(rows[0].sleep_efficiency, 0.9)
        events = sleep_quality_events(rows)
        self.assertEqual(events[0]["source_name"], "sleep_quality")
        self.assertEqual(events[0]["event_type"], "sleep_quality_night")
        self.assertNotIn("note", str(events).lower())


class LocalSummaryImportTests(unittest.TestCase):
    def test_summary_fixtures_auto_detect_and_land(self) -> None:
        cases = {
            "training_sessions.json": "training_sessions",
            "habit_goals.json": "habit_goals",
            "market_watchlist_snapshot.json": "market_watchlist_snapshot",
            "github_project_activity_summary.json": "github_project_activity",
            "learning_activity.json": "learning_activity",
            "finance_event_calendar.json": "finance_event_calendar",
            "health_summary.json": "health_summary",
            "location_area_summary.json": "location_area_summary",
            "finance_transactions_summary.json": "finance_transactions",
            "data_source_runs.json": "data_source_runs",
            "digital_activity.json": "browser_and_app_usage",
            "tasks_projects.json": "tasks_and_projects",
            "communications_summary.json": "communications_metadata",
            "location_visits.json": "location_visits",
            "health_metrics.json": "health_metrics",
            "identity_pointers.json": "identity_documents",
            "credential_rotation.json": "secrets_inventory",
        }
        for fixture_name, source_name in cases.items():
            path = FIXTURES / fixture_name
            self.assertEqual(detect_local_kind(path), source_name)
            events = import_local_file(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["source_name"], source_name)
            self.assertIn("summary_only", events[0]["quality_flags"])
            serialized = json.dumps(events[0], sort_keys=True)
            for forbidden in ["home_address", "account_id", "account_number", "chat_id", "api_key"]:
                self.assertNotIn(forbidden, serialized)

    def test_inbox_scan_imports_expanded_domain_coverage(self) -> None:
        imports = scan_inbox(FIXTURES / "local_inbox")
        observed = {event["source_name"] for _path, _kind, events in imports for event in events}
        for source_name in {
            "calendar_events",
            "moto_learning_log",
            "personal_notes_summary",
            "sleep_quality",
            "trade_journal_summary",
            "training_sessions",
            "habit_goals",
            "market_watchlist_snapshot",
            "github_project_activity",
            "learning_activity",
            "finance_event_calendar",
            "health_summary",
            "location_area_summary",
            "finance_transactions",
            "data_source_runs",
            "browser_and_app_usage",
            "tasks_and_projects",
            "communications_metadata",
            "location_visits",
            "health_metrics",
            "identity_documents",
            "secrets_inventory",
        }:
            self.assertIn(source_name, observed)


class DiaryTests(unittest.TestCase):
    def test_parse_log_command(self) -> None:
        log = parse_log_command("/log skate 7 8 4 good dry session")
        self.assertEqual(log.activity_type, "skate")
        self.assertIsNone(log.location_label)
        self.assertEqual(log.intensity, 7)
        self.assertEqual(log.mood, 8)
        self.assertEqual(log.fatigue, 4)
        self.assertFalse(log.pain_flag)
        self.assertEqual(log.result, "good")
        self.assertEqual(log.notes, "dry session")

    def test_parse_detailed_log_command(self) -> None:
        log = parse_log_command(
            "/log activity=moto_lesson intensity=6 mood=7 fatigue=5 "
            "result=ok loc=training_ground pain=yes pain_text=wrist notes=slow_turns"
        )
        self.assertEqual(log.activity_type, "moto_lesson")
        self.assertEqual(log.location_label, "training ground")
        self.assertTrue(log.pain_flag)
        self.assertEqual(log.pain_text, "wrist")
        self.assertEqual(log.notes, "slow turns")

    def test_rejects_unknown_activity(self) -> None:
        with self.assertRaises(ValueError):
            parse_log_command("/log chess 7 8 4 good notes")

    def test_command_name(self) -> None:
        self.assertEqual(command_name("/today now"), "/today")
        self.assertEqual(command_name("hello"), "")

    def test_parse_quick_capture_commands(self) -> None:
        sleep = parse_capture_command("/sleep 7.5h quality=82 recovery=76")
        self.assertEqual(sleep.capture_type, "sleep")
        self.assertEqual(sleep.value, 450)
        self.assertEqual(sleep.payload["quality"], "82")

        mood = parse_capture_command("/mood 8 calm_focus")
        self.assertEqual(mood.domain, "wellbeing")
        self.assertEqual(mood.value, 8)
        self.assertEqual(mood.note, "calm focus")

        pain = parse_capture_command("/pain 4 wrist")
        self.assertTrue(pain.pain_flag)
        self.assertEqual(pain.value, 4)

    def test_moto_capture_can_become_activity_log(self) -> None:
        capture = parse_capture_command("/moto 6 good cones pain=no mood=7 fatigue=4")
        log = capture_to_activity_log(capture)
        self.assertIsNotNone(log)
        assert log
        self.assertEqual(log.activity_type, "moto_lesson")
        self.assertEqual(log.result, "good")
        self.assertEqual(log.intensity, 6)
        self.assertEqual(log.mood, 7)


class FeedbackTests(unittest.TestCase):
    def test_parse_done_command(self) -> None:
        feedback = parse_feedback_command("/done skate good dry_session")
        self.assertEqual(feedback.activity, "skate")
        self.assertEqual(feedback.action, "followed")
        self.assertEqual(feedback.result, "good")
        self.assertEqual(feedback.note, "dry session")

    def test_parse_skip_command(self) -> None:
        feedback = parse_feedback_command("/skip moto_lesson rain")
        self.assertEqual(feedback.activity, "moto_lesson")
        self.assertEqual(feedback.action, "skipped")
        self.assertEqual(feedback.result, "skipped")

    def test_rejects_unknown_feedback_activity(self) -> None:
        with self.assertRaises(ValueError):
            parse_feedback_command("/done chess good")

    def test_parse_done_callback(self) -> None:
        feedback = parse_feedback_callback("lhfb:done:skate:good")
        self.assertEqual(feedback.activity, "skate")
        self.assertEqual(feedback.action, "followed")
        self.assertEqual(feedback.result, "good")

    def test_parse_skip_callback(self) -> None:
        feedback = parse_feedback_callback("lhfb:skip:snowboard:skipped")
        self.assertEqual(feedback.activity, "snowboard")
        self.assertEqual(feedback.action, "skipped")
        self.assertEqual(feedback.result, "skipped")

    def test_feedback_keyboard_has_compact_callback_data(self) -> None:
        keyboard = feedback_keyboard("skate")
        callbacks = [
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
        ]
        self.assertIn("lhfb:done:skate:good", callbacks)
        self.assertTrue(all(len(value) <= 64 for value in callbacks))


class ConfigTests(unittest.TestCase):
    def test_loads_locations(self) -> None:
        locations = load_locations(ROOT / "config" / "lifehub" / "locations.yaml")
        self.assertGreaterEqual(len(locations), 3)
        self.assertEqual(locations[0].id, "spb_center")

    def test_loads_preferences(self) -> None:
        preferences = load_preferences(ROOT / "config" / "lifehub" / "preferences.yaml")
        self.assertEqual(preferences["weekly_goals"]["skate"], 2)
        self.assertGreaterEqual(preferences["priority_activities"]["moto_lesson"], 8)

    def test_weekly_activity_counts(self) -> None:
        counts = weekly_activity_counts({"by_activity": [{"activity_type": "skate", "sessions": 2}]})
        self.assertEqual(counts["skate"], 2)


class PlaceTests(unittest.TestCase):
    def test_normalizes_overpass_fixture(self) -> None:
        spots = load_spot_fixture(FIXTURES / "overpass_spots.json")
        self.assertEqual(len(spots), 2)
        self.assertIn("skate", spots[0].tags)
        self.assertEqual(spots[0].source, "overpass")

    def test_place_spots_become_lake_events(self) -> None:
        spots = load_spot_fixture(FIXTURES / "overpass_spots.json")
        events = place_spot_events(spots)
        self.assertEqual(events[0]["source_name"], "place_spots")
        self.assertEqual(events[0]["privacy_class"], "public_context")
        self.assertIn("latitude", events[0]["payload"])


class SignalTests(unittest.TestCase):
    def test_loads_context_signal_fixture(self) -> None:
        signals = load_signal_fixture(FIXTURES / "context_signals.json")
        self.assertEqual(len(signals), 3)
        self.assertEqual(signals[0].domain, "market")
        self.assertGreaterEqual(signals[0].urgency, 1)

    def test_rejects_unknown_signal_domain(self) -> None:
        with self.assertRaises(ValueError):
            normalize_signals({"signals": [{"domain": "private", "title": "bad"}]})

    def test_loads_github_repo_activity_fixture(self) -> None:
        signals = load_github_fixture(FIXTURES / "github_repo_activity.json")
        self.assertEqual(len(signals), 2)
        self.assertTrue(all(signal.domain == "github" for signal in signals))
        backlog = next(signal for signal in signals if "Issue backlog" in signal.title)
        self.assertEqual(backlog.direction, "negative")
        self.assertGreaterEqual(backlog.urgency, 6)

    def test_loads_market_snapshot_fixture(self) -> None:
        signals = load_market_fixture(FIXTURES / "market_snapshot.json")
        self.assertEqual(len(signals), 2)
        self.assertTrue(all(signal.domain == "market" for signal in signals))
        self.assertTrue(any(signal.title == "Market volatility watch" for signal in signals))


class SourceSubscriptionTests(unittest.TestCase):
    def test_infers_common_managed_source_types(self) -> None:
        self.assertEqual(infer_source_type("https://t.me/s/public_channel"), "telegram_channel")
        self.assertEqual(infer_source_type("https://example.com/feed.xml"), "rss_feed")
        self.assertEqual(infer_source_type("wss://example.com/events"), "event_stream")
        self.assertEqual(infer_source_type("https://example.com/api/items.json"), "api_json")
        self.assertEqual(infer_source_type("https://example.com/news/story"), "news_url")

    def test_add_pause_resume_remove_subscription(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "subscriptions.json"
            subscription, created = add_subscription(
                path,
                "https://example.com/feed.xml",
                label="Demo Feed",
                domain="news",
                tags=["spb", "demo"],
            )
            self.assertTrue(created)
            self.assertEqual(subscription.source_type, "rss_feed")
            self.assertEqual(len(load_subscriptions(path)), 1)
            paused = set_subscription_enabled(path, subscription.subscription_id[:8], False)
            self.assertFalse(paused.enabled)
            resumed = set_subscription_enabled(path, subscription.subscription_id[:8], True)
            self.assertTrue(resumed.enabled)
            removed = remove_subscription(path, subscription.subscription_id[:8])
            self.assertEqual(removed.subscription_id, subscription.subscription_id)
            self.assertEqual(load_subscriptions(path), [])

    def test_parse_source_add_command(self) -> None:
        parsed = parse_source_add_command(
            "/source_add rss_feed https://example.com/feed.xml label=MarketFeed domain=trading tags=market,watchlist"
        )
        self.assertEqual(parsed["source_type"], "rss_feed")
        self.assertEqual(parsed["reference"], "https://example.com/feed.xml")
        self.assertEqual(parsed["label"], "MarketFeed")
        self.assertEqual(parsed["domain"], "trading")
        self.assertIn("market", parsed["tags"])

    def test_rss_subscription_becomes_privacy_safe_landing_events(self) -> None:
        subscriptions = load_subscriptions(FIXTURES / "source_subscriptions.json")
        events = subscription_events(subscriptions, fixture=FIXTURES / "rss_feed.xml")
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event["source_name"] == "external_source_items" for event in events))
        self.assertTrue(all("reference_hash" in event["payload"] for event in events))
        self.assertTrue(all("https://example.com" not in json.dumps(event["payload"]) for event in events))
        self.assertIn("title_preview", events[0]["payload_summary"])

    def test_render_subscriptions_names_short_ids(self) -> None:
        text = render_subscriptions(FIXTURES / "source_subscriptions.json")
        self.assertIn("LifeHub source subscriptions", text)
        self.assertIn("Synthetic RSS demo", text)


class StorageTests(unittest.TestCase):
    def test_clickhouse_datetime_normalization(self) -> None:
        self.assertEqual(
            clickhouse_datetime("2026-06-15T08:00:00+00:00"),
            "2026-06-15 08:00:00",
        )


class TemporalContractTests(unittest.TestCase):
    def test_score_send_telegram_does_not_require_recommendations(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "infra" / "lifehub")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lifehub.cli",
                "score",
                "--fixture",
                str(FIXTURES / "open_meteo_clear_day.json"),
                "--send-telegram",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LifeHub today:", result.stdout)

    def test_today_recommendation_sends_feedback_keyboard(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn("feedback_keyboard(recommendations[0].activity)", text)
        self.assertIn("handle_telegram_callback", text)

    def test_weekly_review_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("weekly-report")', text)
        self.assertIn('name == "/review"', text)

    def test_metrics_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("metrics")', text)
        self.assertIn('name == "/metrics"', text)

    def test_capture_sources_and_data_gaps_commands_are_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("capture")', text)
        self.assertIn('sub.add_parser("sources")', text)
        self.assertIn('sub.add_parser("data-gaps")', text)
        self.assertIn('name == "/sources"', text)
        self.assertIn('name == "/data_gaps"', text)
        self.assertIn("CAPTURE_COMMANDS", text)

    def test_managed_source_commands_are_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        for phrase in [
            'sub.add_parser("source-add")',
            'sub.add_parser("source-list")',
            'sub.add_parser("source-pause")',
            'sub.add_parser("source-resume")',
            'sub.add_parser("source-remove")',
            'sub.add_parser("source-sync")',
            "handle_source_subscription_command",
            "/source_add",
            "/source_list",
            "/source_sync",
        ]:
            self.assertIn(phrase, text)

    def test_daily_workflow_orchestrates_expected_steps(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/temporal/workflows.py").read_text(encoding="utf-8")
        for phrase in [
            "LifeHubDailyDecisionWorkflow",
            "def status",
            "ingest_weather",
            "sync_places",
            "import_context_signals",
            "compute_daily_recommendations",
            "build_daily_context",
            "execute_activity",
        ]:
            self.assertIn(phrase, text)

    def test_weekly_workflow_orchestrates_review_and_metrics(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/temporal/workflows.py").read_text(encoding="utf-8")
        for phrase in [
            "LifeHubWeeklyReviewWorkflow",
            "building_weekly_review",
            "building_metrics",
            "build_weekly_review",
            "build_progress_metrics",
            "def status",
        ]:
            self.assertIn(phrase, text)

    def test_temporal_activities_are_importable_without_temporal_runtime(self) -> None:
        import lifehub.temporal.activities as activities

        self.assertTrue(callable(activities.ingest_weather))
        self.assertTrue(callable(activities.sync_places))
        self.assertTrue(callable(activities.build_daily_context))
        self.assertTrue(callable(activities.build_weekly_review))
        self.assertTrue(callable(activities.build_progress_metrics))

    def test_temporal_worker_registers_weekly_workflow(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/temporal/worker.py").read_text(encoding="utf-8")
        self.assertIn("LifeHubWeeklyReviewWorkflow", text)
        self.assertIn("build_daily_context", text)
        self.assertIn("build_weekly_review", text)
        self.assertIn("build_progress_metrics", text)

    def test_temporal_starter_supports_weekly_mode(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/temporal/starter.py").read_text(encoding="utf-8")
        self.assertIn('choices=["daily", "weekly"]', text)
        self.assertIn("LifeHubWeeklyReviewWorkflow", text)
        self.assertIn("summary_fixture", text)
        self.assertIn("metrics_fixture", text)


class EvidenceFlowTests(unittest.TestCase):
    def test_evidence_flow_extracts_expected_json_payload(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_lifehub_evidence_flow",
            ROOT / "scripts" / "run_lifehub_evidence_flow.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        payload = module.extract_json_with_keys(
            (
                'build log {"top": "nested"}\n'
                '{"weather": {"weather_rows": 112}, "recommendations": {"recommendations": 4}, '
                '"daily_context": {"readiness_state": "trusted_go"}}\n'
            ),
            {"weather", "recommendations", "daily_context"},
        )
        self.assertEqual(payload["weather"]["weather_rows"], 112)
        self.assertEqual(payload["recommendations"]["recommendations"], 4)
        self.assertEqual(payload["daily_context"]["readiness_state"], "trusted_go")

    def test_evidence_flow_dry_run_contains_ordered_product_steps(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_lifehub_evidence_flow.py",
                "--dry-run",
                "--include-temporal",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        for phrase in [
            "up -d --build postgres clickhouse",
            "place-sync --fixture",
            "weather-ingest --fixture",
            "recommend --fixture",
            "context-profile --fixture",
            "lifehub.temporal.starter --weather-fixture",
            "lifehub.temporal.starter --workflow weekly",
            "lifehub_quality_check.py",
            "capture_lifehub_evidence.py",
            "build_lifehub_cockpit.py",
        ]:
            self.assertIn(phrase, output)

    def test_cli_log_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("log")', text)
        self.assertIn("cmd_log", text)

    def test_cli_context_profile_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("context-profile")', text)
        self.assertIn("cmd_context_profile", text)

    def test_cli_lake_export_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("lake-export")', text)
        self.assertIn("cmd_lake_export", text)

    def test_cli_activity_file_import_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("activity-file-import")', text)
        self.assertIn("cmd_activity_file_import", text)

    def test_cli_sleep_import_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("sleep-import")', text)
        self.assertIn("cmd_sleep_import", text)
        self.assertIn("--sleep-fixture", text)

    def test_cli_custom_source_import_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("custom-source-import")', text)
        self.assertIn("cmd_custom_source_import", text)

    def test_cli_source_onboard_command_is_registered(self) -> None:
        text = (ROOT / "infra/lifehub/lifehub/cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("source-onboard")', text)
        self.assertIn("cmd_source_onboard", text)

    def test_lakehouse_runtime_smoke_targets_real_dwh_tables(self) -> None:
        text = (ROOT / "scripts" / "run_lifehub_lakehouse_runtime_smoke.py").read_text(encoding="utf-8")
        self.assertIn("spark-submit", text)
        self.assertIn("iceberg.bronze.lifehub_events", text)
        self.assertIn("iceberg.silver.lifehub_events", text)
        self.assertIn("iceberg.gold.lifehub_decision_events", text)
        self.assertIn("trino", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
