select
  activity,
  count(*) as feedback_events,
  countIf(action = 'followed') as followed_events,
  countIf(action = 'skipped') as skipped_events,
  countIf(result = 'good') as good_results,
  countIf(result = 'bad') as bad_results,
  round(followed_events / greatest(feedback_events, 1), 3) as follow_rate,
  max(created_at) as latest_feedback_at
from {{ source('analytics', 'life_decision_feedback_events') }}
where created_at >= now() - interval 30 day
group by activity
