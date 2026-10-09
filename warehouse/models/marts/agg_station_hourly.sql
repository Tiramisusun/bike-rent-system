-- Grain: one row per station per local hour that has at least one snapshot.
-- Shared by the dashboard, the model features and ad-hoc analysis, so metric
-- definitions live here once.

select
    f.station_id,
    f.hour_key,
    t.date_day,
    t.hour_of_day,
    t.is_weekend,
    t.is_public_holiday,
    t.is_peak_hour,
    count(*)                                                        as snapshot_count,
    sum(f.minutes_observed)                                         as observed_minutes,
    sum(case when f.is_empty then f.minutes_observed else 0 end)    as empty_minutes,
    sum(case when f.is_full  then f.minutes_observed else 0 end)    as full_minutes,
    round(avg(f.available_bikes), 2)                                as avg_available_bikes,
    min(f.available_bikes)                                          as min_available_bikes,
    max(f.available_bikes)                                          as max_available_bikes,
    round(avg(f.available_docks), 2)                                as avg_available_docks,
    round(avg(f.temperature_c)::numeric, 1)                         as avg_temperature_c,
    bool_or(f.is_precipitation)                                     as had_precipitation
from {{ ref('fct_station_snapshot') }} f
join {{ ref('dim_time') }} t using (hour_key)
group by 1, 2, 3, 4, 5, 6, 7
