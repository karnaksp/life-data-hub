select
    activity,
    action,
    result,
    note,
    created_at
from {{ source('clickhouse_lifehub', 'life_decision_feedback_events') }}
