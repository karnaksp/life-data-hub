select
    cast(generated_at as date) as recommendation_date,
    recommendation_type,
    activity,
    decision,
    count(*) as recommendations,
    avg(score) as avg_score,
    max(generated_at) as latest_generated_at
from {{ ref('stg_lifehub_recommendation_events') }}
group by 1, 2, 3, 4
