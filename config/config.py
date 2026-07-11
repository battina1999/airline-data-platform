"""
Central configuration for the Airline Data Platform.

Everything that differs between the *local* (DuckDB) and *cloud* (Snowflake)
runs is resolved here, so the rest of the codebase never hard-codes a warehouse.
Set WAREHOUSE=snowflake in your .env to point the identical pipeline at Snowflake.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _default_bts_dir() -> Path:
    """Resolve the BTS data directory: env var, in-repo data/bts, or a sibling
    bts_data/ folder next to the project (handy for local drops)."""
    env = os.environ.get("BTS_DATA_DIR")
    if env:
        return Path(env)
    in_repo = PROJECT_ROOT / "data" / "bts"
    if in_repo.exists() and any(in_repo.rglob("*.csv")):
        return in_repo
    sibling = PROJECT_ROOT.parent / "bts_data"
    if sibling.exists():
        return sibling
    return in_repo


@dataclass(frozen=True)
class Settings:
    # --- data source: synthetic (default) | bts (real US DOT data) ---
    data_source: str = field(default_factory=lambda: _get("DATA_SOURCE", "synthetic").lower())
    bts_data_dir: Path = field(default_factory=_default_bts_dir)

    # --- warehouse selection ---
    warehouse: str = field(default_factory=lambda: _get("WAREHOUSE", "duckdb").lower())
    duckdb_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / _get("DUCKDB_PATH", "warehouse/airline.duckdb")
    )

    # --- schemas (identical names on DuckDB + Snowflake) ---
    raw_schema: str = "raw"
    staging_schema: str = "staging"
    mart_schema: str = "marts"

    # --- filesystem ---
    data_raw_dir: Path = PROJECT_ROOT / "data" / "raw"

    # --- synthetic data generation ---
    seed: int = field(default_factory=lambda: int(_get("DATA_SEED", "42")))
    n_flights: int = field(default_factory=lambda: int(_get("N_FLIGHTS", "60000")))
    start_date: date = field(
        default_factory=lambda: date.fromisoformat(_get("START_DATE", "2024-01-01"))
    )
    end_date: date = field(
        default_factory=lambda: date.fromisoformat(_get("END_DATE", "2024-03-31"))
    )

    # source table -> raw file name
    raw_files = {
        "airports": "airports.csv",
        "carriers": "carriers.csv",
        "flights": "flights.csv",
        "weather": "weather.csv",
    }

    def ensure_dirs(self) -> None:
        self.data_raw_dir.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()


def get_duckdb_connection(read_only: bool = False):
    """Return a DuckDB connection with the standard schemas created.

    Kept deliberately tiny so ingestion / quality / dashboard code all share
    one entry-point to the local warehouse.
    """
    import duckdb

    settings.ensure_dirs()
    con = duckdb.connect(str(settings.duckdb_path), read_only=read_only)
    if not read_only:
        for schema in (settings.raw_schema, settings.staging_schema, settings.mart_schema):
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    return con


if __name__ == "__main__":
    print(f"Warehouse : {settings.warehouse}")
    print(f"DuckDB    : {settings.duckdb_path}")
    print(f"Raw dir   : {settings.data_raw_dir}")
    print(f"Date range: {settings.start_date} -> {settings.end_date}")
    print(f"Flights   : {settings.n_flights:,}")
