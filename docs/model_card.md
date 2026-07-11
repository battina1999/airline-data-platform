# Model Card — Flight Departure-Delay Classifier

_Last trained 2026-07-11T02:19Z · artifacts in `ml/artifacts/`_

## Intended use

Rank upcoming flights by probability of a **departure delay ≥ 15 minutes** for
**operations planning** (crew buffers, gate staffing, proactive rebooking
triage). NOT for passenger-facing promises or automated decisions about
individuals — it predicts flights, not people.

## Data & split

Trained on the dbt feature mart `fct_features_flight` built from
**3.4M real US DOT BTS flights**. Split **by date, never randomly**:

| Split | Window | Rows | Delay base rate |
|---|---|---|---|
| Train | 2024-02-01 → 2024-05-31 | ~2.28M | — |
| Validation | 2024-06 | 603,256 | 25.3% |
| Test | 2025-01 (6 months later) | 523,435 | 18.2% |

**Why a date split:** a random split places flights from the same day/route in
both train and test; with rolling-history features that leaks the target and
inflates every metric. The January test set also measures temporal
generalization across an unseen 6-month gap — the honest deployment scenario.

## Metrics (test = Jan 2025)

| Metric | Baseline (logreg, 5 feats) | LightGBM (15 trees) |
|---|---|---|
| ROC-AUC | 0.6156 | **0.6223** |
| Average precision (PR-AUC) | 0.2553 | **0.2519** |
| Brier score (calibration) | 0.1492 | **0.1461** |
| Precision @ tuned threshold | 0.2583 (t=0.2695) | 0.2533 (t=0.2444) |
| Recall @ tuned threshold | 0.4103 | 0.4533 |
| **Precision @ riskiest 10%** | 0.2966 | **0.2911** |
| Lift @ riskiest 10% | 1.63x | **1.6x** |

The operating threshold is chosen on **validation** (max-F1), never on test —
at an ~18% base rate a default 0.5 threshold produces zero positive
predictions, which is itself a classic calibration lesson. For the intended
*ranking* use-case, top-decile precision/lift is the metric that matters.
The baseline is committed and reported permanently: improvements must be
earned against it, not against nothing.

## Features (10)

Defined, tested and documented **in dbt** (`models/ml/_ml_models.yml`), shared
verbatim between training and batch scoring: schedule facts (departure hour,
day-of-week, weekend, distance + bucket, carrier type), origin-hour scheduled
congestion, and leakage-safe 30-day rolling delay rates for route and carrier
(windows end the day before the flight).

## Limitations

- **No weather features** — the single biggest missing signal; rolling rates
  absorb some of it indirectly.
- **Class imbalance** (~21% positive): threshold 0.5 favours precision over
  recall; operations should pick the threshold per use-case from the PR curve.
- **Temporal drift**: trained on Feb–Jun 2024; January (holiday tail, winter
  ops) differs — visible in the val→test metric gap. Retrain monthly.
- **`month` deliberately excluded**: the test month is outside the training
  months; a month feature would extrapolate on an unseen category.
- **New routes/carriers** fall back to zero-history rates (cold start).

## Ethics-ish note

Operational tooling for airline planning. Delay probability must not be used
to make individual passenger decisions (pricing, rebooking priority by person),
and the model has no visibility into any personal data — inputs are schedule
and aggregate history only.
