select
    id                                  as snapshot_id,
    station_id,
    update_time                         as snapshot_at_utc,
    {{ to_local('update_time') }}       as snapshot_at_local,
    avail_bikes                         as available_bikes,
    avail_bike_stands                   as available_docks,
    upper(status)                       as station_status,
    upper(status) = 'OPEN'              as is_open
from {{ source('raw', 'station_status') }}
where station_id is not null
