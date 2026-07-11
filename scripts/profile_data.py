"""
Profile the raw BTS files BEFORE building against them, and write the findings
to docs/data_profile.md — row counts, null rates, distincts, delay ranges, and
the specific quirks (sentinels, null-on-cancelled, duplicate keys) with how the
platform handles each. Run:

    python scripts/profile_data.py        # or: make profile-data
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from config import PROJECT_ROOT, settings

OUT = PROJECT_ROOT / "docs" / "data_profile.md"

KEY_COLS = ["FlightDate", "Reporting_Airline", "Tail_Number", "Origin", "Dest",
            "DepDelay", "ArrDelay", "Cancelled", "CancellationCode", "Distance",
            "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]


def main() -> None:
    files = sorted(settings.bts_data_dir.rglob("*.csv"))
    if not files:
        print(f"No BTS csvs found in {settings.bts_data_dir} — nothing to profile.")
        sys.exit(1)

    pattern = str(settings.bts_data_dir / "**" / "*.csv").replace("'", "''")
    con = duckdb.connect()

    # single scan of the (possibly multi-GB) CSVs into a columnar temp table,
    # keeping ONLY the profiled columns (the raw extract has ~110)
    print(f"scanning {len(files)} files once ...")
    needed = set(KEY_COLS) | {"Flight_Number_Reporting_Airline", "CRSDepTime"}
    col_list = ", ".join(f'"{c}"' for c in needed)
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE t AS SELECT {col_list}, "
        f"regexp_extract(filename, '([^/\\\\]+)$', 1) AS _f "
        f"FROM read_csv('{pattern}', header=true, union_by_name=true, "
        f"sample_size=200000, ignore_errors=true, filename=true)"
    )
    rel = "t"

    total = con.sql("SELECT count(*) FROM t").fetchone()[0]
    per_file = con.sql("SELECT _f, count(*) FROM t GROUP BY 1 ORDER BY 1").fetchall()

    cols_present = [r[0] for r in con.sql(
        "SELECT column_name FROM (DESCRIBE SELECT * FROM t LIMIT 1)").fetchall()]
    prof_cols = [c for c in KEY_COLS if c in cols_present]

    null_exprs = ", ".join(
        f'sum(CASE WHEN "{c}" IS NULL THEN 1 ELSE 0 END)' for c in prof_cols)
    null_counts = con.sql(f"SELECT {null_exprs} FROM t").fetchone()
    null_rates = {c: (100.0 * n / total if total else 0)
                  for c, n in zip(prof_cols, null_counts)}

    carriers = con.sql('SELECT count(DISTINCT "Reporting_Airline") FROM t').fetchone()[0]
    airports = con.sql(
        'SELECT count(DISTINCT code) FROM (SELECT "Origin" code FROM t '
        'UNION SELECT "Dest" FROM t)').fetchone()[0]
    date_range = con.sql('SELECT min("FlightDate"), max("FlightDate") FROM t').fetchone()

    delay_stats = con.sql(
        'SELECT min("DepDelay"), max("DepDelay"), round(avg("DepDelay"),2), '
        'min("ArrDelay"), max("ArrDelay"), round(avg("ArrDelay"),2) FROM t'
    ).fetchone()

    cancelled = con.sql('SELECT count(*) FROM t WHERE "Cancelled" = 1').fetchone()[0]
    cancelled_null_delay = con.sql(
        'SELECT count(*) FROM t WHERE "Cancelled" = 1 AND "DepDelay" IS NULL').fetchone()[0]

    dup_keys = con.sql(
        'SELECT count(*) - count(DISTINCT ("FlightDate"::VARCHAR || \'|\' || "Reporting_Airline" '
        "|| '|' || \"Flight_Number_Reporting_Airline\"::VARCHAR || '|' || \"Origin\" || '|' || "
        'coalesce("CRSDepTime"::VARCHAR, \'\'))) FROM t'
    ).fetchone()[0]

    sentinel = con.sql('SELECT count(*) FROM t WHERE "DepDelay" <= -900').fetchone()[0]
    null_tails = null_rates.get("Tail_Number", 0.0)

    lines = [
        "# Data Profile — US DOT BTS On-Time Performance",
        "",
        f"_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by `scripts/profile_data.py`. "
        "Profiled BEFORE building — every quirk below is handled explicitly in the pipeline._",
        "",
        "## Volume",
        "",
        f"- **Total rows:** {total:,} across {len(files)} monthly files",
        f"- **Date range:** {date_range[0]} → {date_range[1]}",
        f"- **Distinct carriers:** {carriers} · **Distinct airports:** {airports}",
        "",
        "| File | Rows |",
        "|---|---|",
        *[f"| {f} | {n:,} |" for f, n in per_file],
        "",
        "## Null rates (key columns)",
        "",
        "| Column | Null % |",
        "|---|---|",
        *[f"| {c} | {null_rates[c]:.2f}% |" for c in prof_cols],
        "",
        "## Delay distributions",
        "",
        f"- DepDelay: min {delay_stats[0]}, max {delay_stats[1]}, mean {delay_stats[2]} min",
        f"- ArrDelay: min {delay_stats[3]}, max {delay_stats[4]}, mean {delay_stats[5]} min",
        "",
        "## Quirks found → how the platform handles each",
        "",
        f"1. **NULL delays on cancelled flights** — {cancelled_null_delay:,} of {cancelled:,} "
        "cancelled flights have `DepDelay IS NULL`. This is *correct* BTS behaviour (a flight "
        "that never departed has no delay). Handled: staging keeps them NULL, `delay_bucket` "
        "maps NULL → `unknown`, and marts exclude cancelled flights from delay averages. A "
        "dedicated GE expectation asserts the pattern instead of flagging it as dirty.",
        "",
        f"2. **Duplicate natural keys** — {dup_keys:,} rows share a "
        "(FlightDate, carrier, flight number, origin, CRSDepTime) key: real double-reported "
        "records. Handled: surfaced by a GE compound-uniqueness expectation (warn), "
        "de-duplicated in `stg_flights` (latest `_loaded_at` wins), and every removed row is "
        "accounted for in source-to-target reconciliation.",
        "",
        f"3. **Sentinel delay values** — {sentinel:,} rows with `DepDelay <= -900` "
        "(legacy sentinel pattern; common in older extracts). Handled: converted to NULL in "
        "staging; GE bounds delays to [-60, 2000] minutes.",
        "",
        f"4. **Missing tail numbers** — {null_tails:.2f}% of rows. Cancelled flights often "
        "have no tail assigned. Handled: nullable column; no join depends on it.",
        "",
        "5. **HHMM-encoded times** — `CRSDepTime` is an integer like `1530` (= 15:30), not "
        "minutes. Handled: converted to minutes-past-midnight in the adapter "
        "(`floor(x/100)*60 + x%100`).",
        "",
        "6. **Local times, no timezone** — BTS times are airport-local with no UTC offset. "
        "Handled: modelled as local wall-clock; the airport dimension carries a tz offset for "
        "the majors; cross-timezone duration math deliberately uses `CRSElapsedTime` instead "
        "of arrival-minus-departure.",
        "",
        "7. **Delay-cause columns only populated when ArrDelay ≥ 15** — BTS convention. "
        "Handled: `coalesce(...,0)` at ingestion; cause analysis restricted to delayed flights "
        "in `fact_flight_delays`.",
        "",
        "## S3 landing layout",
        "",
        "Raw files land (private bucket) under a partitioned prefix before ingestion:",
        "",
        "```",
        "s3://aeroops-raw/bts/year=2025/month=01/On_Time_..._2025_1.csv",
        "s3://aeroops-raw/bts/year=2025/month=02/On_Time_..._2025_2.csv",
        "```",
        "",
        "Locally the same files sit in `data/bts/` (or `../bts_data/`), and "
        "`DATA_SOURCE=bts make pipeline` ingests them identically.",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}  ({total:,} rows profiled)")


if __name__ == "__main__":
    main()
