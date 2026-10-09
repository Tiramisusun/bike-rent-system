select
    id                  as weather_code,
    main                as condition_group,
    description         as condition_description,
    icon                as icon_code
from {{ source('raw', 'weather') }}
