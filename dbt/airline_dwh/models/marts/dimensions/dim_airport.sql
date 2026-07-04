-- Airport dimension with a hashed surrogate key, hub flag and region rollup.
select
    md5(airport_code)             as airport_key,
    airport_code,
    airport_name,
    city,
    state,
    latitude,
    longitude,
    tz_offset,
    hub_weight,
    (hub_weight >= 7)             as is_major_hub,
    case
        when state in ('WA', 'OR', 'CA', 'NV', 'AZ', 'HI') then 'West'
        when state in ('CO', 'UT', 'TX', 'NM', 'MT', 'ID', 'WY') then 'Mountain/Southwest'
        when state in ('IL', 'MN', 'MI', 'OH', 'MO', 'WI', 'IN') then 'Midwest'
        when state in ('GA', 'FL', 'NC', 'TN', 'LA', 'SC') then 'Southeast'
        when state in ('NY', 'NJ', 'MA', 'PA', 'MD', 'DC', 'VA') then 'Northeast'
        else 'Other'
    end                          as region
from {{ ref('stg_airports') }}
