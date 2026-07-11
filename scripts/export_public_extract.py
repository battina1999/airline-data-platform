"""
Export a small, committable extract of the analytics marts for the PUBLIC
dashboard deployment (Streamlit Community Cloud runs without a warehouse).

Only aggregated marts are exported — a few thousand rows, no raw data — so the
repo stays light and no sensitive/full-fidelity data is published.

    python scripts/export_public_extract.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from config import settings

OUT = Path(__file__).resolve().parents[1] / "dashboards" / "public_data"
TABLES = ["operational_kpis", "delay_trends", "route_performance",
          "cancellations", "dim_airport", "dim_airline"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        for t in TABLES:
            path = OUT / f"{t}.parquet"
            con.execute(f"COPY (SELECT * FROM marts.{t}) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            n = con.sql(f"SELECT count(*) FROM marts.{t}").fetchone()[0]
            kb = path.stat().st_size // 1024
            print(f"exported {t:<18} rows={n:>7,}  {kb:>5} KB")
        # provenance stamp for the public app
        meta = con.sql(
            "SELECT count(*), min(flight_date), max(flight_date) FROM marts.fact_flights"
        ).fetchone()
        (OUT / "_provenance.txt").write_text(
            f"source=US DOT BTS On-Time Performance\nflights={meta[0]}\n"
            f"from={meta[1]}\nto={meta[2]}\n"
        )
        print(f"provenance: {meta[0]:,} flights {meta[1]} → {meta[2]}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
