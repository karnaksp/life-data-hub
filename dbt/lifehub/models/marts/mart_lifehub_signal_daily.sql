select
    cast(occurred_at as date) as signal_date,
    domain,
    source,
    direction,
    count(*) as signals,
    max(urgency) as max_urgency,
    avg(confidence) as avg_confidence,
    max(ingested_at) as latest_ingested_at
from {{ ref('stg_lifehub_signal_events') }}
group by 1, 2, 3, 4
