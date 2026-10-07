-- Grain: one row per rental.

select
    rental_id,
    user_id,
    pickup_station_id,
    dropoff_station_id,
    date_trunc('hour', started_at_local)    as hour_key,
    started_at_utc,
    started_at_local,
    ended_at_utc,
    ended_at_local,
    duration_minutes,
    cost_eur,
    is_completed
from {{ ref('stg_rental') }}
