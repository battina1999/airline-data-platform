"""
Ingestion driver: land every source into the raw warehouse.

    python -m ingestion.run_ingestion                # synthetic (default)
    DATA_SOURCE=bts python -m ingestion.run_ingestion  # real US DOT data

Two source modes, one raw contract:
  * synthetic — extract CSVs from the generator, load via pandas (small data).
  * bts       — real BTS monthly files loaded directly by DuckDB (6M+ rows),
                see ingestion/bts_adapter.py.

Talend analogy: this is the parent Job that wires the input components
(extract) to the database output components (load) and records run metadata.
"""
from __future__ import annotations

from config import settings, get_duckdb_connection
from ingestion.extract import extract_all
from ingestion.load import ensure_audit_table, load_dataframe, new_batch_id
from ingestion.logging_config import get_logger

logger = get_logger("ingestion.run")

# source name -> raw table name
SOURCE_TO_TABLE = {
    "airports": "airports",
    "carriers": "carriers",
    "weather": "weather",
    "flights": "flights",
}


def run_bts() -> None:
    """Real-data mode: land BTS monthly files straight into raw via DuckDB."""
    from ingestion.bts_adapter import bts_files, load_bts

    files = bts_files()
    if not files:
        raise FileNotFoundError(
            f"DATA_SOURCE=bts but no CSVs found in {settings.bts_data_dir}. "
            "Download monthly 'Reporting Carrier On-Time Performance' files from "
            "transtats.bts.gov and place them there."
        )
    logger.info("=== ingestion (source=bts, %d files, warehouse=%s) ===",
                len(files), settings.warehouse)
    con = get_duckdb_connection()
    try:
        stats = load_bts(con)
        logger.info("=== BTS ingestion complete: %s flights ===", f"{stats['flights']:,}")
    finally:
        con.close()


def run() -> None:
    if settings.data_source == "bts":
        run_bts()
        return

    batch_id = new_batch_id()
    logger.info("=== ingestion batch %s (source=synthetic, warehouse=%s) ===",
                batch_id, settings.warehouse)

    frames = extract_all()

    con = get_duckdb_connection()
    try:
        ensure_audit_table(con)
        total = 0
        for source_name, table in SOURCE_TO_TABLE.items():
            df = frames[source_name]
            total += load_dataframe(
                con, df, table=table,
                source_file=settings.raw_files[source_name], batch_id=batch_id,
            )
        logger.info("=== ingestion complete: %s rows across %d tables ===",
                    f"{total:,}", len(SOURCE_TO_TABLE))

        preview = con.sql(
            f"SELECT target_table, rows_extracted, rows_loaded, status "
            f"FROM {settings.raw_schema}._ingestion_audit WHERE batch_id = '{batch_id}' "
            f"ORDER BY target_table"
        ).fetchall()
        logger.info("audit:")
        for row in preview:
            logger.info("   %-28s extracted=%-8s loaded=%-8s %s", *row)
    finally:
        con.close()


if __name__ == "__main__":
    run()
