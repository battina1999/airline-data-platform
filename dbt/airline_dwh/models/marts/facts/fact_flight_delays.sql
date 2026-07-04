-- Delay-cause fact: unpivots the five BTS delay-cause columns into one row per
-- (flight, contributing cause). Makes "what is driving our delays?" a trivial
-- group-by instead of summing five separate columns.
with delayed as (
    select *
    from {{ ref('fact_flights') }}
    where is_delayed and not is_cancelled
),

unpivoted as (
    select flight_id, date_key, airline_key, origin_airport_key, dest_airport_key,
           'Carrier'       as delay_cause, carrier_delay_min       as delay_minutes from delayed
    union all
    select flight_id, date_key, airline_key, origin_airport_key, dest_airport_key,
           'Weather'       as delay_cause, weather_delay_min       as delay_minutes from delayed
    union all
    select flight_id, date_key, airline_key, origin_airport_key, dest_airport_key,
           'NAS'           as delay_cause, nas_delay_min           as delay_minutes from delayed
    union all
    select flight_id, date_key, airline_key, origin_airport_key, dest_airport_key,
           'Security'      as delay_cause, security_delay_min      as delay_minutes from delayed
    union all
    select flight_id, date_key, airline_key, origin_airport_key, dest_airport_key,
           'Late Aircraft' as delay_cause, late_aircraft_delay_min as delay_minutes from delayed
)

select *
from unpivoted
where delay_minutes > 0
