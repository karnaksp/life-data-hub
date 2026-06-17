"""Storage adapters for LifeHub services."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from lifehub.config import Location
from lifehub.context import DailyContextProfile
from lifehub.diary import ActivityLog
from lifehub.feedback import DecisionFeedback
from lifehub.places import Spot
from lifehub.recommendations import RecommendationEvent
from lifehub.scoring import ReadinessScore
from lifehub.signals import ContextSignal
from lifehub.weather import WeatherHour


def insert_weather_clickhouse(clickhouse_url: str, rows: Iterable[WeatherHour]) -> None:
    payload = "\n".join(json.dumps(weather_row(row)) for row in rows)
    if payload:
        ensure_clickhouse_schema(clickhouse_url)
        clickhouse_insert(clickhouse_url, "analytics.life_weather_hourly", payload)


def insert_scores_clickhouse(clickhouse_url: str, rows: Iterable[ReadinessScore]) -> None:
    payload = "\n".join(json.dumps(asdict(row)) for row in rows)
    if payload:
        ensure_clickhouse_schema(clickhouse_url)
        clickhouse_insert(clickhouse_url, "analytics.life_readiness_scores", payload)


def insert_activity_clickhouse(clickhouse_url: str, log: ActivityLog) -> None:
    ensure_clickhouse_schema(clickhouse_url)
    clickhouse_insert(
        clickhouse_url,
        "analytics.life_activity_events",
        json.dumps(activity_row(log)),
    )


def insert_recommendations_clickhouse(
    clickhouse_url: str, rows: Iterable[RecommendationEvent]
) -> None:
    payload = "\n".join(json.dumps(recommendation_row(row)) for row in rows)
    if payload:
        ensure_clickhouse_schema(clickhouse_url)
        clickhouse_insert(clickhouse_url, "analytics.life_recommendation_events", payload)


def insert_feedback_clickhouse(clickhouse_url: str, feedback: DecisionFeedback) -> None:
    ensure_clickhouse_schema(clickhouse_url)
    clickhouse_insert(
        clickhouse_url,
        "analytics.life_decision_feedback_events",
        json.dumps(feedback_row(feedback)),
    )


def insert_signals_clickhouse(clickhouse_url: str, rows: Iterable[ContextSignal]) -> None:
    payload = "\n".join(json.dumps(signal_row(row)) for row in rows)
    if payload:
        ensure_clickhouse_schema(clickhouse_url)
        clickhouse_insert(clickhouse_url, "analytics.life_signal_events", payload)


def insert_daily_context_clickhouse(clickhouse_url: str, profile: DailyContextProfile) -> None:
    ensure_clickhouse_schema(clickhouse_url)
    clickhouse_insert(
        clickhouse_url,
        "analytics.life_daily_context_profiles",
        json.dumps(daily_context_row(profile)),
    )


def ensure_clickhouse_schema(clickhouse_url: str) -> None:
    statements = [
        "CREATE DATABASE IF NOT EXISTS analytics",
        """
        CREATE TABLE IF NOT EXISTS analytics.life_weather_hourly
        (
            location_id LowCardinality(String),
            forecast_time DateTime,
            temperature_c Float32,
            precipitation_mm Float32,
            rain_mm Float32,
            snowfall_cm Float32,
            snow_depth_cm Float32,
            wind_speed_kmh Float32,
            wind_gust_kmh Float32,
            visibility_m Float32,
            is_day Bool,
            fetched_at DateTime64(3, 'UTC') DEFAULT now()
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(forecast_time)
        ORDER BY (location_id, forecast_time)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_readiness_scores
        (
            activity LowCardinality(String),
            location_id LowCardinality(String),
            score UInt8,
            decision LowCardinality(String),
            explanation String,
            computed_at DateTime64(3, 'UTC') DEFAULT now()
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(computed_at)
        ORDER BY (activity, location_id, computed_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_activity_events
        (
            activity_type LowCardinality(String),
            start_time Nullable(DateTime64(3, 'UTC')),
            end_time Nullable(DateTime64(3, 'UTC')),
            location_label Nullable(String),
            intensity UInt8,
            mood UInt8,
            fatigue UInt8,
            pain_flag Bool,
            pain_text Nullable(String),
            result LowCardinality(String),
            notes String,
            logged_at DateTime64(3, 'UTC')
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(logged_at)
        ORDER BY (activity_type, logged_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_recommendation_events
        (
            recommendation_type LowCardinality(String),
            activity LowCardinality(String),
            location_id LowCardinality(String),
            score UInt8,
            decision LowCardinality(String),
            reasons String,
            generated_at DateTime64(3, 'UTC')
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(generated_at)
        ORDER BY (recommendation_type, activity, generated_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_decision_feedback_events
        (
            activity LowCardinality(String),
            action LowCardinality(String),
            result Nullable(String),
            note String,
            created_at DateTime64(3, 'UTC')
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(created_at)
        ORDER BY (activity, action, created_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_signal_events
        (
            signal_id String,
            domain LowCardinality(String),
            source LowCardinality(String),
            title String,
            direction LowCardinality(String),
            urgency UInt8,
            confidence UInt8,
            summary String,
            occurred_at DateTime64(3, 'UTC'),
            ingested_at DateTime64(3, 'UTC')
        )
        ENGINE = ReplacingMergeTree(ingested_at)
        PARTITION BY toYYYYMM(occurred_at)
        ORDER BY (domain, source, signal_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics.life_daily_context_profiles
        (
            profile_date Date,
            timezone LowCardinality(String),
            top_activity LowCardinality(String),
            top_decision LowCardinality(String),
            top_score UInt8,
            readiness_state LowCardinality(String),
            sessions_7d UInt16,
            avg_mood_7d Float32,
            avg_fatigue_7d Float32,
            pain_sessions_7d UInt16,
            useful_decision_days_7d UInt8,
            follow_rate_7d Float32,
            open_goal_count UInt8,
            signal_count_7d UInt16,
            highest_signal_domain LowCardinality(String),
            highest_signal_urgency UInt8,
            context_summary String,
            generated_at DateTime64(3, 'UTC')
        )
        ENGINE = ReplacingMergeTree(generated_at)
        PARTITION BY toYYYYMM(profile_date)
        ORDER BY (profile_date, timezone)
        """,
    ]
    for statement in statements:
        clickhouse_query(clickhouse_url, statement)


def weather_row(row: WeatherHour) -> dict:
    data = asdict(row)
    data["forecast_time"] = clickhouse_datetime(data["forecast_time"])
    data["fetched_at"] = clickhouse_datetime(data["fetched_at"])
    return data


def activity_row(log: ActivityLog) -> dict:
    data = asdict(log)
    for key in ["start_time", "end_time", "logged_at"]:
        data[key] = clickhouse_datetime(data[key]) if data.get(key) else None
    return data


def recommendation_row(row: RecommendationEvent) -> dict:
    data = asdict(row)
    data["generated_at"] = clickhouse_datetime(data["generated_at"])
    return data


def feedback_row(row: DecisionFeedback) -> dict:
    data = asdict(row)
    data["created_at"] = clickhouse_datetime(data["created_at"])
    return data


def signal_row(row: ContextSignal) -> dict:
    data = asdict(row)
    data["occurred_at"] = clickhouse_datetime(data["occurred_at"])
    data["ingested_at"] = clickhouse_datetime(data["ingested_at"])
    return data


def daily_context_row(row: DailyContextProfile) -> dict:
    data = asdict(row)
    data["generated_at"] = clickhouse_datetime(data["generated_at"])
    return data


def clickhouse_datetime(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value.replace("T", " ")
    return parsed.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def clickhouse_insert(clickhouse_url: str, table: str, json_each_row_payload: str) -> None:
    query = f"INSERT INTO {table} FORMAT JSONEachRow"
    clickhouse_query(clickhouse_url, query, json_each_row_payload.encode("utf-8"))


def clickhouse_query(clickhouse_url: str, query: str, data: bytes | None = None) -> None:
    parsed = urllib.parse.urlsplit(clickhouse_url)
    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    params["query"] = query
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(params), parsed.fragment)
    )
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def upsert_spots_postgres(postgres_dsn: str, locations: list[Location] | list[Spot]) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            for item in locations:
                cur.execute(
                    """
                    INSERT INTO life_spots (spot_id, label, latitude, longitude, tags, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (spot_id) DO UPDATE SET
                      label = EXCLUDED.label,
                      latitude = EXCLUDED.latitude,
                      longitude = EXCLUDED.longitude,
                      tags = EXCLUDED.tags,
                      source = EXCLUDED.source,
                      updated_at = now()
                    """,
                    (
                        item.id,
                        item.label,
                        item.latitude,
                        item.longitude,
                        list(item.tags),
                        getattr(item, "source", "config"),
                    ),
                )


def insert_activity_postgres(postgres_dsn: str, log: ActivityLog) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                INSERT INTO life_activity_log
                  (
                    activity_type, start_time, end_time, location_label,
                    intensity, mood, fatigue, pain_flag, pain_text,
                    result, notes, logged_at
                  )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    log.activity_type,
                    log.start_time,
                    log.end_time,
                    log.location_label,
                    log.intensity,
                    log.mood,
                    log.fatigue,
                    log.pain_flag,
                    log.pain_text,
                    log.result,
                    log.notes,
                    log.logged_at,
                ),
            )


def insert_digest_run_postgres(
    postgres_dsn: str,
    digest_type: str,
    sent_to: str,
    status: str,
    summary: str,
) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                INSERT INTO life_digest_runs (digest_type, sent_to, status, summary)
                VALUES (%s, %s, %s, %s)
                """,
                (digest_type, sent_to, status, summary[:1000]),
            )


def insert_recommendations_postgres(
    postgres_dsn: str,
    recommendations: Iterable[RecommendationEvent],
) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            for item in recommendations:
                cur.execute(
                    """
                    INSERT INTO life_recommendation_events
                      (
                        recommendation_type, activity, location_id, score,
                        decision, reasons, generated_at
                      )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item.recommendation_type,
                        item.activity,
                        item.location_id,
                        item.score,
                        item.decision,
                        item.reasons,
                        item.generated_at,
                    ),
                )


def insert_feedback_postgres(postgres_dsn: str, feedback: DecisionFeedback) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                INSERT INTO life_decision_feedback
                  (activity, action, result, note, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    feedback.activity,
                    feedback.action,
                    feedback.result,
                    feedback.note,
                    feedback.created_at,
                ),
            )


def upsert_signals_postgres(postgres_dsn: str, signals: Iterable[ContextSignal]) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            for item in signals:
                cur.execute(
                    """
                    INSERT INTO life_signal_events
                      (
                        signal_id, domain, source, title, direction, urgency,
                        confidence, summary, occurred_at, ingested_at
                      )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (signal_id) DO UPDATE SET
                      domain = EXCLUDED.domain,
                      source = EXCLUDED.source,
                      title = EXCLUDED.title,
                      direction = EXCLUDED.direction,
                      urgency = EXCLUDED.urgency,
                      confidence = EXCLUDED.confidence,
                      summary = EXCLUDED.summary,
                      occurred_at = EXCLUDED.occurred_at,
                      ingested_at = EXCLUDED.ingested_at
                    """,
                    (
                        item.signal_id,
                        item.domain,
                        item.source,
                        item.title,
                        item.direction,
                        item.urgency,
                        item.confidence,
                        item.summary,
                        item.occurred_at,
                        item.ingested_at,
                    ),
                )


def upsert_daily_context_postgres(postgres_dsn: str, profile: DailyContextProfile) -> None:
    import psycopg2

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                INSERT INTO life_daily_context_profiles
                  (
                    profile_date, timezone, top_activity, top_decision, top_score,
                    readiness_state, sessions_7d, avg_mood_7d, avg_fatigue_7d,
                    pain_sessions_7d, useful_decision_days_7d, follow_rate_7d,
                    open_goal_count, signal_count_7d, highest_signal_domain,
                    highest_signal_urgency, context_summary, generated_at
                  )
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (profile_date, timezone) DO UPDATE SET
                  top_activity = EXCLUDED.top_activity,
                  top_decision = EXCLUDED.top_decision,
                  top_score = EXCLUDED.top_score,
                  readiness_state = EXCLUDED.readiness_state,
                  sessions_7d = EXCLUDED.sessions_7d,
                  avg_mood_7d = EXCLUDED.avg_mood_7d,
                  avg_fatigue_7d = EXCLUDED.avg_fatigue_7d,
                  pain_sessions_7d = EXCLUDED.pain_sessions_7d,
                  useful_decision_days_7d = EXCLUDED.useful_decision_days_7d,
                  follow_rate_7d = EXCLUDED.follow_rate_7d,
                  open_goal_count = EXCLUDED.open_goal_count,
                  signal_count_7d = EXCLUDED.signal_count_7d,
                  highest_signal_domain = EXCLUDED.highest_signal_domain,
                  highest_signal_urgency = EXCLUDED.highest_signal_urgency,
                  context_summary = EXCLUDED.context_summary,
                  generated_at = EXCLUDED.generated_at
                """,
                (
                    profile.profile_date,
                    profile.timezone,
                    profile.top_activity,
                    profile.top_decision,
                    profile.top_score,
                    profile.readiness_state,
                    profile.sessions_7d,
                    profile.avg_mood_7d,
                    profile.avg_fatigue_7d,
                    profile.pain_sessions_7d,
                    profile.useful_decision_days_7d,
                    profile.follow_rate_7d,
                    profile.open_goal_count,
                    profile.signal_count_7d,
                    profile.highest_signal_domain,
                    profile.highest_signal_urgency,
                    profile.context_summary,
                    profile.generated_at,
                ),
            )


def fetch_recent_signals_postgres(postgres_dsn: str, limit: int = 5) -> list[ContextSignal]:
    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                SELECT
                  signal_id, domain, source, title, direction, urgency,
                  confidence, summary, occurred_at, ingested_at
                FROM life_signal_events
                WHERE occurred_at >= now() - interval '7 days'
                ORDER BY urgency DESC, confidence DESC, occurred_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [
        ContextSignal(
            signal_id=row["signal_id"],
            domain=row["domain"],
            source=row["source"],
            title=row["title"],
            direction=row["direction"],
            urgency=row["urgency"],
            confidence=row["confidence"],
            summary=row["summary"],
            occurred_at=row["occurred_at"].isoformat(),
            ingested_at=row["ingested_at"].isoformat(),
        )
        for row in rows
    ]


def fetch_week_summary_postgres(postgres_dsn: str) -> dict:
    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                SELECT
                  count(*)::int AS sessions,
                  coalesce(round(avg(intensity), 1), 0)::float AS avg_intensity,
                  coalesce(round(avg(mood), 1), 0)::float AS avg_mood,
                  coalesce(round(avg(fatigue), 1), 0)::float AS avg_fatigue,
                  count(*) FILTER (WHERE pain_flag)::int AS pain_sessions
                FROM life_activity_log
                WHERE logged_at >= now() - interval '7 days'
                """
            )
            summary = dict(cur.fetchone())
            cur.execute(
                """
                SELECT activity_type, count(*)::int AS sessions
                FROM life_activity_log
                WHERE logged_at >= now() - interval '7 days'
                GROUP BY activity_type
                ORDER BY sessions DESC, activity_type
                """
            )
            summary["by_activity"] = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT result, count(*)::int AS sessions
                FROM life_activity_log
                WHERE logged_at >= now() - interval '7 days'
                GROUP BY result
                ORDER BY sessions DESC, result
                """
            )
            summary["by_result"] = [dict(row) for row in cur.fetchall()]
    return summary


def fetch_feedback_profile_postgres(postgres_dsn: str, days: int = 30) -> dict[str, dict]:
    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                SELECT
                  activity,
                  count(*)::int AS feedback_events,
                  count(*) FILTER (WHERE action = 'followed')::int AS followed_events,
                  count(*) FILTER (WHERE action = 'skipped')::int AS skipped_events,
                  count(*) FILTER (WHERE result = 'good')::int AS good_results,
                  count(*) FILTER (WHERE result = 'bad')::int AS bad_results,
                  coalesce(
                    round(
                      count(*) FILTER (WHERE action = 'followed')::numeric
                      / nullif(count(*), 0),
                      3
                    ),
                    0
                  )::float AS follow_rate
                FROM life_decision_feedback
                WHERE created_at >= now() - (%s || ' days')::interval
                GROUP BY activity
                ORDER BY activity
                """,
                (days,),
            )
            rows = cur.fetchall()
    return {row["activity"]: dict(row) for row in rows}


def fetch_decision_metrics_postgres(postgres_dsn: str, days: int = 7) -> dict:
    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_postgres_schema(cur)
            cur.execute(
                """
                SELECT
                  (count(DISTINCT date_trunc('day', created_at))
                    FILTER (WHERE action = 'followed'))::int AS useful_decision_days,
                  (count(*) FILTER (WHERE action = 'followed'))::int AS followed_events,
                  (count(*) FILTER (WHERE action = 'skipped'))::int AS skipped_events,
                  coalesce(
                    round(
                      count(*) FILTER (WHERE action = 'followed')::numeric
                      / nullif(count(*) FILTER (WHERE action IN ('followed', 'skipped')), 0),
                      3
                    ),
                    0
                  )::float AS follow_rate
                FROM life_decision_feedback
                WHERE created_at >= now() - (%s || ' days')::interval
                """,
                (days,),
            )
            row = cur.fetchone()
    return dict(row or {})


def ensure_postgres_schema(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS life_user_preferences(
          preference_key   TEXT PRIMARY KEY,
          preference_value TEXT NOT NULL,
          updated_at       TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_spots(
          spot_id    TEXT PRIMARY KEY,
          label      TEXT NOT NULL,
          latitude   DOUBLE PRECISION NOT NULL,
          longitude  DOUBLE PRECISION NOT NULL,
          tags       TEXT[] NOT NULL DEFAULT '{}',
          source     TEXT NOT NULL DEFAULT 'config',
          updated_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_activity_log(
          activity_id   BIGSERIAL PRIMARY KEY,
          activity_type TEXT NOT NULL CHECK (
            activity_type IN ('skate', 'snowboard', 'volleyball', 'moto_lesson', 'gym', 'walk', 'rest')
          ),
          start_time     TIMESTAMPTZ,
          end_time       TIMESTAMPTZ,
          location_label TEXT,
          intensity      INT CHECK (intensity BETWEEN 1 AND 10),
          mood           INT CHECK (mood BETWEEN 1 AND 10),
          fatigue        INT CHECK (fatigue BETWEEN 1 AND 10),
          pain_flag      BOOLEAN NOT NULL DEFAULT false,
          pain_text      TEXT,
          result         TEXT CHECK (result IN ('good', 'ok', 'bad', 'skipped')),
          notes          TEXT,
          logged_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_digest_runs(
          digest_id    BIGSERIAL PRIMARY KEY,
          digest_type  TEXT NOT NULL,
          sent_to      TEXT,
          status       TEXT NOT NULL CHECK (status IN ('planned', 'sent', 'skipped', 'failed')),
          summary      TEXT,
          generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_recommendation_events(
          recommendation_id   BIGSERIAL PRIMARY KEY,
          recommendation_type TEXT NOT NULL,
          activity            TEXT NOT NULL,
          location_id         TEXT NOT NULL,
          score               INT NOT NULL CHECK (score BETWEEN 0 AND 100),
          decision            TEXT NOT NULL CHECK (decision IN ('go', 'caution', 'recover')),
          reasons             TEXT NOT NULL,
          generated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_decision_feedback(
          feedback_id BIGSERIAL PRIMARY KEY,
          activity    TEXT NOT NULL,
          action      TEXT NOT NULL CHECK (action IN ('followed', 'skipped', 'changed')),
          result      TEXT CHECK (result IN ('good', 'ok', 'bad', 'skipped')),
          note        TEXT,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_signal_events(
          signal_id   TEXT PRIMARY KEY,
          domain      TEXT NOT NULL CHECK (domain IN ('market', 'github', 'career', 'wellbeing', 'system')),
          source      TEXT NOT NULL,
          title       TEXT NOT NULL,
          direction   TEXT NOT NULL CHECK (direction IN ('positive', 'negative', 'neutral')),
          urgency     INT NOT NULL CHECK (urgency BETWEEN 1 AND 10),
          confidence  INT NOT NULL CHECK (confidence BETWEEN 1 AND 100),
          summary     TEXT,
          occurred_at TIMESTAMPTZ NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS life_daily_context_profiles(
          profile_date            DATE NOT NULL,
          timezone                TEXT NOT NULL,
          top_activity            TEXT NOT NULL,
          top_decision            TEXT NOT NULL CHECK (top_decision IN ('go', 'caution', 'recover')),
          top_score               INT NOT NULL CHECK (top_score BETWEEN 0 AND 100),
          readiness_state         TEXT NOT NULL,
          sessions_7d             INT NOT NULL CHECK (sessions_7d >= 0),
          avg_mood_7d             NUMERIC(4,2) NOT NULL CHECK (avg_mood_7d BETWEEN 0 AND 10),
          avg_fatigue_7d          NUMERIC(4,2) NOT NULL CHECK (avg_fatigue_7d BETWEEN 0 AND 10),
          pain_sessions_7d        INT NOT NULL CHECK (pain_sessions_7d >= 0),
          useful_decision_days_7d INT NOT NULL CHECK (useful_decision_days_7d BETWEEN 0 AND 7),
          follow_rate_7d          NUMERIC(5,3) NOT NULL CHECK (follow_rate_7d BETWEEN 0 AND 1),
          open_goal_count         INT NOT NULL CHECK (open_goal_count >= 0),
          signal_count_7d         INT NOT NULL CHECK (signal_count_7d >= 0),
          highest_signal_domain   TEXT NOT NULL,
          highest_signal_urgency  INT NOT NULL CHECK (highest_signal_urgency BETWEEN 0 AND 10),
          context_summary         TEXT NOT NULL,
          generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (profile_date, timezone)
        );

        CREATE INDEX IF NOT EXISTS idx_life_activity_logged ON life_activity_log(logged_at);
        CREATE INDEX IF NOT EXISTS idx_life_activity_type ON life_activity_log(activity_type);
        CREATE INDEX IF NOT EXISTS idx_life_spots_tags ON life_spots USING GIN(tags);
        CREATE INDEX IF NOT EXISTS idx_life_recommendation_generated ON life_recommendation_events(generated_at);
        CREATE INDEX IF NOT EXISTS idx_life_recommendation_activity ON life_recommendation_events(activity);
        CREATE INDEX IF NOT EXISTS idx_life_feedback_created ON life_decision_feedback(created_at);
        CREATE INDEX IF NOT EXISTS idx_life_feedback_activity ON life_decision_feedback(activity);
        CREATE INDEX IF NOT EXISTS idx_life_signal_occurred ON life_signal_events(occurred_at);
        CREATE INDEX IF NOT EXISTS idx_life_signal_domain ON life_signal_events(domain);
        CREATE INDEX IF NOT EXISTS idx_life_daily_context_generated ON life_daily_context_profiles(generated_at);
        """
    )
