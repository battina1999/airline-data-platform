"""Build the small JSON payload consumed by the static GitHub Pages dashboard.

The source Parquet files are the same committed public marts used by the
Streamlit dashboard.  Keeping this export deterministic means Pages can be
rebuilt on every push without a database, API, token, or always-on server.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "dashboards" / "public_data"
DEFAULT_OUTPUT = ROOT / "docs" / "dashboard" / "data" / "dashboard-data.json"


def _serialise(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    result = connection.execute(sql)
    columns = [column[0] for column in result.description]
    return [
        {name: _serialise(value) for name, value in zip(columns, row, strict=True)}
        for row in result.fetchall()
    ]


def _parquet(name: str) -> str:
    return str(SOURCE / f"{name}.parquet").replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON file to write (defaults to the local dashboard data directory)",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    provenance = {
        key: value
        for line in (SOURCE / "_provenance.txt").read_text().splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }

    connection = duckdb.connect()
    try:
        payload = {
            "meta": {
                "source": provenance.get("source", "US DOT BTS On-Time Performance"),
                "flights": int(provenance.get("flights", "0")),
                "from": provenance.get("from", ""),
                "to": provenance.get("to", ""),
            },
            "kpis": _rows(
                connection,
                f"""
                SELECT carrier_code, carrier_name, carrier_type, total_flights,
                       cancelled_flights, diverted_flights, completion_factor_pct,
                       on_time_pct, avg_dep_delay_min, avg_arr_delay_min,
                       total_delay_minutes
                FROM read_parquet('{_parquet('operational_kpis')}')
                ORDER BY total_flights DESC, carrier_code
                """,
            ),
            "trends": _rows(
                connection,
                f"""
                SELECT date_day, total_flights, delayed_flights, cancelled_flights,
                       delayed_pct, avg_arr_delay_min, total_weather_delay_min,
                       total_carrier_delay_min, total_nas_delay_min,
                       total_late_aircraft_delay_min
                FROM read_parquet('{_parquet('delay_trends')}')
                ORDER BY date_day
                """,
            ),
            "cancellations": _rows(
                connection,
                f"""
                SELECT cancellation_reason,
                       CAST(sum(cancelled_flights) AS BIGINT) AS cancelled_flights
                FROM read_parquet('{_parquet('cancellations')}')
                GROUP BY cancellation_reason
                ORDER BY cancelled_flights DESC, cancellation_reason
                """,
            ),
            "routes": _rows(
                connection,
                f"""
                SELECT origin_airport, dest_airport, route, total_flights,
                       cancelled_flights, cancellation_pct, avg_dep_delay_min,
                       avg_arr_delay_min, on_time_pct, avg_distance_miles
                FROM read_parquet('{_parquet('route_performance')}')
                WHERE total_flights >= 20
                ORDER BY total_flights DESC, route
                """,
            ),
            "airports": _rows(
                connection,
                f"""
                SELECT airport_code, city, state, region, is_major_hub
                FROM read_parquet('{_parquet('dim_airport')}')
                ORDER BY airport_code
                """,
            ),
        }
    finally:
        connection.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    try:
        display_path = output.relative_to(ROOT)
    except ValueError:
        display_path = output
    print(f"Wrote {display_path} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
