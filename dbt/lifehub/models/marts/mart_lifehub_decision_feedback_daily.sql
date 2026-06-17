select
    cast(created_at as date) as feedback_date,
    activity,
    action,
    count(*) as feedback_events,
    sum(case when action = 'followed' then 1 else 0 end) as followed_events,
    sum(case when action = 'skipped' then 1 else 0 end) as skipped_events,
    max(created_at) as latest_feedback_at
from {{ ref('stg_lifehub_decision_feedback_events') }}
group by 1, 2, 3
