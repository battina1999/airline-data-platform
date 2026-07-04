"""
Export the analytics marts to Parquet so BI tools without a DuckDB connector
(e.g. Power BI Desktop) can import them.

    python scripts/export_marts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from config import settings

EXPORT_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "powerbi" / "export"
MARTS = [
    "fact_flights", "fact_flight_delays", "dim_airport", "dim_airline",
    "dim_date", "route_performance", "delay_trends", "cancellations",
    "operational_kpis",
]


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        for table in MARTS:
            out = EXPORT_DIR / f"{table}.parquet"
            con.execute(f"COPY marts.{table} TO '{out}' (FORMAT PARQUET)")
            n = con.sql(f"SELECT COUNT(*) FROM marts.{table}").fetchone()[0]
            print(f"exported marts.{table:<20} rows={n:>8,} -> {out.name}")
    finally:
        con.close()
    print(f"\nAll marts exported to {EXPORT_DIR}")


if __name__ == "__main__":
    main()
