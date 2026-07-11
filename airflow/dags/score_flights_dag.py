"""
Airflow DAG: daily batch scoring of upcoming flights.

    rebuild feature mart -> score next-day flights -> write predictions table
    -> alert if the high-risk share spikes

Writes marts.predictions_daily so BI can join predicted risk against actual
outcomes the day after — the beginning of a drift monitor.
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

HIGH_RISK_ALERT_SHARE = 0.25  # alert when >25% of tomorrow's flights are high-risk


def _score(**_):
    import duckdb
    import joblib
    import pandas as pd
    from pathlib import Path

    from config import settings

    art = Path(PROJECT_DIR) / "ml" / "artifacts"
    model = joblib.load(art / "lgbm_delay.joblib")
    import json
    thr = json.loads((art / "metrics.json").read_text())["lgbm"]["val"]["threshold"]

    con = duckdb.connect(str(settings.duckdb_path))
    features = ["dep_hour", "route_delay_rate_30d", "carrier_delay_rate_30d",
                "scheduled_departures_hour", "distance_miles", "route_flights_30d",
                "day_of_week", "distance_bucket", "carrier_type", "is_weekend"]
    # score the most recent day in the feature mart (stands in for "tomorrow's
    # schedule" — in production this would read the forward schedule feed)
    df = con.sql(f"""
        select flight_id, flight_date, carrier_code, origin_airport, dest_airport,
               {', '.join(features)}
        from main.fct_features_flight
        where flight_date = (select max(flight_date) from main.fct_features_flight)
    """).df()
    for c in ("distance_bucket", "carrier_type", "is_weekend"):
        df[c] = df[c].astype("category")
    df["delay_probability"] = model.predict_proba(df[features])[:, 1]
    df["is_high_risk"] = df["delay_probability"] >= thr
    df["scored_at"] = datetime.utcnow()

    out = df[["flight_id", "flight_date", "carrier_code", "origin_airport",
              "dest_airport", "delay_probability", "is_high_risk", "scored_at"]]
    con.register("_scored", out)
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("CREATE OR REPLACE TABLE marts.predictions_daily AS SELECT * FROM _scored")
    share = float(out["is_high_risk"].mean())
    con.close()
    print(f"scored {len(out):,} flights; high-risk share = {share:.1%}")
    if share > HIGH_RISK_ALERT_SHARE:
        raise ValueError(
            f"ALERT: {share:.1%} of scored flights are high-risk "
            f"(> {HIGH_RISK_ALERT_SHARE:.0%}) — page ops planning."
        )


with DAG(
    dag_id="score_flights_daily",
    description="Daily delay-risk batch scoring into marts.predictions_daily",
    default_args={"owner": "data-engineering", "retries": 1,
                  "retry_delay": timedelta(minutes=2)},
    schedule="30 6 * * *",          # after the 06:00 pipeline run
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "scoring", "airline"],
) as dag:

    refresh_features = BashOperator(
        task_id="refresh_feature_mart",
        bash_command=(f"cd {PROJECT_DIR}/dbt/airline_dwh && "
                      f"DBT_DUCKDB_PATH={PROJECT_DIR}/warehouse/airline.duckdb "
                      f"dbt build --profiles-dir . --select fct_features_flight"),
    )

    score = PythonOperator(task_id="score_flights", python_callable=_score)

    refresh_features >> score
