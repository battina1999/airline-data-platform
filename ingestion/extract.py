"""
Extract stage (Talend `tFileInputDelimited` equivalent).

Reads each raw delimited source into a DataFrame and profiles it. Kept as a
separate stage from `load` so the extract logic could be swapped for an API,
SFTP drop, or S3 object without touching the loader - exactly how a Talend job
separates input components from database output components.
"""
from __future__ import annotations

import pandas as pd

from config import settings
from ingestion.logging_config import get_logger

logger = get_logger("ingestion.extract")


def extract_source(name: str) -> pd.DataFrame:
    """Extract a single named source ('flights', 'airports', ...)."""
    filename = settings.raw_files[name]
    path = settings.data_raw_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Raw file not found: {path}. Run `make generate` (python -m data.generate_data) first."
        )
    df = pd.read_csv(path)
    logger.info("extracted '%s' -> rows=%s cols=%s file=%s",
                name, f"{len(df):,}", df.shape[1], filename)
    return df


def extract_all() -> dict[str, pd.DataFrame]:
    """Extract every configured source. Returns {source_name: dataframe}."""
    logger.info("starting extract for %d sources", len(settings.raw_files))
    return {name: extract_source(name) for name in settings.raw_files}
