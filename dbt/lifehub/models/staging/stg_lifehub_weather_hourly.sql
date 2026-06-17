select
    location_id,
    forecast_time,
    temperature_c,
    precipitation_mm,
    rain_mm,
    snowfall_cm,
    snow_depth_cm,
    wind_speed_kmh,
    wind_gust_kmh,
    visibility_m,
    is_day,
    fetched_at
from {{ source('clickhouse_lifehub', 'life_weather_hourly') }}
