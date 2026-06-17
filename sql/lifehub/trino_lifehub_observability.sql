-- Cross-engine LifeHub observability examples for Trino.
-- Requires the ClickHouse and Postgres catalogs configured in infra/trino/config/catalog.

SELECT
  'postgres_spots' AS metric,
  count(*) AS value
FROM pg_demo_retail.public.life_spots
UNION ALL
SELECT
  'postgres_activity_rows' AS metric,
  count(*) AS value
FROM pg_demo_retail.public.life_activity_log
UNION ALL
SELECT
  'clickhouse_weather_rows' AS metric,
  count(*) AS value
FROM clickhouse.analytics.life_weather_hourly
UNION ALL
SELECT
  'clickhouse_readiness_rows' AS metric,
  count(*) AS value
FROM clickhouse.analytics.life_readiness_scores
UNION ALL
SELECT
  'clickhouse_recommendation_rows' AS metric,
  count(*) AS value
FROM clickhouse.analytics.life_recommendation_events
UNION ALL
SELECT
  'clickhouse_feedback_rows' AS metric,
  count(*) AS value
FROM clickhouse.analytics.life_decision_feedback_events
UNION ALL
SELECT
  'clickhouse_signal_rows' AS metric,
  count(*) AS value
FROM clickhouse.analytics.life_signal_events;

SELECT
  activity,
  decision,
  count(*) AS score_rows,
  min(score) AS min_score,
  max(score) AS max_score,
  max(computed_at) AS latest_computed_at
FROM clickhouse.analytics.life_readiness_scores
GROUP BY activity, decision
ORDER BY activity, decision;

SELECT
  recommendation_type,
  activity,
  decision,
  count(*) AS recommendations,
  min(score) AS min_score,
  max(score) AS max_score,
  max(generated_at) AS latest_generated_at
FROM clickhouse.analytics.life_recommendation_events
GROUP BY recommendation_type, activity, decision
ORDER BY recommendation_type, activity, decision;

SELECT
  week_start,
  useful_decision_days,
  followed_events,
  skipped_events,
  follow_rate
FROM clickhouse.analytics.life_useful_decision_days_v
ORDER BY week_start DESC
LIMIT 12;

SELECT
  signal_date,
  domain,
  source,
  direction,
  signals,
  max_urgency,
  avg_confidence
FROM clickhouse.analytics.life_signal_daily_v
ORDER BY signal_date DESC, max_urgency DESC
LIMIT 50;

SELECT
  s.spot_id,
  s.label,
  s.source,
  cardinality(s.tags) AS tag_count,
  max(r.computed_at) AS latest_score_at
FROM pg_demo_retail.public.life_spots s
LEFT JOIN clickhouse.analytics.life_readiness_scores r
  ON r.location_id = s.spot_id
GROUP BY s.spot_id, s.label, s.source, cardinality(s.tags)
ORDER BY latest_score_at DESC NULLS LAST, s.label
LIMIT 50;
