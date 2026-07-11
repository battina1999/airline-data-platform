"""
Local, no-Docker pipeline runner.

Executes the full flow in order and prints a timed summary:

    generate -> ingest -> validate (GE) -> dbt build -> reconcile

This is the same sequence the Airflow DAG runs; keeping a plain-Python runner
means the project is demonstrable on any laptop without standing up Airflow.

    python -m orchestration.run_pipeline
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from config import settings, PROJECT_ROOT
from ingestion.logging_config import get_logger

logger = get_logger("orchestration")

DBT_DIR = PROJECT_ROOT / "dbt" / "airline_dwh"


def _last_source() -> str | None:
    """Which DATA_SOURCE last built this warehouse (None on first build)."""
    import duckdb

    try:
        con = duckdb.connect(str(settings.duckdb_path))
        con.execute("CREATE TABLE IF NOT EXISTS main._pipeline_meta "
                    "(key VARCHAR PRIMARY KEY, value VARCHAR)")
        row = con.execute(
            "SELECT value FROM main._pipeline_meta WHERE key = 'last_source'"
        ).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def _record_source() -> None:
    import duckdb

    con = duckdb.connect(str(settings.duckdb_path))
    con.execute("CREATE TABLE IF NOT EXISTS main._pipeline_meta "
                "(key VARCHAR PRIMARY KEY, value VARCHAR)")
    con.execute("INSERT OR REPLACE INTO main._pipeline_meta VALUES ('last_source', ?)",
                [settings.data_source])
    con.close()


def _run_dbt() -> int:
    env = os.environ.copy()
    env.setdefault("DBT_DUCKDB_PATH", str(settings.duckdb_path))

    cmd = [sys.executable, "-m", "dbt.cli.main", "build", "--profiles-dir", "."]

    # SOURCE GUARD: incremental models must never mix rows from different
    # sources. If this warehouse was last built from a different DATA_SOURCE
    # (e.g. bts -> synthetic), force a full refresh so facts and dimensions are
    # rebuilt consistently instead of appending across sources.
    last = _last_source()
    if last is not None and last != settings.data_source:
        logger.warning("source changed since last build (%s -> %s): forcing --full-refresh",
                       last, settings.data_source)
        cmd.append("--full-refresh")

    proc = subprocess.run(cmd, cwd=DBT_DIR, env=env)
    if proc.returncode == 0:
        _record_source()
    return proc.returncode


def main() -> int:
    from data.generate_data import main as generate
    from ingestion.run_ingestion import run as ingest
    from quality.validate import run as validate
    from quality.reconciliation import run as reconcile

    stages = [
        ("generate", lambda: (generate(), 0)[1]),
        ("ingest", lambda: (ingest(), 0)[1]),
        ("validate (GE)", lambda: validate(strict=False)),  # monitor mode
        ("dbt build", _run_dbt),
        ("reconcile", reconcile),
    ]
    if settings.data_source == "bts":
        # real data: nothing to generate — the BTS files ARE the source
        stages = stages[1:]

    logger.info("################ PIPELINE START (source=%s, warehouse=%s) ################",
                settings.data_source, settings.warehouse)
    results, failed = [], False
    for name, fn in stages:
        t0 = time.time()
        try:
            rc = fn() or 0
        except Exception as exc:  # noqa: BLE001
            logger.exception("stage '%s' crashed: %s", name, exc)
            rc = 1
        elapsed = time.time() - t0
        status = "OK" if rc == 0 else "FAIL"
        results.append((name, status, f"{elapsed:5.1f}s"))
        logger.info(">>> stage '%s' finished: %s (%.1fs)", name, status, elapsed)
        if rc != 0 and name in ("dbt build", "reconcile"):  # hard-stop stages
            failed = True
            break

    logger.info("################ PIPELINE SUMMARY ################")
    for name, status, elapsed in results:
        logger.info("   %-16s %-4s %s", name, status, elapsed)
    logger.info("################ %s ################", "FAILED" if failed else "SUCCESS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
