"""Deterministic explainability: every number in the explanation is traceable to readings, events or parameters."""
from __future__ import annotations

from datetime import datetime

from .reference import nearest_place

GROUPS = [
    # display group, physics factors, description
    ("temperature", "Temperature exposure", ("temperature_excursion", "cold_damage", "thermal_history")),
    ("dwell", "Warehouse dwell", ("warehouse_dwell",)),
    ("transit", "Transit duration", ("transit_duration",)),
    ("handling", "Handling (doors / shocks)", ("door_openings", "mishandling")),
    ("humidity", "Humidity variation", ("humidity",)),
]


def _level(days: float, product: dict) -> str:
    frac = days / product["declared_shelf_life_days"]
    if frac >= 0.2:
        return "HIGH"
    if frac >= 0.05:
        return "MEDIUM"
    return "LOW"


def excursion_episodes(clean: list[dict], product: dict, min_minutes: float = 10) -> list[dict]:
    """Contiguous periods outside the product's target band, with linearly-interpolated crossing times."""
    lo, hi = product["required_min_temperature"], product["required_max_temperature"]
    out: list[dict] = []
    cur: dict | None = None

    def outside(t: float) -> str | None:
        if t > hi:
            return "above"
        if lo is not None and t < lo:
            return "below"
        return None

    def cross(a: dict, b: dict, limit: float) -> datetime:
        ta, tb = a["temperature_c"], b["temperature_c"]
        f = 0.5 if tb == ta else min(1.0, max(0.0, (limit - ta) / (tb - ta)))
        return a["ts"] + (b["ts"] - a["ts"]) * f

    for prev, r in zip([None] + clean[:-1], clean):
        kind = outside(r["temperature_c"])
        if kind and cur is None:
            limit = hi if kind == "above" else lo
            start = cross(prev, r, limit) if prev else r["ts"]
            cur = {"kind": kind, "start": start, "peak": r["temperature_c"], "peak_ts": r["ts"],
                   "lat": r.get("lat"), "lon": r.get("lon")}
        elif cur is not None and kind == cur["kind"]:
            if (kind == "above" and r["temperature_c"] > cur["peak"]) or (kind == "below" and r["temperature_c"] < cur["peak"]):
                cur["peak"], cur["peak_ts"] = r["temperature_c"], r["ts"]
        elif cur is not None:
            limit = hi if cur["kind"] == "above" else lo
            cur["end"] = cross(prev, r, limit)
            out.append(cur)
            cur = None
    if cur is not None:
        cur["end"] = clean[-1]["ts"]
        out.append(cur)

    result = []
    for e in out:
        minutes = (e["end"] - e["start"]).total_seconds() / 60
        if minutes < min_minutes:
            continue
        place = nearest_place(e["lat"], e["lon"]) if e.get("lat") is not None else "unknown"
        result.append({
            "kind": e["kind"], "start": e["start"].isoformat(timespec="minutes"), "end": e["end"].isoformat(timespec="minutes"),
            "duration_h": round(minutes / 60, 2), "peak_c": round(e["peak"], 1),
            "peak_ts": e["peak_ts"].isoformat(timespec="minutes"), "location": place,
            "limit_c": hi if e["kind"] == "above" else lo,
        })
    return result


def _hm(hours: float) -> str:
    h, m = int(hours), int(round((hours - int(hours)) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h}h {m:02d}m"


def build(product: dict, feats: dict, physics_loss: dict, final_loss_days: float, episodes: list[dict],
          declared_remaining: float, estimated_remaining: float, quality: dict) -> dict:
    phys_total = sum(physics_loss.values())
    scale = final_loss_days / phys_total if phys_total > 1e-6 else 0.0

    factors = []
    for key, label, members in GROUPS:
        raw = sum(physics_loss[m] for m in members)
        days = max(0.0, raw * scale)
        factors.append({"key": key, "label": label, "days": round(days, 2), "level": _level(days, product),
                        "share_pct": round(100 * days / final_loss_days, 1) if final_loss_days > 0 else 0.0})
    # rounding reconciliation so the waterfall sums exactly
    drift = round(final_loss_days, 2) - round(sum(f["days"] for f in factors), 2)
    if factors and abs(drift) > 0:
        top = max(factors, key=lambda f: f["days"])
        top["days"] = round(top["days"] + drift, 2)
    factors_sorted = sorted(factors, key=lambda f: -f["days"])

    # Evidence strings for each factor ------------------------------------------------------------------------
    above = [e for e in episodes if e["kind"] == "above"]
    evidence = {
        "temperature": (f"{len(above)} excursion(s) above {product['required_max_temperature']:.0f} C, "
                        f"{feats['hours_above']:.2f} h total, peak {feats['max_temp']:.1f} C, "
                        f"{feats['degree_hours_above']:.1f} degree-hours above band"
                        if feats["hours_above"] > 0 else
                        f"Mean {feats['mean_temp']:.1f} C vs reference {product['ref_c']:.1f} C; no excursion above band"),
        "dwell": f"{feats['dwell_h']:.1f} h in cold storage vs {product['dwell_allowance_h']:.0f} h normal allowance",
        "transit": f"{feats['transit_h']:.1f} h in transit/handling vs {product['transit_allowance_h']:.0f} h allowance",
        "handling": f"{feats['door_openings']:.0f} door openings, {feats['shock_events']:.0f} shock event(s)",
        "humidity": (f"{feats['hours_humidity_outside']:.1f} h outside {product['humidity_min']:.0f}-{product['humidity_max']:.0f}% RH"
                     if product.get("humidity_min") is not None else "No humidity target for this product"),
    }
    for f in factors_sorted:
        f["evidence"] = evidence[f["key"]]

    # Narrative ----------------------------------------------------------------------------------------------
    drivers = [f for f in factors_sorted if f["days"] >= 0.05 * max(final_loss_days, 0.01) and f["days"] > 0.02]
    parts = []
    for f in drivers[:3]:
        if f["key"] == "temperature" and above:
            e = max(above, key=lambda x: x["duration_h"])
            parts.append(f"experienced temperatures above the target range for approximately {_hm(feats['hours_above'])} "
                         f"(peak {e['peak_c']:.1f} C near {e['location']})")
        elif f["key"] == "temperature":
            parts.append(f"was held slightly warmer than its reference temperature (mean {feats['mean_temp']:.1f} C)")
        elif f["key"] == "dwell":
            extra = max(0.0, feats["dwell_h"] - product["dwell_allowance_h"])
            parts.append(f"remained in cold storage for {feats['dwell_h']:.1f} hours ({extra:.1f} h beyond the normal allowance)")
        elif f["key"] == "transit":
            parts.append(f"spent {feats['transit_h']:.1f} hours in transit and handling")
        elif f["key"] == "handling":
            parts.append(f"had {feats['door_openings']:.0f} door openings and {feats['shock_events']:.0f} shock event(s)")
        elif f["key"] == "humidity":
            parts.append(f"spent {feats['hours_humidity_outside']:.1f} hours outside its humidity target")

    if final_loss_days < 0.1 or not parts:
        summary = ("The journey stayed close to the product's reference conditions, so the estimated usable quality "
                   "window is close to the declared remaining shelf life.")
    else:
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        summary = (f"Estimated usable shelf life decreased by {final_loss_days:.1f} days primarily because the shipment {joined}.")

    citations = [
        {"ref": "S1", "type": "sensor_readings", "text": f"{quality['valid_readings']} validated readings at "
                                                         f"{quality['interval_min']:.0f}-min interval (data quality {quality['score']:.0f}%)"},
        {"ref": "S2", "type": "journey_events", "text": f"Journey reconstruction: transit {feats['transit_h']:.1f} h, dwell {feats['dwell_h']:.1f} h"},
        {"ref": "S3", "type": "product_parameters", "text": f"Demo parameters for {product['name']}: band "
                                                            f"{product['required_min_temperature']}-{product['required_max_temperature']} C, Q10 {product['q10']}"},
    ]
    for i, e in enumerate(above[:3]):
        citations.append({"ref": f"E{i + 1}", "type": "excursion",
                          "text": f"{e['start'][11:16]}-{e['end'][11:16]} on {e['start'][:10]}: {_hm(e['duration_h'])} above "
                                  f"{e['limit_c']:.0f} C, peak {e['peak_c']} C near {e['location']}"})

    return {
        "headline": "Why did the shelf life drop?",
        "summary": summary,
        "factors": factors_sorted,
        "episodes": episodes,
        "timeline": {
            "declared_total_days": product["declared_shelf_life_days"],
            "elapsed_days": round(feats["time_since_production_h"] / 24, 2),
            "declared_remaining_days": round(declared_remaining, 2),
            "estimated_remaining_days": round(estimated_remaining, 2),
            "lost_days": round(declared_remaining - estimated_remaining, 2),
        },
        "citations": citations,
        "disclaimer": "Prototype calculation from synthetic data - not a scientific or food-safety claim.",
    }
