-- Airline dimension with a hashed surrogate key and carrier-type classification.
select
    md5(carrier_code)   as airline_key,
    carrier_code,
    carrier_name,
    is_low_cost,
    case when is_low_cost then 'Low-Cost Carrier' else 'Legacy/Network Carrier' end as carrier_type,
    fleet_size,
    founded_year
from {{ ref('stg_carriers') }}
