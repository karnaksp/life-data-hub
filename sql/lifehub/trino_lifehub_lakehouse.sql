-- LifeHub lakehouse / DWH checks.
-- Run in Trino after `lifehub_lakehouse_pipeline` loads Iceberg tables.

SELECT
    source_name,
    event_type,
    count(*) AS events,
    min(event_time) AS min_event_time,
    max(event_time) AS max_event_time
FROM iceberg.bronze.lifehub_events
GROUP BY source_name, event_type
ORDER BY source_name, event_type;

SELECT
    source_name,
    privacy_class,
    count(*) AS valid_events
FROM iceberg.silver.lifehub_events
WHERE event_time IS NOT NULL
  AND source_name IS NOT NULL
  AND event_type IS NOT NULL
GROUP BY source_name, privacy_class
ORDER BY source_name, privacy_class;

SELECT
    event_type,
    count(*) AS decision_events
FROM iceberg.gold.lifehub_decision_events
GROUP BY event_type
ORDER BY event_type;

SELECT
    count(*) AS forbidden_payload_rows
FROM iceberg.bronze.lifehub_events
WHERE regexp_like(json_payload, '(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|pain_text|raw_diary_notes|raw_sleep_notes|home_address)');

SELECT
    date(event_time) AS sleep_date,
    count(*) AS nights,
    avg(CAST(json_extract_scalar(json_payload, '$.duration_minutes') AS DOUBLE)) AS avg_duration_minutes,
    avg(CAST(json_extract_scalar(json_payload, '$.quality_score') AS DOUBLE)) AS avg_quality_score,
    avg(CAST(json_extract_scalar(json_payload, '$.recovery_score') AS DOUBLE)) AS avg_recovery_score,
    avg(CAST(json_extract_scalar(json_payload, '$.sleep_efficiency') AS DOUBLE)) AS avg_sleep_efficiency
FROM iceberg.silver.lifehub_events
WHERE source_name = 'sleep_quality'
  AND event_type = 'sleep_quality_night'
GROUP BY date(event_time)
ORDER BY sleep_date DESC;
