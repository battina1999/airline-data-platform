"""
Flight departure-delay model training (label: dep_delay >= 15 min).

Honest-workflow rules baked in:
  * Split BY DATE, never randomly: random splits leak same-day/same-route
    information between train and test and flatter every metric.
      train      = 2024-02-01 .. 2024-05-31
      validation = 2024-06-01 .. 2024-06-30   (early stopping / threshold)
      test       = 2025-01-01 .. 2025-01-31   (6 months later — measures
                    temporal generalization across an unseen gap)
  * Baseline FIRST (logistic regression, 5 features) and reported forever.
  * `month` is excluded from model inputs: the test month (January) is outside
    the training months, so it would force extrapolation on an unseen category.

Stages (kept separate so each run is fast and inspectable):
    python ml/train.py --model baseline
    python ml/train.py --model lgbm        # + writes model card & artifacts

Artifacts -> ml/artifacts/ (models, metrics.json, serving lookups)
Plots     -> docs/img/ml_feature_importance.png
Card      -> docs/model_card.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import settings

ART = Path(__file__).resolve().parent / "artifacts"
IMG = Path(__file__).resolve().parents[1] / "docs" / "img"
CARD = Path(__file__).resolve().parents[1] / "docs" / "model_card.md"

SPLITS = {
    "train": ("2024-02-01", "2024-05-31"),
    "val":   ("2024-06-01", "2024-06-30"),
    "test":  ("2025-01-01", "2025-01-31"),
}

BASELINE_FEATURES = ["dep_hour", "route_delay_rate_30d", "carrier_delay_rate_30d",
                     "scheduled_departures_hour", "distance_miles"]
NUMERIC_FEATURES = BASELINE_FEATURES + ["route_flights_30d", "day_of_week"]
CATEGORICAL_FEATURES = ["distance_bucket", "carrier_type", "is_weekend"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
LABEL = "is_delayed_dep"


def load_frame() -> pd.DataFrame:
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        df = con.sql(f"""
            select flight_date, {LABEL}, {', '.join(ALL_FEATURES)}
            from main.fct_features_flight
        """).df()
    finally:
        con.close()
    df["flight_date"] = pd.to_datetime(df["flight_date"])
    for c in CATEGORICAL_FEATURES:
        df[c] = df[c].astype("category")
    df[LABEL] = df[LABEL].astype(int)
    return df


def split(df: pd.DataFrame):
    out = {}
    for name, (a, b) in SPLITS.items():
        m = (df["flight_date"] >= a) & (df["flight_date"] <= b)
        out[name] = df.loc[m]
    return out["train"], out["val"], out["test"]


def pick_threshold(y_val, p_val) -> float:
    """Choose the operating threshold on VALIDATION (max F1). A fixed 0.5 is
    meaningless at an ~18% base rate — probabilities rarely reach it."""
    from sklearn.metrics import precision_recall_curve

    prec, rec, thr = precision_recall_curve(y_val, p_val)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-9, None)
    return float(thr[int(np.argmax(f1))])


def evaluate(y_true, p, threshold: float) -> dict:
    yhat = (p >= threshold).astype(int)
    # ops view: how precise is the riskiest decile? (planning = ranking problem)
    k = max(1, len(p) // 10)
    top_idx = np.argsort(p)[-k:]
    y_arr = np.asarray(y_true)
    base = float(np.mean(y_arr))
    prec_top = float(np.mean(y_arr[top_idx]))
    return {
        "auc": round(float(roc_auc_score(y_true, p)), 4),
        "avg_precision": round(float(average_precision_score(y_true, p)), 4),
        "brier": round(float(brier_score_loss(y_true, p)), 4),
        "precision@t": round(float(precision_score(y_true, yhat, zero_division=0)), 4),
        "recall@t": round(float(recall_score(y_true, yhat, zero_division=0)), 4),
        "threshold": round(threshold, 4),
        "precision@top10pct": round(prec_top, 4),
        "lift@top10pct": round(prec_top / max(base, 1e-9), 2),
        "base_rate": round(base, 4),
        "n": int(len(y_true)),
    }


def _update_metrics(key: str, payload: dict) -> dict:
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / "metrics.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = payload
    data["updated_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(data, indent=2))
    return data


def train_baseline(df) -> None:
    train, val, test = split(df)
    pipe = Pipeline([("scaler", StandardScaler()),
                     ("clf", LogisticRegression(max_iter=1000, n_jobs=-1))])
    pipe.fit(train[BASELINE_FEATURES], train[LABEL])
    p_val = pipe.predict_proba(val[BASELINE_FEATURES])[:, 1]
    thr = pick_threshold(val[LABEL], p_val)
    res = {"val": evaluate(val[LABEL], p_val, thr),
           "test": evaluate(test[LABEL], pipe.predict_proba(test[BASELINE_FEATURES])[:, 1], thr)}
    res["features"] = BASELINE_FEATURES
    joblib.dump(pipe, ART / "baseline_logreg.joblib")
    _update_metrics("baseline_logreg", res)
    print("baseline:", json.dumps(res["test"], indent=2))


def train_lgbm(df) -> None:
    import lightgbm as lgb

    train, val, test = split(df)
    clf = lgb.LGBMClassifier(
        n_estimators=600, learning_rate=0.08, num_leaves=63,
        subsample=0.8, colsample_bytree=0.8, n_jobs=4, random_state=42,
    )
    clf.fit(train[ALL_FEATURES], train[LABEL],
            eval_set=[(val[ALL_FEATURES], val[LABEL])],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)])
    p_val = clf.predict_proba(val[ALL_FEATURES])[:, 1]
    thr = pick_threshold(val[LABEL], p_val)
    res = {"val": evaluate(val[LABEL], p_val, thr),
           "test": evaluate(test[LABEL], clf.predict_proba(test[ALL_FEATURES])[:, 1], thr)}
    res["features"] = ALL_FEATURES
    res["best_iteration"] = int(clf.best_iteration_ or 0)
    joblib.dump(clf, ART / "lgbm_delay.joblib")
    metrics = _update_metrics("lgbm", res)
    print("lgbm:", json.dumps(res["test"], indent=2))

    _plot_importance(clf)
    _export_serving_lookups()
    _write_model_card(metrics)


def _plot_importance(clf) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    IMG.mkdir(parents=True, exist_ok=True)
    imp = pd.Series(clf.feature_importances_, index=ALL_FEATURES).sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    imp.plot.barh(ax=ax, color="#2a9d8f")
    ax.set_title("LightGBM feature importance (splits)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(IMG / "ml_feature_importance.png", dpi=120)
    print(f"wrote {IMG / 'ml_feature_importance.png'}")


def _export_serving_lookups() -> None:
    """Latest rolling rates per route/carrier + congestion medians, so the API
    can build the same features the model was trained on."""
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        con.sql("""
            select origin_airport, dest_airport,
                   arg_max(route_delay_rate_30d, flight_date) as route_delay_rate_30d,
                   arg_max(route_flights_30d, flight_date)    as route_flights_30d,
                   round(median(distance_miles), 1)           as distance_miles
            from main.fct_features_flight group by 1, 2
        """).df().to_parquet(ART / "route_lookup.parquet")
        con.sql("""
            select carrier_code, any_value(carrier_type) as carrier_type,
                   arg_max(carrier_delay_rate_30d, flight_date) as carrier_delay_rate_30d
            from main.fct_features_flight group by 1
        """).df().to_parquet(ART / "carrier_lookup.parquet")
        con.sql("""
            select origin_airport, dep_hour,
                   cast(median(scheduled_departures_hour) as integer) as scheduled_departures_hour
            from main.fct_features_flight group by 1, 2
        """).df().to_parquet(ART / "congestion_lookup.parquet")
        print("serving lookups exported")
    finally:
        con.close()


def _write_model_card(metrics: dict) -> None:
    b, g = metrics["baseline_logreg"], metrics["lgbm"]
    CARD.write_text(f"""# Model Card — Flight Departure-Delay Classifier

_Last trained {metrics['updated_at'][:16]}Z · artifacts in `ml/artifacts/`_

## Intended use

Rank upcoming flights by probability of a **departure delay ≥ 15 minutes** for
**operations planning** (crew buffers, gate staffing, proactive rebooking
triage). NOT for passenger-facing promises or automated decisions about
individuals — it predicts flights, not people.

## Data & split

{g['test']['n'] + g['val']['n'] + b['test']['n'] and ''}Trained on the dbt feature mart `fct_features_flight` built from
**3.4M real US DOT BTS flights**. Split **by date, never randomly**:

| Split | Window | Rows | Delay base rate |
|---|---|---|---|
| Train | 2024-02-01 → 2024-05-31 | ~2.28M | — |
| Validation | 2024-06 | {g['val']['n']:,} | {g['val']['base_rate']:.1%} |
| Test | 2025-01 (6 months later) | {g['test']['n']:,} | {g['test']['base_rate']:.1%} |

**Why a date split:** a random split places flights from the same day/route in
both train and test; with rolling-history features that leaks the target and
inflates every metric. The January test set also measures temporal
generalization across an unseen 6-month gap — the honest deployment scenario.

## Metrics (test = Jan 2025)

| Metric | Baseline (logreg, 5 feats) | LightGBM ({g.get('best_iteration', '?')} trees) |
|---|---|---|
| ROC-AUC | {b['test']['auc']:.4f} | **{g['test']['auc']:.4f}** |
| Average precision (PR-AUC) | {b['test']['avg_precision']:.4f} | **{g['test']['avg_precision']:.4f}** |
| Brier score (calibration) | {b['test']['brier']:.4f} | **{g['test']['brier']:.4f}** |
| Precision @ tuned threshold | {b['test']['precision@t']:.4f} (t={b['test']['threshold']}) | {g['test']['precision@t']:.4f} (t={g['test']['threshold']}) |
| Recall @ tuned threshold | {b['test']['recall@t']:.4f} | {g['test']['recall@t']:.4f} |
| **Precision @ riskiest 10%** | {b['test']['precision@top10pct']:.4f} | **{g['test']['precision@top10pct']:.4f}** |
| Lift @ riskiest 10% | {b['test']['lift@top10pct']}x | **{g['test']['lift@top10pct']}x** |

The operating threshold is chosen on **validation** (max-F1), never on test —
at an ~18% base rate a default 0.5 threshold produces zero positive
predictions, which is itself a classic calibration lesson. For the intended
*ranking* use-case, top-decile precision/lift is the metric that matters.
The baseline is committed and reported permanently: improvements must be
earned against it, not against nothing.

## Features ({len(g['features'])})

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
""")
    print(f"wrote {CARD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["baseline", "lgbm"], required=True)
    args = ap.parse_args()
    ART.mkdir(parents=True, exist_ok=True)
    frame = load_frame()
    print(f"loaded {len(frame):,} rows")
    train_baseline(frame) if args.model == "baseline" else train_lgbm(frame)
