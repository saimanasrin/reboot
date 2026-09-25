"""Layer 2: gradient-boosting shelf-life model trained on a SYNTHETIC dataset.

There is no public labelled dataset of Qatar cold-chain journeys with measured food quality, so the prototype
trains on simulated journeys whose labels come from a "synthetic ground truth": the physics layer with lot-to-lot
variability, an ageing interaction (older product is more fragile to abuse) and noise. The model is therefore a
stand-in with the right interface: swap `train()` for a fit on real labelled quality data and nothing else changes.

Target: extra quality-life lost as a fraction of the declared shelf life (lets one model serve every product).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

from .config import MODEL_PATH
from .features import ML_FEATURES, compute_features, ml_vector
from .physics import deterioration
from .reference import DEMO_PRODUCT_PARAMETERS
from .simulator import SCENARIOS, build_plan, generate_readings

MODEL_VERSION = "qchain-gbr-synthetic-v1"
_cache: dict | None = None


def _synthetic_label(feats: dict, trace, product: dict, age_frac: float, rng: np.random.Generator) -> float:
    loss = deterioration(feats, trace, product)
    exc = loss["temperature_excursion"] * rng.lognormal(0, 0.18) * (1 + 0.8 * age_frac)
    dwell = loss["warehouse_dwell"] * rng.lognormal(0, 0.2)
    transit = loss["transit_duration"] * rng.lognormal(0, 0.2)
    hum_interaction = 0.12 * exc if feats["hours_humidity_outside"] > 0.5 else 0.0
    rest = sum(v for k, v in loss.items() if k not in ("temperature_excursion", "warehouse_dwell", "transit_duration"))
    total = exc + dwell + transit + hum_interaction + rest * rng.lognormal(0, 0.15)
    total += rng.normal(0, 0.015 * product["declared_shelf_life_days"])
    return max(0.0, total) / product["declared_shelf_life_days"]


def build_dataset(n: int = 2500, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X, y = [], []
    scen = list(SCENARIOS)
    weights = np.array([0.25, 0.25, 0.2, 0.15, 0.15])
    start = datetime(2026, 1, 1)
    for _ in range(n):
        product = DEMO_PRODUCT_PARAMETERS[int(rng.integers(len(DEMO_PRODUCT_PARAMETERS)))]
        scenario = str(rng.choice(scen, p=weights))
        plan, _ = build_plan(product, scenario, rng, stop_after_stage=str(rng.choice(["cold_storage", "none"])))
        readings, events = generate_readings(plan, start, 15, rng, "TRAIN")
        pre_h = rng.uniform(0, 24) if product["category"] != "frozen" else rng.uniform(15, 120) * 24
        production = start - timedelta(hours=pre_h)
        as_of = readings[-1]["ts"]
        feats, trace = compute_features(readings, events, product, production, as_of)
        age_frac = min(1.0, feats["time_since_production_h"] / 24 / product["declared_shelf_life_days"])
        X.append(ml_vector(feats, product))
        y.append(_synthetic_label(feats, trace, product, age_frac, rng))
    return np.array(X), np.array(y)


def train(n: int = 2500, verbose: bool = True) -> dict:
    t0 = time.time()
    X, y = build_dataset(n)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
    common = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.85, random_state=0)
    point = GradientBoostingRegressor(loss="squared_error", **common).fit(Xtr, ytr)
    q_lo = GradientBoostingRegressor(loss="quantile", alpha=0.1, **common).fit(Xtr, ytr)
    q_hi = GradientBoostingRegressor(loss="quantile", alpha=0.9, **common).fit(Xtr, ytr)
    pred = point.predict(Xte)
    mae = float(np.mean(np.abs(pred - yte)))
    r2 = float(1 - np.sum((pred - yte) ** 2) / np.sum((yte - yte.mean()) ** 2))
    bundle = {
        "version": MODEL_VERSION,
        "point": point, "q_lo": q_lo, "q_hi": q_hi,
        "features": ML_FEATURES,
        "metrics": {"samples": int(n), "holdout_mae_fraction": round(mae, 4), "holdout_r2": round(r2, 3),
                    "note": "Metrics are on SYNTHETIC holdout data only; they say nothing about real-world accuracy."},
        "importances": dict(sorted(zip(ML_FEATURES, point.feature_importances_.round(4).tolist()),
                                   key=lambda kv: -kv[1])),
        "trained_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    global _cache
    _cache = bundle
    if verbose:
        print(f"  trained {MODEL_VERSION} on {n} synthetic journeys in {time.time() - t0:.1f}s "
              f"(holdout MAE {mae:.4f} of declared life, R2 {r2:.3f})")
    return bundle


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else train()
    return _cache


def predict(feats: dict, product: dict) -> dict:
    """Return extra loss in days with an 80% interval."""
    b = load()
    x = np.array([ml_vector(feats, product)])
    life = product["declared_shelf_life_days"]
    point = max(0.0, float(b["point"].predict(x)[0])) * life
    lo = max(0.0, float(b["q_lo"].predict(x)[0])) * life
    hi = max(0.0, float(b["q_hi"].predict(x)[0])) * life
    lo, hi = min(lo, point), max(hi, point)
    return {"loss_days": point, "loss_lo_days": lo, "loss_hi_days": hi, "version": b["version"]}


def model_card() -> dict:
    b = load()
    return {"version": b["version"], "type": "GradientBoostingRegressor (scikit-learn) + 10/90% quantile models",
            "features": b["features"], "metrics": b["metrics"], "importances": b["importances"],
            "trained_at": b["trained_at"],
            "training_data": "Synthetic journeys from the Q-Chain sensor simulator; labels from a synthetic ground truth.",
            "status": "Prototype - not validated against measured food-quality data."}
