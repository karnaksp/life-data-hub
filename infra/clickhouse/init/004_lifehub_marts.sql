CREATE DATABASE IF NOT EXISTS analytics;

CREATE VIEW IF NOT EXISTS analytics.life_latest_readiness_v AS
SELECT
    activity,
    location_id,
    argMax(score, computed_at) AS score,
    argMax(decision, computed_at) AS decision,
    argMax(explanation, computed_at) AS explanation,
    max(computed_at) AS latest_computed_at
FROM analytics.life_readiness_scores
GROUP BY activity, location_id;

CREATE VIEW IF NOT EXISTS analytics.life_location_weather_daily_v AS
SELECT
    location_id,
    toDate(forecast_time) AS forecast_date,
    count() AS hourly_rows,
    min(temperature_c) AS min_temperature_c,
    max(temperature_c) AS max_temperature_c,
    sum(precipitation_mm) AS precipitation_mm,
    sum(rain_mm) AS rain_mm,
    sum(snowfall_cm) AS snowfall_cm,
    max(snow_depth_cm) AS max_snow_depth_cm,
    max(wind_gust_kmh) AS max_wind_gust_kmh,
    min(visibility_m) AS min_visibility_m,
    max(fetched_at) AS latest_fetch_at
FROM analytics.life_weather_hourly
GROUP BY location_id, forecast_date;

CREATE VIEW IF NOT EXISTS analytics.life_activity_daily_v AS
SELECT
    toDate(logged_at) AS activity_date,
    activity_type,
    count() AS sessions,
    round(avg(intensity), 2) AS avg_intensity,
    round(avg(mood), 2) AS avg_mood,
    round(avg(fatigue), 2) AS avg_fatigue,
    countIf(pain_flag) AS pain_sessions,
    countIf(result = 'good') AS good_sessions,
    countIf(result = 'skipped') AS skipped_sessions
FROM analytics.life_activity_events
GROUP BY activity_date, activity_type;

CREATE VIEW IF NOT EXISTS analytics.life_recommendation_daily_v AS
SELECT
    toDate(generated_at) AS recommendation_date,
    recommendation_type,
    activity,
    decision,
    count() AS recommendations,
    round(avg(score), 2) AS avg_score,
    max(generated_at) AS latest_generated_at
FROM analytics.life_recommendation_events
GROUP BY recommendation_date, recommendation_type, activity, decision;

CREATE VIEW IF NOT EXISTS analytics.life_decision_feedback_daily_v AS
SELECT
    toDate(created_at) AS feedback_date,
    activity,
    action,
    count() AS feedback_events,
    countIf(action = 'followed') AS followed_events,
    countIf(action = 'skipped') AS skipped_events,
    round(followed_events / greatest(feedback_events, 1), 3) AS follow_rate,
    max(created_at) AS latest_feedback_at
FROM analytics.life_decision_feedback_events
GROUP BY feedback_date, activity, action;

CREATE VIEW IF NOT EXISTS analytics.life_useful_decision_days_v AS
SELECT
    toStartOfWeek(feedback_date) AS week_start,
    uniqExactIf(feedback_date, followed_events > 0) AS useful_decision_days,
    sum(followed_events) AS total_followed_events,
    sum(skipped_events) AS total_skipped_events,
    round(sum(followed_events) / greatest(sum(feedback_events), 1), 3) AS follow_rate
FROM analytics.life_decision_feedback_daily_v
GROUP BY week_start;

CREATE VIEW IF NOT EXISTS analytics.life_signal_daily_v AS
SELECT
    toDate(occurred_at) AS signal_date,
    domain,
    source,
    direction,
    count() AS signals,
    max(urgency) AS max_urgency,
    round(avg(confidence), 2) AS avg_confidence,
    max(ingested_at) AS latest_ingested_at
FROM analytics.life_signal_events
GROUP BY signal_date, domain, source, direction;

CREATE VIEW IF NOT EXISTS analytics.life_activity_feedback_profile_v AS
SELECT
    activity,
    count() AS feedback_events,
    countIf(action = 'followed') AS followed_events,
    countIf(action = 'skipped') AS skipped_events,
    countIf(result = 'good') AS good_results,
    countIf(result = 'bad') AS bad_results,
    round(followed_events / greatest(feedback_events, 1), 3) AS follow_rate,
    max(created_at) AS latest_feedback_at
FROM analytics.life_decision_feedback_events
WHERE created_at >= now() - INTERVAL 30 DAY
GROUP BY activity;

CREATE VIEW IF NOT EXISTS analytics.life_daily_context_latest_v AS
SELECT
    profile_date,
    timezone,
    argMax(top_activity, generated_at) AS top_activity,
    argMax(top_decision, generated_at) AS top_decision,
    argMax(top_score, generated_at) AS top_score,
    argMax(readiness_state, generated_at) AS readiness_state,
    argMax(sessions_7d, generated_at) AS sessions_7d,
    argMax(avg_mood_7d, generated_at) AS avg_mood_7d,
    argMax(avg_fatigue_7d, generated_at) AS avg_fatigue_7d,
    argMax(pain_sessions_7d, generated_at) AS pain_sessions_7d,
    argMax(useful_decision_days_7d, generated_at) AS useful_decision_days_7d,
    argMax(follow_rate_7d, generated_at) AS follow_rate_7d,
    argMax(open_goal_count, generated_at) AS open_goal_count,
    argMax(signal_count_7d, generated_at) AS signal_count_7d,
    argMax(highest_signal_domain, generated_at) AS highest_signal_domain,
    argMax(highest_signal_urgency, generated_at) AS highest_signal_urgency,
    argMax(context_summary, generated_at) AS context_summary,
    max(generated_at) AS latest_generated_at
FROM analytics.life_daily_context_profiles
GROUP BY profile_date, timezone;
