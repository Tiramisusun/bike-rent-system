select
    id                                  as rental_id,
    user_id,
    pickup_station_id,
    dropoff_station_id,
    start_time                          as started_at_utc,
    {{ to_local('start_time') }}        as started_at_local,
    end_time                            as ended_at_utc,
    {{ to_local('end_time') }}          as ended_at_local,
    duration_minutes,
    cost_eur,
    end_time is not null                as is_completed
from {{ source('raw', 'rental') }}
