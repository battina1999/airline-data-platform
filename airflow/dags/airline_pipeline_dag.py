"""
Airflow DAG: airline_operations_pipeline

Orchestrates the daily batch:

    generate_data -> ingest_raw -> validate_raw (Great Expectations)
        -> dbt_build (staging -> dims/facts -> marts + tests) -> reconcile

The Python stages import the project modules (the same code the local runner
uses); dbt runs as a BashOperator so the dbt CLI owns its own process. The
project is mounted into the Airflow containers at $PROJECT_DIR (see
docker-compose.yml).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/airflow/project")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "depends_on_past": False,
}


# --- task callables (import inside to keep DAG parsing cheap) ----------------
def _generate(**_):
    from data.generate_data import main
    main()


def _ingest(**_):
    from ingestion.run_ingestion import run
    run()


def _validate(**_):
    from quality.validate import run
    # monitor mode: report defects but let the DAG continue into cleaning
    run(strict=False)


def _reconcile(**_):
    from quality.reconciliation import run
    if run() != 0:
        raise ValueError("Source-to-target reconciliation failed: unexplained row loss")


with DAG(
    dag_id="airline_operations_pipeline",
    description="End-to-end airline operations batch: ingest -> validate -> model -> reconcile",
    default_args=DEFAULT_ARGS,
    schedule="0 6 * * *",          # daily at 06:00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["airline", "dbt", "great-expectations", "duckdb-or-snowflake"],
) as dag:

    generate_data = PythonOperator(task_id="generate_data", python_callable=_generate)
    ingest_raw = PythonOperator(task_id="ingest_raw", python_callable=_ingest)
    validate_raw = PythonOperator(task_id="validate_raw", python_callable=_validate)

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt/airline_dwh && "
            f"DBT_DUCKDB_PATH={PROJECT_DIR}/warehouse/airline.duckdb "
            f"dbt build --profiles-dir ."
        ),
    )

    reconcile = PythonOperator(task_id="reconcile", python_callable=_reconcile)

    generate_data >> ingest_raw >> validate_raw >> dbt_build >> reconcile
