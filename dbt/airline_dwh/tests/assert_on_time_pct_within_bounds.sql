-- On-time percentage is a percentage: it must sit between 0 and 100 in every mart.
select route, on_time_pct
from {{ ref('route_performance') }}
where on_time_pct < 0 or on_time_pct > 100

union all

select carrier_code as route, on_time_pct
from {{ ref('operational_kpis') }}
where on_time_pct < 0 or on_time_pct > 100
