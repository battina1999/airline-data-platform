# Power BI Semantic Model & Connection Guide

The dbt marts are the single source of truth. Power BI connects to the **same
star schema** the Streamlit app uses, so both tools show identical numbers.

## 1. Connect Power BI to the marts

Pick whichever matches how you ran the platform:

**A. Local DuckDB (this repo, default)**
The pipeline writes `warehouse/airline.duckdb`. Export the marts to Parquet
once and point Power BI at them (DuckDB has no native Power BI connector):

```bash
python scripts/export_marts.py      # writes dashboards/powerbi/export/*.parquet
```

Then in Power BI Desktop: *Get Data → Parquet* → select each file in
`dashboards/powerbi/export/`.

**B. Snowflake (cloud target)**
When the platform runs with `WAREHOUSE=snowflake`, the marts live in
`AIRLINE_DWH.MARTS`. In Power BI: *Get Data → Snowflake*, enter your account
URL and warehouse, and select the `MARTS` schema. Use **Import** mode for this
data volume (DirectQuery is available if you need live refresh).

## 2. Model (star schema)

Import these tables and set relationships (single-direction, one-to-many from
dimension to fact):

| From (dimension)          | To (fact)            | Key                 |
|---------------------------|----------------------|---------------------|
| `dim_date[date_key]`      | `fact_flights`       | `date_key`          |
| `dim_airport[airport_key]`| `fact_flights`       | `origin_airport_key`|
| `dim_airport[airport_key]`| `fact_flights`       | `dest_airport_key` *(inactive; USERELATIONSHIP for destination analysis)* |
| `dim_airline[airline_key]`| `fact_flights`       | `airline_key`       |
| `dim_date[date_key]`      | `fact_flight_delays` | `date_key`          |
| `dim_airline[airline_key]`| `fact_flight_delays` | `airline_key`       |

Mark `dim_date` as the official **Date table** (`date_day`).

## 3. Measures

All measures are in [`measures.dax`](./measures.dax). Core set:

- **Total Flights**, **Cancelled Flights**, **Cancellation %**
- **On-Time %**, **Completion Factor %**
- **Avg Arrival Delay**, **Avg Departure Delay**
- **Total Delay Minutes** + one measure per cause (Carrier / Weather / NAS /
  Security / Late Aircraft) for a delay-cause breakdown visual

## 4. Report pages (matches the Streamlit app)

1. **Executive KPIs** — cards (Total Flights, On-Time %, Cancellation %, Avg
   Delay) + On-Time % by carrier bar.
2. **Delay analysis** — daily delayed/cancelled line (uses `dim_date`), delay
   minutes by cause, delay bucket distribution.
3. **Route performance** — table of routes with On-Time % and Avg Delay + a
   map using `dim_airport` lat/long.
4. **Cancellations** — reason breakdown donut + reason-by-carrier matrix.
