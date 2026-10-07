-- Grain: one row per station availability snapshot (~every 5 minutes per station).

select
    s.snapshot_id,
    s.station_id,
    s.hour_key,
    s.snapshot_at_utc,
    s.snapshot_at_local,
    s.available_bikes,
    s.available_docks,
    st.capacity,
    s.is_open,
    s.is_open and s.available_bikes = 0                 as is_empty,
    s.is_open and s.available_docks = 0                 as is_full,
    s.minutes_observed,
    s.weather_code,
    s.temperature_c,
    w.is_precipitation
from {{ ref('int_station_snapshot_enriched') }} s
left join {{ ref('dim_station') }} st using (station_id)
left join {{ ref('dim_weather') }} w using (weather_code)
