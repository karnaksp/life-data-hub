select
    signal_id,
    domain,
    source,
    title,
    direction,
    urgency,
    confidence,
    summary,
    occurred_at,
    ingested_at
from {{ source('clickhouse_lifehub', 'life_signal_events') }}
