-- Daily operational trend, enriched with calendar attributes from dim_date.
with f as (
    select * from {{ ref('fact_flights') }}
)

select
    d.date_day,
    d.year,
    d.month,
    d.month_name,
    d.day_name,
    d.is_weekend,
    count(*)                                                          as total_flights,
    sum(case when f.is_delayed then 1 else 0 end)                    as delayed_flights,
    sum(case when f.is_cancelled then 1 else 0 end)                  as cancelled_flights,
    round(100.0 * sum(case when f.is_delayed then 1 else 0 end) / count(*), 2) as delayed_pct,
    round(avg(case when not f.is_cancelled then f.arr_delay_min end), 2)       as avg_arr_delay_min,
    sum(f.weather_delay_min)                                         as total_weather_delay_min,
    sum(f.carrier_delay_min)                                         as total_carrier_delay_min,
    sum(f.nas_delay_min)                                             as total_nas_delay_min,
    sum(f.late_aircraft_delay_min)                                   as total_late_aircraft_delay_min
from f
join {{ ref('dim_date') }} d on f.date_key = d.date_key
group by 1, 2, 3, 4, 5, 6
order by 1
