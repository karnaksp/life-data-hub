select
    recommendation_type,
    activity,
    location_id,
    score,
    decision,
    reasons,
    generated_at
from {{ source('clickhouse_lifehub', 'life_recommendation_events') }}
