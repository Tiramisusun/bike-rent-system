select
    forecast_time                       as forecast_for_utc,
    {{ to_local('forecast_time') }}     as forecast_for_local,
    fetched_at                          as fetched_at_utc,
    temp                                as temperature_c,
    feels_like                          as feels_like_c,
    humidity                            as humidity_pct,
    wind_speed                          as wind_speed_ms,
    visibility                          as visibility_m,
    weather_id                          as weather_code
from {{ source('raw', 'weather_forecast') }}
