CREATE DATABASE IF NOT EXISTS analytics;

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
ORDER BY (location_id, forecast_time);

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
ORDER BY (activity, location_id, computed_at);

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
ORDER BY (activity_type, logged_at);

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
ORDER BY (recommendation_type, activity, generated_at);

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
ORDER BY (activity, action, created_at);

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
ORDER BY (domain, source, signal_id);

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
ORDER BY (profile_date, timezone);
