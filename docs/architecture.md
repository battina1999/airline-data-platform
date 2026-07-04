# Architecture

This document explains **how the platform is built, why each choice was made,
and the trade-offs behind them**. It is written to be read on its own — by a
hiring manager, a teammate, or future-me six months from now.

![Architecture](img/architecture.png)

---

## 1. What the platform does

It takes raw airline operational data from four sources — **flights, airports,
carriers, weather** — and turns it into governed, tested, analytics-ready
tables and dashboards that answer questions such as:

- Which routes and carriers have the worst on-time performance?
- What is driving delays — weather, carrier, national airspace, or knock-on
  "late aircraft" effects?
- How do cancellations break down by reason and airline?
- How do delays trend day-to-day and across the week?

The whole thing runs on a laptop with one command (`make pipeline`) and is
built to lift-and-shift to the cloud (Snowflake + managed Airflow) without
rewriting a single model.

## 2. Design principles

1. **Local-first, cloud-ready.** The default target is an embedded DuckDB file
   so anyone can clone and run it in minutes. Because all transformation logic
   lives in **dbt**, the same models run on Snowflake by switching one profile
   — no SQL changes.
2. **Layered / medallion-style modelling.** Data flows through clearly
   separated `raw → staging → marts` layers. Each layer has one job, which
   keeps models small, testable and debuggable.
3. **Quality is enforced, not assumed.** Great Expectations validates the raw
   layer, dbt tests validate every modelled layer, and a reconciliation step
   proves no rows are silently lost. Nothing reaches a dashboard untested.
4. **Everything is reproducible.** A single seed drives data generation, loads
   are idempotent, and the pipeline is orchestrated the same way locally
   (Python runner) and in production (Airflow DAG).

## 3. The pipeline, layer by layer

### 3.1 Sources (`data/`)
A seeded generator (`data/generate_data.py`) produces realistic CSVs using
**real** IATA airport codes and US carriers, haversine-based route distances,
weather-correlated delays and BTS-style cancellation reason codes. It also
injects a small, controlled amount of **realistic mess** — duplicate events,
`-9999` sentinel delays, missing tail numbers, orphan airport codes — so the
data-quality stack has something real to catch. In production this module is
replaced by the DOT/BTS On-Time Performance extract and the OpenFlights
airport database; the schemas were modelled to line up with them.

### 3.2 Ingestion (`ingestion/`)
A deliberately Talend-shaped split: an **extract** stage (`tFileInputDelimited`
equivalent) profiles each source, and a **load** stage (`tDBOutput`
equivalent) lands it into the `raw` schema with audit columns
(`_loaded_at`, `_source_file`, `_batch_id`). Every load writes a row to
`raw._ingestion_audit` recording rows extracted vs rows loaded — the first
line of defence for row-count integrity. Loads are idempotent
(`CREATE OR REPLACE`), so re-runs are safe and deterministic.

### 3.3 Data quality on raw (`quality/validate.py`)
**Great Expectations** runs a declarative suite (null checks, uniqueness,
schema/length, accepted-value sets, range checks) against the raw tables and
writes a JSON report. It runs in **monitor mode** — it reports the injected
defects (and would alert in production) but lets the pipeline continue into
staging, where those defects are cleaned. A `--strict` flag flips it to a hard
gate. This mirrors the real trade-off between observability and enforcement.

### 3.4 Transformation with dbt (`dbt/airline_dwh/`)
Three model layers:

- **Staging** (views) — the cleaning layer. `stg_flights` de-duplicates
  double-published events (keep latest by load time), converts `-9999`
  sentinels to `NULL`, drops flights whose airports aren't in the master data,
  standardizes codes, maps cancellation codes to readable reasons via a seed,
  and derives on-time / delay-bucket flags. `stg_airports` fixes casing and
  whitespace using a portable `title_case` macro that dispatches to
  `initcap()` on Snowflake and a lambda on DuckDB.
- **Dimensions + Facts** (tables) — a Kimball **star schema**: `dim_date`,
  `dim_airport` (with hub flag + region), `dim_airline` (with carrier type),
  a central `fact_flights` at one-row-per-flight with hashed surrogate foreign
  keys, and `fact_flight_delays` which unpivots the five delay causes to one
  row per (flight, cause).
- **Analytics marts** (tables) — business-facing aggregates:
  `route_performance`, `delay_trends`, `cancellations`, `operational_kpis`.

Testing is layered too: `unique` / `not_null` on keys, `relationships` tests
that enforce referential integrity from `fact_flights` to every dimension,
`accepted_values` on categorical columns, and custom singular tests
(e.g. positive distance, on-time % within 0–100).

### 3.5 Reconciliation (`quality/reconciliation.py`)
After modelling, this proves the transformation didn't lose data it shouldn't:
for each source it reconciles `source file → raw → staging` and classifies
every delta as either a **duplicate removed** or a **row filtered by a DQ
rule**. A run only passes when every source row is accounted for; unexplained
loss fails the build.

### 3.6 Consumption (`dashboards/`)
Two interchangeable views of the **same marts**: a runnable **Streamlit** app
(the free, always-works option) and a documented **Power BI** semantic model
(relationships + DAX measures + connection guide) for the enterprise BI story.

## 4. Orchestration & packaging

- **Airflow** (`airflow/dags/airline_pipeline_dag.py`) runs the DAG
  `generate → ingest → validate → dbt build → reconcile` daily. Python stages
  call the same modules the local runner uses; dbt runs as a `BashOperator`.
- **Local runner** (`orchestration/run_pipeline.py`) executes the identical
  sequence with no Docker, so the project is demonstrable anywhere.
- **Docker Compose** brings up Postgres (Airflow metadata), the Airflow
  webserver + scheduler, and the Streamlit dashboard.

## 5. Local vs cloud

| Concern        | Local (default)          | Cloud (production)             |
|----------------|--------------------------|--------------------------------|
| Warehouse      | DuckDB (embedded file)   | Snowflake                      |
| dbt profile    | `local`                  | `snowflake` (env-var driven)   |
| Orchestration  | Python runner / Airflow  | Managed Airflow (MWAA/Astro)   |
| Object storage | local `data/raw`         | S3 / stage                     |
| Cost           | $0                       | pay-per-use compute            |

Only the dbt **profile** and the ingestion **target** change — the models,
tests, and business logic are identical. That portability is the point of
putting all logic in dbt rather than in warehouse-specific scripts.

## 6. Key trade-offs (and why)

- **Synthetic data over a live feed** — keeps the repo self-contained and
  reproducible while still exercising every DQ rule. The generator is isolated
  so a real BTS feed drops straight in.
- **DuckDB over a Postgres/Snowflake server for the default** — zero setup, and
  dbt makes the Snowflake swap trivial. The alternative (requiring a running
  server) would hurt the "clone and run" experience that matters for reviewers.
- **Full-refresh loads over incremental** — deterministic and simple for this
  volume. Incremental/merge is a localized change in the loader + dbt configs
  and is called out as the next step.
- **Great Expectations in monitor mode** — the pipeline demonstrates cleaning
  rather than hard-failing on known-dirty raw data; `--strict` is provided for
  a production gate.

## 7. Scaling this up

- Swap the generator for the DOT/BTS feed and load to S3 → Snowflake stages.
- Make `fact_flights` **incremental** on `flight_date` for large history.
- Add **dbt snapshots** for slowly-changing dimensions (e.g. carrier fleet).
- Publish dbt docs + lineage and wire **freshness** SLAs and Airflow alerting.
- Add CI (dbt build + GE on a sample) on every pull request.

## 8. Data dictionary (core tables)

**`fact_flights`** — grain: one row per flight
| Column | Type | Notes |
|---|---|---|
| `flight_id` | bigint | natural key |
| `date_key` | int | FK → `dim_date` (YYYYMMDD) |
| `origin_airport_key` / `dest_airport_key` | varchar | FK → `dim_airport` |
| `airline_key` | varchar | FK → `dim_airline` |
| `dep_delay_min` / `arr_delay_min` | int | minutes; sentinel cleaned to NULL |
| `is_cancelled` / `is_diverted` / `is_delayed` / `is_on_time` | boolean | flags |
| `delay_bucket` | varchar | early / on_time / minor / major / severe |
| `*_delay_min` (carrier, weather, nas, security, late_aircraft) | int | cause split |

**`dim_airport`** — `airport_key`, `airport_code`, `city`, `state`, `latitude`,
`longitude`, `is_major_hub`, `region`.
**`dim_airline`** — `airline_key`, `carrier_code`, `carrier_name`,
`carrier_type`, `fleet_size`.
**`dim_date`** — `date_key`, `date_day`, `year`, `quarter`, `month`,
`day_name`, `is_weekend`.
