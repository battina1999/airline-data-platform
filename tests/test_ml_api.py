"""API tests for the delay-risk service (skipped until models are trained)."""
from pathlib import Path

import pytest

ART = Path(__file__).resolve().parents[1] / "ml" / "artifacts"

pytestmark = pytest.mark.skipif(
    not (ART / "lgbm_delay.joblib").exists(),
    reason="model artifacts not trained — run: make train",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from ml.api import app

    return TestClient(app)


def test_health(client):
    j = client.get("/health").json()
    assert j["status"] == "ok" and j["routes_known"] > 100


def test_predict_known_route(client):
    j = client.post("/predict", json={
        "carrier_code": "AA", "origin": "ATL", "dest": "DFW",
        "flight_date": "2025-02-14", "dep_hour": 17}).json()
    assert 0.0 <= j["delay_probability"] <= 1.0
    assert j["risk_band"] in ("normal", "elevated", "high")
    assert j["features_used"]["carrier_type"]


def test_predict_unknown_route_cold_start(client):
    j = client.post("/predict", json={
        "carrier_code": "DL", "origin": "XNA", "dest": "OGG",
        "flight_date": "2025-03-01", "dep_hour": 6}).json()
    assert 0.0 <= j["delay_probability"] <= 1.0  # falls back to zero-history features


def test_unknown_carrier_422(client):
    r = client.post("/predict", json={
        "carrier_code": "ZZ", "origin": "ATL", "dest": "DFW",
        "flight_date": "2025-02-14", "dep_hour": 17})
    assert r.status_code == 422


def test_validation_bad_hour(client):
    r = client.post("/predict", json={
        "carrier_code": "AA", "origin": "ATL", "dest": "DFW",
        "flight_date": "2025-02-14", "dep_hour": 99})
    assert r.status_code == 422
