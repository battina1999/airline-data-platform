-- Central fact table: one row per flight, with surrogate foreign keys to the
-- date / airport / airline dimensions and all additive delay measures.
with flights as (
    select * from {{ ref('stg_flights') }}
)

select
    -- degenerate + surrogate keys
    flight_id,
    cast(strftime(flight_date, '%Y%m%d') as integer) as date_key,
    md5(origin_airport)                              as origin_airport_key,
    md5(dest_airport)                                as dest_airport_key,
    md5(carrier_code)                                as airline_key,

    -- descriptive / degenerate attributes
    flight_date,
    carrier_code,
    flight_number,
    tail_number,
    origin_airport,
    dest_airport,
    scheduled_departure_ts,

    -- measures
    distance_miles,
    scheduled_air_time_min,
    dep_delay_min,
    arr_delay_min,

    -- flags
    is_cancelled,
    cancellation_code,
    cancellation_reason,
    is_diverted,
    is_delayed,
    is_on_time,
    delay_bucket,

    -- delay-cause breakdown (0 when not reportable)
    coalesce(carrier_delay_min, 0)        as carrier_delay_min,
    coalesce(weather_delay_min, 0)        as weather_delay_min,
    coalesce(nas_delay_min, 0)            as nas_delay_min,
    coalesce(security_delay_min, 0)       as security_delay_min,
    coalesce(late_aircraft_delay_min, 0)  as late_aircraft_delay_min
from flights
