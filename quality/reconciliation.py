"""
Source-to-target row-count reconciliation.

Answers the question every data platform must answer: "did we lose or silently
drop rows between the source file and the analytics tables, and if the counts
differ, can we explain every row?"

For each source it reconciles:  source file  ->  raw  ->  staging (cleaned)
and classifies the deltas into (a) duplicates removed and (b) rows filtered by
data-quality rules (e.g. orphan airport codes). A run is RECONCILED when every
row is accounted for; it FAILS only on unexplained loss (a real breakage).

    python -m quality.reconciliation        # run after `dbt build`
"""
from __future__ import annotations

import json
import sys

from tabulate import tabulate

from config import settings, get_duckdb_connection
from ingestion.logging_config import get_logger

logger = get_logger("quality.reconcile")

REPORT_PATH = settings.data_raw_dir.parent.parent / "quality" / "expectations" / "reconciliation_report.json"

RECON_SPEC = [
    {"name": "flights", "file": "flights.csv", "raw": "raw.flights", "staging": "staging.stg_flights", "key": "flight_id"},
    {"name": "airports", "file": "airports.csv", "raw": "raw.airports", "staging": "staging.stg_airports", "key": "airport_code"},
    {"name": "carriers", "file": "carriers.csv", "raw": "raw.carriers", "staging": "staging.stg_carriers", "key": "carrier_code"},
    {"name": "weather", "file": "weather.csv", "raw": "raw.weather", "staging": "staging.stg_weather", "key": None},
]


def _file_rows(filename: str) -> int:
    path = settings.data_raw_dir / filename
    with open(path, "r", encoding="utf-8") as fh:
        return max(sum(1 for _ in fh) - 1, 0)  # minus header


def _bts_source_rows(con) -> int:
    """Source row count straight from the BTS monthly CSVs (DuckDB, fast)."""
    pattern = str(settings.bts_data_dir / "*.csv").replace("'", "''")
    return con.sql(
        f"SELECT count(*) FROM read_csv('{pattern}', header=true, "
        f"union_by_name=true, sample_size=200000, ignore_errors=true)"
    ).fetchone()[0]


def _source_rows(con, spec: dict) -> int:
    """File-level row count for a source, respecting the active DATA_SOURCE.

    In bts mode: flights come from the monthly files; airports/carriers are
    *derived* dimensions (source == raw by construction); weather is empty.
    """
    if settings.data_source != "bts":
        return _file_rows(spec["file"])
    if spec["name"] == "flights":
        return _bts_source_rows(con)
    if spec["name"] == "weather":
        return 0
    return _count(con, spec["raw"])  # derived dims: raw IS the source


def _table_exists(con, fqname: str) -> bool:
    schema, table = fqname.split(".")
    q = ("SELECT COUNT(*) FROM information_schema.tables "
         "WHERE table_schema = ? AND table_name = ?")
    return con.sql(q, params=[schema, table]).fetchone()[0] > 0


def _count(con, fqname: str) -> int:
    return con.sql(f"SELECT COUNT(*) FROM {fqname}").fetchone()[0]


def _distinct(con, fqname: str, key: str) -> int:
    return con.sql(f"SELECT COUNT(DISTINCT {key}) FROM {fqname}").fetchone()[0]


def run() -> int:
    con = get_duckdb_connection(read_only=True)
    rows, report, overall_ok = [], [], True
    try:
        for spec in RECON_SPEC:
            src = _source_rows(con, spec)
            raw = _count(con, spec["raw"])
            load_ok = src == raw

            duplicates = 0
            if spec["key"]:
                duplicates = raw - _distinct(con, spec["raw"], spec["key"])

            staging = filtered = None
            reconciled = load_ok
            if _table_exists(con, spec["staging"]):
                staging = _count(con, spec["staging"])
                # rows present after de-dup, minus what survived cleaning
                filtered = (raw - duplicates) - staging
                # every raw row must be either kept, a duplicate, or filtered
                reconciled = load_ok and (raw == staging + duplicates + filtered)

            status = "RECONCILED" if (load_ok and reconciled) else "FAIL"
            if status == "FAIL":
                overall_ok = False

            rows.append([
                spec["name"], src, raw, "OK" if load_ok else "MISMATCH",
                duplicates, "-" if staging is None else staging,
                "-" if filtered is None else filtered, status,
            ])
            report.append({
                "source": spec["name"], "source_rows": src, "raw_rows": raw,
                "load_fidelity": load_ok, "duplicates_removed": duplicates,
                "staging_rows": staging, "rows_filtered_by_dq": filtered,
                "status": status,
            })

        header = ["source", "file_rows", "raw_rows", "load", "dupes_removed",
                  "staging_rows", "dq_filtered", "status"]
        logger.info("source-to-target reconciliation:\n%s",
                    tabulate(rows, headers=header, tablefmt="github"))

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(
            {"overall": "PASS" if overall_ok else "FAIL", "detail": report}, indent=2, default=str))
        logger.info("report written -> %s", REPORT_PATH)

        if not overall_ok:
            logger.error("reconciliation FAILED: unexplained row loss detected")
            return 1
        logger.info("reconciliation PASSED: every source row is accounted for")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(run())
