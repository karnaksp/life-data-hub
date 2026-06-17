SELECT
  profile_date,
  timezone,
  top_activity,
  top_decision,
  top_score,
  readiness_state,
  sessions_7d,
  avg_mood_7d,
  avg_fatigue_7d,
  pain_sessions_7d,
  useful_decision_days_7d,
  follow_rate_7d,
  open_goal_count,
  signal_count_7d,
  highest_signal_domain,
  highest_signal_urgency,
  context_summary,
  generated_at AS latest_generated_at
FROM {{ ref('stg_lifehub_daily_context_profiles') }}
QUALIFY row_number() OVER (
  PARTITION BY profile_date, timezone
  ORDER BY generated_at DESC
) = 1
