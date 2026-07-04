-- Conformed date dimension, generated across the range present in the data.
with bounds as (
    select
        min(flight_date) as min_date,
        max(flight_date) as max_date
    from {{ ref('stg_flights') }}
),

spine as (
    select
        cast(unnest(generate_series(min_date, max_date, interval 1 day)) as date) as date_day
    from bounds
)

select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day,
    extract(year   from date_day)                 as year,
    extract(quarter from date_day)                as quarter,
    extract(month  from date_day)                 as month,
    strftime(date_day, '%B')                      as month_name,
    extract(day    from date_day)                 as day_of_month,
    extract(dayofweek from date_day)              as day_of_week,
    strftime(date_day, '%A')                      as day_name,
    (extract(dayofweek from date_day) in (0, 6))  as is_weekend,
    extract(week from date_day)                   as week_of_year
from spine
