#!/usr/bin/env python3
"""Build a local static LifeHub cockpit from redacted analytical marts."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "lifehub-cockpit.html"
sys.path.insert(0, str(ROOT / "infra" / "lifehub"))

from lifehub.runtime_sources import load_source_run_status  # noqa: E402
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.evidence.yml",
    "--profile",
    "lifehub",
]


@dataclass(frozen=True)
class CockpitData:
    generated_at: str
    latest_readiness: list[dict[str, Any]]
    recommendation_daily: list[dict[str, Any]]
    useful_decision_days: list[dict[str, Any]]
    feedback_profile: list[dict[str, Any]]
    goal_progress: list[dict[str, Any]]
    signal_daily: list[dict[str, Any]]
    weather_daily: list[dict[str, Any]]
    daily_context_latest: list[dict[str, Any]]
    source_health: list[dict[str, Any]]


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def compose(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = run([*COMPOSE, *args], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def clickhouse_json_each_row(query: str) -> list[dict[str, Any]]:
    result = compose(["exec", "-T", "clickhouse", "clickhouse-client", "--query", f"{query} FORMAT JSONEachRow"])
    rows = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_live_data() -> CockpitData:
    preferences = load_preferences()
    weekly_counts = {
        row["activity_type"]: int(number(row.get("sessions")))
        for row in clickhouse_json_each_row(
            """
            SELECT activity_type, sum(sessions) AS sessions
            FROM analytics.life_activity_daily_v
            WHERE activity_date >= toStartOfWeek(today())
            GROUP BY activity_type
            """
        )
    }
    return CockpitData(
        generated_at=datetime.now(timezone.utc).isoformat(),
        latest_readiness=clickhouse_json_each_row(
            """
            SELECT activity, location_id, score, decision, explanation, latest_computed_at
            FROM analytics.life_latest_readiness_v
            ORDER BY score DESC, activity, location_id
            LIMIT 20
            """
        ),
        recommendation_daily=clickhouse_json_each_row(
            """
            SELECT recommendation_date, activity, decision, recommendations, avg_score
            FROM analytics.life_recommendation_daily_v
            ORDER BY recommendation_date ASC, activity ASC, decision ASC
            LIMIT 60
            """
        ),
        useful_decision_days=clickhouse_json_each_row(
            """
            SELECT week_start, useful_decision_days, total_followed_events, total_skipped_events, follow_rate
            FROM analytics.life_useful_decision_days_v
            ORDER BY week_start DESC
            LIMIT 8
            """
        ),
        feedback_profile=clickhouse_json_each_row(
            """
            SELECT activity, feedback_events, followed_events, skipped_events, good_results, bad_results, follow_rate, latest_feedback_at
            FROM analytics.life_activity_feedback_profile_v
            ORDER BY follow_rate DESC, feedback_events DESC, activity ASC
            LIMIT 20
            """
        ),
        goal_progress=build_goal_progress(preferences, weekly_counts),
        signal_daily=clickhouse_json_each_row(
            """
            SELECT signal_date, domain, source, direction, signals, max_urgency, avg_confidence
            FROM analytics.life_signal_daily_v
            ORDER BY signal_date DESC, max_urgency DESC, domain ASC
            LIMIT 30
            """
        ),
        weather_daily=clickhouse_json_each_row(
            """
            SELECT location_id, forecast_date, max_temperature_c, precipitation_mm, snowfall_cm, max_wind_gust_kmh
            FROM analytics.life_location_weather_daily_v
            ORDER BY forecast_date DESC, location_id ASC
            LIMIT 30
            """
        ),
        daily_context_latest=clickhouse_json_each_row(
            """
            SELECT
              profile_date, timezone, top_activity, top_decision, top_score,
              readiness_state, sessions_7d, avg_mood_7d, avg_fatigue_7d,
              pain_sessions_7d, useful_decision_days_7d, follow_rate_7d,
              open_goal_count, signal_count_7d, highest_signal_domain,
              highest_signal_urgency, context_summary, latest_generated_at
            FROM analytics.life_daily_context_latest_v
            ORDER BY profile_date DESC, latest_generated_at DESC
            LIMIT 7
            """
        ),
        source_health=load_source_run_status(ROOT / "tmp" / "lake"),
    )


def load_demo_data() -> CockpitData:
    return CockpitData(
        generated_at=datetime.now(timezone.utc).isoformat(),
        latest_readiness=[
            {
                "activity": "skate",
                "location_id": "spb_center",
                "score": 100,
                "decision": "go",
                "explanation": "conditions look usable",
                "latest_computed_at": "2026-06-16 08:00:00",
            },
            {
                "activity": "moto_lesson",
                "location_id": "pulkovo_heights",
                "score": 86,
                "decision": "go",
                "explanation": "dry enough, moderate wind",
                "latest_computed_at": "2026-06-16 08:00:00",
            },
            {
                "activity": "volleyball",
                "location_id": "krestovsky_island",
                "score": 78,
                "decision": "go",
                "explanation": "indoor session is mostly readiness-driven",
                "latest_computed_at": "2026-06-16 08:00:00",
            },
            {
                "activity": "snowboard",
                "location_id": "okhta_park",
                "score": 22,
                "decision": "recover",
                "explanation": "thaw risk",
                "latest_computed_at": "2026-06-16 08:00:00",
            },
        ],
        recommendation_daily=[
            {"recommendation_date": "2026-06-14", "activity": "skate", "decision": "go", "recommendations": 2, "avg_score": 92},
            {"recommendation_date": "2026-06-15", "activity": "moto_lesson", "decision": "go", "recommendations": 1, "avg_score": 84},
            {"recommendation_date": "2026-06-16", "activity": "skate", "decision": "go", "recommendations": 1, "avg_score": 100},
            {"recommendation_date": "2026-06-16", "activity": "snowboard", "decision": "recover", "recommendations": 1, "avg_score": 22},
        ],
        useful_decision_days=[
            {
                "week_start": "2026-06-15",
                "useful_decision_days": 1,
                "total_followed_events": 1,
                "total_skipped_events": 0,
                "follow_rate": 1,
            }
        ],
        feedback_profile=[
            {
                "activity": "skate",
                "feedback_events": 3,
                "followed_events": 3,
                "skipped_events": 0,
                "good_results": 2,
                "bad_results": 0,
                "follow_rate": 1,
                "latest_feedback_at": "2026-06-16 08:20:00",
            },
            {
                "activity": "moto_lesson",
                "feedback_events": 2,
                "followed_events": 0,
                "skipped_events": 2,
                "good_results": 0,
                "bad_results": 1,
                "follow_rate": 0,
                "latest_feedback_at": "2026-06-15 19:00:00",
            },
        ],
        goal_progress=[
            {"activity": "skate", "done": 1, "target": 2, "progress": 0.5},
            {"activity": "volleyball", "done": 0, "target": 1, "progress": 0},
            {"activity": "moto_lesson", "done": 1, "target": 1, "progress": 1},
            {"activity": "walk", "done": 1, "target": 2, "progress": 0.5},
        ],
        signal_daily=[
            {
                "signal_date": "2026-06-16",
                "domain": "market",
                "source": "fixture",
                "direction": "negative",
                "signals": 1,
                "max_urgency": 7,
                "avg_confidence": 0.8,
            },
            {
                "signal_date": "2026-06-16",
                "domain": "github",
                "source": "fixture",
                "direction": "positive",
                "signals": 1,
                "max_urgency": 5,
                "avg_confidence": 0.9,
            },
            {
                "signal_date": "2026-06-16",
                "domain": "system",
                "source": "fixture",
                "direction": "neutral",
                "signals": 1,
                "max_urgency": 4,
                "avg_confidence": 0.7,
            },
        ],
        weather_daily=[
            {
                "location_id": "spb_center",
                "forecast_date": "2026-06-16",
                "max_temperature_c": 18,
                "precipitation_mm": 0,
                "snowfall_cm": 0,
                "max_wind_gust_kmh": 19,
            },
            {
                "location_id": "okhta_park",
                "forecast_date": "2026-06-16",
                "max_temperature_c": 15,
                "precipitation_mm": 0.3,
                "snowfall_cm": 0,
                "max_wind_gust_kmh": 25,
            },
        ],
        daily_context_latest=[
            {
                "profile_date": "2026-06-16",
                "timezone": "Europe/Moscow",
                "top_activity": "skate",
                "top_decision": "go",
                "top_score": 100,
                "readiness_state": "act_on_open_goal",
                "sessions_7d": 5,
                "avg_mood_7d": 7,
                "avg_fatigue_7d": 5,
                "pain_sessions_7d": 0,
                "useful_decision_days_7d": 3,
                "follow_rate_7d": 0.8,
                "open_goal_count": 2,
                "signal_count_7d": 3,
                "highest_signal_domain": "market",
                "highest_signal_urgency": 7,
                "context_summary": "skate is top action at 100/100 (go); state=act_on_open_goal; sessions_7d=5",
                "latest_generated_at": "2026-06-16 08:25:00",
            }
        ],
        source_health=[
            {
                "source_name": "lifehub.cli",
                "status": "ok",
                "quality_state": "fresh",
                "freshness_minutes": 0,
                "row_count": 14,
                "error_count": 0,
                "latest_event_time": "2026-06-16T12:00:00+00:00",
                "last_error": "",
            },
            {
                "source_name": "lifehub.telegram",
                "status": "failed",
                "quality_state": "has_failures",
                "freshness_minutes": 8,
                "row_count": 3,
                "error_count": 1,
                "latest_event_time": "2026-06-16T11:52:00+00:00",
                "last_error": "Telegram credentials missing; printed to stdout.",
            },
            {
                "source_name": "lifehub.lake",
                "status": "ok",
                "quality_state": "fresh",
                "freshness_minutes": 0,
                "row_count": 8,
                "error_count": 0,
                "latest_event_time": "2026-06-16T12:00:00+00:00",
                "last_error": "",
            },
        ],
    )


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def load_preferences() -> dict[str, Any]:
    path = ROOT / "config" / "lifehub" / "preferences.yaml"
    if not path.exists():
        return {}
    data: dict[str, Any] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line[:-1].strip()
            data[current] = {}
            continue
        if current and ":" in line:
            key, value = line.strip().split(":", 1)
            data[current][key.strip()] = parse_pref_value(value.strip())
    return data


def parse_pref_value(value: str) -> Any:
    try:
        return int(value)
    except ValueError:
        return value.strip('"')


def build_goal_progress(preferences: dict[str, Any], weekly_counts: dict[str, int]) -> list[dict[str, Any]]:
    rows = []
    for activity, target in (preferences.get("weekly_goals") or {}).items():
        done = int(weekly_counts.get(activity, 0))
        target_int = int(target)
        rows.append(
            {
                "activity": activity,
                "done": done,
                "target": target_int,
                "progress": min(1, done / target_int) if target_int else 0,
            }
        )
    return rows


def number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def latest_top(data: CockpitData) -> dict[str, Any]:
    return data.latest_readiness[0] if data.latest_readiness else {}


def latest_context(data: CockpitData) -> dict[str, Any]:
    return data.daily_context_latest[0] if data.daily_context_latest else {}


def kpis(data: CockpitData) -> list[tuple[str, str, str]]:
    useful = data.useful_decision_days[0] if data.useful_decision_days else {}
    top = latest_top(data)
    context = latest_context(data)
    recommendations = sum(int(number(row.get("recommendations"))) for row in data.recommendation_daily)
    signal_count = sum(int(number(row.get("signals"))) for row in data.signal_daily)
    failed_sources = sum(1 for row in data.source_health if int(number(row.get("error_count"))) > 0)
    covered_goals = sum(1 for row in data.goal_progress if number(row.get("progress")) >= 1)
    total_goals = len(data.goal_progress)
    return [
        (
            "Best action",
            esc(context.get("top_activity") or top.get("activity", "n/a")),
            f"{int(number(context.get('top_score') or top.get('score')))} / 100",
        ),
        ("Useful decision days", str(int(number(useful.get("useful_decision_days")))), "this week"),
        ("Follow rate", f"{number(useful.get('follow_rate')):.0%}", "feedback based"),
        ("Recommendations", str(recommendations), "stored events"),
        ("Context signals", str(int(number(context.get("signal_count_7d")) or signal_count)), "market, GitHub, system"),
        ("Source health", str(failed_sources), "sources with errors"),
        ("Weekly goals", f"{covered_goals}/{total_goals}", "targets covered"),
    ]


def readiness_rows(data: CockpitData) -> str:
    rows = []
    for row in data.latest_readiness:
        score = max(0, min(100, number(row.get("score"))))
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(row.get("activity"))}</strong><span>{esc(row.get("location_id"))}</span></td>
              <td><div class="bar"><i style="width:{score:.0f}%"></i></div></td>
              <td class="num">{score:.0f}</td>
              <td><span class="pill {esc(row.get("decision"))}">{esc(row.get("decision"))}</span></td>
              <td class="hide-sm">{esc(row.get("explanation"))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="5">No readiness rows yet.</td></tr>'


def recommendation_bars(data: CockpitData) -> str:
    grouped: dict[str, float] = {}
    for row in data.recommendation_daily:
        key = f"{row.get('recommendation_date')} · {row.get('activity')}"
        grouped[key] = grouped.get(key, 0) + number(row.get("avg_score"))
    if not grouped:
        return '<p class="empty">No recommendation history yet.</p>'
    max_value = max(grouped.values()) or 1
    bars = []
    for label, value in grouped.items():
        width = max(4, value / max_value * 100)
        bars.append(f'<div class="hbar"><span>{esc(label)}</span><b style="width:{width:.0f}%"></b><em>{value:.0f}</em></div>')
    return "\n".join(bars)


def signal_rows(data: CockpitData) -> str:
    rows = []
    for row in data.signal_daily:
        rows.append(
            f"""
            <tr>
              <td>{esc(row.get("signal_date"))}</td>
              <td><strong>{esc(row.get("domain"))}</strong><span>{esc(row.get("source"))}</span></td>
              <td><span class="pill {esc(row.get("direction"))}">{esc(row.get("direction"))}</span></td>
              <td class="num">{esc(row.get("max_urgency"))}</td>
              <td class="num">{number(row.get("avg_confidence")):.2f}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="5">No context signals yet.</td></tr>'


def feedback_profile_rows(data: CockpitData) -> str:
    rows = []
    for row in data.feedback_profile:
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(row.get("activity"))}</strong><span>{esc(row.get("latest_feedback_at"))}</span></td>
              <td class="num">{int(number(row.get("feedback_events")))}</td>
              <td class="num">{number(row.get("follow_rate")):.0%}</td>
              <td class="num">{int(number(row.get("good_results")))}</td>
              <td class="num">{int(number(row.get("bad_results")))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="5">No feedback profile yet. Use /done or /skip after recommendations.</td></tr>'


def goal_progress_rows(data: CockpitData) -> str:
    rows = []
    for row in data.goal_progress:
        progress = max(0, min(1, number(row.get("progress"))))
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(row.get("activity"))}</strong></td>
              <td><div class="bar"><i style="width:{progress * 100:.0f}%"></i></div></td>
              <td class="num">{int(number(row.get("done")))}</td>
              <td class="num">{int(number(row.get("target")))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="4">No weekly goals configured.</td></tr>'


def weather_rows(data: CockpitData) -> str:
    rows = []
    for row in data.weather_daily[:12]:
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(row.get("location_id"))}</strong><span>{esc(row.get("forecast_date"))}</span></td>
              <td class="num">{number(row.get("max_temperature_c")):.1f}</td>
              <td class="num">{number(row.get("precipitation_mm")):.1f}</td>
              <td class="num">{number(row.get("snowfall_cm")):.1f}</td>
              <td class="num">{number(row.get("max_wind_gust_kmh")):.1f}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="5">No weather aggregates yet.</td></tr>'


def source_health_rows(data: CockpitData) -> str:
    rows = []
    for row in data.source_health[:12]:
        status = str(row.get("status") or "unknown")
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(row.get("source_name"))}</strong><span>{esc(row.get("latest_event_time"))}</span></td>
              <td><span class="pill {esc(status)}">{esc(status)}</span></td>
              <td class="num">{int(number(row.get("freshness_minutes")))}</td>
              <td class="num">{int(number(row.get("row_count")))}</td>
              <td class="num">{int(number(row.get("error_count")))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="5">No runtime source health yet. Run runtime-log-import.</td></tr>'


def weekly_review_card(data: CockpitData) -> str:
    open_goals = [row for row in data.goal_progress if number(row.get("progress")) < 1]
    covered_goals = [row for row in data.goal_progress if number(row.get("progress")) >= 1]
    best_feedback = data.feedback_profile[0] if data.feedback_profile else {}
    high_signal = sorted(data.signal_daily, key=lambda row: number(row.get("max_urgency")), reverse=True)
    top_signal = high_signal[0] if high_signal else {}

    if open_goals:
        next_focus = f"Close {esc(open_goals[0].get('activity'))} first when readiness allows."
    elif data.goal_progress:
        next_focus = "Weekly targets are covered; protect recovery."
    else:
        next_focus = "Configure weekly goals to make the review actionable."

    open_text = ", ".join(
        f"{row.get('activity')} {int(number(row.get('done')))}/{int(number(row.get('target')))}"
        for row in open_goals[:4]
    ) or "none"
    covered_text = ", ".join(str(row.get("activity")) for row in covered_goals[:4]) or "none"
    learning = (
        f"{best_feedback.get('activity')} follow rate {number(best_feedback.get('follow_rate')):.0%}"
        if best_feedback
        else "no feedback yet"
    )
    context = (
        f"{top_signal.get('domain')} urgency {int(number(top_signal.get('max_urgency')))}"
        if top_signal
        else "no context watch"
    )
    return f"""
      <ul class="review-list">
        <li><span>Open goals</span><strong>{esc(open_text)}</strong></li>
        <li><span>Covered</span><strong>{esc(covered_text)}</strong></li>
        <li><span>Learning</span><strong>{esc(learning)}</strong></li>
        <li><span>Context watch</span><strong>{esc(context)}</strong></li>
        <li><span>Next focus</span><strong>{next_focus}</strong></li>
      </ul>
    """


def daily_context_card(data: CockpitData) -> str:
    context = latest_context(data)
    if not context:
        return '<p class="empty">No daily context profile yet. Run `lifehub.cli context-profile`.</p>'
    return f"""
      <ul class="review-list">
        <li><span>Date</span><strong>{esc(context.get("profile_date"))} · {esc(context.get("timezone"))}</strong></li>
        <li><span>State</span><strong>{esc(context.get("readiness_state"))}</strong></li>
        <li><span>Top action</span><strong>{esc(context.get("top_activity"))} · {int(number(context.get("top_score")))} / 100 · {esc(context.get("top_decision"))}</strong></li>
        <li><span>7d loop</span><strong>{int(number(context.get("sessions_7d")))} sessions · fatigue {number(context.get("avg_fatigue_7d")):.1f} · mood {number(context.get("avg_mood_7d")):.1f}</strong></li>
        <li><span>Quality</span><strong>{int(number(context.get("useful_decision_days_7d")))} useful days · follow {number(context.get("follow_rate_7d")):.0%} · open goals {int(number(context.get("open_goal_count")))}</strong></li>
        <li><span>Signals</span><strong>{int(number(context.get("signal_count_7d")))} active · {esc(context.get("highest_signal_domain"))} urgency {int(number(context.get("highest_signal_urgency")))}</strong></li>
        <li><span>Summary</span><strong>{esc(context.get("context_summary"))}</strong></li>
      </ul>
    """


def render_html(data: CockpitData, source_mode: str) -> str:
    top = latest_top(data)
    kpi_cards = "\n".join(
        f"""
        <section class="kpi">
          <span>{esc(label)}</span>
          <strong>{value}</strong>
          <em>{esc(caption)}</em>
        </section>
        """
        for label, value, caption in kpis(data)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LifeHub Cockpit</title>
  <style>
    :root {{
      --bg: #f6f7f4;
      --panel: #ffffff;
      --text: #18211d;
      --muted: #667067;
      --line: #dfe4dd;
      --green: #2f7d5a;
      --blue: #376f96;
      --red: #a94b4b;
      --amber: #a66f2b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 18px 42px; }}
    header {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 16px; align-items: end; margin-bottom: 22px; }}
    h1 {{ margin: 0; font-size: clamp(28px, 4vw, 46px); letter-spacing: 0; }}
    .subtitle {{ margin: 8px 0 0; color: var(--muted); max-width: 760px; }}
    .stamp {{ text-align: right; color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }}
    .kpi, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(24, 33, 29, 0.04);
    }}
    .kpi {{ padding: 14px; min-height: 118px; display: flex; flex-direction: column; justify-content: space-between; }}
    .kpi span, .kpi em, caption {{ color: var(--muted); font-style: normal; font-size: 13px; }}
    .kpi strong {{ display: block; font-size: 28px; letter-spacing: 0; overflow-wrap: anywhere; }}
    .layout {{ display: grid; grid-template-columns: 1.35fr 0.85fr; gap: 14px; }}
    .panel {{ padding: 16px; min-width: 0; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    .hero-action {{ display: flex; gap: 12px; align-items: center; margin: 10px 0 2px; }}
    .hero-action strong {{ font-size: 34px; }}
    .score-ring {{
      width: 74px;
      aspect-ratio: 1;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: conic-gradient(var(--green) {min(100, max(0, number(top.get("score")))):.0f}%, #e6ebe6 0);
      font-weight: 800;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; table-layout: fixed; }}
    th {{ text-align: left; color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--line); padding: 8px 6px; }}
    td {{ border-bottom: 1px solid var(--line); padding: 9px 6px; vertical-align: middle; overflow-wrap: anywhere; }}
    td span {{ display: block; color: var(--muted); font-size: 12px; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bar {{ height: 9px; background: #e7ece8; border-radius: 99px; overflow: hidden; min-width: 90px; }}
    .bar i {{ display: block; height: 100%; background: linear-gradient(90deg, var(--blue), var(--green)); }}
    .pill {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #eef1ef; color: var(--text); font-size: 12px; }}
    .pill.go, .pill.positive {{ background: #e3f1e9; color: var(--green); }}
    .pill.caution, .pill.neutral {{ background: #f3ead9; color: var(--amber); }}
    .pill.recover, .pill.skip, .pill.negative {{ background: #f5e3e1; color: var(--red); }}
    .hbar {{ display: grid; grid-template-columns: minmax(120px, 180px) 1fr 42px; gap: 10px; align-items: center; margin: 10px 0; }}
    .hbar span {{ color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
    .hbar b {{ height: 12px; background: var(--blue); border-radius: 999px; display: block; }}
    .hbar em {{ color: var(--muted); font-style: normal; font-variant-numeric: tabular-nums; text-align: right; }}
    .empty {{ color: var(--muted); }}
    .stack {{ display: grid; gap: 14px; }}
    .review-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
    .review-list li {{ display: grid; grid-template-columns: 110px 1fr; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }}
    .review-list li:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .review-list span {{ color: var(--muted); font-size: 13px; }}
    .review-list strong {{ font-size: 14px; overflow-wrap: anywhere; }}
    @media (max-width: 920px) {{
      header, .layout {{ grid-template-columns: 1fr; }}
      .stamp {{ text-align: left; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      main {{ padding-inline: 12px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .hero-action strong {{ font-size: 28px; }}
      table {{ font-size: 13px; }}
      th.hide-sm, td.hide-sm {{ display: none; }}
      .bar {{ min-width: 0; }}
      .hbar {{ grid-template-columns: 1fr; gap: 4px; }}
      .hbar em {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>LifeHub Cockpit</h1>
        <p class="subtitle">Local decision intelligence for Saint Petersburg: readiness, recommendations, feedback and context signals without exposing raw personal diary data.</p>
      </div>
      <div class="stamp">Generated {esc(data.generated_at)}<br>Source: {esc(source_mode)}</div>
    </header>
    <section class="grid">{kpi_cards}</section>
    <section class="layout">
      <div class="stack">
        <section class="panel">
          <h2>Today Decision</h2>
          <div class="hero-action">
            <div class="score-ring">{int(number(top.get("score")))}</div>
            <div>
              <strong>{esc(top.get("activity", "No recommendation"))}</strong>
              <p class="subtitle">{esc(top.get("explanation", "Run LifeHub recommendation pipeline to populate the cockpit."))}</p>
            </div>
          </div>
        </section>
        <section class="panel">
          <h2>Readiness By Activity</h2>
          <table>
            <thead><tr><th>Activity</th><th>Score</th><th class="num">Value</th><th>Decision</th><th class="hide-sm">Reason</th></tr></thead>
            <tbody>{readiness_rows(data)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>Recommendation Score Trend</h2>
          {recommendation_bars(data)}
        </section>
      </div>
      <div class="stack">
        <section class="panel">
          <h2>Daily Context Profile</h2>
          {daily_context_card(data)}
        </section>
        <section class="panel">
          <h2>Weekly Review</h2>
          {weekly_review_card(data)}
        </section>
        <section class="panel">
          <h2>Weekly Goal Progress</h2>
          <table>
            <thead><tr><th>Activity</th><th>Progress</th><th class="num">Done</th><th class="num">Target</th></tr></thead>
            <tbody>{goal_progress_rows(data)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>Activity Learning Profile</h2>
          <table>
            <thead><tr><th>Activity</th><th class="num">Events</th><th class="num">Follow</th><th class="num">Good</th><th class="num">Bad</th></tr></thead>
            <tbody>{feedback_profile_rows(data)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>Context Signals</h2>
          <table>
            <thead><tr><th>Date</th><th>Domain</th><th>Direction</th><th class="num">Urgency</th><th class="num">Conf.</th></tr></thead>
            <tbody>{signal_rows(data)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>DataOps Health</h2>
          <table>
            <thead><tr><th>Source</th><th>Status</th><th class="num">Fresh</th><th class="num">Rows</th><th class="num">Errors</th></tr></thead>
            <tbody>{source_health_rows(data)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>Weather Aggregates</h2>
          <table>
            <thead><tr><th>Location</th><th class="num">Temp</th><th class="num">Rain</th><th class="num">Snow</th><th class="num">Gust</th></tr></thead>
            <tbody>{weather_rows(data)}</tbody>
          </table>
        </section>
      </div>
    </section>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demo", action="store_true", help="Use privacy-safe synthetic cockpit data.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    data = load_demo_data() if args.demo else load_live_data()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(data, "demo fixture" if args.demo else "local ClickHouse marts"), encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
