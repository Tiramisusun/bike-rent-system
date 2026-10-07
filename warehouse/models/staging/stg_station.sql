select
    station_id,
    name                as station_name,
    contract            as contract_name,
    latitude,
    longitude,
    bike_stands         as reported_capacity
from {{ source('raw', 'station') }}
