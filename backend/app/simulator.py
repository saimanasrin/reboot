"""IoT sensor simulator (SYNTHETIC DEMO DATA).

Generates reefer/cold-store telemetry with the variables documented by Qatar IoT providers: temperature,
humidity, GPS position, door state, motion/shock and battery. Temperature follows a mean-reverting
(Ornstein-Uhlenbeck) process around each segment's set-point, with smooth overlays for excursions and door
openings, so values drift gradually instead of jumping randomly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from .reference import LOCATIONS

SCENARIOS = {
    "A_healthy": {"label": "A - Healthy shipment", "description": "Stable temperature inside the target band, normal handling."},
    "B_excursion": {"label": "B - Temperature excursion", "description": "Temperature temporarily rises above the product's target range."},
    "C_delay": {"label": "C - Long port/warehouse delay", "description": "Temperature acceptable but dwell time becomes excessive."},
    "D_multiple": {"label": "D - Multiple disruptions", "description": "Temperature excursion + delay + repeated door openings."},
    "E_good": {"label": "E - Good shipment", "description": "Short, well-controlled journey; almost no degradation."},
}

ORIGINS = {
    # Synthetic origin points for imported goods (off the Qatar map). Named generically on purpose.
    "air": ("Origin packhouse (import, synthetic)", (27.40, 45.20)),
    "sea": ("Transshipment hub (import, synthetic)", (25.60, 54.50)),
    "road": ("Origin distribution centre (import, synthetic)", (24.20, 47.00)),
    "local": ("Local farm / processor (synthetic)", (25.55, 51.20)),
}


@dataclass
class Segment:
    stage: str  # origin | transport | port | cold_storage | distribution
    segment_type: str  # transit | handling | dwell | distribution
    label: str
    location_name: str
    start: tuple[float, float]
    end: tuple[float, float]
    hours: float
    setpoint_c: float
    humidity_pct: float


@dataclass
class Excursion:
    start_h: float
    peak_c: float
    rise_h: float = 0.6
    plateau_h: float = 1.0
    fall_h: float = 0.8
    profile: list[float] | None = None  # explicit values at the reading interval (overrides the smooth shape)
    humidity_boost: float = 12.0


@dataclass
class JourneyPlan:
    segments: list[Segment]
    excursions: list[Excursion] = field(default_factory=list)
    door_events_h: list[float] = field(default_factory=list)
    shock_events_h: list[float] = field(default_factory=list)
    door_amp_c: float = 1.2
    noise_sd: float = 0.14
    clamp_max_c: float | None = None  # optional cap outside excursions (keeps a "healthy" band realistic)

    @property
    def total_hours(self) -> float:
        return sum(s.hours for s in self.segments)


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def generate_readings(plan: JourneyPlan, start: datetime, interval_min: int, rng: np.random.Generator,
                      device_id: str, battery_start: float = 97.0) -> tuple[list[dict], list[dict]]:
    """Return (readings, journey_events) for the plan. Readings are plain dicts ready for bulk insert."""
    dt_h = interval_min / 60.0
    n = int(round(plan.total_hours / dt_h)) + 1
    t_h = np.arange(n) * dt_h

    # Segment lookup per sample
    bounds = np.cumsum([0.0] + [s.hours for s in plan.segments])
    seg_idx = np.clip(np.searchsorted(bounds, t_h, side="right") - 1, 0, len(plan.segments) - 1)
    setpoint = np.array([plan.segments[i].setpoint_c for i in seg_idx])
    hum_set = np.array([plan.segments[i].humidity_pct for i in seg_idx])

    # Ornstein-Uhlenbeck temperature around set-point
    theta, sigma = 1.4, plan.noise_sd * math.sqrt(2 * 1.4)
    temp = np.empty(n)
    temp[0] = setpoint[0] + rng.normal(0, plan.noise_sd)
    for i in range(1, n):
        temp[i] = temp[i - 1] + theta * (setpoint[i] - temp[i - 1]) * dt_h + sigma * math.sqrt(dt_h) * rng.normal()

    # Door openings: short warm bumps that decay (also bump humidity)
    door = np.zeros(n, dtype=bool)
    hum_bump = np.zeros(n)
    for td in plan.door_events_h:
        k = int(round(td / dt_h))
        if 0 <= k < n:
            door[k] = True
            decay = np.exp(-np.clip(t_h - t_h[k], 0, None) / 0.35) * (t_h >= t_h[k])
            temp += plan.door_amp_c * decay
            hum_bump += 6.0 * decay

    if plan.clamp_max_c is not None:
        temp = np.minimum(temp, plan.clamp_max_c - np.abs(rng.normal(0, 0.05, n)))

    temp = temp + rng.normal(0, 0.04, n)  # sensor noise

    # Excursions
    in_exc = np.zeros(n, dtype=bool)
    for ex in plan.excursions:
        if ex.profile is not None:
            k0 = int(round(ex.start_h / dt_h))
            for j, v in enumerate(ex.profile):
                if 0 <= k0 + j < n:
                    temp[k0 + j] = v
                    in_exc[k0 + j] = True
                    hum_bump[k0 + j] += ex.humidity_boost * max(0.0, (v - ex.profile[0])) / max(1e-6, max(ex.profile) - ex.profile[0])
        else:
            rel = t_h - ex.start_h
            up = _smoothstep(rel / ex.rise_h)
            down = 1 - _smoothstep((rel - ex.rise_h - ex.plateau_h) / ex.fall_h)
            shape = np.where(rel < 0, 0.0, np.minimum(up, down))
            temp = temp + (ex.peak_c - temp) * shape
            hum_bump += ex.humidity_boost * shape
            in_exc |= shape > 0.05

    # Humidity: slow OU + bumps
    hum = np.empty(n)
    hum[0] = hum_set[0]
    for i in range(1, n):
        hum[i] = hum[i - 1] + 0.8 * (hum_set[i] - hum[i - 1]) * dt_h + 1.2 * math.sqrt(dt_h) * rng.normal()
    hum = np.clip(hum + hum_bump, 5, 99.5)

    # GPS: linear interpolation within each segment plus small jitter while moving
    lat = np.empty(n)
    lon = np.empty(n)
    motion = np.empty(n, dtype=object)
    for i in range(n):
        s = plan.segments[seg_idx[i]]
        frac = 0.0 if s.hours <= 0 else min(1.0, (t_h[i] - bounds[seg_idx[i]]) / s.hours)
        lat[i] = s.start[0] + (s.end[0] - s.start[0]) * frac
        lon[i] = s.start[1] + (s.end[1] - s.start[1]) * frac
        moving = s.segment_type in ("transit", "distribution") and s.start != s.end
        if moving:
            lat[i] += rng.normal(0, 0.002)
            lon[i] += rng.normal(0, 0.002)
        motion[i] = "normal" if moving else "stationary"
    for ts in plan.shock_events_h:
        k = int(round(ts / dt_h))
        if 0 <= k < n:
            motion[k] = "shock"

    battery = np.clip(battery_start - t_h * rng.uniform(0.05, 0.09), 5, 100)

    readings = []
    for i in range(n):
        readings.append({
            "device_id": device_id,
            "ts": start + timedelta(hours=float(t_h[i])),
            "temperature_c": round(float(temp[i]), 2),
            "humidity_pct": round(float(hum[i]), 1),
            "lat": round(float(lat[i]), 5),
            "lon": round(float(lon[i]), 5),
            "door_open": bool(door[i]),
            "motion": str(motion[i]),
            "battery_pct": round(float(battery[i]), 1),
        })

    events = []
    for i, s in enumerate(plan.segments):
        events.append({
            "seq": i, "stage": s.stage, "segment_type": s.segment_type, "label": s.label,
            "location_name": s.location_name, "lat": s.end[0], "lon": s.end[1],
            "start_ts": start + timedelta(hours=float(bounds[i])),
            "end_ts": start + timedelta(hours=float(bounds[i + 1])),
        })
    return readings, events


def inject_data_quality_issues(readings: list[dict], rng: np.random.Generator, *, missing_frac: float = 0.02,
                               spikes: int = 0, impossible: int = 0, duplicates: int = 0,
                               disconnect_h: float = 0.0, stale_gps: int = 0, protect: set[int] | None = None) -> list[dict]:
    """Corrupt a clean series the way real gateways do. `protect` holds indices that must stay untouched."""
    protect = protect or set()
    n = len(readings)
    candidates = [i for i in range(2, n - 2) if i not in protect]
    out = [dict(r) for r in readings]
    drop: set[int] = set()

    if disconnect_h > 0 and candidates:
        interval_h = (readings[1]["ts"] - readings[0]["ts"]).total_seconds() / 3600
        span = max(1, int(disconnect_h / interval_h))
        start = int(rng.choice(candidates[: max(1, len(candidates) - span)]))
        drop.update(i for i in range(start, min(n - 1, start + span)) if i not in protect)

    k_missing = int(round(missing_frac * n)) - len(drop)
    pool = [i for i in candidates if i not in drop]
    if k_missing > 0 and pool:
        drop.update(int(i) for i in rng.choice(pool, size=min(k_missing, len(pool)), replace=False))

    pool = [i for i in candidates if i not in drop]
    for i in rng.choice(pool, size=min(spikes, len(pool)), replace=False) if spikes else []:
        out[int(i)]["temperature_c"] = round(out[int(i)]["temperature_c"] + float(rng.choice([-1, 1])) * rng.uniform(9, 16), 2)
    pool = [i for i in candidates if i not in drop]
    for i in rng.choice(pool, size=min(impossible, len(pool)), replace=False) if impossible else []:
        out[int(i)]["temperature_c"] = float(rng.choice([-99.9, 127.0]))
    if stale_gps and n > stale_gps + 4:
        s = int(rng.integers(2, n - stale_gps - 2))
        for i in range(s, s + stale_gps):
            out[i]["lat"], out[i]["lon"] = out[s - 1]["lat"], out[s - 1]["lon"]

    result = [r for i, r in enumerate(out) if i not in drop]
    if duplicates:
        for i in rng.choice(range(1, len(result) - 1), size=duplicates, replace=False):
            result.append(dict(result[int(i)]))
        result.sort(key=lambda r: r["ts"])
    return result


# ---------------------------------------------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------------------------------------------

def _loc(name: str) -> tuple[float, float]:
    return LOCATIONS[name]


def _mode_for(product: dict, rng: np.random.Generator) -> str:
    cat = product["category"]
    if cat == "frozen":
        return "sea"
    if cat == "seafood":
        return str(rng.choice(["air", "local"], p=[0.7, 0.3]))
    if cat == "dairy":
        return str(rng.choice(["road", "local"], p=[0.6, 0.4]))
    if cat == "meat":
        return str(rng.choice(["road", "local", "air"], p=[0.45, 0.35, 0.2]))
    return str(rng.choice(["air", "road", "local"], p=[0.35, 0.4, 0.25]))


def build_plan(product: dict, scenario: str, rng: np.random.Generator, mode: str | None = None,
               destination: str | None = None, stop_after_stage: str | None = None) -> tuple[JourneyPlan, str]:
    """Build a synthetic journey for a product under one of the A-E scenarios. Returns (plan, transport_mode)."""
    mode = mode or _mode_for(product, rng)
    lo, hi = product["required_min_temperature"], product["required_max_temperature"]
    band = hi - lo
    sp = product["ref_c"] - (0.15 * band if scenario == "E_good" else 0.0)
    sp_handling = sp + (0.3 if scenario == "E_good" else 0.7)
    hum = (product["humidity_min"] + product["humidity_max"]) / 2 if product["humidity_min"] else 60.0
    cold_store = str(rng.choice(["Doha Industrial Area", "Al Wakrah Logistics", "Doha (Old Airport)"]))
    destination = destination or str(rng.choice(["Doha (Al Sadd)", "Doha (West Bay)", "Lusail", "Al Rayyan",
                                                 "Umm Salal", "Al Khor", "Doha (Old Airport)"]))
    origin_name, origin = ORIGINS[mode]
    short = scenario == "E_good"

    segs: list[Segment] = []
    if mode == "air":
        entry, entry_label, entry_stage = "Hamad Intl Airport Cargo", "Air cargo handling - Hamad International Airport", "port"
        segs.append(Segment("origin", "transit", "Packhouse to origin airport, air freight", origin_name, origin, _loc(entry),
                            rng.uniform(9, 14) if short else rng.uniform(12, 22), sp, hum))
    elif mode == "sea":
        entry, entry_label, entry_stage = "Hamad Port", "Reefer container discharge - Hamad Port", "port"
        segs.append(Segment("origin", "transit", "Reefer vessel to Hamad Port", origin_name, origin, _loc(entry),
                            rng.uniform(40, 70) if short else rng.uniform(50, 110), sp, hum))
    elif mode == "road":
        entry, entry_label, entry_stage = "Abu Samra Border", "Border clearance - Abu Samra", "port"
        segs.append(Segment("origin", "transit", "Reefer truck to Abu Samra border", origin_name, origin, _loc(entry),
                            rng.uniform(8, 14) if short else rng.uniform(10, 20), sp, hum))
    else:
        entry, entry_label, entry_stage = None, None, None
        segs.append(Segment("origin", "transit", "Farm / processor to cold store", origin_name, origin, _loc(cold_store),
                            rng.uniform(1.5, 3) if short else rng.uniform(2, 5), sp, hum))

    if entry:
        segs.append(Segment(entry_stage, "handling", entry_label, entry, _loc(entry), _loc(entry),
                            rng.uniform(2, 4) if short else rng.uniform(3, 9), sp_handling, hum))
        segs.append(Segment("transport", "transit", f"Reefer transfer to {cold_store} cold store", entry, _loc(entry),
                            _loc(cold_store), rng.uniform(1, 2.5), sp, hum))

    dwell = rng.uniform(2, 6) if short else rng.uniform(4, 14)
    if scenario in ("C_delay", "D_multiple"):
        dwell = rng.uniform(26, 48) if product["category"] != "frozen" else rng.uniform(120, 240)
    if product["category"] == "frozen" and scenario not in ("C_delay", "D_multiple"):
        dwell = rng.uniform(24, 96)
    segs.append(Segment("cold_storage", "dwell", f"Cold storage - {cold_store}", cold_store, _loc(cold_store),
                        _loc(cold_store), dwell, sp + (0.2 if not short else 0.0), hum))
    if stop_after_stage != "cold_storage":
        segs.append(Segment("distribution", "distribution", f"Out for delivery to {destination}", cold_store,
                            _loc(cold_store), _loc(destination), rng.uniform(0.5, 3), sp, hum))

    plan = JourneyPlan(segments=segs, noise_sd=0.12 if short else 0.16,
                       door_amp_c=1.0 if product["storage_class"] != "frozen" else 4.0)
    total = plan.total_hours
    # Doors: loading/unloading at every handling/dwell boundary plus random extra openings
    boundaries = np.cumsum([s.hours for s in segs])[:-1]
    plan.door_events_h = sorted(float(b + rng.uniform(0.1, 0.4)) for b in boundaries)
    extra_doors = {"A_healthy": 1, "B_excursion": 1, "C_delay": 3, "D_multiple": 8, "E_good": 0}[scenario]
    plan.door_events_h += sorted(float(x) for x in rng.uniform(0.2 * total, 0.95 * total, extra_doors))
    shocks = {"A_healthy": 1, "B_excursion": 1, "C_delay": 1, "D_multiple": 3, "E_good": 0}[scenario]
    plan.shock_events_h = sorted(float(x) for x in rng.uniform(0.05 * total, 0.6 * total, shocks))
    if scenario in ("A_healthy", "E_good", "C_delay"):
        plan.clamp_max_c = hi - 0.15

    if scenario in ("B_excursion", "D_multiple"):
        # Excursion during handling at the port/airport/border (or mid-journey for local)
        handling = next((i for i, s in enumerate(segs) if s.segment_type == "handling"), 0)
        seg_start = float(np.cumsum([0] + [s.hours for s in segs])[handling])
        start_h = seg_start + rng.uniform(0.3, max(0.4, segs[handling].hours * 0.5))
        if product["storage_class"] == "frozen":
            peak = rng.uniform(-15, -9)
        else:
            peak = hi + rng.uniform(2.5, 6.0) * (1.4 if scenario == "D_multiple" else 1.0)
        plan.excursions.append(Excursion(start_h=start_h, peak_c=peak, rise_h=rng.uniform(0.4, 0.9),
                                         plateau_h=rng.uniform(0.6, 2.2), fall_h=rng.uniform(0.6, 1.2)))
    return plan, mode


# ---------------------------------------------------------------------------------------------------------------
# Hero demo shipment Q4821 (fresh strawberries). Explicit, reproducible story used in the pitch.
# ---------------------------------------------------------------------------------------------------------------
Q4821_EXCURSION_PROFILE = [3.2, 3.4, 4.2, 5.8, 7.2, 8.1, 8.4, 8.6, 8.3, 8.0, 7.8, 7.4, 7.0, 6.5, 6.0, 5.6, 5.2, 4.2, 3.8]
Q4821_TRANSIT_HOURS = 25.2
Q4821_DWELL_HOURS = 18.0


def build_q4821_plan() -> JourneyPlan:
    hia = _loc("Hamad Intl Airport Cargo")
    store = _loc("Doha Industrial Area")
    origin_name, origin = ORIGINS["air"]
    segs = [
        Segment("origin", "transit", "Packhouse to origin airport (reefer truck)", origin_name, origin, (26.9, 46.4), 6.0, 3.6, 76),
        Segment("transport", "transit", "Origin air-cargo handling and flight to Doha", origin_name, (26.9, 46.4), hia, 13.2, 3.7, 74),
        Segment("port", "handling", "Air cargo handling - Hamad International Airport", "Hamad Intl Airport Cargo", hia, hia, 4.5, 3.9, 73),
        Segment("transport", "transit", "Reefer transfer to Doha Industrial Area cold store", "Hamad Intl Airport Cargo", hia, store, 1.5, 3.8, 74),
        Segment("cold_storage", "dwell", "Cold storage - Doha Industrial Area (awaiting dispatch)", "Doha Industrial Area", store, store, Q4821_DWELL_HOURS, 4.1, 75),
    ]
    plan = JourneyPlan(segments=segs, noise_sd=0.16, door_amp_c=0.7, clamp_max_c=4.85)
    # Excursion on the airport apron: starts 20h into the journey (10-minute grid)
    plan.excursions.append(Excursion(start_h=20.0, peak_c=8.6, profile=Q4821_EXCURSION_PROFILE, humidity_boost=14.0))
    plan.door_events_h = [6.1, 19.3, 23.8, 25.3, 31.0, 36.5, 40.2]
    plan.shock_events_h = [5.9, 19.4]
    return plan
