"""Demand engine (SYNTHETIC demand data).

Forecast method: seasonal-naive - mean of the same weekday over the last 4 weeks of (synthetic) history.
Expected sales of a new lot use FIFO: stock already on hand sells first, then the new lot sells until its usable
window closes. Demand uncertainty is integrated with a fixed normal quadrature, so results are deterministic.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

# Qatar retail week: Thursday/Friday peaks (demo assumption).
WEEKDAY_INDEX = [0.95, 0.93, 0.96, 1.12, 1.18, 1.0, 0.86]  # Mon..Sun
CHANNEL_PRICE_FACTOR = {
    "supermarket": 1.0, "small_retailer": 1.0, "restaurant": 0.9, "wholesaler": 0.72, "direct_consumer": 0.85,
}
# Price elasticity used for discount what-ifs (demo assumption): demand uplift per 10% discount.
UPLIFT_PER_10PCT = 0.2

_Z = np.linspace(-3, 3, 41)
_W = np.exp(-0.5 * _Z ** 2)
_W /= _W.sum()


def synth_history(daily_kg: float, cv: float, end: datetime, rng: np.random.Generator, days: int = 28) -> list[float]:
    out = []
    for d in range(days, 0, -1):
        day = end - timedelta(days=d)
        out.append(round(max(0.0, daily_kg * WEEKDAY_INDEX[day.weekday()] * rng.normal(1, cv * 0.8)), 1))
    return out


def forecast(history: list[float], start: datetime, days: int = 7, history_end: datetime | None = None) -> list[dict]:
    """Seasonal-naive forecast from 28 days of history ending the day before `start`."""
    history_end = history_end or start
    hist = np.array(history, dtype=float)
    n = len(hist)
    out = []
    for k in range(days):
        day = start + timedelta(days=k)
        same = [hist[i] for i in range(n) if (history_end - timedelta(days=n - i)).weekday() == day.weekday()]
        mu = float(np.mean(same)) if same else float(hist.mean())
        sd = float(np.std(same)) if len(same) > 1 else 0.2 * mu
        out.append({"date": day.date().isoformat(), "expected_kg": round(mu, 1), "std_kg": round(sd, 1)})
    return out


def daily_rate(customer: dict, product_id: str) -> tuple[float, float]:
    prof = customer["demand_profile"].get(product_id)
    if not prof:
        return 0.0, 0.0
    return float(prof["daily_kg"]), float(prof.get("cv", 0.2))


def expected_sell_through_days(customer: dict, product_id: str, qty_kg: float, uplift: float = 0.0) -> float:
    d, _ = daily_rate(customer, product_id)
    if d <= 0:
        return float("inf")
    inv = customer["current_inventory"].get(product_id, 0.0)
    return (inv + qty_kg) / (d * (1 + uplift))


def expected_sold(qty: float, daily_kg: float, cv: float, window_days: float, inventory_kg: float) -> float:
    """E[min(qty, max(0, D * window - inventory))] with D ~ Normal(daily, cv*daily) truncated at 0."""
    if qty <= 0 or window_days <= 0 or daily_kg <= 0:
        return 0.0
    D = np.clip(daily_kg * (1 + cv * _Z), 0, None)
    sold = np.clip(D * window_days - inventory_kg, 0, qty)
    return float((sold * _W).sum())
