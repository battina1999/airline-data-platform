-- ML feature mart: one row per COMPLETED flight, features + label.
--
-- Features live in dbt (not pandas) so they are versioned, tested, documented
-- and identical between training and batch scoring. Every feature is
-- computable BEFORE departure (leakage-safe):
--   * rolling rates use a 30-day window ENDING THE DAY BEFORE the flight
--   * origin-hour congestion counts SCHEDULED departures (known in advance)
--   * calendar/route attributes are static schedule facts
--
-- Label: is_delayed_dep = dep_delay_min >= 15 (US DOT convention).
-- Cancelled flights are excluded (no departure -> no label).
{{ config(materialized='table') }}

with flights as (
    select *
    from {{ ref('fact_flights') }}
    where not is_cancelled and dep_delay_min is not null
),

-- daily aggregates once, then rolling windows over days (cheap + exact)
daily_route as (
    select
        origin_airport, dest_airport, flight_date,
        count(*)                                            as flights,
        sum(case when dep_delay_min >= 15 then 1 else 0 end) as delayed
    from flights group by 1, 2, 3
),

rolling_route as (
    select
        origin_airport, dest_airport, flight_date,
        sum(flights) over w  as r_flights_30d,
        sum(delayed) over w  as r_delayed_30d
    from daily_route
    window w as (
        partition by origin_airport, dest_airport order by flight_date
        range between interval 30 days preceding and interval 1 day preceding
    )
),

daily_carrier as (
    select
        carrier_code, flight_date,
        count(*)                                             as flights,
        sum(case when dep_delay_min >= 15 then 1 else 0 end) as delayed
    from flights group by 1, 2
),

rolling_carrier as (
    select
        carrier_code, flight_date,
        sum(flights) over w as c_flights_30d,
        sum(delayed) over w as c_delayed_30d
    from daily_carrier
    window w as (
        partition by carrier_code order by flight_date
        range between interval 30 days preceding and interval 1 day preceding
    )
),

-- congestion: how many departures were SCHEDULED at this origin in this hour
origin_hour as (
    select
        origin_airport, flight_date,
        extract(hour from scheduled_departure_ts)::integer as dep_hour,
        count(*) as scheduled_departures_hour
    from flights group by 1, 2, 3
)

select
    f.flight_id,
    f.flight_date,
    f.carrier_code,
    f.origin_airport,
    f.dest_airport,

    -- label
    (f.dep_delay_min >= 15)                                   as is_delayed_dep,

    -- schedule features
    extract(hour from f.scheduled_departure_ts)::integer      as dep_hour,
    d.day_of_week,
    d.month,
    (d.is_weekend)                                            as is_weekend,
    f.distance_miles,
    case
        when f.distance_miles < 500  then 'short'
        when f.distance_miles < 1500 then 'medium'
        else 'long'
    end                                                       as distance_bucket,
    a.carrier_type,

    -- congestion feature (scheduled, known in advance)
    oh.scheduled_departures_hour,

    -- rolling history features (window ends the day BEFORE the flight)
    coalesce(rr.r_delayed_30d * 1.0 / nullif(rr.r_flights_30d, 0), 0) as route_delay_rate_30d,
    coalesce(rr.r_flights_30d, 0)                             as route_flights_30d,
    coalesce(rc.c_delayed_30d * 1.0 / nullif(rc.c_flights_30d, 0), 0) as carrier_delay_rate_30d

from flights f
join {{ ref('dim_date') }}    d  on f.date_key = d.date_key
join {{ ref('dim_airline') }} a  on f.airline_key = a.airline_key
left join rolling_route  rr on f.origin_airport = rr.origin_airport
                           and f.dest_airport   = rr.dest_airport
                           and f.flight_date    = rr.flight_date
left join rolling_carrier rc on f.carrier_code = rc.carrier_code
                            and f.flight_date  = rc.flight_date
left join origin_hour oh on f.origin_airport = oh.origin_airport
                        and f.flight_date    = oh.flight_date
                        and extract(hour from f.scheduled_departure_ts)::integer = oh.dep_hour
