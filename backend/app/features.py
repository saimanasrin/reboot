"""Feature engineering: reconstruct the cold-chain journey from (cleaned) readings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

SUBSTEPS = 12  # linear sub-sampling per reading interval -> accurate threshold-crossing durations
SENSITIVITY_NUM = {"low": 0.25, "medium": 0.5, "high": 0.75, "very high": 1.0}
TRANSIT_TYPES = ("transit", "handling", "distribution")


@dataclass
class Trace:
    """Sub-sampled journey used by the physics layer for attribution."""
    temp: np.ndarray
    hum: np.ndarray
    dt_h: np.ndarray
    seg_type: np.ndarray  # transit | handling | dwell | distribution


def build_trace(clean: list[dict], events: list[dict]) -> Trace:
    if len(clean) < 2:
        empty = np.array([])
        return Trace(empty, empty, empty, np.array([], dtype=object))
    ts = np.array([r["ts"].timestamp() for r in clean], dtype=float)
    temp = np.array([r["temperature_c"] for r in clean], dtype=float)
    hum_raw = np.array([np.nan if r.get("humidity_pct") is None else r["humidity_pct"] for r in clean], dtype=float)
    if np.isnan(hum_raw).all():
        hum_raw[:] = 0.0
    else:
        ok = ~np.isnan(hum_raw)
        hum_raw = np.interp(ts, ts[ok], hum_raw[ok])

    frac = (np.arange(SUBSTEPS) + 0.5) / SUBSTEPS
    t0, t1 = ts[:-1, None], ts[1:, None]
    mid_ts = (t0 + (t1 - t0) * frac).ravel()
    t_sub = (temp[:-1, None] + (temp[1:, None] - temp[:-1, None]) * frac).ravel()
    h_sub = (hum_raw[:-1, None] + (hum_raw[1:, None] - hum_raw[:-1, None]) * frac).ravel()
    dt_sub = np.repeat(np.diff(ts) / 3600.0 / SUBSTEPS, SUBSTEPS)

    seg = np.full(mid_ts.shape, "transit", dtype=object)
    for ev in events:
        s = ev["start_ts"].timestamp()
        e = ev["end_ts"].timestamp() if ev.get("end_ts") else np.inf
        seg[(mid_ts >= s) & (mid_ts < e)] = ev["segment_type"]
    return Trace(t_sub, h_sub, dt_sub, seg)


def _episodes(mask: np.ndarray, dt: np.ndarray, min_h: float = 1 / 6) -> list[float]:
    """Durations (h) of contiguous True runs longer than min_h."""
    out, cur = [], 0.0
    for m, d in zip(mask, dt):
        if m:
            cur += d
        elif cur:
            out.append(cur)
            cur = 0.0
    if cur:
        out.append(cur)
    return [x for x in out if x >= min_h]


def compute_features(clean: list[dict], events: list[dict], product: dict, production_date: datetime,
                     as_of: datetime) -> tuple[dict, Trace]:
    tr = build_trace(clean, events)
    lo = product["required_min_temperature"]
    hi = product["required_max_temperature"]
    total_h = max(0.0, (as_of - production_date).total_seconds() / 3600)
    if tr.dt_h.size == 0:
        feats = {k: 0.0 for k in FEATURE_KEYS}
        feats.update(time_since_production_h=total_h)
        return feats, tr

    dt = tr.dt_h
    above = tr.temp > hi
    below = tr.temp < lo if lo is not None else np.zeros_like(above)
    journey_h = float(dt.sum())
    mean_t = float(np.average(tr.temp, weights=dt))
    std_t = float(np.sqrt(np.average((tr.temp - mean_t) ** 2, weights=dt)))
    exc = _episodes(above | below, dt)

    hum_out_h = 0.0
    if product.get("humidity_min") is not None:
        hum_out = (tr.hum < product["humidity_min"]) | (tr.hum > product["humidity_max"])
        hum_out_h = float(dt[hum_out].sum())

    is_transit = np.isin(tr.seg_type, TRANSIT_TYPES)
    doors = sum(1 for r in clean if r.get("door_open"))
    shocks = sum(1 for r in clean if r.get("motion") == "shock")

    feats = {
        "time_since_production_h": total_h,
        "journey_h": journey_h,
        "transit_h": float(dt[is_transit].sum()),
        "dwell_h": float(dt[tr.seg_type == "dwell"].sum()),
        "hours_in_range": float(dt[~(above | below)].sum()),
        "hours_above": float(dt[above].sum()),
        "hours_below": float(dt[below].sum()),
        "pct_outside": 100.0 * float(dt[above | below].sum()) / journey_h if journey_h else 0.0,
        "max_temp": float(tr.temp.max()),
        "min_temp": float(tr.temp.min()),
        "mean_temp": mean_t,
        "temp_std": std_t,
        "degree_hours_above": float((np.clip(tr.temp - hi, 0, None) * dt).sum()),
        "degree_hours_below": float((np.clip(lo - tr.temp, 0, None) * dt).sum()) if lo is not None else 0.0,
        "longest_excursion_h": max(exc) if exc else 0.0,
        "excursion_count": float(len(exc)),
        "humidity_mean": float(np.average(tr.hum, weights=dt)),
        "hours_humidity_outside": hum_out_h,
        "door_openings": float(doors),
        "shock_events": float(shocks),
    }
    return feats, tr


FEATURE_KEYS = [
    "time_since_production_h", "journey_h", "transit_h", "dwell_h", "hours_in_range", "hours_above", "hours_below",
    "pct_outside", "max_temp", "min_temp", "mean_temp", "temp_std", "degree_hours_above", "degree_hours_below",
    "longest_excursion_h", "excursion_count", "humidity_mean", "hours_humidity_outside", "door_openings", "shock_events",
]

# Product-relative feature vector for the ML layer (temperatures expressed relative to each product's band so
# one model can serve every product).
ML_FEATURES = [
    "time_since_production_d", "transit_h", "dwell_h", "hours_above", "hours_below", "pct_outside",
    "max_over_limit_c", "mean_over_ref_c", "temp_std", "degree_hours_above", "degree_hours_below",
    "longest_excursion_h", "hours_humidity_outside", "door_openings", "shock_events",
    "declared_shelf_life_d", "q10", "sensitivity", "excursion_days_per_ch", "dwell_days_per_h", "dwell_allowance_h",
]


def ml_vector(feats: dict, product: dict) -> list[float]:
    return [
        feats["time_since_production_h"] / 24.0,
        feats["transit_h"], feats["dwell_h"], feats["hours_above"], feats["hours_below"], feats["pct_outside"],
        feats["max_temp"] - product["required_max_temperature"],
        feats["mean_temp"] - product["ref_c"],
        feats["temp_std"], feats["degree_hours_above"], feats["degree_hours_below"],
        feats["longest_excursion_h"], feats["hours_humidity_outside"], feats["door_openings"], feats["shock_events"],
        product["declared_shelf_life_days"], product["q10"], SENSITIVITY_NUM[product["sensitivity"]],
        product["excursion_days_per_ch"], product["dwell_days_per_h"], product["dwell_allowance_h"],
    ]
