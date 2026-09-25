"""Sensor data-quality screening. A real IoT pipeline cannot trust every reading blindly."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TEMP_PLAUSIBLE = (-45.0, 60.0)


@dataclass
class QualityResult:
    clean: list[dict]  # readings used downstream (sorted, deduplicated, invalid temperatures removed)
    flags: list[str | None]  # per raw (sorted) reading: None | duplicate | impossible | outlier
    raw_sorted: list[dict]
    report: dict


def assess(readings: list[dict], product_info_complete: bool = True) -> QualityResult:
    raw = sorted(readings, key=lambda r: r["ts"])
    flags: list[str | None] = [None] * len(raw)
    if not raw:
        return QualityResult([], [], [], _report(0, 0, 0, 0, 0, 0, 0.0, 0, 0, None, product_info_complete, 0.0))

    # 1) duplicate timestamps
    seen = set()
    for i, r in enumerate(raw):
        if r["ts"] in seen:
            flags[i] = "duplicate"
        seen.add(r["ts"])

    # 2) physically impossible / missing values
    for i, r in enumerate(raw):
        t = r.get("temperature_c")
        if flags[i] is None and (t is None or not (TEMP_PLAUSIBLE[0] <= t <= TEMP_PLAUSIBLE[1])):
            flags[i] = "impossible"

    # 3) isolated spikes relative to a rolling median of neighbours
    idx = [i for i, f in enumerate(flags) if f is None]
    temps = np.array([raw[i]["temperature_c"] for i in idx], dtype=float)
    for j in range(len(idx)):
        lo, hi = max(0, j - 3), min(len(idx), j + 4)
        neigh = np.delete(temps[lo:hi], j - lo)
        if len(neigh) < 2:
            continue
        med = float(np.median(neigh))
        mad = float(np.median(np.abs(neigh - med))) or 0.1
        prev_ = temps[j - 1] if j > 0 else med
        next_ = temps[j + 1] if j + 1 < len(idx) else med
        if abs(temps[j] - med) > max(3.0, 6 * mad) and abs(prev_ - next_) < 2.0:
            flags[idx[j]] = "outlier"

    clean = [dict(raw[i]) for i, f in enumerate(flags) if f is None]
    for r in clean:
        h = r.get("humidity_pct")
        if h is not None and not (0 <= h <= 100):
            r["humidity_pct"] = None

    # 4) cadence, missing readings and disconnects
    ts = np.array([r["ts"].timestamp() for r in raw], dtype=float)
    diffs = np.diff(np.unique(ts))
    interval_s = float(np.median(diffs)) if len(diffs) else 600.0
    span_s = ts[-1] - ts[0]
    expected = int(round(span_s / interval_s)) + 1 if interval_s > 0 else len(raw)
    unique_ok = len({r["ts"] for r in clean})
    usable = len({r["ts"] for i, r in enumerate(raw) if flags[i] in (None, "outlier", "impossible")})
    missing = max(0, expected - usable)
    cts = np.array(sorted(r["ts"].timestamp() for r in clean))
    gaps = np.diff(cts) if len(cts) > 1 else np.array([])
    disconnect_mask = gaps > 3.5 * interval_s
    disconnects = int(disconnect_mask.sum())
    unverified_h = float((gaps[disconnect_mask] - interval_s).sum() / 3600) if disconnects else 0.0

    # 5) stale GPS: identical fix repeated >= 4 times while the unit reports motion
    stale = 0
    run = 1
    for a, b in zip(clean, clean[1:] + [None]):
        same = b is not None and a.get("lat") == b.get("lat") and a.get("lon") == b.get("lon") \
            and b.get("motion") in ("normal", "shock")
        if same:
            run += 1
        else:
            if run >= 4:
                stale += run
            run = 1

    battery = clean[-1].get("battery_pct") if clean else None
    n_out = flags.count("outlier")
    n_imp = flags.count("impossible")
    n_dup = flags.count("duplicate")
    report = _report(expected, missing, n_out, n_imp, n_dup, disconnects, unverified_h, stale, unique_ok,
                     battery, product_info_complete, interval_s / 60)
    return QualityResult(clean, flags, raw, report)


def _report(expected, missing, outliers, impossible, duplicates, disconnects, unverified_h, stale, valid,
            battery, product_ok, interval_min) -> dict:
    missing_pct = 100.0 * missing / expected if expected else 100.0
    stale_pct = 100.0 * stale / valid if valid else 0.0
    score = 100.0 - missing_pct - 1.5 * outliers - 2.0 * impossible - 0.5 * duplicates - 4.0 * disconnects - 0.3 * stale_pct
    if battery is not None and battery < 15:
        score -= 5
    if not product_ok:
        score -= 25
    score = float(np.clip(score, 0, 100))
    if disconnects == 0 and missing_pct < 5:
        connectivity = "Good"
    elif missing_pct < 15 and disconnects <= 2:
        connectivity = "Fair"
    else:
        connectivity = "Poor"
    issues = []
    if missing:
        issues.append(f"{missing} expected readings missing ({missing_pct:.1f}%)")
    if outliers:
        issues.append(f"{outliers} isolated spike(s) removed as outliers")
    if impossible:
        issues.append(f"{impossible} physically impossible value(s) rejected")
    if duplicates:
        issues.append(f"{duplicates} duplicate timestamp(s) dropped")
    if disconnects:
        issues.append(f"{disconnects} sensor disconnect(s), {unverified_h:.1f} h without data")
    if stale:
        issues.append(f"{stale} reading(s) with stale GPS fix while moving")
    if battery is not None and battery < 15:
        issues.append(f"Device battery low ({battery:.0f}%)")
    if not product_ok:
        issues.append("Product information incomplete")
    return {
        "score": round(score, 1),
        "connectivity": connectivity,
        "expected_readings": expected,
        "valid_readings": valid,
        "missing_readings": missing,
        "missing_pct": round(missing_pct, 1),
        "outliers": outliers,
        "impossible_values": impossible,
        "duplicates": duplicates,
        "disconnects": disconnects,
        "unverified_hours": round(unverified_h, 2),
        "stale_gps_readings": stale,
        "battery_pct": battery,
        "product_info_complete": product_ok,
        "interval_min": round(interval_min, 1),
        "issues": issues,
    }
