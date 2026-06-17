select
    location_id,
    cast(forecast_time as date) as forecast_date,
    count(*) as hourly_rows,
    min(temperature_c) as min_temperature_c,
    max(temperature_c) as max_temperature_c,
    sum(precipitation_mm) as precipitation_mm,
    sum(rain_mm) as rain_mm,
    sum(snowfall_cm) as snowfall_cm,
    max(snow_depth_cm) as max_snow_depth_cm,
    max(wind_gust_kmh) as max_wind_gust_kmh,
    min(visibility_m) as min_visibility_m,
    max(fetched_at) as latest_fetch_at
from {{ ref('stg_lifehub_weather_hourly') }}
group by 1, 2
