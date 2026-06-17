select
    spot_id,
    label,
    latitude,
    longitude,
    tags,
    source,
    updated_at
from {{ source('postgres_lifehub', 'life_spots') }}
