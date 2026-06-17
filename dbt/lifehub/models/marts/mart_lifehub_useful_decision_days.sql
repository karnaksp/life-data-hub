select
    date_trunc('week', feedback_date) as week_start,
    count(distinct case when followed_events > 0 then feedback_date end) as useful_decision_days,
    sum(followed_events) as followed_events,
    sum(skipped_events) as skipped_events,
    sum(followed_events) * 1.0 / nullif(sum(feedback_events), 0) as follow_rate
from {{ ref('mart_lifehub_decision_feedback_daily') }}
group by 1
