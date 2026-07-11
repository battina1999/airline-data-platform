"""
Flight delay-risk API (FastAPI).

    uvicorn ml.api:app --port 8000
    POST /predict  {"carrier_code":"AA","origin":"ATL","dest":"DFW",
                    "flight_date":"2025-02-14","dep_hour":17}

Serving features are built from the SAME dbt feature definitions via lookup
tables exported at training time (route/carrier rolling rates, congestion
medians) — no training/serving skew. Model + card: docs/model_card.md.
"""
from __future__ import annotations

from datetime import date as date_type
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ART = Path(__file__).resolve().parent / "artifacts"

app = FastAPI(
    title="Flight Delay-Risk API",
    version="1.0.0",
    description="Probability that a flight departs ≥15 min late. Trained on 3.4M "
                "real US DOT flights; features defined in dbt. See docs/model_card.md "
                "for metrics, limitations and intended use (ops planning, not "
                "passenger-facing decisions).",
)

FEATURES = ["dep_hour", "route_delay_rate_30d", "carrier_delay_rate_30d",
            "scheduled_departures_hour", "distance_miles", "route_flights_30d",
            "day_of_week", "distance_bucket", "carrier_type", "is_weekend"]


class PredictRequest(BaseModel):
    carrier_code: str = Field(..., examples=["AA"], min_length=2, max_length=3)
    origin: str = Field(..., examples=["ATL"], min_length=3, max_length=3)
    dest: str = Field(..., examples=["DFW"], min_length=3, max_length=3)
    flight_date: date_type = Field(..., examples=["2025-02-14"])
    dep_hour: int = Field(..., ge=0, le=23, examples=[17])


class PredictResponse(BaseModel):
    delay_probability: float
    risk_band: str
    threshold: float
    model: str
    features_used: dict


@lru_cache(maxsize=1)
def _bundle():
    model = joblib.load(ART / "lgbm_delay.joblib")
    routes = pd.read_parquet(ART / "route_lookup.parquet")
    carriers = pd.read_parquet(ART / "carrier_lookup.parquet")
    congestion = pd.read_parquet(ART / "congestion_lookup.parquet")
    import json

    thr = json.loads((ART / "metrics.json").read_text())["lgbm"]["val"]["threshold"]
    return model, routes, carriers, congestion, thr


def build_features(req: PredictRequest) -> dict:
    _, routes, carriers, congestion, _ = _bundle()

    r = routes[(routes.origin_airport == req.origin.upper())
               & (routes.dest_airport == req.dest.upper())]
    c = carriers[carriers.carrier_code == req.carrier_code.upper()]
    g = congestion[(congestion.origin_airport == req.origin.upper())
                   & (congestion.dep_hour == req.dep_hour)]

    if c.empty:
        raise HTTPException(422, f"unknown carrier '{req.carrier_code}'")
    distance = float(r.distance_miles.iloc[0]) if not r.empty else 800.0

    dow = (req.flight_date.weekday() + 1) % 7  # dim_date: 0=Sunday
    return {
        "dep_hour": req.dep_hour,
        "route_delay_rate_30d": float(r.route_delay_rate_30d.iloc[0]) if not r.empty else 0.0,
        "carrier_delay_rate_30d": float(c.carrier_delay_rate_30d.iloc[0]),
        "scheduled_departures_hour": int(g.scheduled_departures_hour.iloc[0]) if not g.empty else 5,
        "distance_miles": distance,
        "route_flights_30d": float(r.route_flights_30d.iloc[0]) if not r.empty else 0.0,
        "day_of_week": dow,
        "distance_bucket": ("short" if distance < 500 else "medium" if distance < 1500 else "long"),
        "carrier_type": str(c.carrier_type.iloc[0]),
        "is_weekend": dow in (0, 6),
    }


@app.get("/health")
def health() -> dict:
    model, routes, carriers, _, thr = _bundle()
    return {"status": "ok", "model": type(model).__name__,
            "routes_known": int(len(routes)), "carriers_known": int(len(carriers)),
            "operating_threshold": thr}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    model, *_ , thr = _bundle()
    feats = build_features(req)
    row = pd.DataFrame([feats])[FEATURES]
    for col in ("distance_bucket", "carrier_type", "is_weekend"):
        row[col] = row[col].astype("category")
    p = float(model.predict_proba(row)[:, 1][0])
    band = "high" if p >= thr else ("elevated" if p >= 0.7 * thr else "normal")
    return PredictResponse(delay_probability=round(p, 4), risk_band=band,
                           threshold=round(thr, 4), model="lgbm_delay",
                           features_used=feats)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return """<!doctype html><html><head><title>Flight Delay Risk</title><style>
body{font-family:'Segoe UI',sans-serif;max-width:620px;margin:40px auto;padding:0 16px;color:#0f172a}
h1{color:#1f3b5c}input,select,button{padding:9px 12px;margin:4px 0;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
button{background:#2a9d8f;color:#fff;border:0;font-weight:600;cursor:pointer}
#out{margin-top:18px;padding:14px;border-radius:10px;background:#f1f5f9;white-space:pre-wrap;font-family:monospace}
.small{color:#64748b;font-size:12.5px}</style></head><body>
<h1>✈️ Flight delay risk</h1>
<p class="small">Probability of a ≥15-min departure delay. Trained on 3.4M real US DOT flights.
Ops planning tool — see the <a href="https://github.com/battina1999/airline-data-platform/blob/main/docs/model_card.md">model card</a>. API docs at <a href="/docs">/docs</a>.</p>
<div>
Carrier <input id="carrier" value="AA" size="4"> Origin <input id="origin" value="ATL" size="4">
Dest <input id="dest" value="DFW" size="4"><br>
Date <input id="date" type="date" value="2025-02-14"> Hour <input id="hour" type="number" value="17" min="0" max="23">
<button onclick="go()">Predict</button></div><div id="out">…</div>
<script>
async function go(){
  const body={carrier_code:carrier.value,origin:origin.value,dest:dest.value,
              flight_date:date.value,dep_hour:+hour.value};
  const r=await fetch('/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  out.textContent = r.ok ? `delay probability: ${(d.delay_probability*100).toFixed(1)}%  (${d.risk_band})\\n\\n`+JSON.stringify(d.features_used,null,2) : JSON.stringify(d,null,2);
}
</script></body></html>"""
