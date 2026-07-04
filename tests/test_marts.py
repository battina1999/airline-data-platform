"""
Warehouse-dependent tests: run after `make pipeline`. They validate the built
marts (grain, KPI bounds, referential integrity). Skipped cleanly if the
warehouse or marts have not been built yet.
"""
import duckdb
import pytest

from config import settings

pytestmark = pytest.mark.skipif(
    not settings.duckdb_path.exists(),
    reason="warehouse not built - run `make pipeline` first",
)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(settings.duckdb_path), read_only=True)
    yield c
    c.close()


def _marts_ready(con) -> bool:
    return con.sql(
        "select count(*) from information_schema.tables where table_schema='marts'"
    ).fetchone()[0] > 0


def test_fact_flights_grain_is_one_per_flight(con):
    if not _marts_ready(con):
        pytest.skip("marts not built")
    total, distinct = con.sql(
        "select count(*), count(distinct flight_id) from marts.fact_flights"
    ).fetchone()
    assert total == distinct
    assert total > 50_000


def test_on_time_pct_within_bounds(con):
    if not _marts_ready(con):
        pytest.skip("marts not built")
    bad = con.sql(
        "select count(*) from marts.operational_kpis where on_time_pct < 0 or on_time_pct > 100"
    ).fetchone()[0]
    assert bad == 0


def test_fact_has_no_orphan_airport_keys(con):
    if not _marts_ready(con):
        pytest.skip("marts not built")
    orphans = con.sql(
        """
        select count(*)
        from marts.fact_flights f
        left join marts.dim_airport a on f.origin_airport_key = a.airport_key
        where a.airport_key is null
        """
    ).fetchone()[0]
    assert orphans == 0
