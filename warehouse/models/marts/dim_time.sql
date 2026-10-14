-- One row per local hour. Peak / weekend / holiday flags use Dublin local time.

with hours as (

    select generate_series(
        '{{ var("dim_time_start") }}'::timestamp,
        '{{ var("dim_time_end") }}'::timestamp + interval '23 hours',
        interval '1 hour'
    ) as hour_key

),

holidays as (

    select holiday_date::date as holiday_date, holiday_name
    from {{ ref('irish_public_holidays') }}

)

select
    h.hour_key,
    h.hour_key::date                                    as date_day,
    extract(year from h.hour_key)::int                  as year,
    extract(month from h.hour_key)::int                 as month,
    extract(hour from h.hour_key)::int                  as hour_of_day,
    extract(isodow from h.hour_key)::int                as day_of_week,     -- 1 = Monday
    trim(to_char(h.hour_key, 'Day'))                    as day_name,
    extract(isodow from h.hour_key) in (6, 7)           as is_weekend,
    hol.holiday_name is not null                        as is_public_holiday,
    hol.holiday_name,
    extract(isodow from h.hour_key) not in (6, 7)
        and hol.holiday_name is null                    as is_working_day,
    extract(isodow from h.hour_key) not in (6, 7)
        and hol.holiday_name is null
        and extract(hour from h.hour_key)::int in ({{ var('peak_hours') | join(', ') }})
                                                        as is_peak_hour
from hours h
left join holidays hol on hol.holiday_date = h.hour_key::date
