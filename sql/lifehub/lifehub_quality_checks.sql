-- Postgres checks. Run inside the Postgres service:
-- psql -U admin -d demo -f sql/lifehub/lifehub_quality_checks.sql

SELECT 'life_spots_count' AS check_name, count(*)::text AS observed_value
FROM life_spots;

SELECT 'life_spots_missing_labels' AS check_name, count(*)::text AS observed_value
FROM life_spots
WHERE label IS NULL OR btrim(label) = '';

SELECT 'life_spots_bad_coordinates' AS check_name, count(*)::text AS observed_value
FROM life_spots
WHERE latitude NOT BETWEEN -90 AND 90
   OR longitude NOT BETWEEN -180 AND 180;

SELECT 'life_activity_bad_scores' AS check_name, count(*)::text AS observed_value
FROM life_activity_log
WHERE intensity NOT BETWEEN 1 AND 10
   OR mood NOT BETWEEN 1 AND 10
   OR fatigue NOT BETWEEN 1 AND 10;

SELECT 'life_activity_unknown_types' AS check_name, count(*)::text AS observed_value
FROM life_activity_log
WHERE activity_type NOT IN ('skate', 'snowboard', 'volleyball', 'moto_lesson', 'gym', 'walk', 'rest');

SELECT 'life_activity_unknown_results' AS check_name, count(*)::text AS observed_value
FROM life_activity_log
WHERE result NOT IN ('good', 'ok', 'bad', 'skipped');

SELECT 'life_recommendation_bad_scores' AS check_name, count(*)::text AS observed_value
FROM life_recommendation_events
WHERE score NOT BETWEEN 0 AND 100
   OR decision NOT IN ('go', 'caution', 'recover')
   OR reasons IS NULL
   OR btrim(reasons) = '';

SELECT 'life_feedback_bad_actions' AS check_name, count(*)::text AS observed_value
FROM life_decision_feedback
WHERE action NOT IN ('followed', 'skipped', 'changed')
   OR (result IS NOT NULL AND result NOT IN ('good', 'ok', 'bad', 'skipped'));

SELECT 'life_signal_bad_values' AS check_name, count(*)::text AS observed_value
FROM life_signal_events
WHERE domain NOT IN ('market', 'github', 'career', 'wellbeing', 'system')
   OR direction NOT IN ('positive', 'negative', 'neutral')
   OR urgency NOT BETWEEN 1 AND 10
   OR confidence NOT BETWEEN 1 AND 100
   OR btrim(title) = '';

SELECT 'life_daily_context_bad_values' AS check_name, count(*)::text AS observed_value
FROM life_daily_context_profiles
WHERE top_score NOT BETWEEN 0 AND 100
   OR top_decision NOT IN ('go', 'caution', 'recover')
   OR sessions_7d < 0
   OR avg_mood_7d NOT BETWEEN 0 AND 10
   OR avg_fatigue_7d NOT BETWEEN 0 AND 10
   OR useful_decision_days_7d NOT BETWEEN 0 AND 7
   OR follow_rate_7d NOT BETWEEN 0 AND 1
   OR highest_signal_urgency NOT BETWEEN 0 AND 10
   OR btrim(context_summary) = '';
