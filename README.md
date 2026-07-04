<h1 align="center">✈️ AI-Ready Airline Data Pipeline &amp; Analytics Platform</h1>

<p align="center">
  An end-to-end, production-shaped data engineering platform that ingests airline
  operational data, validates and models it into a tested star schema, and serves
  analytics — <b>runs on a laptop, ships to the cloud unchanged.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/dbt-1.9-FF694B?logo=dbt&logoColor=white">
  <img src="https://img.shields.io/badge/Apache%20Airflow-2.9-017CEE?logo=apacheairflow&logoColor=white">
  <img src="https://img.shields.io/badge/Great%20Expectations-0.18-FF6310">
  <img src="https://img.shields.io/badge/DuckDB%20%7C%20Snowflake-warehouse-FFF000?logo=duckdb&logoColor=black">
  <img src="https://img.shields.io/badge/Power%20BI-semantic%20model-F2C811?logo=powerbi&logoColor=black">
  <img src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white">
  <img src="https://img.shields.io/badge/tests-30%20dbt%20%2B%2025%20GE-2a9d8f">
</p>

<p align="center"><img src="docs/img/dashboard_overview.png" width="90%" alt="Dashboard overview"></p>

---

## Why this project

Airlines live and die by operational data — delays, cancellations, on-time
performance. This project takes messy, multi-source airline data and turns it
into **governed, tested, analytics-ready** tables and dashboards, using the same
tools and patterns used on real data platforms: **Python, SQL, dbt, Airflow,
Great Expectations, a cloud warehouse, and Power BI** — all wrapped in Docker.

The headline design goal is **local-first, cloud-ready**: clone it and run the
whole thing on your laptop against DuckDB in a couple of minutes, or point the
identical dbt models at **Snowflake** by changing one profile.

## Architecture

<p align="center"><img src="docs/img/architecture.png" width="92%" alt="Architecture diagram"></p>

```
sources ─► ingestion (extract+load) ─► RAW ─► Great Expectations
                                              │
                          dbt:  staging ─► dims + facts ─► analytics marts
                                              │
                          reconciliation (source→target)   Power BI / Streamlit
        orchestrated by Airflow · packaged with Docker
```

Full write-up with design decisions and trade-offs: **[docs/architecture.md](docs/architecture.md)**.

## What it demonstrates

- **ETL / ELT** — Talend-style extract + load into a warehouse `raw` layer with
  audit logging and idempotent, reproducible runs.
- **Dimensional modelling** — a Kimball **star schema** (`fact_flights`,
  `fact_flight_delays` + conformed `dim_date` / `dim_airport` / `dim_airline`)
  built in **dbt** with surrogate keys and referential-integrity tests.
- **Data quality** — **Great Expectations** on the raw layer (nulls, duplicates,
  schema, ranges), **30 dbt tests** on the modelled layers, and a
  **source-to-target row-count reconciliation** that proves no data is silently
  lost.
- **Orchestration** — an **Airflow** DAG running the daily batch, plus a no-Docker
  Python runner for instant local demos.
- **Analytics** — a **Power BI** semantic model (relationships + DAX) and a
  runnable **Streamlit** dashboard over the same marts.
- **Engineering hygiene** — config-driven, containerized, `make`-driven, and
  portable between DuckDB and Snowflake with zero model changes.

## Quickstart

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
make setup

# 2. run the whole pipeline (generate → ingest → validate → dbt build → reconcile)
make pipeline

# 3. explore the results
make dashboard          # Streamlit at http://localhost:8501
```

Prefer the production-like stack? `make docker-up` brings up **Airflow**
(http://localhost:8080) + the dashboard via Docker Compose.

Point it at **Snowflake** instead of DuckDB:

```bash
export WAREHOUSE=snowflake            # + fill the SNOWFLAKE_* vars in .env
cd dbt/airline_dwh && dbt build --target snowflake
```

## The data model

A classic star schema — one fact at the grain of a single flight, surrounded by
conformed dimensions:

| Table | Grain | Rows* |
|---|---|---|
| `fact_flights` | one row per flight | ~59.9k |
| `fact_flight_delays` | one row per flight × delay cause | ~44k |
| `dim_airport` / `dim_airline` / `dim_date` | dimension | 40 / 10 / 91 |
| `route_performance` / `delay_trends` / `cancellations` / `operational_kpis` | analytics marts | 1.4k / 91 / 40 / 10 |

\*from the default seeded run (60k synthetic flights over Q1).

## Data quality in three layers

1. **Great Expectations** validates the raw feed and reports every defect
   (duplicate keys, `-9999` sentinel delays, orphan airport codes, missing tail
   numbers) to `quality/expectations/validation_report.json`.
2. **dbt tests** (`unique`, `not_null`, `relationships`, `accepted_values`, and
   custom singular tests) guard every modelled layer — the build fails if the
   star schema loses integrity.
3. **Reconciliation** accounts for every source row across
   `source → raw → staging`, classifying each delta as a removed duplicate or a
   DQ-filtered row.

## Project structure

```
airline-data-platform/
├── data/               # seeded synthetic source generator (+ real-data notes)
├── ingestion/          # extract + load into the raw warehouse (Talend-style)
├── quality/            # Great Expectations suites + reconciliation
├── dbt/airline_dwh/    # staging → dims/facts → analytics marts (+ tests)
├── airflow/dags/       # daily orchestration DAG
├── orchestration/      # no-Docker local pipeline runner
├── dashboards/         # Streamlit app + Power BI model (DAX, connection guide)
├── scripts/            # mart export + chart rendering utilities
├── docs/               # architecture write-up + diagrams
├── docker-compose.yml  # Airflow + Postgres + dashboard
└── Makefile            # one-command entrypoints
```

## Tech stack

**Python · SQL · dbt · Apache Airflow · Great Expectations · DuckDB / Snowflake ·
Power BI · Docker · Pandas**

## Roadmap

- Incremental `fact_flights` on `flight_date` + dbt snapshots for SCD dimensions
- Swap the generator for the live DOT/BTS On-Time Performance feed via S3 → Snowflake
- dbt docs site with lineage, freshness SLAs, and Airflow alerting
- CI (dbt build + Great Expectations on a sample) on every pull request

---

<p align="center"><i>Built by Dhanush Battina · data engineering portfolio project</i></p>
