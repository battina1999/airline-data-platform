-- Executive KPI summary per carrier: completion factor, on-time %, avg delays.
with f as (
    select * from {{ ref('fact_flights') }}
)

select
    a.carrier_code,
    a.carrier_name,
    a.carrier_type,
    count(*)                                                          as total_flights,
    sum(case when f.is_cancelled then 1 else 0 end)                  as cancelled_flights,
    sum(case when f.is_diverted then 1 else 0 end)                   as diverted_flights,
    round(
        100.0 * (count(*) - sum(case when f.is_cancelled then 1 else 0 end)) / count(*), 2
    )                                                                as completion_factor_pct,
    round(
        100.0 * sum(case when f.is_on_time then 1 else 0 end)
        / nullif(sum(case when not f.is_cancelled then 1 else 0 end), 0), 2
    )                                                                as on_time_pct,
    round(avg(case when not f.is_cancelled then f.dep_delay_min end), 2) as avg_dep_delay_min,
    round(avg(case when not f.is_cancelled then f.arr_delay_min end), 2) as avg_arr_delay_min,
    sum(
        f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min
        + f.security_delay_min + f.late_aircraft_delay_min
    )                                                                as total_delay_minutes
from f
join {{ ref('dim_airline') }} a on f.airline_key = a.airline_key
group by 1, 2, 3
order by total_flights desc
