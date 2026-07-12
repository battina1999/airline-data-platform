"""
Airline Operations Analytics — 3-page Streamlit app over the dbt marts.

Data source resolution (parameterized, zero-config):
  1. live DuckDB warehouse (warehouse/airline.duckdb) when present — local dev
  2. bundled parquet extract (dashboards/public_data/) — public cloud deploy,
     no warehouse needed (this is what share.streamlit.io runs)

Pages: Overview KPIs · Route explorer · Delay causes
KPI definitions: docs/kpi_definitions.md (the single source of truth).

    streamlit run dashboards/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PUBLIC_DIR = Path(__file__).resolve().parent / "public_data"
MARTS = ["operational_kpis", "delay_trends", "route_performance",
         "cancellations", "dim_airport", "dim_airline"]


# ----------------------------- data access --------------------------------- #
@st.cache_data(show_spinner=False)
def load_marts() -> tuple[dict, str]:
    """Return ({mart: DataFrame}, source_label). Warehouse first, extract fallback."""
    try:
        from config import settings
        import duckdb

        if settings.duckdb_path.exists():
            con = duckdb.connect(str(settings.duckdb_path), read_only=True)
            try:
                data = {t: con.sql(f"SELECT * FROM marts.{t}").df() for t in MARTS}
                return data, "live warehouse (DuckDB)"
            finally:
                con.close()
    except Exception:
        pass

    if PUBLIC_DIR.exists():
        data = {t: pd.read_parquet(PUBLIC_DIR / f"{t}.parquet") for t in MARTS}
        return data, "bundled real-data extract"

    raise FileNotFoundError(
        "No data found. Run `make pipeline` (local) or commit dashboards/public_data/."
    )


def provenance() -> str:
    p = PUBLIC_DIR / "_provenance.txt"
    if p.exists():
        kv = dict(line.split("=", 1) for line in p.read_text().splitlines() if "=" in line)
        return (f"{int(kv.get('flights', 0)):,} real flights · US DOT BTS · "
                f"{kv.get('from')} → {kv.get('to')}")
    return "synthetic demo data"


# ----------------------------- pages --------------------------------------- #
def page_overview(m: dict) -> None:
    k = m["operational_kpis"]
    trend = m["delay_trends"].sort_values("date_day")

    total = int(k["total_flights"].sum())
    cancelled = int(k["cancelled_flights"].sum())
    completed = total - cancelled
    on_time_pct = (k["on_time_pct"] * k["total_flights"]).sum() / max(total, 1)
    avg_delay = (k["avg_arr_delay_min"] * k["total_flights"]).sum() / max(total, 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Flights", f"{total:,}")
    c2.metric("On-Time %", f"{on_time_pct:.1f}%",
              help="Completed flights arriving < 15 min late (US DOT A14). See docs/kpi_definitions.md")
    c3.metric("Cancellation rate", f"{100.0 * cancelled / max(total,1):.2f}%")
    c4.metric("Avg arrival delay", f"{avg_delay:.1f} min",
              help="Mean over completed flights; early arrivals count negative.")

    st.subheader("Daily delayed vs cancelled flights")
    fig = px.line(trend, x="date_day", y=["delayed_flights", "cancelled_flights"],
                  labels={"value": "flights", "date_day": "", "variable": ""})
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("On-Time % by carrier")
        kk = k.sort_values("on_time_pct", ascending=True)
        st.plotly_chart(px.bar(kk, x="on_time_pct", y="carrier_name", orientation="h",
                               labels={"on_time_pct": "On-Time %", "carrier_name": ""}),
                        use_container_width=True)
    with right:
        st.subheader("Cancellations by reason")
        c = m["cancellations"].groupby("cancellation_reason", as_index=False)["cancelled_flights"].sum()
        st.plotly_chart(px.pie(c, names="cancellation_reason", values="cancelled_flights"),
                        use_container_width=True)


def page_routes(m: dict) -> None:
    rp = m["route_performance"]
    airports = m["dim_airport"][["airport_code", "city", "state"]]

    st.subheader("Route explorer")
    st.caption("Directional origin→destination pairs · routes with <20 flights suppressed "
               "(see KPI definitions).")

    codes = sorted(set(rp["origin_airport"]) | set(rp["dest_airport"]))
    c1, c2, c3 = st.columns([1, 1, 2])
    origin = c1.selectbox("Origin", ["(all)"] + codes)
    dest = c2.selectbox("Destination", ["(all)"] + codes)
    min_flights = c3.slider("Min flights on route", 20, 2000, 100, step=20)

    view = rp[rp["total_flights"] >= min_flights]
    if origin != "(all)":
        view = view[view["origin_airport"] == origin]
    if dest != "(all)":
        view = view[view["dest_airport"] == dest]

    st.plotly_chart(
        px.scatter(view, x="on_time_pct", y="avg_arr_delay_min", size="total_flights",
                   hover_name="route", color="cancellation_pct",
                   labels={"on_time_pct": "On-Time %", "avg_arr_delay_min": "Avg arrival delay (min)",
                           "cancellation_pct": "Cancel %"},
                   color_continuous_scale="Reds"),
        use_container_width=True)

    st.subheader("Most-delayed routes (within filter)")
    cols = ["route", "total_flights", "on_time_pct", "avg_arr_delay_min", "cancellation_pct"]
    st.dataframe(view.sort_values("avg_arr_delay_min", ascending=False).head(25)[cols],
                 use_container_width=True, hide_index=True)
    st.caption(f"{len(view):,} routes in view")

    with st.expander("Airport reference"):
        st.dataframe(airports, use_container_width=True, hide_index=True)


def page_delay_causes(m: dict) -> None:
    trend = m["delay_trends"].sort_values("date_day")
    cause_cols = {
        "total_carrier_delay_min": "Carrier",
        "total_weather_delay_min": "Weather",
        "total_nas_delay_min": "NAS",
        "total_late_aircraft_delay_min": "Late aircraft",
    }

    st.subheader("Delay minutes by cause")
    st.caption("BTS attributes causes only when arrival delay ≥ 15 min. "
               "'Late aircraft' is knock-on delay from an upstream flight.")

    totals = trend[list(cause_cols)].sum().rename(index=cause_cols).reset_index()
    totals.columns = ["cause", "minutes"]
    left, right = st.columns([1, 2])
    with left:
        st.plotly_chart(px.pie(totals, names="cause", values="minutes"), use_container_width=True)
    with right:
        long = trend.melt(id_vars="date_day", value_vars=list(cause_cols),
                          var_name="cause", value_name="minutes")
        long["cause"] = long["cause"].map(cause_cols)
        st.plotly_chart(px.area(long, x="date_day", y="minutes", color="cause",
                                labels={"date_day": ""}), use_container_width=True)

    st.subheader("Delay rate over time")
    st.plotly_chart(px.line(trend, x="date_day", y="delayed_pct",
                            labels={"delayed_pct": "flights delayed ≥15min (%)", "date_day": ""}),
                    use_container_width=True)


# ----------------------------- shell ---------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Airline Operations Analytics", layout="wide", page_icon="✈️")
    try:
        marts, source = load_marts()
    except FileNotFoundError as e:
        st.error(str(e))
        return

    st.sidebar.title("✈️ Airline Ops Analytics")
    page = st.sidebar.radio("Page", ["Overview KPIs", "Route explorer", "Delay causes"])
    st.sidebar.markdown("---")
    st.sidebar.caption(f"**Data:** {provenance()}")
    st.sidebar.caption(f"**Serving from:** {source}")
    st.sidebar.markdown(
        "[KPI definitions](https://github.com/battina1999/airline-data-platform/blob/main/docs/kpi_definitions.md) · "
        "[Always-on dashboard](https://battina1999.github.io/airline-data-platform/) · "
        "[Lineage](https://battina1999.github.io/airline-data-platform/lineage/) · "
        "[Repo](https://github.com/battina1999/airline-data-platform)")

    st.title("Airline Operations Analytics")
    st.caption(f"{provenance()} — built by the dbt star schema, definitions in docs/kpi_definitions.md")

    if page == "Overview KPIs":
        page_overview(marts)
    elif page == "Route explorer":
        page_routes(marts)
    else:
        page_delay_causes(marts)


main()
