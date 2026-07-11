"""
BTS adapter tests against a committed real-format fixture
(tests/fixtures/bts_sample/, actual BTS prezip column names + quirks:
duplicate key, cancelled flight with NULL delays, missing tail, airports
outside the curated reference).
"""
import os
from pathlib import Path

import duckdb
import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bts_sample"


@pytest.fixture()
def bts_env(monkeypatch):
    monkeypatch.setenv("BTS_DATA_DIR", str(FIXTURE_DIR))
    monkeypatch.setenv("DATA_SOURCE", "bts")
    import config.config as cfg
    import ingestion.bts_adapter as adapter

    fresh = cfg.Settings()
    monkeypatch.setattr(cfg, "settings", fresh)
    monkeypatch.setattr(adapter, "settings", fresh)

    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    yield adapter, con
    con.close()


def test_schema_validation_passes_on_real_format(bts_env):
    adapter, con = bts_env
    assert adapter.validate_schema(con) == []


def test_load_bts_lands_all_rows(bts_env):
    adapter, con = bts_env
    stats = adapter.load_bts(con)
    assert stats["source_rows"] == 16          # fixture rows incl. the duplicate
    assert stats["flights"] == 16              # raw keeps everything (staging dedupes)
    assert stats["carriers"] == 10


def test_airports_derived_from_data_not_whitelist(bts_env):
    adapter, con = bts_env
    adapter.load_bts(con)
    codes = {r[0] for r in con.execute("SELECT airport_code FROM raw.airports").fetchall()}
    # BOI / ANC / OGG / SFB / HOU are NOT in the curated 40-airport reference:
    # real-data mode must keep them (derived dims), not silently drop their flights.
    assert {"BOI", "ANC", "OGG", "SFB", "HOU"} <= codes
    # enriched majors keep coordinates; derived-only airports have NULL lat
    lat_atl = con.execute("SELECT latitude FROM raw.airports WHERE airport_code='ATL'").fetchone()[0]
    lat_boi = con.execute("SELECT latitude FROM raw.airports WHERE airport_code='BOI'").fetchone()[0]
    assert lat_atl is not None and lat_boi is None


def test_quirks_preserved_in_raw(bts_env):
    adapter, con = bts_env
    adapter.load_bts(con)
    # cancelled flight keeps NULL delays (BTS convention — not "dirty" data)
    n = con.execute("SELECT count(*) FROM raw.flights "
                    "WHERE cancelled=1 AND dep_delay_min IS NULL").fetchone()[0]
    assert n == 2
    # the double-reported UA523 pair shares one flight_id (hash of natural key)
    dup = con.execute("""
        SELECT count(*) FROM (
            SELECT flight_id FROM raw.flights GROUP BY 1 HAVING count(*) > 1
        )""").fetchone()[0]
    assert dup == 1
    # HHMM -> minutes conversion: 0730 -> 450
    m = con.execute("SELECT scheduled_departure_min FROM raw.flights "
                    "WHERE carrier_code='AA' AND flight_number=104").fetchone()[0]
    assert m == 450


def test_missing_columns_detected(bts_env, tmp_path, monkeypatch):
    adapter, con = bts_env
    (tmp_path / "bad.csv").write_text("A,B\n1,2\n")
    import config.config as cfg
    monkeypatch.setenv("BTS_DATA_DIR", str(tmp_path))
    broken = cfg.Settings()
    monkeypatch.setattr(adapter, "settings", broken)
    missing = adapter.validate_schema(con)
    assert "FlightDate" in missing and "Origin" in missing
