-- Every flight must have a positive great-circle distance. Returns offending rows.
select flight_id, distance_miles
from {{ ref('fact_flights') }}
where distance_miles is null or distance_miles <= 0
