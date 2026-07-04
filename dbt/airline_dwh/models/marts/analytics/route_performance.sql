-- Route-level performance: on-time %, delays and cancellations per origin->dest.
with f as (
    select * from {{ ref('fact_flights') }}
)

select
    origin_airport,
    dest_airport,
    origin_airport || '-' || dest_airport                              as route,
    count(*)                                                           as total_flights,
    sum(case when is_cancelled then 1 else 0 end)                     as cancelled_flights,
    round(100.0 * sum(case when is_cancelled then 1 else 0 end) / count(*), 2) as cancellation_pct,
    round(avg(case when not is_cancelled then dep_delay_min end), 2)   as avg_dep_delay_min,
    round(avg(case when not is_cancelled then arr_delay_min end), 2)   as avg_arr_delay_min,
    round(
        100.0 * sum(case when is_on_time then 1 else 0 end)
        / nullif(sum(case when not is_cancelled then 1 else 0 end), 0), 2
    )                                                                  as on_time_pct,
    round(avg(distance_miles), 1)                                      as avg_distance_miles
from f
group by 1, 2, 3
having count(*) >= 20
