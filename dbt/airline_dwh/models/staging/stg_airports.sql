-- Clean + standardize airport master data.
-- Fixes the raw casing/whitespace noise and de-duplicates by airport_code.
with source as (
    select * from {{ source('raw', 'airports') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by upper(trim(airport_code))
            order by _loaded_at desc
        ) as _rn
    from source
)

select
    upper(trim(airport_code))            as airport_code,
    trim(airport_name)                   as airport_name,
    {{ title_case('city') }}             as city,
    upper(trim(state))                   as state,
    cast(latitude as double)             as latitude,
    cast(longitude as double)            as longitude,
    cast(tz_offset as integer)           as tz_offset,
    cast(hub_weight as integer)          as hub_weight
from deduped
where _rn = 1
