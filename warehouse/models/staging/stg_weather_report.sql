select
    update_time                         as observed_at_utc,
    {{ to_local('update_time') }}       as observed_at_local,
    temp                                as temperature_c,
    feels_like                          as feels_like_c,
    humidity                            as humidity_pct,
    wind_speed                          as wind_speed_ms,
    visibility                          as visibility_m,
    weather_id                          as weather_code
from {{ source('raw', 'weather_report') }}
