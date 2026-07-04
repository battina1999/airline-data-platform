"""
Synthetic airline operations data generator.

Produces four raw source files under data/raw/ that imitate what you would
land from operational systems + a weather API:

    airports.csv   dimension-style master data
    carriers.csv   dimension-style master data
    weather.csv    daily weather per airport
    flights.csv    the operational fact feed (delays, cancellations, causes)

Design goals
------------
* Reproducible  - everything is driven by a single seed.
* Realistic     - real IATA codes, haversine distances, weather-correlated
                  delays, BTS-style cancellation reason codes, delay-cause
                  breakdown only populated for arrivals >= 15 min late.
* Deliberately messy - a small, controlled number of rows contain nulls,
                  duplicates, sentinel values, casing/whitespace noise and
                  orphan airport codes so that the downstream Great
                  Expectations + dbt tests + reconciliation have something
                  real to detect and clean.  Rates live in `DQ_ISSUE_RATES`.

Swap-in for real data: replace this generator with the US DOT Bureau of
Transportation Statistics "On-Time Performance" extract and the OpenFlights
airports database - the schemas were modelled to line up with them.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from config import settings
from data.reference import AIRPORTS, CARRIERS, CANCELLATION_CODES, WEATHER_CONDITIONS

# fraction of rows that receive each intentional data-quality defect
DQ_ISSUE_RATES = {
    "null_tail_number": 0.006,
    "duplicate_flight": 0.003,
    "sentinel_delay": 0.002,     # -9999 sentinel instead of a real value
    "orphan_airport": 0.0015,    # dest code not present in airports.csv
    "null_weather_precip": 0.02,
}


def _haversine(lat1, lon1, lat2, lon2):
    r = 3958.8  # miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


def _date_range(start: date, end: date):
    days = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(days)]


def build_airports() -> pd.DataFrame:
    df = pd.DataFrame(
        AIRPORTS,
        columns=["airport_code", "airport_name", "city", "state",
                 "latitude", "longitude", "tz_offset", "hub_weight"],
    )
    # inject a little raw noise: inconsistent casing + trailing whitespace
    df.loc[df.index % 11 == 0, "city"] = df.loc[df.index % 11 == 0, "city"].str.upper()
    df.loc[df.index % 7 == 0, "airport_name"] = df.loc[df.index % 7 == 0, "airport_name"] + "  "
    return df


def build_carriers() -> pd.DataFrame:
    return pd.DataFrame(
        CARRIERS,
        columns=["carrier_code", "carrier_name", "is_low_cost", "fleet_size", "founded_year"],
    )


def build_weather(rng: np.random.Generator, dates) -> pd.DataFrame:
    rows = []
    for a in AIRPORTS:
        code, _, _, _, lat, _lon, _tz, _hw = a
        # colder / snowier the further north
        base_temp = 78 - (lat - 25) * 1.6
        for d in dates:
            seasonal = 8 * math.sin((d.timetuple().tm_yday / 365) * 2 * math.pi)
            temp = round(float(rng.normal(base_temp + seasonal, 9)), 1)
            precip = max(0.0, round(float(rng.exponential(0.08)), 2))
            wind = round(abs(float(rng.normal(9, 5))), 1)
            snow = temp < 34 and precip > 0.05
            if snow:
                cond = "Snow"
            elif precip > 0.30:
                cond = "Thunderstorm" if temp > 55 else "Rain"
            elif precip > 0.05:
                cond = "Rain"
            elif wind > 18:
                cond = "Cloudy"
            else:
                cond = rng.choice(["Clear", "Cloudy", "Fog"], p=[0.68, 0.24, 0.08])
            visibility = 10.0 if cond in ("Clear", "Cloudy") else round(float(rng.uniform(0.5, 8)), 1)
            severe = cond in ("Snow", "Thunderstorm") or wind > 28 or visibility < 1.5
            rows.append((d.isoformat(), code, temp, precip, wind, visibility, cond, int(severe)))
    df = pd.DataFrame(
        rows,
        columns=["weather_date", "airport_code", "temperature_f", "precipitation_in",
                 "wind_speed_mph", "visibility_mi", "conditions", "is_severe"],
    )
    # null out a small % of precipitation to mimic a flaky weather feed
    mask = rng.random(len(df)) < DQ_ISSUE_RATES["null_weather_precip"]
    df.loc[mask, "precipitation_in"] = np.nan
    return df


def build_flights(rng: np.random.Generator, dates, weather: pd.DataFrame) -> pd.DataFrame:
    n = settings.n_flights
    codes = [a[0] for a in AIRPORTS]
    coords = {a[0]: (a[4], a[5]) for a in AIRPORTS}
    hub_w = np.array([a[7] for a in AIRPORTS], dtype=float)
    hub_p = hub_w / hub_w.sum()

    carrier_codes = [c[0] for c in CARRIERS]
    carrier_w = np.array([c[3] for c in CARRIERS], dtype=float)
    carrier_p = carrier_w / carrier_w.sum()

    origin_idx = rng.choice(len(codes), size=n, p=hub_p)
    dest_idx = rng.choice(len(codes), size=n, p=hub_p)
    # no origin == dest
    clash = origin_idx == dest_idx
    while clash.any():
        dest_idx[clash] = rng.choice(len(codes), size=clash.sum(), p=hub_p)
        clash = origin_idx == dest_idx

    origin = np.array(codes)[origin_idx]
    dest = np.array(codes)[dest_idx]
    carrier = rng.choice(carrier_codes, size=n, p=carrier_p)
    flight_dates = np.array([dates[i].isoformat() for i in rng.integers(0, len(dates), n)])

    distance = np.array([_haversine(*coords[o], *coords[d]) for o, d in zip(origin, dest)])
    air_time = (distance / 8.0 + 28).round()  # ~480mph + taxi buffer, minutes

    # scheduled departure minute-of-day, peaked morning + evening
    dep_min = rng.choice(
        np.arange(5 * 60, 23 * 60),
        size=n,
        p=_dep_time_weights(),
    )

    # --- weather-driven delay signal at the origin on the day ---
    wx = weather[["weather_date", "airport_code", "is_severe", "precipitation_in"]].copy()
    wx = wx.rename(columns={"weather_date": "flight_date", "airport_code": "origin"})
    fl = pd.DataFrame({"flight_date": flight_dates, "origin": origin})
    fl = fl.merge(wx, on=["flight_date", "origin"], how="left")
    severe = fl["is_severe"].fillna(0).to_numpy()
    precip = fl["precipitation_in"].fillna(0).to_numpy()

    base_delay = rng.exponential(11, n) - 6                      # many on-time / early
    weather_delay_signal = severe * rng.exponential(45, n) + precip * rng.uniform(10, 40, n)
    late_aircraft = (rng.random(n) < 0.10) * rng.exponential(30, n)
    dep_delay = np.round(base_delay + weather_delay_signal + late_aircraft).astype(int)

    # arrival delay tracks departure delay, recoverable in the air
    arr_delay = np.round(dep_delay - rng.uniform(0, 12, n) + rng.normal(0, 6, n)).astype(int)

    # --- cancellations ---
    cancel_base = 0.012 + severe * 0.09
    cancelled = rng.random(n) < cancel_base
    cancel_code = np.where(cancelled, "", "")
    cc_choices = np.array(list(CANCELLATION_CODES.keys()))
    cc_p_weather = np.array([0.15, 0.6, 0.2, 0.05])   # weather-heavy when severe
    cc_p_normal = np.array([0.55, 0.1, 0.3, 0.05])
    for i in np.where(cancelled)[0]:
        p = cc_p_weather if severe[i] else cc_p_normal
        cancel_code[i] = rng.choice(cc_choices, p=p)
    # cancelled flights have no delay/arrival numbers
    dep_delay = np.where(cancelled, 0, dep_delay)
    arr_delay = np.where(cancelled, 0, arr_delay)

    # --- delay cause breakdown (BTS convention: only when arr_delay >= 15) ---
    reportable = (~cancelled) & (arr_delay >= 15)
    total = np.where(reportable, arr_delay, 0).astype(float)
    w_share = np.clip(severe * rng.uniform(0.3, 0.8, n), 0, 1)
    weather_cause = np.round(total * w_share).astype(int)
    remaining = total - weather_cause
    carrier_cause = np.round(remaining * rng.uniform(0.2, 0.5, n)).astype(int)
    nas_cause = np.round((remaining - carrier_cause) * rng.uniform(0.4, 0.8, n)).astype(int)
    late_cause = np.clip(remaining - carrier_cause - nas_cause, 0, None).astype(int)
    security_cause = ((rng.random(n) < 0.01) * reportable * rng.integers(1, 8, n)).astype(int)

    tail = np.array([f"N{rng.integers(100, 999)}{chr(rng.integers(65,90))}{chr(rng.integers(65,90))}"
                     for _ in range(n)])

    df = pd.DataFrame({
        "flight_id": np.arange(1, n + 1),
        "flight_date": flight_dates,
        "carrier_code": carrier,
        "flight_number": rng.integers(1, 6500, n),
        "tail_number": tail,
        "origin": origin,
        "dest": dest,
        "scheduled_departure_min": dep_min,
        "distance_miles": distance,
        "scheduled_air_time_min": air_time.astype(int),
        "dep_delay_min": dep_delay,
        "arr_delay_min": arr_delay,
        "cancelled": cancelled.astype(int),
        "cancellation_code": cancel_code,
        "diverted": (rng.random(n) < 0.002).astype(int),
        "carrier_delay_min": np.where(reportable, carrier_cause, 0),
        "weather_delay_min": np.where(reportable, weather_cause, 0),
        "nas_delay_min": np.where(reportable, nas_cause, 0),
        "security_delay_min": np.where(reportable, security_cause, 0),
        "late_aircraft_delay_min": np.where(reportable, late_cause, 0),
    })
    return _inject_flight_defects(df, rng)


def _dep_time_weights():
    minutes = np.arange(5 * 60, 23 * 60)
    hours = minutes / 60.0
    morning = np.exp(-((hours - 8) ** 2) / 6)
    evening = np.exp(-((hours - 18) ** 2) / 8)
    w = 0.2 + morning + 0.8 * evening
    return w / w.sum()


def _inject_flight_defects(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    n = len(df)

    # 1) null tail numbers
    m = rng.random(n) < DQ_ISSUE_RATES["null_tail_number"]
    df.loc[m, "tail_number"] = None

    # 2) sentinel delay values (bad -9999 from a legacy source)
    m = rng.random(n) < DQ_ISSUE_RATES["sentinel_delay"]
    df.loc[m, "dep_delay_min"] = -9999

    # 3) orphan destination airport codes (not in airports.csv)
    m = rng.random(n) < DQ_ISSUE_RATES["orphan_airport"]
    df.loc[m, "dest"] = "ZZZ"

    # 4) exact duplicate rows (double-published events)
    dup = df.sample(frac=DQ_ISSUE_RATES["duplicate_flight"], random_state=1)
    out = pd.concat([df, dup], ignore_index=True)
    return out.sample(frac=1, random_state=2).reset_index(drop=True)


def main() -> None:
    settings.ensure_dirs()
    rng = np.random.default_rng(settings.seed)
    dates = _date_range(settings.start_date, settings.end_date)

    print(f"[generate] seed={settings.seed}  dates={dates[0]}..{dates[-1]}  flights={settings.n_flights:,}")

    airports = build_airports()
    carriers = build_carriers()
    weather = build_weather(rng, dates)
    flights = build_flights(rng, dates, weather)

    out = settings.data_raw_dir
    airports.to_csv(out / "airports.csv", index=False)
    carriers.to_csv(out / "carriers.csv", index=False)
    weather.to_csv(out / "weather.csv", index=False)
    flights.to_csv(out / "flights.csv", index=False)

    print(f"[generate] airports.csv  rows={len(airports):>6,}")
    print(f"[generate] carriers.csv  rows={len(carriers):>6,}")
    print(f"[generate] weather.csv   rows={len(weather):>6,}")
    print(f"[generate] flights.csv   rows={len(flights):>6,}  (incl. injected duplicates)")
    print(f"[generate] wrote to {out}")


if __name__ == "__main__":
    main()
