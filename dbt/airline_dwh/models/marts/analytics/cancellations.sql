-- Cancellation analysis by reason and carrier, with share of total cancellations.
with cancelled as (
    select * from {{ ref('fact_flights') }} where is_cancelled
),

by_reason_carrier as (
    select
        coalesce(c.cancellation_reason, 'Unknown') as cancellation_reason,
        a.carrier_code,
        a.carrier_name,
        count(*) as cancelled_flights
    from cancelled c
    join {{ ref('dim_airline') }} a on c.airline_key = a.airline_key
    group by 1, 2, 3
)

select
    cancellation_reason,
    carrier_code,
    carrier_name,
    cancelled_flights,
    round(100.0 * cancelled_flights / sum(cancelled_flights) over (), 2) as pct_of_all_cancellations
from by_reason_carrier
order by cancelled_flights desc
