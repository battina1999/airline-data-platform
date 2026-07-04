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


def _run_dbt() -> int:
    env = os.environ.copy()
    env.setdefault("DBT_DUCKDB_PATH", str(settings.duckdb_path))
    proc = subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "build", "--profiles-dir", "."],
        cwd=DBT_DIR, env=env,
    )
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

    logger.info("################ PIPELINE START (warehouse=%s) ################", settings.warehouse)
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
