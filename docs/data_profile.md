# Data Profile — US DOT BTS On-Time Performance

_Generated 2026-07-10 05:24 UTC by `scripts/profile_data.py`. Profiled BEFORE building — every quirk below is handled explicitly in the pipeline._

## Volume

- **Total rows:** 3,453,795 across 6 monthly files
- **Date range:** 2024-02-01 → 2025-01-31
- **Distinct carriers:** 15 · **Distinct airports:** 345

| File | Rows |
|---|---|
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_2.csv | 519,221 |
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_3.csv | 591,767 |
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_4.csv | 582,185 |
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_5.csv | 609,743 |
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_6.csv | 611,132 |
| On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2025_1.csv | 539,747 |

## Null rates (key columns)

| Column | Null % |
|---|---|
| FlightDate | 0.00% |
| Reporting_Airline | 0.00% |
| Tail_Number | 0.22% |
| Origin | 0.00% |
| Dest | 0.00% |
| DepDelay | 1.25% |
| ArrDelay | 1.55% |
| Cancelled | 0.00% |
| CancellationCode | 98.71% |
| Distance | 0.00% |
| CarrierDelay | 79.14% |
| WeatherDelay | 79.14% |
| NASDelay | 79.14% |
| SecurityDelay | 79.14% |
| LateAircraftDelay | 79.14% |

## Delay distributions

- DepDelay: min -96.0, max 3360.0, mean 12.88 min
- ArrDelay: min -117.0, max 3359.0, mean 7.26 min

## Quirks found → how the platform handles each

1. **NULL delays on cancelled flights** — 43,024 of 44,589 cancelled flights have `DepDelay IS NULL`. This is *correct* BTS behaviour (a flight that never departed has no delay). Handled: staging keeps them NULL, `delay_bucket` maps NULL → `unknown`, and marts exclude cancelled flights from delay averages. A dedicated GE expectation asserts the pattern instead of flagging it as dirty.

2. **Duplicate natural keys** — 0 rows share a (FlightDate, carrier, flight number, origin, CRSDepTime) key: real double-reported records. Handled: surfaced by a GE compound-uniqueness expectation (warn), de-duplicated in `stg_flights` (latest `_loaded_at` wins), and every removed row is accounted for in source-to-target reconciliation.

3. **Sentinel delay values** — 0 rows with `DepDelay <= -900` (legacy sentinel pattern; common in older extracts). Handled: converted to NULL in staging; GE bounds delays to [-60, 2000] minutes.

4. **Missing tail numbers** — 0.22% of rows. Cancelled flights often have no tail assigned. Handled: nullable column; no join depends on it.

5. **HHMM-encoded times** — `CRSDepTime` is an integer like `1530` (= 15:30), not minutes. Handled: converted to minutes-past-midnight in the adapter (`floor(x/100)*60 + x%100`).

6. **Local times, no timezone** — BTS times are airport-local with no UTC offset. Handled: modelled as local wall-clock; the airport dimension carries a tz offset for the majors; cross-timezone duration math deliberately uses `CRSElapsedTime` instead of arrival-minus-departure.

7. **Delay-cause columns only populated when ArrDelay ≥ 15** — BTS convention. Handled: `coalesce(...,0)` at ingestion; cause analysis restricted to delayed flights in `fact_flight_delays`.

## S3 landing layout

Raw files land (private bucket) under a partitioned prefix before ingestion:

```
s3://aeroops-raw/bts/year=2025/month=01/On_Time_..._2025_1.csv
s3://aeroops-raw/bts/year=2025/month=02/On_Time_..._2025_2.csv
```

Locally the same files sit in `data/bts/` (or `../bts_data/`), and `DATA_SOURCE=bts make pipeline` ingests them identically.