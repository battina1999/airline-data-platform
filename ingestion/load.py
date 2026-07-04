"""
Load stage (Talend `tDBOutput` equivalent).

Lands extracted DataFrames into the warehouse `raw` schema, adding audit
columns and recording an ingestion-audit row per source so the load is
observable and can be reconciled later (source-to-target row counts).

The load is *idempotent*: `CREATE OR REPLACE TABLE` gives a clean full refresh
every run, which keeps the demo deterministic. Swapping to an incremental /
merge strategy would be a one-line change in `load_dataframe`.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from config import settings
from ingestion.logging_config import get_logger

logger = get_logger("ingestion.load")

AUDIT_TABLE = f"{settings.raw_schema}._ingestion_audit"


def ensure_audit_table(con) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            batch_id        VARCHAR,
            source_file     VARCHAR,
            target_table    VARCHAR,
            rows_extracted  BIGINT,
            rows_loaded     BIGINT,
            loaded_at       TIMESTAMP,
            status          VARCHAR
        );
        """
    )


def load_dataframe(con, df: pd.DataFrame, table: str, source_file: str, batch_id: str) -> int:
    """Full-refresh a raw table from a DataFrame and write an audit row."""
    target = f"{settings.raw_schema}.{table}"
    rows_extracted = len(df)

    con.register("_incoming_df", df)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {target} AS
        SELECT
            *,
            CURRENT_TIMESTAMP        AS _loaded_at,
            '{source_file}'          AS _source_file,
            '{batch_id}'             AS _batch_id
        FROM _incoming_df;
        """
    )
    con.unregister("_incoming_df")

    rows_loaded = con.sql(f"SELECT COUNT(*) FROM {target}").fetchone()[0]
    status = "OK" if rows_loaded == rows_extracted else "ROW_COUNT_MISMATCH"

    con.execute(
        f"INSERT INTO {AUDIT_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
        [batch_id, source_file, target, rows_extracted, rows_loaded, datetime.utcnow(), status],
    )
    logger.info("loaded %-22s rows=%s status=%s", target, f"{rows_loaded:,}", status)
    return rows_loaded


def new_batch_id() -> str:
    return "batch_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")
