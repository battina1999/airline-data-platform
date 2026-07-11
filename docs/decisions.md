# Decision Records

Short "why we chose X" records — the reasoning interviewers ask about.

**1. DuckDB default, Snowflake by profile switch.** Reviewers must be able to
clone and run in minutes; requiring a cloud account kills that. All transform
logic lives in dbt, so the warehouse is a config concern: the identical models
run on Snowflake by switching one profile. The one dialect difference
(title-casing) is isolated in a dispatched macro.

**2. Airports/carriers derived from the data, enriched from a reference.** The
synthetic-era curated 40-airport whitelist would have silently dropped most of
the 345 real airports (and their flights). Deriving dimensions from the data
keeps every real flight; the reference only adds coordinates/names where known.

**3. Single-scan materialization for BTS ingestion.** The naive adapter
re-parsed 1.5 GB of CSV five times (count, flights, airports ×2, carriers).
Materializing the needed 23 columns into a temp table once cut ingestion to
~25s for 3.45M rows.

**4. `delete+insert` incremental strategy with a 3-day lookback.** Late and
corrected BTS records arrive within days. Keyed delete+insert makes
reprocessing a window idempotent — replaying never duplicates rows — and the
strategy compiles natively on both DuckDB and Snowflake.

**5. Full-refresh on source switch (the source guard).** CI caught incremental
facts appending synthetic rows onto BTS dimensions (orphaned keys). The
orchestrator now stamps the active DATA_SOURCE in the warehouse and forces
`--full-refresh` when it changes — mixing sources is structurally impossible.

**6. Great Expectations in monitor mode, reconciliation as the hard gate.**
Real raw data is legitimately dirty (duplicates, NULL-on-cancelled); failing
ingestion on known-dirty input would be wrong. GE *reports* raw defects;
staging cleans them; reconciliation *fails the build* only on unexplained row
loss — every removed row must be attributable.

**7. Date-based ML split, never random.** With rolling-history features, a
random split leaks same-day/same-route signal into test and flatters every
metric. Train = Feb–May 2024, val = Jun 2024, test = Jan 2025: the 6-month gap
measures the honest deployment scenario (temporal generalization).

**8. Features in dbt, not pandas.** Feature definitions are versioned, tested
(`not_null`, ranges, accepted values) and documented in YAML, and the SAME
tables feed training and batch scoring — training/serving skew is designed out.

**9. Threshold tuned on validation; top-decile precision as the ops metric.**
At an ~18% base rate a fixed 0.5 threshold predicts zero positives. The
operating point is chosen on validation (max-F1) and the ranking use-case is
reported as precision/lift in the riskiest decile (1.6×).

**10. Staging materialized as tables.** `stg_flights` de-duplicates with a
window function over 3.4M rows; as a view it recomputed per downstream model.
As tables, the full dbt build is 45/45 green in ~11s.
