"""
BTS source adapter: real US DOT "Reporting Carrier On-Time Performance" data.

Replaces the synthetic generator when DATA_SOURCE=bts. Reads the monthly CSVs
downloaded from transtats.bts.gov (PREZIP files, ~500-600K rows/month) and
lands them in the warehouse `raw` schema with the SAME shape the rest of the
platform expects — so staging, dbt, GE and the dashboards run unchanged.

Design decisions (see docs/data_profile.md and docs/decisions.md):
  * Flights load DIRECTLY via DuckDB `read_csv` (no pandas): 6M+ rows stream
    into the warehouse in seconds instead of exhausting RAM.
  * `dim_airport` / `dim_airline` inputs are DERIVED FROM THE DATA (distinct
    origins/dests with city+state; distinct reporting carriers), enriched with
    coordinates/names from the curated reference where known. This avoids the
    synthetic-era 40-airport whitelist silently dropping most real flights.
  * `flight_id` is synthesized as a 64-bit hash of the natural key
    (FlightDate, carrier, flight number, origin, CRSDepTime, tail). Remaining
    duplicates by that key are *real* double-reported flights — kept in raw,
    surfaced by Great Expectations, de-duplicated in staging (latest wins).
  * Weather has no BTS equivalent: an empty weather.csv-shaped table keeps the
    contract; downstream models treat weather as optional enrichment.

Usage:
    DATA_SOURCE=bts python -m ingestion.run_ingestion
"""
from __future__ import annotations

from datetime import datetime

from config import settings
from data.reference import AIRPORTS, CARRIERS
from ingestion.load import AUDIT_TABLE, ensure_audit_table, new_batch_id
from ingestion.logging_config import get_logger

logger = get_logger("ingestion.bts")

# Core columns the adapter requires (extra BTS columns are ignored).
REQUIRED_COLUMNS = [
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
    "Origin", "Dest", "CRSDepTime", "Distance", "Cancelled", "Diverted",
]


def bts_files() -> list:
    return sorted(settings.bts_data_dir.glob("*.csv"))


def _rel(with_filename: bool = False) -> str:
    """read_csv relation over every BTS csv in the data dir."""
    pattern = str(settings.bts_data_dir / "*.csv").replace("'", "''")
    fn = ", filename=true" if with_filename else ""
    return (
        f"read_csv('{pattern}', header=true, union_by_name=true, "
        f"sample_size=200000, ignore_errors=true{fn})"
    )


def validate_schema(con) -> list:
    """Return the list of required columns missing from the source files."""
    cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM (DESCRIBE SELECT * FROM {_rel()} LIMIT 1)"
    ).fetchall()]
    return [c for c in REQUIRED_COLUMNS if c not in cols]


def load_bts(con) -> dict:
    """Land raw.flights / raw.airports / raw.carriers / raw.weather from BTS."""
    batch_id = new_batch_id()
    ensure_audit_table(con)

    missing = validate_schema(con)
    if missing:
        raise ValueError(f"BTS files are missing required columns: {missing}")

    src_rows = con.execute(f"SELECT count(*) FROM {_rel()}").fetchone()[0]
    logger.info("BTS source rows across %d files: %s", len(bts_files()), f"{src_rows:,}")

    # ---------------- flights (direct DuckDB load, no pandas) ----------------
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.flights AS
        SELECT
            (hash(
                coalesce(FlightDate::VARCHAR,'') || '|' ||
                coalesce(Reporting_Airline,'')   || '|' ||
                coalesce(Flight_Number_Reporting_Airline::VARCHAR,'') || '|' ||
                coalesce(Origin,'') || '|' ||
                coalesce(CRSDepTime::VARCHAR,'') || '|' ||
                coalesce(Tail_Number,'')
            ) >> 1)::BIGINT                                  AS flight_id,
            FlightDate::DATE                                 AS flight_date,
            Reporting_Airline                                AS carrier_code,
            Flight_Number_Reporting_Airline::INTEGER         AS flight_number,
            nullif(trim(Tail_Number), '')                    AS tail_number,
            Origin                                           AS origin,
            Dest                                             AS dest,
            (floor(CRSDepTime::INTEGER / 100) * 60
             + CRSDepTime::INTEGER % 100)::INTEGER           AS scheduled_departure_min,
            Distance::DOUBLE                                 AS distance_miles,
            CRSElapsedTime::INTEGER                          AS scheduled_air_time_min,
            DepDelay::INTEGER                                AS dep_delay_min,
            ArrDelay::INTEGER                                AS arr_delay_min,
            Cancelled::DOUBLE::INTEGER                       AS cancelled,
            coalesce(nullif(trim(CancellationCode), ''), '') AS cancellation_code,
            Diverted::DOUBLE::INTEGER                        AS diverted,
            coalesce(CarrierDelay::INTEGER, 0)               AS carrier_delay_min,
            coalesce(WeatherDelay::INTEGER, 0)               AS weather_delay_min,
            coalesce(NASDelay::INTEGER, 0)                   AS nas_delay_min,
            coalesce(SecurityDelay::INTEGER, 0)              AS security_delay_min,
            coalesce(LateAircraftDelay::INTEGER, 0)          AS late_aircraft_delay_min,
            CURRENT_TIMESTAMP                                AS _loaded_at,
            'bts/' || regexp_extract(filename, '([^/\\\\]+)$', 1) AS _source_file,
            '{batch_id}'                                     AS _batch_id
        FROM {_rel(with_filename=True)}
    """)
    n_flights = con.execute("SELECT count(*) FROM raw.flights").fetchone()[0]

    # -------- airports: derived from the data, enriched from the reference ----
    con.execute("CREATE OR REPLACE TEMP TABLE _airport_ref (code VARCHAR, name VARCHAR, "
                "lat DOUBLE, lon DOUBLE, tz INTEGER, hub INTEGER)")
    con.executemany(
        "INSERT INTO _airport_ref VALUES (?,?,?,?,?,?)",
        [[a[0], a[1], a[4], a[5], a[6], a[7]] for a in AIRPORTS],
    )
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.airports AS
        WITH seen AS (
            SELECT Origin AS code, any_value(OriginCityName) AS city_name,
                   any_value(OriginState) AS state
            FROM {_rel()} GROUP BY 1
            UNION ALL
            SELECT Dest, any_value(DestCityName), any_value(DestState)
            FROM {_rel()} GROUP BY 1
        ),
        dedup AS (
            SELECT code, any_value(city_name) AS city_name, any_value(state) AS state
            FROM seen GROUP BY 1
        )
        SELECT
            d.code                                                        AS airport_code,
            coalesce(r.name, d.code || ' Airport')                        AS airport_name,
            coalesce(nullif(split_part(d.city_name, ',', 1), ''), d.code) AS city,
            coalesce(d.state, '')                                         AS state,
            r.lat  AS latitude,
            r.lon  AS longitude,
            coalesce(r.tz, -6)  AS tz_offset,
            coalesce(r.hub, 1)  AS hub_weight,
            CURRENT_TIMESTAMP AS _loaded_at, 'bts:derived' AS _source_file,
            '{batch_id}' AS _batch_id
        FROM dedup d LEFT JOIN _airport_ref r ON d.code = r.code
    """)
    n_airports = con.execute("SELECT count(*) FROM raw.airports").fetchone()[0]

    # -------- carriers: derived + enrichment ----------
    con.execute("CREATE OR REPLACE TEMP TABLE _carrier_ref (code VARCHAR, name VARCHAR, "
                "lc BOOLEAN, fleet INTEGER, founded INTEGER)")
    con.executemany(
        "INSERT INTO _carrier_ref VALUES (?,?,?,?,?)",
        [[c[0], c[1], c[2], c[3], c[4]] for c in CARRIERS],
    )
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.carriers AS
        SELECT
            s.code                                 AS carrier_code,
            coalesce(r.name, 'Carrier ' || s.code) AS carrier_name,
            coalesce(r.lc, false)                  AS is_low_cost,
            coalesce(r.fleet, 0)                   AS fleet_size,
            coalesce(r.founded, 0)                 AS founded_year,
            CURRENT_TIMESTAMP AS _loaded_at, 'bts:derived' AS _source_file,
            '{batch_id}' AS _batch_id
        FROM (SELECT DISTINCT Reporting_Airline AS code FROM {_rel()}) s
        LEFT JOIN _carrier_ref r ON s.code = r.code
    """)
    n_carriers = con.execute("SELECT count(*) FROM raw.carriers").fetchone()[0]

    # -------- weather: no BTS equivalent -> empty contract table ----------
    con.execute("""
        CREATE OR REPLACE TABLE raw.weather (
            weather_date DATE, airport_code VARCHAR, temperature_f DOUBLE,
            precipitation_in DOUBLE, wind_speed_mph DOUBLE, visibility_mi DOUBLE,
            conditions VARCHAR, is_severe INTEGER,
            _loaded_at TIMESTAMP, _source_file VARCHAR, _batch_id VARCHAR
        )
    """)

    # -------- audit rows ----------
    now = datetime.utcnow()
    for table, extracted, loaded in [
        ("raw.flights", src_rows, n_flights),
        ("raw.airports", n_airports, n_airports),
        ("raw.carriers", n_carriers, n_carriers),
        ("raw.weather", 0, 0),
    ]:
        con.execute(f"INSERT INTO {AUDIT_TABLE} VALUES (?,?,?,?,?,?,?)",
                    [batch_id, "bts_monthly_csvs", table, extracted, loaded, now,
                     "OK" if extracted == loaded else "ROW_COUNT_MISMATCH"])

    logger.info("BTS load complete: flights=%s airports=%s carriers=%s",
                f"{n_flights:,}", n_airports, n_carriers)
    return {"source_rows": src_rows, "flights": n_flights,
            "airports": n_airports, "carriers": n_carriers, "batch_id": batch_id}
