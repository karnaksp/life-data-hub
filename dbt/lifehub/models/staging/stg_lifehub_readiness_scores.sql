select
    activity,
    location_id,
    score,
    decision,
    explanation,
    computed_at
from {{ source('clickhouse_lifehub', 'life_readiness_scores') }}
