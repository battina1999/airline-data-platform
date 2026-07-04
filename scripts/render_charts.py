"""
Render static dashboard images from the marts for the README / docs.
Produces a single 2x2 "dashboard overview" PNG plus individual panels.

    python scripts/render_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config import settings  # noqa: E402

IMG_DIR = Path(__file__).resolve().parents[1] / "docs" / "img"
NAVY, TEAL, AMBER, RED = "#1f3b5c", "#2a9d8f", "#e9a23b", "#c1435c"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "#cccccc", "axes.grid": True, "grid.color": "#eeeeee",
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
})


def _con():
    return duckdb.connect(str(settings.duckdb_path), read_only=True)


def render() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    con = _con()

    trend = con.sql("select date_day, delayed_flights, cancelled_flights "
                    "from marts.delay_trends order by date_day").df()
    carriers = con.sql("select carrier_name, on_time_pct from marts.operational_kpis "
                       "order by on_time_pct desc").df()
    causes = con.sql("select delay_cause, sum(delay_minutes) m from marts.fact_flight_delays "
                     "group by 1 order by 2 desc").df()
    cancels = con.sql("select cancellation_reason, sum(cancelled_flights) c "
                      "from marts.cancellations group by 1 order by 2 desc").df()

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Airline Operations Analytics — Dashboard Overview",
                 fontsize=16, fontweight="bold", color=NAVY)

    ax = axes[0, 0]
    ax.plot(trend["date_day"], trend["delayed_flights"], color=AMBER, label="Delayed")
    ax.plot(trend["date_day"], trend["cancelled_flights"], color=RED, label="Cancelled")
    ax.set_title("Daily Delayed vs Cancelled Flights")
    ax.legend(); ax.tick_params(axis="x", rotation=30)

    ax = axes[0, 1]
    ax.barh(carriers["carrier_name"], carriers["on_time_pct"], color=TEAL)
    ax.set_title("On-Time % by Carrier"); ax.invert_yaxis(); ax.set_xlim(0, 100)

    ax = axes[1, 0]
    ax.bar(causes["delay_cause"], causes["m"], color=NAVY)
    ax.set_title("Total Delay Minutes by Cause"); ax.tick_params(axis="x", rotation=20)

    ax = axes[1, 1]
    ax.pie(cancels["c"], labels=cancels["cancellation_reason"], autopct="%1.0f%%",
           colors=[NAVY, TEAL, AMBER, RED, "#888888"])
    ax.set_title("Cancellations by Reason")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = IMG_DIR / "dashboard_overview.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(f"wrote {out}")
    con.close()


if __name__ == "__main__":
    render()
