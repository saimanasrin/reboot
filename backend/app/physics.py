"""Layer 1: rule/physics-inspired deterioration model (PROTOTYPE - not scientifically validated).

The declared shelf life is assumed to hold when the product is kept at its reference temperature. Every
departure from that assumption consumes extra quality life, attributed to a named factor so it can be explained:

* thermal acceleration  Q10 rate law: rate = q10 ** ((T - ref) / 10). Time at rate r consumes r hours of life.
* excursion abuse       extra loss per degree-hour above the band (condensation, microbial jump-start).
* chilling / freezing   extra loss per degree-hour below the band.
* dwell / transit       handling beyond the product's normal allowance.
* door / shock / humidity events.
"""
from __future__ import annotations

import numpy as np

from .features import Trace

FACTOR_LABELS = {
    "temperature_excursion": "Temperature excursion",
    "thermal_history": "In-range temperature history",
    "cold_damage": "Below-range exposure",
    "warehouse_dwell": "Warehouse dwell time",
    "transit_duration": "Transit duration",
    "door_openings": "Door openings",
    "mishandling": "Shock / mishandling",
    "humidity": "Humidity exposure",
}


def deterioration(feats: dict, trace: Trace, product: dict) -> dict:
    """Return per-factor extra life loss in days (>= 0 except in-range history, which can be slightly negative)."""
    p = product
    hi, lo, ref, q10 = p["required_max_temperature"], p["required_min_temperature"], p["ref_c"], p["q10"]
    loss: dict[str, float] = {k: 0.0 for k in FACTOR_LABELS}

    if trace.dt_h.size:
        rate = np.power(q10, (trace.temp - ref) / 10.0)
        extra_h = (rate - 1.0) * trace.dt_h
        above = trace.temp > hi
        loss["temperature_excursion"] += float(extra_h[above].sum()) / 24.0
        loss["thermal_history"] = float(extra_h[~above].sum()) / 24.0

    loss["temperature_excursion"] += feats["degree_hours_above"] * p["excursion_days_per_ch"]
    loss["cold_damage"] = feats["degree_hours_below"] * p["below_days_per_ch"]
    # Dwell penalty tapers after 24 h of excess (handling stress front-loads; plain aging is already in the declared life)
    excess = max(0.0, feats["dwell_h"] - p["dwell_allowance_h"])
    loss["warehouse_dwell"] = (min(excess, 24.0) + 0.3 * max(0.0, excess - 24.0)) * p["dwell_days_per_h"]
    loss["transit_duration"] = max(0.0, feats["transit_h"] - p["transit_allowance_h"]) * p["transit_days_per_h"]
    loss["door_openings"] = feats["door_openings"] * p["door_days_per_event"]
    loss["mishandling"] = feats["shock_events"] * p["shock_days_per_event"]
    loss["humidity"] = feats["hours_humidity_outside"] * p["humidity_days_per_h"]
    return loss


def deterioration_score(loss: dict, product: dict) -> float:
    """0-100 exposure score: share of the declared life consumed by abnormal conditions (scaled, capped)."""
    total = sum(max(0.0, v) for v in loss.values())
    return float(np.clip(100.0 * total / product["declared_shelf_life_days"] * 1.6, 0, 100))
