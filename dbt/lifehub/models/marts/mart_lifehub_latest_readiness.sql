with ranked as (
    select
        activity,
        location_id,
        score,
        decision,
        explanation,
        computed_at,
        row_number() over (
            partition by activity, location_id
            order by computed_at desc
        ) as rn
    from {{ ref('stg_lifehub_readiness_scores') }}
)

select
    activity,
    location_id,
    score,
    decision,
    explanation,
    computed_at as latest_computed_at
from ranked
where rn = 1
