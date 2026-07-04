-- Clean carrier master data.
with source as (
    select * from {{ source('raw', 'carriers') }}
)

select
    upper(trim(carrier_code))    as carrier_code,
    trim(carrier_name)           as carrier_name,
    cast(is_low_cost as boolean) as is_low_cost,
    cast(fleet_size as integer)  as fleet_size,
    cast(founded_year as integer) as founded_year
from source
