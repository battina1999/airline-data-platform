"""
Airline Operations dashboard (Streamlit) - the runnable, free stand-in for the
Power BI report. Reads the dbt marts straight from the DuckDB warehouse.

    streamlit run dashboards/streamlit_app.py

The data-access functions are deliberately plain (connection in, DataFrame out)
so they can be unit-tested and reused by the Power BI export or an API.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from config import settings


# ----------------------------- data access --------------------------------- #
def _connect():
    return duckdb.connect(str(settings.duckdb_path), read_only=True)


def load_kpis(con) -> dict:
    row = con.sql(
        """
        select
            count(*)                                                         as total_flights,
            round(100.0 * sum(case when is_on_time then 1 else 0 end)
                  / nullif(sum(case when not is_cancelled then 1 else 0 end), 0), 1) as on_time_pct,
            round(100.0 * sum(case when is_cancelled then 1 else 0 end) / count(*), 1) as cancel_pct,
            round(avg(case when not is_cancelled then arr_delay_min end), 1) as avg_arr_delay
        from marts.fact_flights
        """
    ).df().iloc[0]
    return row.to_dict()


def load_daily_trend(con) -> pd.DataFrame:
    return con.sql("select * from marts.delay_trends order by date_day").df()


def load_carrier_kpis(con) -> pd.DataFrame:
    return con.sql("select * from marts.operational_kpis order by total_flights desc").df()


def load_delay_causes(con) -> pd.DataFrame:
    return con.sql(
        "select delay_cause, sum(delay_minutes) as total_minutes, count(*) as flights "
        "from marts.fact_flight_delays group by 1 order by 2 desc"
    ).df()


def load_cancellations(con) -> pd.DataFrame:
    return con.sql(
        "select cancellation_reason, sum(cancelled_flights) as cancelled_flights "
        "from marts.cancellations group by 1 order by 2 desc"
    ).df()


def load_top_routes(con) -> pd.DataFrame:
    return con.sql(
        "select route, total_flights, on_time_pct, avg_arr_delay_min, cancellation_pct "
        "from marts.route_performance order by avg_arr_delay_min desc limit 15"
    ).df()


# ------------------------------- UI ---------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Airline Operations Analytics", layout="wide")
    st.title("✈️  Airline Operations Analytics")
    st.caption("Flight delays, cancellations and route performance — served from the dbt marts.")

    try:
        con = _connect()
    except Exception:
        st.error("Warehouse not found. Run `make pipeline` first to build it.")
        return

    kpis = load_kpis(con)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total flights", f"{int(kpis['total_flights']):,}")
    c2.metric("On-time %", f"{kpis['on_time_pct']}%")
    c3.metric("Cancellation %", f"{kpis['cancel_pct']}%")
    c4.metric("Avg arrival delay", f"{kpis['avg_arr_delay']} min")

    st.subheader("Daily delay & cancellation trend")
    trend = load_daily_trend(con)
    fig = px.line(trend, x="date_day", y=["delayed_flights", "cancelled_flights"],
                  labels={"value": "flights", "date_day": "date", "variable": ""})
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Delay minutes by cause")
        causes = load_delay_causes(con)
        st.plotly_chart(px.bar(causes, x="delay_cause", y="total_minutes"),
                        use_container_width=True)
    with right:
        st.subheader("On-time % by carrier")
        carriers = load_carrier_kpis(con)
        st.plotly_chart(px.bar(carriers, x="carrier_name", y="on_time_pct"),
                        use_container_width=True)

    left2, right2 = st.columns(2)
    with left2:
        st.subheader("Cancellations by reason")
        cancels = load_cancellations(con)
        st.plotly_chart(px.pie(cancels, names="cancellation_reason", values="cancelled_flights"),
                        use_container_width=True)
    with right2:
        st.subheader("Most-delayed routes")
        st.dataframe(load_top_routes(con), use_container_width=True, hide_index=True)

    con.close()


if __name__ == "__main__":
    main()
