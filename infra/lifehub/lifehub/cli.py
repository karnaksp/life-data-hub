"""LifeHub command line entrypoints."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from zoneinfo import ZoneInfo

from lifehub.activity_files import parse_gpx
from lifehub.context import build_daily_context_profile, render_daily_context_profile
from lifehub.config import env_config, load_locations, load_preferences, load_scoring
from lifehub.diary import command_name, parse_log_command
from lifehub.feedback import feedback_keyboard, parse_feedback_callback, parse_feedback_command
from lifehub.generic_sources import custom_source_events, load_json_rows
from lifehub.lake import (
    activity_file_events,
    daily_context_events,
    decision_metrics_events,
    recommendation_events,
    signal_events,
    weather_events,
    week_summary_events,
    write_landing_events,
    write_landing_manifest,
)
from lifehub.places import fetch_overpass_spots, load_spot_fixture
from lifehub.recommendations import (
    build_recommendations,
    render_coach_summary,
    render_goal_summary,
    render_personal_digest,
    render_progress_scorecard,
    render_weekly_intelligence_report,
)
from lifehub.scoring import render_digest, score_readiness
from lifehub.signals import (
    env_symbols,
    fetch_alpaca_market_snapshot,
    fetch_github_repo_activity,
    load_github_fixture,
    load_market_fixture,
    load_signal_fixture,
    summarize_signals,
)
from lifehub.sleep import load_sleep_fixture, normalize_sleep_rows, sleep_quality_events, summarize_sleep
from lifehub.source_onboarding import (
    SourceOnboardingSpec,
    apply_registry_entry,
    csv,
    registry_entry,
    write_onboarding_package,
)
from lifehub.storage import (
    fetch_recent_signals_postgres,
    fetch_decision_metrics_postgres,
    fetch_feedback_profile_postgres,
    fetch_week_summary_postgres,
    insert_daily_context_clickhouse,
    insert_activity_clickhouse,
    insert_activity_postgres,
    insert_digest_run_postgres,
    insert_feedback_clickhouse,
    insert_feedback_postgres,
    insert_recommendations_clickhouse,
    insert_recommendations_postgres,
    insert_scores_clickhouse,
    insert_signals_clickhouse,
    insert_weather_clickhouse,
    upsert_daily_context_postgres,
    upsert_spots_postgres,
    upsert_signals_postgres,
)
from lifehub.telegram_bot import answer_callback_query, get_updates, send_message
from lifehub.weather import fetch_open_meteo, load_fixture, normalize_weather


def cmd_weather_ingest(args: argparse.Namespace) -> int:
    cfg = env_config()
    locations = load_locations(cfg.locations_path)
    fixture_path = args.fixture or cfg.fixture_weather_path
    all_rows = []
    for location in locations:
        payload = load_fixture(fixture_path) if fixture_path else fetch_open_meteo(location, cfg.timezone)
        rows = normalize_weather(payload, location.id)
        all_rows.extend(rows)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(row.__dict__) for row in all_rows) + "\n",
            encoding="utf-8",
        )
    if args.write_clickhouse:
        insert_weather_clickhouse(cfg.clickhouse_url, all_rows)
    print(f"Prepared {len(all_rows)} weather rows for {len(locations)} locations.")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    cfg = env_config()
    scores = compute_scores(cfg, args.fixture)
    digest = render_digest(scores)
    if args.write_clickhouse:
        insert_scores_clickhouse(cfg.clickhouse_url, scores)
    if args.send_telegram:
        send_message(cfg.telegram_token, cfg.telegram_chat_id, digest)
        try:
            insert_digest_run_postgres(
                cfg.postgres_dsn,
                "today",
                cfg.telegram_chat_id or "stdout",
                "sent",
                digest,
            )
        except Exception as exc:
            print(f"Postgres digest run insert skipped: {exc}")
    print(digest)
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    cfg = env_config()
    scores = compute_scores(cfg, args.fixture)
    try:
        week_summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception as exc:
        print(f"Diary summary unavailable, using weather-only recommendation: {exc}")
        week_summary = {}
    try:
        feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
    except Exception as exc:
        print(f"Feedback profile unavailable, using diary/weather-only recommendation: {exc}")
        feedback_profile = {}
    preferences = load_preferences(cfg.preferences_path)
    recovery_summary = load_recovery_summary(getattr(args, "sleep_fixture", None))
    recommendations = build_recommendations(scores, week_summary, feedback_profile, preferences, recovery_summary)
    signals = fetch_signals_safe(cfg)
    digest = render_personal_digest(recommendations)
    if signals:
        digest = f"{digest}\n\nContext signals:\n" + "\n".join(f"- {line}" for line in summarize_signals(signals))
    if args.write_clickhouse:
        insert_scores_clickhouse(cfg.clickhouse_url, scores)
        insert_recommendations_clickhouse(cfg.clickhouse_url, recommendations)
    if args.write_postgres:
        insert_recommendations_postgres(cfg.postgres_dsn, recommendations)
    if args.send_telegram:
        send_message(
            cfg.telegram_token,
            cfg.telegram_chat_id,
            digest,
            feedback_keyboard(recommendations[0].activity) if recommendations else None,
        )
        try:
            insert_digest_run_postgres(
                cfg.postgres_dsn,
                "recommendation",
                cfg.telegram_chat_id or "stdout",
                "sent",
                digest,
            )
        except Exception as exc:
            print(f"Postgres recommendation digest insert skipped: {exc}")
    print(digest)
    return 0


def cmd_context_profile(args: argparse.Namespace) -> int:
    cfg = env_config()
    profile = build_context_profile(
        cfg,
        args.fixture,
        summary_fixture=args.summary_fixture,
        feedback_fixture=args.feedback_fixture,
        metrics_fixture=args.metrics_fixture,
        signal_fixture=args.signal_fixture,
        sleep_fixture=args.sleep_fixture,
    )
    if args.write_postgres:
        upsert_daily_context_postgres(cfg.postgres_dsn, profile)
    if args.write_clickhouse:
        insert_daily_context_clickhouse(cfg.clickhouse_url, profile)
    text = render_daily_context_profile(profile)
    print(text)
    return 0


def cmd_lake_export(args: argparse.Namespace) -> int:
    cfg = env_config()
    weather_rows = compute_weather_rows(cfg, args.fixture)
    summary = load_summary(cfg, args.summary_fixture)
    feedback_profile = load_feedback_profile(cfg, args.feedback_fixture)
    decision_metrics = load_decision_metrics(cfg, args.metrics_fixture)
    signals = load_signal_fixture(args.signal_fixture) if args.signal_fixture else fetch_signals_safe(cfg)
    preferences = load_preferences(cfg.preferences_path)
    scores = compute_scores(cfg, args.fixture)
    recovery_summary = load_recovery_summary(args.sleep_fixture)
    recommendations = build_recommendations(scores, summary, feedback_profile, preferences, recovery_summary)
    profile = build_daily_context_profile(
        recommendations,
        summary,
        decision_metrics,
        signals,
        preferences,
        cfg.timezone,
        recovery_summary,
    )
    events = []
    selected = set(args.sources.split(",")) if args.sources else set()
    if not selected or "weather_forecast" in selected:
        events.extend(weather_events(weather_rows))
    if not selected or "activity_diary" in selected:
        events.extend(week_summary_events(summary))
    if not selected or "decision_feedback" in selected:
        events.extend(decision_metrics_events(decision_metrics))
    if not selected or "context_signals" in selected:
        events.extend(signal_events(signals))
    if not selected or "daily_context_profile" in selected:
        events.extend(daily_context_events(profile))
        events.extend(recommendation_events(recommendations))
    if args.activity_file and (not selected or "activity_files" in selected):
        events.extend(
            activity_file_events(
                [
                    parse_gpx(
                        args.activity_file,
                        activity_type=args.activity_type,
                        city_hint=args.city_hint,
                    )
                ]
            )
        )
    if args.sleep_fixture and (not selected or "sleep_quality" in selected):
        events.extend(sleep_quality_events(normalize_sleep_rows(load_sleep_fixture(args.sleep_fixture))))
    written = write_landing_events(events, args.output_root, args.dt)
    manifest = write_landing_manifest(written, args.output_root)
    print(f"Wrote {sum(written.values())} LifeHub lake landing events.")
    for path, rows in sorted(written.items()):
        print(f"- {path}: {rows}")
    print(f"Manifest: {manifest}")
    return 0


def cmd_activity_file_import(args: argparse.Namespace) -> int:
    summary = parse_gpx(args.path, activity_type=args.activity_type, city_hint=args.city_hint)
    events = activity_file_events([summary])
    written = write_landing_events(events, args.output_root, args.dt)
    manifest = write_landing_manifest(written, args.output_root)
    print(f"Imported {summary.source_file}: {summary.distance_km} km, {summary.duration_minutes} min.")
    for path, rows in sorted(written.items()):
        print(f"- {path}: {rows}")
    print(f"Manifest: {manifest}")
    return 0


def cmd_sleep_import(args: argparse.Namespace) -> int:
    events = sleep_quality_events(normalize_sleep_rows(load_sleep_fixture(args.path), source=args.source))
    written = write_landing_events(events, args.output_root, args.dt)
    manifest = write_landing_manifest(written, args.output_root)
    print(f"Imported {len(events)} sleep quality nights from {args.path}.")
    for path, rows in sorted(written.items()):
        print(f"- {path}: {rows}")
    print(f"Manifest: {manifest}")
    return 0


def cmd_custom_source_import(args: argparse.Namespace) -> int:
    rows = load_json_rows(args.path)
    events = custom_source_events(
        source_name=args.source_name,
        rows=rows,
        registry_path=args.registry,
        event_type=args.event_type,
        event_time_field=args.event_time_field,
        privacy_class=args.privacy_class,
    )
    written = write_landing_events(events, args.output_root, args.dt)
    manifest = write_landing_manifest(written, args.output_root)
    print(f"Imported {len(events)} events from {args.path} into source {args.source_name}.")
    for path, row_count in sorted(written.items()):
        print(f"- {path}: {row_count}")
    print(f"Manifest: {manifest}")
    return 0


def cmd_source_onboard(args: argparse.Namespace) -> int:
    spec = SourceOnboardingSpec(
        source_name=args.source_name,
        domain=args.domain,
        source_type=args.source_type,
        producer=args.producer or f"lifehub-{args.source_name.replace('_', '-')}-import",
        consumers=csv(args.consumers),
        required_fields=csv(args.required_fields),
        event_time_field=args.event_time_field,
        idempotency_key=csv(args.idempotency_key) or [args.event_time_field],
        pii=args.pii,
        privacy_class=args.privacy_class,
        event_type=args.event_type,
    )
    paths = write_onboarding_package(spec, args.output_dir)
    if args.apply_registry:
        apply_registry_entry(args.registry, registry_entry(spec), spec.source_name)
        print(f"Applied registry entry to {args.registry}.")
    print(f"Generated LifeHub source onboarding package for {spec.source_name}.")
    for label, path in paths.items():
        print(f"- {label}: {path}")
    print("Next: review README.md, import the demo fixture, then run make lifehub-lakehouse-runtime-smoke.")
    return 0


def cmd_weekly_report(args: argparse.Namespace) -> int:
    cfg = env_config()
    report = render_weekly_review(
        cfg,
        args.fixture,
        summary_fixture=args.summary_fixture,
        feedback_fixture=args.feedback_fixture,
        signal_fixture=args.signal_fixture,
        sleep_fixture=args.sleep_fixture,
    )
    if args.send_telegram:
        send_message(cfg.telegram_token, cfg.telegram_chat_id, report)
        try:
            insert_digest_run_postgres(
                cfg.postgres_dsn,
                "weekly_review",
                cfg.telegram_chat_id or "stdout",
                "sent",
                report,
            )
        except Exception as exc:
            print(f"Postgres weekly review insert skipped: {exc}")
    print(report)
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    cfg = env_config()
    text = render_metrics(
        cfg,
        summary_fixture=args.summary_fixture,
        feedback_fixture=args.feedback_fixture,
        metrics_fixture=args.metrics_fixture,
    )
    if args.send_telegram:
        send_message(cfg.telegram_token, cfg.telegram_chat_id, text)
    print(text)
    return 0


def compute_scores(cfg, fixture_path: Path | None = None):
    scoring = load_scoring(cfg.scoring_path)
    locations = load_locations(cfg.locations_path)
    selected_fixture = fixture_path or cfg.fixture_weather_path
    grouped = defaultdict(list)
    for location in locations:
        payload = load_fixture(selected_fixture) if selected_fixture else fetch_open_meteo(location, cfg.timezone)
        for row in normalize_weather(payload, location.id):
            grouped[row.location_id].append(row)
    scores = []
    for rows in grouped.values():
        scores.extend(score_readiness(rows, scoring))
    return scores


def compute_weather_rows(cfg, fixture_path: Path | None = None):
    locations = load_locations(cfg.locations_path)
    selected_fixture = fixture_path or cfg.fixture_weather_path
    rows = []
    for location in locations:
        payload = load_fixture(selected_fixture) if selected_fixture else fetch_open_meteo(location, cfg.timezone)
        rows.extend(normalize_weather(payload, location.id))
    return rows


def load_summary(cfg, summary_fixture: Path | None = None) -> dict:
    if summary_fixture:
        return json.loads(Path(summary_fixture).read_text(encoding="utf-8"))
    try:
        return fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception:
        return {}


def load_feedback_profile(cfg, feedback_fixture: Path | None = None) -> dict:
    if feedback_fixture:
        return json.loads(Path(feedback_fixture).read_text(encoding="utf-8"))
    try:
        return fetch_feedback_profile_postgres(cfg.postgres_dsn)
    except Exception:
        return {}


def load_decision_metrics(cfg, metrics_fixture: Path | None = None) -> dict:
    if metrics_fixture:
        return json.loads(Path(metrics_fixture).read_text(encoding="utf-8"))
    try:
        return fetch_decision_metrics_postgres(cfg.postgres_dsn)
    except Exception:
        return {}


def load_recovery_summary(sleep_fixture: Path | None = None) -> dict:
    if not sleep_fixture:
        return {}
    return summarize_sleep(normalize_sleep_rows(load_sleep_fixture(sleep_fixture)))


def build_context_profile(
    cfg,
    fixture_path: Path | None = None,
    summary_fixture: Path | None = None,
    feedback_fixture: Path | None = None,
    metrics_fixture: Path | None = None,
    signal_fixture: Path | None = None,
    sleep_fixture: Path | None = None,
):
    if summary_fixture:
        week_summary = json.loads(Path(summary_fixture).read_text(encoding="utf-8"))
    else:
        try:
            week_summary = fetch_week_summary_postgres(cfg.postgres_dsn)
        except Exception:
            week_summary = {}
    if feedback_fixture:
        feedback_profile = json.loads(Path(feedback_fixture).read_text(encoding="utf-8"))
    else:
        try:
            feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
        except Exception:
            feedback_profile = {}
    if metrics_fixture:
        decision_metrics = json.loads(Path(metrics_fixture).read_text(encoding="utf-8"))
    else:
        try:
            decision_metrics = fetch_decision_metrics_postgres(cfg.postgres_dsn)
        except Exception:
            decision_metrics = {}
    signals = load_signal_fixture(signal_fixture) if signal_fixture else fetch_signals_safe(cfg)
    preferences = load_preferences(cfg.preferences_path)
    scores = compute_scores(cfg, fixture_path or cfg.fixture_weather_path)
    recovery_summary = load_recovery_summary(sleep_fixture)
    recommendations = build_recommendations(scores, week_summary, feedback_profile, preferences, recovery_summary)
    return build_daily_context_profile(
        recommendations,
        week_summary,
        decision_metrics,
        signals,
        preferences,
        cfg.timezone,
        recovery_summary,
    )


def cmd_place_sync(args: argparse.Namespace) -> int:
    cfg = env_config()
    locations = load_locations(cfg.locations_path)
    spots = []
    if args.fixture:
        spots = load_spot_fixture(args.fixture)
    elif args.source in {"auto", "overpass"}:
        center = locations[0]
        try:
            spots = fetch_overpass_spots(center.latitude, center.longitude, args.radius_m)
        except Exception as exc:
            if args.source == "overpass":
                raise
            print(f"Overpass sync failed, falling back to config spots: {exc}")
    if not spots:
        spots = locations
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(asdict(spot)) for spot in spots) + "\n",
            encoding="utf-8",
        )
    if not args.output_only:
        upsert_spots_postgres(cfg.postgres_dsn, spots)
    print(f"Synced {len(spots)} LifeHub spots from {args.source}.")
    return 0


def cmd_signal_import(args: argparse.Namespace) -> int:
    cfg = env_config()
    signals = load_signal_fixture(args.fixture)
    if args.write_postgres:
        upsert_signals_postgres(cfg.postgres_dsn, signals)
    if args.write_clickhouse:
        insert_signals_clickhouse(cfg.clickhouse_url, signals)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(asdict(signal)) for signal in signals) + "\n",
            encoding="utf-8",
        )
    print(f"Prepared {len(signals)} LifeHub context signals.")
    return 0


def cmd_github_signal_import(args: argparse.Namespace) -> int:
    cfg = env_config()
    if args.fixture:
        signals = load_github_fixture(args.fixture)
    else:
        owner, repo = parse_repo(args.repo)
        signals = fetch_github_repo_activity(owner, repo, args.token)
    write_signals(cfg, signals, args)
    print(f"Prepared {len(signals)} LifeHub GitHub signals.")
    return 0


def cmd_market_signal_import(args: argparse.Namespace) -> int:
    cfg = env_config()
    if args.fixture:
        signals = load_market_fixture(args.fixture)
    else:
        api_key = args.alpaca_api_key
        api_secret = args.alpaca_api_secret
        if not api_key or not api_secret:
            raise ValueError("Real market import requires ALPACA_API_KEY and ALPACA_API_SECRET.")
        signals = fetch_alpaca_market_snapshot(
            env_symbols(args.symbols),
            api_key,
            api_secret,
            args.alpaca_market_data_url,
        )
    write_signals(cfg, signals, args)
    print(f"Prepared {len(signals)} LifeHub market signals.")
    return 0


def write_signals(cfg, signals, args: argparse.Namespace) -> None:
    if args.write_postgres:
        upsert_signals_postgres(cfg.postgres_dsn, signals)
    if args.write_clickhouse:
        insert_signals_clickhouse(cfg.clickhouse_url, signals)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(asdict(signal)) for signal in signals) + "\n",
            encoding="utf-8",
        )


def parse_repo(value: str) -> tuple[str, str]:
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("GitHub repo must use owner/repo format.")
    return parts[0], parts[1]


def cmd_telegram_poll(args: argparse.Namespace) -> int:
    cfg = env_config()
    offset = None
    last_digest_date = ""
    while True:
        for update in get_updates(cfg.telegram_token, offset):
            offset = update["update_id"] + 1
            if "callback_query" in update:
                handle_telegram_callback(update["callback_query"], cfg)
                continue
            message = update.get("message", {})
            text = message.get("text", "")
            handle_telegram_text(text, cfg)
        if args.send_daily_digest:
            last_digest_date = maybe_send_daily_digest(cfg, last_digest_date)
        if not args.forever:
            break
        time.sleep(1)
    return 0


def maybe_send_daily_digest(cfg, last_digest_date: str) -> str:
    now = datetime.now(ZoneInfo(cfg.timezone))
    digest_clock = now.strftime("%H:%M")
    today = now.date().isoformat()
    if digest_clock >= cfg.digest_time and today != last_digest_date:
        args = argparse.Namespace(
            fixture=cfg.fixture_weather_path,
            write_clickhouse=False,
            write_postgres=True,
            send_telegram=True,
        )
        cmd_recommend(args)
        return today
    return last_digest_date


def handle_telegram_text(text: str, cfg) -> None:
    name = command_name(text)
    if name == "/today":
        args = argparse.Namespace(
            fixture=cfg.fixture_weather_path,
            write_clickhouse=False,
            write_postgres=True,
            send_telegram=True,
        )
        cmd_recommend(args)
    elif name == "/spots":
        locations = load_locations(cfg.locations_path)
        parts = text.strip().split(maxsplit=1)
        activity = parts[1].strip().lower() if len(parts) > 1 else ""
        if activity:
            locations = [item for item in locations if activity in item.tags or activity == item.id]
        send_message(
            cfg.telegram_token,
            cfg.telegram_chat_id,
            "\n".join(f"- {item.label}: {', '.join(item.tags)}" for item in locations)
            or f"No configured spots for {activity}.",
        )
    elif name == "/week":
        send_message(cfg.telegram_token, cfg.telegram_chat_id, render_week_summary(cfg))
    elif name == "/review":
        send_message(cfg.telegram_token, cfg.telegram_chat_id, render_weekly_review(cfg, cfg.fixture_weather_path))
    elif name == "/metrics":
        send_message(cfg.telegram_token, cfg.telegram_chat_id, render_metrics(cfg))
    elif name == "/coach":
        send_message(cfg.telegram_token, cfg.telegram_chat_id, render_coach(cfg))
    elif name == "/goals":
        send_message(cfg.telegram_token, cfg.telegram_chat_id, render_goals(cfg))
    elif name == "/signals":
        signals = fetch_signals_safe(cfg)
        lines = summarize_signals(signals, limit=5)
        send_message(
            cfg.telegram_token,
            cfg.telegram_chat_id,
            "\n".join(f"- {line}" for line in lines) or "No recent LifeHub context signals.",
        )
    elif name in {"/done", "/skip", "/feedback"}:
        try:
            feedback = parse_feedback_command(text)
        except ValueError as exc:
            send_message(cfg.telegram_token, cfg.telegram_chat_id, str(exc))
            return
        insert_feedback_postgres(cfg.postgres_dsn, feedback)
        try:
            insert_feedback_clickhouse(cfg.clickhouse_url, feedback)
        except Exception as exc:
            print(f"ClickHouse feedback insert skipped: {exc}")
        send_message(cfg.telegram_token, cfg.telegram_chat_id, f"Feedback logged: {feedback.activity} {feedback.action}.")
    elif name == "/log":
        try:
            log = parse_log_command(text)
        except ValueError as exc:
            send_message(cfg.telegram_token, cfg.telegram_chat_id, str(exc))
            return
        insert_activity_postgres(cfg.postgres_dsn, log)
        try:
            insert_activity_clickhouse(cfg.clickhouse_url, log)
        except Exception as exc:
            print(f"ClickHouse activity insert skipped: {exc}")
        send_message(cfg.telegram_token, cfg.telegram_chat_id, f"Logged {log.activity_type}: {log.result}.")
    else:
        send_message(
            cfg.telegram_token,
            cfg.telegram_chat_id,
            "Commands: /today, /review, /metrics, /spots, /signals, /week, /goals, /coach, /done, /skip, /log activity intensity mood fatigue result notes",
        )


def handle_telegram_callback(callback: dict, cfg) -> None:
    data = callback.get("data", "")
    callback_id = callback.get("id", "")
    message = callback.get("message", {})
    chat = message.get("chat", {})
    chat_id = str(chat.get("id") or cfg.telegram_chat_id)
    try:
        feedback = parse_feedback_callback(data)
    except ValueError as exc:
        answer_callback_query(cfg.telegram_token, callback_id, str(exc))
        return
    insert_feedback_postgres(cfg.postgres_dsn, feedback)
    try:
        insert_feedback_clickhouse(cfg.clickhouse_url, feedback)
    except Exception as exc:
        print(f"ClickHouse callback feedback insert skipped: {exc}")
    answer_callback_query(cfg.telegram_token, callback_id, "LifeHub feedback logged.")
    send_message(cfg.telegram_token, chat_id, f"Feedback logged: {feedback.activity} {feedback.action}.")


def cmd_feedback(args: argparse.Namespace) -> int:
    cfg = env_config()
    feedback = parse_feedback_command(args.text)
    insert_feedback_postgres(cfg.postgres_dsn, feedback)
    if args.write_clickhouse:
        insert_feedback_clickhouse(cfg.clickhouse_url, feedback)
    print(f"Feedback logged: {feedback.activity} {feedback.action}.")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    cfg = env_config()
    log = parse_log_command(args.text)
    insert_activity_postgres(cfg.postgres_dsn, log)
    if args.write_clickhouse:
        insert_activity_clickhouse(cfg.clickhouse_url, log)
    print(f"Logged {log.activity_type}: {log.result}.")
    return 0


def render_week_summary(cfg) -> str:
    try:
        summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception as exc:
        return f"LifeHub week: diary storage is not reachable yet ({exc})."
    if summary.get("sessions", 0) == 0:
        return "LifeHub week: no diary entries in the last 7 days. Log one with /log."
    lines = [
        f"LifeHub week: {summary['sessions']} sessions logged.",
        (
            f"Avg intensity {summary['avg_intensity']}/10, "
            f"mood {summary['avg_mood']}/10, fatigue {summary['avg_fatigue']}/10."
        ),
        f"Pain-flagged sessions: {summary['pain_sessions']}.",
    ]
    if summary.get("by_activity"):
        activities = ", ".join(
            f"{row['activity_type']} {row['sessions']}" for row in summary["by_activity"]
        )
        lines.append(f"Activities: {activities}.")
    if summary.get("by_result"):
        results = ", ".join(f"{row['result']} {row['sessions']}" for row in summary["by_result"])
        lines.append(f"Results: {results}.")
    lines.append("Next: keep logging after sessions so recommendations can account for fatigue.")
    return "\n".join(lines)


def render_coach(cfg) -> str:
    try:
        summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception as exc:
        return f"LifeHub coach: diary storage is not reachable yet ({exc})."
    scores = compute_scores(cfg, cfg.fixture_weather_path)
    try:
        feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
    except Exception:
        feedback_profile = {}
    preferences = load_preferences(cfg.preferences_path)
    recommendations = build_recommendations(scores, summary, feedback_profile, preferences)
    return render_coach_summary(summary, recommendations, preferences)


def render_goals(cfg) -> str:
    try:
        summary = fetch_week_summary_postgres(cfg.postgres_dsn)
    except Exception as exc:
        return f"LifeHub goals: diary storage is not reachable yet ({exc})."
    preferences = load_preferences(cfg.preferences_path)
    return render_goal_summary(summary, preferences)


def render_weekly_review(
    cfg,
    fixture_path: Path | None = None,
    summary_fixture: Path | None = None,
    feedback_fixture: Path | None = None,
    signal_fixture: Path | None = None,
    sleep_fixture: Path | None = None,
) -> str:
    if summary_fixture:
        summary = json.loads(Path(summary_fixture).read_text(encoding="utf-8"))
    else:
        try:
            summary = fetch_week_summary_postgres(cfg.postgres_dsn)
        except Exception as exc:
            return f"LifeHub weekly review: diary storage is not reachable yet ({exc})."
    scores = compute_scores(cfg, fixture_path or cfg.fixture_weather_path)
    if feedback_fixture:
        feedback_profile = json.loads(Path(feedback_fixture).read_text(encoding="utf-8"))
    else:
        try:
            feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
        except Exception:
            feedback_profile = {}
    preferences = load_preferences(cfg.preferences_path)
    recovery_summary = load_recovery_summary(sleep_fixture)
    recommendations = build_recommendations(scores, summary, feedback_profile, preferences, recovery_summary)
    signals = load_signal_fixture(signal_fixture) if signal_fixture else fetch_signals_safe(cfg)
    return render_weekly_intelligence_report(summary, recommendations, feedback_profile, preferences, signals)


def render_metrics(
    cfg,
    summary_fixture: Path | None = None,
    feedback_fixture: Path | None = None,
    metrics_fixture: Path | None = None,
) -> str:
    if summary_fixture:
        summary = json.loads(Path(summary_fixture).read_text(encoding="utf-8"))
    else:
        try:
            summary = fetch_week_summary_postgres(cfg.postgres_dsn)
        except Exception as exc:
            return f"LifeHub metrics: diary storage is not reachable yet ({exc})."
    if feedback_fixture:
        feedback_profile = json.loads(Path(feedback_fixture).read_text(encoding="utf-8"))
    else:
        try:
            feedback_profile = fetch_feedback_profile_postgres(cfg.postgres_dsn)
        except Exception:
            feedback_profile = {}
    if metrics_fixture:
        decision_metrics = json.loads(Path(metrics_fixture).read_text(encoding="utf-8"))
    else:
        try:
            decision_metrics = fetch_decision_metrics_postgres(cfg.postgres_dsn)
        except Exception:
            decision_metrics = {}
    preferences = load_preferences(cfg.preferences_path)
    return render_progress_scorecard(summary, decision_metrics, feedback_profile, preferences)


def fetch_signals_safe(cfg):
    try:
        return fetch_recent_signals_postgres(cfg.postgres_dsn)
    except Exception as exc:
        print(f"Signal context unavailable: {exc}")
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LifeHub local sports and wellbeing pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    weather = sub.add_parser("weather-ingest")
    weather.add_argument("--fixture", type=Path)
    weather.add_argument("--output")
    weather.add_argument("--write-clickhouse", action="store_true")
    weather.set_defaults(func=cmd_weather_ingest)

    score = sub.add_parser("score")
    score.add_argument("--fixture", type=Path)
    score.add_argument("--write-clickhouse", action="store_true")
    score.add_argument("--send-telegram", action="store_true")
    score.set_defaults(func=cmd_score)

    recommend = sub.add_parser("recommend")
    recommend.add_argument("--fixture", type=Path)
    recommend.add_argument("--sleep-fixture", type=Path)
    recommend.add_argument("--write-clickhouse", action="store_true")
    recommend.add_argument("--write-postgres", action="store_true")
    recommend.add_argument("--send-telegram", action="store_true")
    recommend.set_defaults(func=cmd_recommend)

    context_profile = sub.add_parser("context-profile")
    context_profile.add_argument("--fixture", type=Path)
    context_profile.add_argument("--summary-fixture", type=Path)
    context_profile.add_argument("--feedback-fixture", type=Path)
    context_profile.add_argument("--metrics-fixture", type=Path)
    context_profile.add_argument("--signal-fixture", type=Path)
    context_profile.add_argument("--sleep-fixture", type=Path)
    context_profile.add_argument("--write-postgres", action="store_true")
    context_profile.add_argument("--write-clickhouse", action="store_true")
    context_profile.set_defaults(func=cmd_context_profile)

    lake_export = sub.add_parser("lake-export")
    lake_export.add_argument("--fixture", type=Path)
    lake_export.add_argument("--summary-fixture", type=Path)
    lake_export.add_argument("--feedback-fixture", type=Path)
    lake_export.add_argument("--metrics-fixture", type=Path)
    lake_export.add_argument("--signal-fixture", type=Path)
    lake_export.add_argument("--activity-file", type=Path)
    lake_export.add_argument("--activity-type", default="walk")
    lake_export.add_argument("--city-hint", default="Saint Petersburg")
    lake_export.add_argument("--sleep-fixture", type=Path)
    lake_export.add_argument("--output-root", type=Path, default=Path("tmp/lake"))
    lake_export.add_argument("--sources", default="", help="Comma-separated source names, defaults to all")
    lake_export.add_argument("--dt", default="", help="Landing partition date, defaults to UTC today")
    lake_export.set_defaults(func=cmd_lake_export)

    activity_file = sub.add_parser("activity-file-import")
    activity_file.add_argument("path", type=Path)
    activity_file.add_argument("--activity-type", default="walk")
    activity_file.add_argument("--city-hint", default="Saint Petersburg")
    activity_file.add_argument("--output-root", type=Path, default=Path("tmp/lake"))
    activity_file.add_argument("--dt", default="", help="Landing partition date, defaults to UTC today")
    activity_file.set_defaults(func=cmd_activity_file_import)

    sleep = sub.add_parser("sleep-import")
    sleep.add_argument("path", type=Path)
    sleep.add_argument("--source", default="local_sleep_log")
    sleep.add_argument("--output-root", type=Path, default=Path("tmp/lake"))
    sleep.add_argument("--dt", default="", help="Landing partition date, defaults to UTC today")
    sleep.set_defaults(func=cmd_sleep_import)

    custom_source = sub.add_parser("custom-source-import")
    custom_source.add_argument("path", type=Path)
    custom_source.add_argument("--source-name", default="custom_life_events")
    custom_source.add_argument("--event-type", default="custom_life_event")
    custom_source.add_argument("--event-time-field", default="occurred_at")
    custom_source.add_argument("--privacy-class", default="custom_local_summary")
    custom_source.add_argument("--registry", type=Path, default=Path("config/lifehub/source_registry.yaml"))
    custom_source.add_argument("--output-root", type=Path, default=Path("tmp/lake"))
    custom_source.add_argument("--dt", default="", help="Landing partition date, defaults to UTC today")
    custom_source.set_defaults(func=cmd_custom_source_import)

    source_onboard = sub.add_parser("source-onboard")
    source_onboard.add_argument("source_name")
    source_onboard.add_argument("--domain", default="personal")
    source_onboard.add_argument("--source-type", default="local_json_event")
    source_onboard.add_argument("--producer", default="")
    source_onboard.add_argument("--consumers", default="daily_context_profile,future_life_domains")
    source_onboard.add_argument("--required-fields", default="occurred_at,domain,metric_name,metric_value")
    source_onboard.add_argument("--event-time-field", default="occurred_at")
    source_onboard.add_argument("--idempotency-key", default="domain,metric_name,occurred_at")
    source_onboard.add_argument("--event-type", default="custom_life_event")
    source_onboard.add_argument("--privacy-class", default="custom_local_summary")
    source_onboard.add_argument("--pii", action="store_true")
    source_onboard.add_argument("--output-dir", type=Path, default=Path("tmp/lifehub/source_onboarding"))
    source_onboard.add_argument("--registry", type=Path, default=Path("config/lifehub/source_registry.yaml"))
    source_onboard.add_argument("--apply-registry", action="store_true")
    source_onboard.set_defaults(func=cmd_source_onboard)

    weekly_report = sub.add_parser("weekly-report")
    weekly_report.add_argument("--fixture", type=Path)
    weekly_report.add_argument("--summary-fixture", type=Path)
    weekly_report.add_argument("--feedback-fixture", type=Path)
    weekly_report.add_argument("--signal-fixture", type=Path)
    weekly_report.add_argument("--sleep-fixture", type=Path)
    weekly_report.add_argument("--send-telegram", action="store_true")
    weekly_report.set_defaults(func=cmd_weekly_report)

    metrics = sub.add_parser("metrics")
    metrics.add_argument("--summary-fixture", type=Path)
    metrics.add_argument("--feedback-fixture", type=Path)
    metrics.add_argument("--metrics-fixture", type=Path)
    metrics.add_argument("--send-telegram", action="store_true")
    metrics.set_defaults(func=cmd_metrics)

    places = sub.add_parser("place-sync")
    places.add_argument("--source", choices=["auto", "overpass", "config"], default="auto")
    places.add_argument("--radius-m", type=int, default=12000)
    places.add_argument("--fixture", type=Path)
    places.add_argument("--output")
    places.add_argument("--output-only", action="store_true")
    places.set_defaults(func=cmd_place_sync)

    signals = sub.add_parser("signal-import")
    signals.add_argument("--fixture", type=Path, required=True)
    signals.add_argument("--write-postgres", action="store_true")
    signals.add_argument("--write-clickhouse", action="store_true")
    signals.add_argument("--output")
    signals.set_defaults(func=cmd_signal_import)

    github_signals = sub.add_parser("github-signal-import")
    github_signals.add_argument("--fixture", type=Path)
    github_signals.add_argument("--repo", default=os.getenv("LIFEHUB_GITHUB_REPO", "karnaksp/data-forge"))
    github_signals.add_argument("--token", default=os.getenv("GITHUB_TOKEN", ""))
    github_signals.add_argument("--write-postgres", action="store_true")
    github_signals.add_argument("--write-clickhouse", action="store_true")
    github_signals.add_argument("--output")
    github_signals.set_defaults(func=cmd_github_signal_import)

    market_signals = sub.add_parser("market-signal-import")
    market_signals.add_argument("--fixture", type=Path)
    market_signals.add_argument("--symbols", default=os.getenv("LIFEHUB_MARKET_SYMBOLS", "SPY,QQQ"))
    market_signals.add_argument("--alpaca-api-key", default=os.getenv("ALPACA_API_KEY", ""))
    market_signals.add_argument("--alpaca-api-secret", default=os.getenv("ALPACA_API_SECRET", ""))
    market_signals.add_argument(
        "--alpaca-market-data-url",
        default=os.getenv("ALPACA_MARKET_DATA_URL", "https://data.alpaca.markets"),
    )
    market_signals.add_argument("--write-postgres", action="store_true")
    market_signals.add_argument("--write-clickhouse", action="store_true")
    market_signals.add_argument("--output")
    market_signals.set_defaults(func=cmd_market_signal_import)

    poll = sub.add_parser("telegram-poll")
    poll.add_argument("--forever", action="store_true")
    poll.add_argument("--send-daily-digest", action="store_true")
    poll.set_defaults(func=cmd_telegram_poll)

    feedback = sub.add_parser("feedback")
    feedback.add_argument("text")
    feedback.add_argument("--write-clickhouse", action="store_true")
    feedback.set_defaults(func=cmd_feedback)

    log = sub.add_parser("log")
    log.add_argument("text")
    log.add_argument("--write-clickhouse", action="store_true")
    log.set_defaults(func=cmd_log)

    sub.add_parser("help").set_defaults(func=lambda _args: (parser.print_help() or 0))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
