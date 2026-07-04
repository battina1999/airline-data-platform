"""
Ingestion driver: extract every source and load it into the raw warehouse.

    python -m ingestion.run_ingestion

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


def run() -> None:
    batch_id = new_batch_id()
    logger.info("=== ingestion batch %s (warehouse=%s) ===", batch_id, settings.warehouse)

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
