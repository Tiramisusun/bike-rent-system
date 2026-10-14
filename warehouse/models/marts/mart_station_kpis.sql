-- Grain: one row per station. The standard operational metrics, defined once:
--   empty_minutes        minutes the station was open with 0 bikes
--   full_minutes         minutes the station was open with 0 free docks
--   peak_shortage_rate   share of peak-hour minutes (working days, local time) spent empty
--   rain_bike_delta      avg bikes in precipitation hours minus avg bikes in dry hours

with hourly as (

    select * from {{ ref('agg_station_hourly') }}

)

select
    h.station_id,
    s.station_name,
    s.zone,
    s.capacity,
    sum(h.observed_minutes)                                                 as observed_minutes,
    sum(h.empty_minutes)                                                    as empty_minutes,
    sum(h.full_minutes)                                                     as full_minutes,
    round(sum(h.empty_minutes) / nullif(sum(h.observed_minutes), 0), 4)     as empty_share,
    round(sum(h.full_minutes)  / nullif(sum(h.observed_minutes), 0), 4)     as full_share,
    sum(h.observed_minutes) filter (where h.is_peak_hour)                   as peak_observed_minutes,
    round(
        sum(h.empty_minutes) filter (where h.is_peak_hour)
        / nullif(sum(h.observed_minutes) filter (where h.is_peak_hour), 0), 4
    )                                                                       as peak_shortage_rate,
    round(
        avg(h.avg_available_bikes) filter (where h.had_precipitation)
        - avg(h.avg_available_bikes) filter (where not h.had_precipitation), 2
    )                                                                       as rain_bike_delta
from hourly h
join {{ ref('dim_station') }} s using (station_id)
group by 1, 2, 3, 4
