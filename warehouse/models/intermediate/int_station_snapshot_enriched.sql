-- One row per snapshot, with
--   * minutes_observed: how long this state lasted (until the station's next
--     snapshot), capped at var('max_snapshot_minutes') so collection outages
--     are not counted as hours of empty/full time. The station's latest
--     snapshot has no successor yet and counts as 5 minutes (one poll).
--   * the most recent weather observation at or before the snapshot, if it
--     is at most 1 hour old (as-of join).

with snapshots as (

    select
        *,
        lead(snapshot_at_utc) over (
            partition by station_id order by snapshot_at_utc
        ) as next_snapshot_at_utc
    from {{ ref('stg_station_status') }}

),

durations as (

    select
        *,
        least(
            coalesce(
                extract(epoch from next_snapshot_at_utc - snapshot_at_utc) / 60.0,
                5
            ),
            {{ var('max_snapshot_minutes') }}
        )::numeric(6, 2) as minutes_observed
    from snapshots

)

select
    d.snapshot_id,
    d.station_id,
    d.snapshot_at_utc,
    d.snapshot_at_local,
    date_trunc('hour', d.snapshot_at_local)     as hour_key,
    d.available_bikes,
    d.available_docks,
    d.station_status,
    d.is_open,
    d.minutes_observed,
    w.observed_at_utc                           as weather_observed_at_utc,
    w.weather_code,
    w.temperature_c,
    w.humidity_pct,
    w.wind_speed_ms
from durations d
left join lateral (
    select *
    from {{ ref('stg_weather_report') }} wr
    where wr.observed_at_utc <= d.snapshot_at_utc
      and wr.observed_at_utc > d.snapshot_at_utc - interval '1 hour'
    order by wr.observed_at_utc desc
    limit 1
) w on true
