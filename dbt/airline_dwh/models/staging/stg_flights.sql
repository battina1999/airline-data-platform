-- The core cleaning model. Takes the messy raw flight feed and produces a
-- trustworthy fact-ready grain of ONE row per flight_id by:
--   * de-duplicating double-published events (keep latest by load time)
--   * converting the -9999 sentinel delays to NULL
--   * dropping flights whose origin/dest airport is not in the master data
--   * standardizing codes + deriving delay / on-time / cancellation flags
--   * mapping cancellation codes to business-readable reasons (via a seed)
with source as (
    select * from {{ source('raw', 'flights') }}
),

reasons as (
    select * from {{ ref('cancellation_reasons') }}
),

valid_airports as (
    select airport_code from {{ ref('stg_airports') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by flight_id
            order by _loaded_at desc
        ) as _rn
    from source
),

cleaned as (
    select
        flight_id,
        cast(flight_date as date)                                  as flight_date,
        upper(trim(carrier_code))                                  as carrier_code,
        flight_number,
        nullif(trim(tail_number), '')                              as tail_number,
        upper(trim(origin))                                        as origin_airport,
        upper(trim(dest))                                          as dest_airport,
        scheduled_departure_min,
        cast(flight_date as timestamp)
            + (scheduled_departure_min * interval 1 minute)        as scheduled_departure_ts,
        cast(distance_miles as double)                             as distance_miles,
        cast(scheduled_air_time_min as integer)                    as scheduled_air_time_min,
        case when dep_delay_min = -9999 then null else dep_delay_min end as dep_delay_min,
        case when arr_delay_min = -9999 then null else arr_delay_min end as arr_delay_min,
        cast(cancelled as boolean)                                 as is_cancelled,
        nullif(trim(cancellation_code), '')                        as cancellation_code,
        cast(diverted as boolean)                                  as is_diverted,
        carrier_delay_min,
        weather_delay_min,
        nas_delay_min,
        security_delay_min,
        late_aircraft_delay_min
    from deduped
    where _rn = 1
)

select
    c.*,
    r.cancellation_reason,
    (c.arr_delay_min >= 15)                                        as is_delayed,
    case
        when c.is_cancelled or c.is_diverted then false
        when c.arr_delay_min < 15 then true
        else false
    end                                                            as is_on_time,
    case
        when c.arr_delay_min is null then 'unknown'
        when c.arr_delay_min < 0   then 'early'
        when c.arr_delay_min < 15  then 'on_time'
        when c.arr_delay_min < 60  then 'minor_delay'
        when c.arr_delay_min < 180 then 'major_delay'
        else 'severe_delay'
    end                                                            as delay_bucket
from cleaned c
left join reasons r
    on c.cancellation_code = r.cancellation_code
where c.origin_airport in (select airport_code from valid_airports)
  and c.dest_airport   in (select airport_code from valid_airports)
