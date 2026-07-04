"""Fast unit tests for reference data + generator helpers (no warehouse needed)."""
from data.reference import AIRPORTS, CARRIERS
from data.generate_data import _haversine, _dep_time_weights, DQ_ISSUE_RATES


def test_airport_codes_unique_and_three_letters():
    codes = [a[0] for a in AIRPORTS]
    assert len(codes) == len(set(codes))
    assert all(len(c) == 3 for c in codes)


def test_carrier_codes_unique():
    codes = [c[0] for c in CARRIERS]
    assert len(codes) == len(set(codes))


def test_haversine_atl_to_lax_is_realistic():
    atl = next(a for a in AIRPORTS if a[0] == "ATL")
    lax = next(a for a in AIRPORTS if a[0] == "LAX")
    dist = _haversine(atl[4], atl[5], lax[4], lax[5])
    assert 1900 < dist < 2000  # true distance is ~1946 miles


def test_departure_time_weights_form_distribution():
    w = _dep_time_weights()
    assert abs(w.sum() - 1.0) < 1e-6
    assert (w >= 0).all()


def test_dq_issue_rates_are_small_positive():
    assert all(0 < v < 0.1 for v in DQ_ISSUE_RATES.values())
