"""
Great Expectations validation of the RAW layer.

Runs a declarative suite of expectations (null checks, uniqueness, schema /
type, accepted-value sets, range checks) against the freshly-landed raw tables
and writes a data-quality report to quality/expectations/validation_report.json.

By design this runs in *monitor* mode: it reports failures (and exits 0) so the
pipeline can continue into staging, where the issues are cleaned. Run with
`--strict` to fail the build on any critical expectation (how you would gate a
production load). This mirrors the real trade-off between observability and
hard enforcement.

    python -m quality.validate            # report + continue
    python -m quality.validate --strict   # non-zero exit on critical failure
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("TQDM_DISABLE", "1")

import great_expectations as gx  # noqa: E402

from config import settings, get_duckdb_connection  # noqa: E402
from data.reference import AIRPORTS, CANCELLATION_CODES  # noqa: E402
from ingestion.logging_config import get_logger  # noqa: E402

logger = get_logger("quality.validate")

VALID_AIRPORTS = [a[0] for a in AIRPORTS]
REPORT_PATH = settings.data_raw_dir.parent.parent / "quality" / "expectations" / "validation_report.json"

# --- declarative expectation suites (expectation, kwargs, severity) ----------
SUITES: dict[str, list[dict]] = {
    "flights": [
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "flight_id"}, "sev": "critical"},
        {"e": "expect_column_values_to_be_unique", "k": {"column": "flight_id"}, "sev": "critical"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "flight_date"}, "sev": "critical"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "carrier_code"}, "sev": "critical"},
        {"e": "expect_column_values_to_be_in_set", "k": {"column": "origin", "value_set": VALID_AIRPORTS}, "sev": "critical"},
        {"e": "expect_column_values_to_be_in_set", "k": {"column": "dest", "value_set": VALID_AIRPORTS}, "sev": "critical"},
        {"e": "expect_column_values_to_be_in_set", "k": {"column": "cancelled", "value_set": [0, 1]}, "sev": "critical"},
        {"e": "expect_column_values_to_be_in_set", "k": {"column": "cancellation_code", "value_set": list(CANCELLATION_CODES)}, "sev": "warn"},
        {"e": "expect_column_values_to_be_between", "k": {"column": "dep_delay_min", "min_value": -120, "max_value": 1800}, "sev": "critical"},
        {"e": "expect_column_values_to_be_between", "k": {"column": "arr_delay_min", "min_value": -120, "max_value": 1800}, "sev": "warn"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "tail_number", "mostly": 0.99}, "sev": "warn"},
        {"e": "expect_table_row_count_to_be_between", "k": {"min_value": 1000, "max_value": 5_000_000}, "sev": "warn"},
    ],
    "airports": [
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "airport_code"}, "sev": "critical"},
        {"e": "expect_column_values_to_be_unique", "k": {"column": "airport_code"}, "sev": "critical"},
        {"e": "expect_column_value_lengths_to_equal", "k": {"column": "airport_code", "value": 3}, "sev": "critical"},
        {"e": "expect_column_values_to_be_between", "k": {"column": "latitude", "min_value": -90, "max_value": 90}, "sev": "critical"},
        {"e": "expect_column_values_to_be_between", "k": {"column": "longitude", "min_value": -180, "max_value": 180}, "sev": "critical"},
    ],
    "carriers": [
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "carrier_code"}, "sev": "critical"},
        {"e": "expect_column_values_to_be_unique", "k": {"column": "carrier_code"}, "sev": "critical"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "carrier_name"}, "sev": "critical"},
    ],
    "weather": [
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "weather_date"}, "sev": "critical"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "airport_code"}, "sev": "critical"},
        {"e": "expect_column_values_to_not_be_null", "k": {"column": "precipitation_in", "mostly": 0.95}, "sev": "warn"},
        {"e": "expect_column_values_to_be_between", "k": {"column": "temperature_f", "min_value": -40, "max_value": 130}, "sev": "warn"},
        {"e": "expect_column_values_to_be_in_set", "k": {"column": "is_severe", "value_set": [0, 1]}, "sev": "critical"},
    ],
}


def _load_raw(table: str):
    con = get_duckdb_connection(read_only=True)
    try:
        return con.sql(f"SELECT * FROM {settings.raw_schema}.{table}").df()
    finally:
        con.close()


def _validate_table(context, source, table: str, specs: list[dict]) -> list[dict]:
    df = _load_raw(table)
    asset = source.add_dataframe_asset(name=table)
    batch_request = asset.build_batch_request(dataframe=df)
    validator = context.get_validator(batch_request=batch_request)

    results = []
    for spec in specs:
        method = getattr(validator, spec["e"])
        with contextlib.redirect_stderr(open(os.devnull, "w")):
            res = method(**spec["k"])
        results.append({
            "table": table,
            "expectation": spec["e"],
            "column": spec["k"].get("column", "(table)"),
            "severity": spec["sev"],
            "success": bool(res.success),
            "unexpected_count": (res.result or {}).get("unexpected_count"),
            "element_count": (res.result or {}).get("element_count"),
        })
    return results


def run(strict: bool = False) -> int:
    logger.info("=== Great Expectations validation of raw layer ===")
    context = gx.get_context(mode="ephemeral")
    source = context.sources.add_pandas("raw_pandas")

    all_results: list[dict] = []
    for table, specs in SUITES.items():
        all_results.extend(_validate_table(context, source, table, specs))

    passed = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]
    critical_failed = [r for r in failed if r["severity"] == "critical"]

    logger.info("expectations: %d total | %d passed | %d failed (%d critical)",
                len(all_results), len(passed), len(failed), len(critical_failed))
    for r in failed:
        logger.warning("  FAIL [%s] %-14s %-40s unexpected=%s",
                       r["severity"], r["table"], f"{r['expectation']}({r['column']})",
                       r["unexpected_count"])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "summary": {
            "total": len(all_results), "passed": len(passed),
            "failed": len(failed), "critical_failed": len(critical_failed),
        },
        "results": all_results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    logger.info("report written -> %s", REPORT_PATH)

    logger.info("NOTE: failures above are the intentional raw-layer defects "
                "(duplicates, sentinel -9999, orphan 'ZZZ', missing tails) that "
                "the dbt staging models clean downstream.")

    if strict and critical_failed:
        logger.error("strict mode: %d critical expectations failed -> failing build",
                     len(critical_failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(strict="--strict" in sys.argv))
