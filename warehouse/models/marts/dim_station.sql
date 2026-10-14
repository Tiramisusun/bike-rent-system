-- One row per station. JCDecaux has no area field, so `zone` is derived from
-- the distance to O'Connell Bridge (53.3472, -6.2592), the usual city-centre reference.

with observed_capacity as (

    select station_id, max(available_bikes + available_docks) as max_observed_capacity
    from {{ ref('stg_station_status') }}
    group by station_id

),

stations as (

    select
        s.station_id,
        s.station_name,
        s.latitude,
        s.longitude,
        coalesce(s.reported_capacity, o.max_observed_capacity)        as capacity,
        case when s.reported_capacity is not null then 'reported'
             else 'max_observed' end                                  as capacity_source,
        -- haversine distance in km
        round((2 * 6371 * asin(sqrt(
            power(sin(radians(s.latitude - 53.3472) / 2), 2)
            + cos(radians(53.3472)) * cos(radians(s.latitude))
              * power(sin(radians(s.longitude - (-6.2592)) / 2), 2)
        )))::numeric, 3)                                              as distance_to_centre_km
    from {{ ref('stg_station') }} s
    left join observed_capacity o using (station_id)

)

select
    *,
    case
        when distance_to_centre_km < 1.0 then 'city_centre'
        when distance_to_centre_km < 2.5 then 'inner'
        else 'outer'
    end as zone
from stations
