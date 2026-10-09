select
    weather_code,
    condition_group,
    condition_description,
    -- OpenWeather groups that mean people get wet on a bike
    condition_group in ('Rain', 'Drizzle', 'Thunderstorm', 'Snow') as is_precipitation
from {{ ref('stg_weather_condition') }}
