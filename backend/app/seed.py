"""Build the SYNTHETIC demo database: products, rules, customers, rescue partners, 1,284 shipments with sensor
histories, predictions and recommendations. Run:  python -m app.seed  [--fleet N] [--retrain]
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import insert
from sqlalchemy.orm import Session

from . import ml
from .compliance import RULES
from .config import DEMO_NOW, FLEET_SIZE, MODEL_PATH, RANDOM_SEED
from .db import Base, SessionLocal, engine
from .demand import forecast, synth_history
from .models import (Alert, AuditLog, ComplianceRule, Customer, DemandForecast, JourneyEvent, Product, RescuePartner,
                     SensorReading, Shipment)
from .pipeline import analyze, customer_dict, partner_dict
from .reference import DEMO_PRODUCT_PARAMETERS, LOCATIONS, PRODUCTS_BY_ID, haversine_km
from .simulator import build_plan, build_q4821_plan, generate_readings, inject_data_quality_issues

HUB = LOCATIONS["Doha Industrial Area"]

# Base daily demand (kg/day) by customer type - SYNTHETIC.
BASE_DEMAND = {
    "P-STRAW": {"supermarket": 180, "small_retailer": 35, "restaurant": 70, "wholesaler": 400, "direct_consumer": 50},
    "P-FISH": {"supermarket": 120, "small_retailer": 20, "restaurant": 90, "wholesaler": 300, "direct_consumer": 25},
    "P-CHICK": {"supermarket": 400, "small_retailer": 60, "restaurant": 200, "wholesaler": 900, "direct_consumer": 50},
    "P-MILK": {"supermarket": 600, "small_retailer": 90, "restaurant": 60, "wholesaler": 1200, "direct_consumer": 80},
    "P-YOG": {"supermarket": 300, "small_retailer": 50, "restaurant": 40, "wholesaler": 700, "direct_consumer": 40},
    "P-LEAFY": {"supermarket": 200, "small_retailer": 30, "restaurant": 80, "wholesaler": 500, "direct_consumer": 30},
    "P-FROZMEAT": {"supermarket": 250, "small_retailer": 25, "restaurant": 120, "wholesaler": 1200, "direct_consumer": 20},
    "P-TOM": {"supermarket": 500, "small_retailer": 70, "restaurant": 150, "wholesaler": 1500, "direct_consumer": 60},
}

CUSTOMERS = [
    # id, name, type, location, delivery_h, downstream_lag_h, min_receipt_days, max_receive_kg, discount, scale
    ("C-RA", "Retailer A - Hypermarket, Al Sadd", "supermarket", "Doha (Al Sadd)", 2.0, 3, 1.0, 1500, False, 1.3),
    ("C-RB", "Retailer B - Neighbourhood grocery, Al Khor", "small_retailer", "Al Khor", 5.0, 2, 1.0, 300, False, 1.0),
    ("C-DC", "Central retail DC (4 branches), Industrial Area", "supermarket", "Doha Industrial Area", 1.5, 20, 2.5, 4000, False, 2.0),
    ("C-LUS", "Supermarket - Lusail Marina", "supermarket", "Lusail", 3.0, 4, 1.5, 1200, False, 1.0),
    ("C-RAY", "Supermarket - Al Rayyan", "supermarket", "Al Rayyan", 2.5, 4, 1.5, 1000, False, 0.8),
    ("C-REST", "Restaurant network - West Bay (6 kitchens)", "restaurant", "Doha (West Bay)", 2.5, 1, 0.5, 400, False, 1.0),
    ("C-HOT", "Hotel & catering group - Lusail", "restaurant", "Lusail", 3.0, 2, 1.0, 500, False, 1.2),
    ("C-WHS", "Wholesale produce market - Abu Hamour", "wholesaler", "Abu Hamour", 1.5, 24, 3.0, 6000, False, 1.0),
    ("C-WAK", "Grocery - Al Wakrah", "small_retailer", "Al Wakrah Logistics", 2.5, 2, 1.0, 250, False, 1.0),
    ("C-UMM", "Neighbourhood grocery - Umm Salal", "small_retailer", "Umm Salal", 3.5, 2, 1.0, 250, False, 0.9),
    ("C-DTC", "Rapid-sale app (direct to consumer)", "direct_consumer", "Doha (Old Airport)", 3.0, 0, 0.5, 300, True, 1.0),
]
# Hero-story overrides for fresh strawberries (daily_kg, cv, inventory_kg)
STRAW_OVERRIDES = {"C-RA": (220, 0.15, 80), "C-REST": (75, 0.15, 15), "C-DC": (330, 0.2, 60),
                   "C-RB": (40, 0.25, 60), "C-DTC": (50, 0.3, 0), "C-LUS": (12, 0.25, 20), "C-RAY": (10, 0.25, 15),
                   "C-HOT": (10, 0.2, 15), "C-WHS": (150, 0.25, 200), "C-WAK": (6, 0.3, 10), "C-UMM": (5, 0.3, 10)}

RESCUE_PARTNERS = [
    # id, name, location, collection_h, capacity/day, available, min_window_days, accepts, social QAR/kg
    ("R-FB1", "Community food bank - Doha (approved partner)", "Doha (Old Airport)", 3.0, 400, 150, 1.0,
     ["P-STRAW", "P-TOM", "P-LEAFY", "P-YOG", "P-MILK"], 10.0),
    ("R-CK2", "Charity kitchen network - Al Rayyan", "Al Rayyan", 4.0, 250, 120, 0.75,
     ["P-STRAW", "P-TOM", "P-LEAFY", "P-CHICK", "P-FROZMEAT"], 12.0),
    ("R-SH3", "Shelter meal programme - Al Wakrah", "Al Wakrah Logistics", 5.0, 300, 200, 2.0,
     ["P-FROZMEAT", "P-YOG", "P-MILK", "P-TOM"], 11.0),
]

LOT_DAYS = {"P-FROZMEAT": (3, 8)}  # lot size in days of the original customer's demand (default 0.8-1.8)


def _dist(loc: str) -> float:
    return round(haversine_km(HUB, LOCATIONS[loc]) * 1.3 + 3, 1)  # road factor


def seed_reference(db: Session, rng: np.random.Generator) -> None:
    for p in DEMO_PRODUCT_PARAMETERS:
        db.add(Product(product_id=p["product_id"], name=p["name"], category=p["category"],
                       storage_class=p["storage_class"], required_min_temperature=p["required_min_temperature"],
                       required_max_temperature=p["required_max_temperature"], humidity_min=p["humidity_min"],
                       humidity_max=p["humidity_max"], declared_shelf_life_days=p["declared_shelf_life_days"],
                       sensitivity=p["sensitivity"], min_window_days=p["min_window_days"], notes=p["notes"],
                       demo_parameters=p))
    for r in RULES:
        db.add(ComplianceRule(**r))

    for cid, name, ctype, loc, dh, lag, minr, maxkg, disc, scale in CUSTOMERS:
        profile, inventory, history = {}, {}, {}
        for pid, base in BASE_DEMAND.items():
            daily = base[ctype] * scale * rng.uniform(0.85, 1.15)
            cv = rng.uniform(0.15, 0.3)
            inv = daily * rng.uniform(0.2, 0.8)
            if pid == "P-STRAW" and cid in STRAW_OVERRIDES:
                daily, cv, inv = STRAW_OVERRIDES[cid]
            profile[pid] = {"daily_kg": round(float(daily), 1), "cv": round(float(cv), 2)}
            inventory[pid] = round(float(inv), 1)
            history[pid] = synth_history(daily, cv, DEMO_NOW, rng)
        lat, lon = LOCATIONS[loc]
        db.add(Customer(customer_id=cid, name=name, type=ctype, location_name=loc, lat=lat, lon=lon,
                        distance_km=_dist(loc), delivery_hours=dh, downstream_lag_hours=lag, min_receipt_days=minr,
                        max_receive_kg=maxkg, discount_channel=disc, accepts=list(BASE_DEMAND),
                        demand_profile=profile, current_inventory=inventory, historical_demand=history))
        tomorrow = datetime(DEMO_NOW.year, DEMO_NOW.month, DEMO_NOW.day) + timedelta(days=1)
        for pid, hist in history.items():
            for f in forecast(hist, tomorrow, 7, history_end=datetime(DEMO_NOW.year, DEMO_NOW.month, DEMO_NOW.day)):
                db.add(DemandForecast(customer_id=cid, product_id=pid, forecast_date=datetime.fromisoformat(f["date"]),
                                      expected_kg=f["expected_kg"], std_kg=f["std_kg"],
                                      method="seasonal-naive (same weekday, 4-week mean)"))

    for pid_, name, loc, ch, cap, avail, minw, accepts, social in RESCUE_PARTNERS:
        lat, lon = LOCATIONS[loc]
        db.add(RescuePartner(partner_id=pid_, name=name, location_name=loc, lat=lat, lon=lon, distance_km=_dist(loc),
                             collection_hours=ch, capacity_kg_per_day=cap, available_capacity_kg=avail,
                             min_window_days=minw, accepts=accepts, social_value_qar_per_kg=social))
    db.flush()


def _store_journey(db: Session, shipment_id: str, readings: list[dict], events: list[dict]) -> None:
    db.execute(insert(SensorReading), [{**r, "shipment_id": shipment_id} for r in readings])
    db.execute(insert(JourneyEvent), [{**e, "shipment_id": shipment_id} for e in events])


def seed_q4821(db: Session) -> Shipment:
    rng = np.random.default_rng(RANDOM_SEED)
    plan = build_q4821_plan()
    start = DEMO_NOW - timedelta(hours=plan.total_hours)
    readings, events = generate_readings(plan, start, 10, rng, "VQ-IOT-4821")
    # protect the excursion window from injected data issues so the story stays exact
    k0 = int(round(20.0 * 6))
    protect = set(range(k0 - 2, k0 + 22))
    readings = inject_data_quality_issues(readings, rng, missing_frac=0.03, spikes=1, duplicates=1, protect=protect)
    s = Shipment(shipment_id="Q4821", product_id="P-STRAW", quantity_kg=500.0, production_date=start,
                 declared_expiry=start + timedelta(days=8), origin="Origin packhouse (import, synthetic)",
                 transport_mode="air", status="in_cold_storage", scenario="B_excursion",
                 original_customer_id="C-DC", device_id="VQ-IOT-4821", featured=True)
    db.add(s)
    db.flush()
    _store_journey(db, "Q4821", readings, events)
    return s


def seed_fleet(db: Session, n: int, customers: list[dict], rng: np.random.Generator) -> list[Shipment]:
    scen = ["A_healthy", "E_good", "B_excursion", "C_delay", "D_multiple"]
    weights = [0.55, 0.25, 0.09, 0.07, 0.04]
    prod_weights = np.array([0.12, 0.1, 0.16, 0.16, 0.12, 0.1, 0.1, 0.14])
    ids = set()
    out = []
    for i in range(n):
        while True:
            sid = f"Q{int(rng.integers(1000, 9999))}"
            if sid not in ids and sid != "Q4821":
                ids.add(sid)
                break
        product = DEMO_PRODUCT_PARAMETERS[int(rng.choice(len(DEMO_PRODUCT_PARAMETERS), p=prod_weights))]
        pid = product["product_id"]
        scenario = str(rng.choice(scen, p=weights))
        stop = "cold_storage" if rng.random() < 0.45 else None
        plan, mode = build_plan(product, scenario, rng, stop_after_stage=stop)
        start = DEMO_NOW - timedelta(hours=plan.total_hours)
        interval = 10 if i < 60 else 20
        device = f"VQ-IOT-{sid[1:]}"
        readings, events = generate_readings(plan, start, interval, rng, device, battery_start=float(rng.uniform(60, 99)))
        roll = rng.random()
        readings = inject_data_quality_issues(
            readings, rng, missing_frac=float(rng.uniform(0.0, 0.05)), spikes=int(rng.integers(0, 3)),
            impossible=int(rng.random() < 0.05), duplicates=int(rng.integers(0, 3)),
            disconnect_h=float(rng.uniform(1, 5)) if roll < 0.05 else 0.0,
            stale_gps=int(rng.integers(4, 8)) if rng.random() < 0.08 else 0)
        if product["category"] == "frozen":
            production = start - timedelta(days=float(rng.uniform(20, 150)))
        else:
            production = start - timedelta(hours=float(rng.uniform(0, 30)))
        # original customer: weighted by demand for this product
        cands = [c for c in customers if not c["discount_channel"]]
        dem = np.array([c["demand_profile"][pid]["daily_kg"] for c in cands])
        cust = cands[int(rng.choice(len(cands), p=dem / dem.sum()))]
        lo, hi = LOT_DAYS.get(pid, (0.8, 1.8))
        qty = max(40.0, round(cust["demand_profile"][pid]["daily_kg"] * rng.uniform(lo, hi) / 10) * 10)
        status = "in_cold_storage" if stop else "out_for_delivery"
        s = Shipment(shipment_id=sid, product_id=pid, quantity_kg=float(qty), production_date=production,
                     declared_expiry=production + timedelta(days=product["declared_shelf_life_days"]),
                     origin=events[0]["location_name"], transport_mode=mode, status=status, scenario=scenario,
                     original_customer_id=cust["customer_id"], device_id=device, featured=False)
        db.add(s)
        db.flush()
        _store_journey(db, sid, readings, events)
        out.append(s)
    return out


def make_alerts(db: Session, s: Shipment, res: dict) -> None:
    for e in res["explanation"]["episodes"]:
        db.add(Alert(shipment_id=s.shipment_id, ts=datetime.fromisoformat(e["end"]), kind="TEMP_EXCURSION",
                     severity="high" if e["kind"] == "above" else "medium",
                     message=f"Temperature excursion detected: {e['duration_h']:.1f} h {'above' if e['kind'] == 'above' else 'below'} "
                             f"{e['limit_c']} C, peak {e['peak_c']} C near {e['location']}."))
    if res["classification"] == "HOLD":
        db.add(Alert(shipment_id=s.shipment_id, ts=DEMO_NOW, kind="COMPLIANCE_HOLD", severity="critical",
                     message="Placed on hold for inspection / compliance review."))
    f = res["features"]
    p = PRODUCTS_BY_ID[s.product_id]
    if f["dwell_h"] > 2.5 * p["dwell_allowance_h"]:
        db.add(Alert(shipment_id=s.shipment_id, ts=DEMO_NOW, kind="DWELL", severity="medium",
                     message=f"Extended warehouse dwell: {f['dwell_h']:.0f} h (allowance {p['dwell_allowance_h']:.0f} h)."))
    if res["data_quality"]["score"] < 80:
        db.add(Alert(shipment_id=s.shipment_id, ts=DEMO_NOW, kind="DATA_QUALITY", severity="medium",
                     message=f"Sensor data quality {res['data_quality']['score']:.0f}%: " + "; ".join(res["data_quality"]["issues"][:2])))


def main(fleet: int = FLEET_SIZE, retrain: bool = False) -> None:
    t0 = time.time()
    print("Q-Chain AI - seeding SYNTHETIC demo data")
    if retrain or not MODEL_PATH.exists():
        print("- training prototype ML model on synthetic journeys ...")
        ml.train()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    rng = np.random.default_rng(RANDOM_SEED)
    with SessionLocal() as db:
        seed_reference(db, rng)
        customers = [customer_dict(c) for c in db.query(Customer).all()]
        partners = [partner_dict(p) for p in db.query(RescuePartner).all()]
        print("- generating hero shipment Q4821 ...")
        hero = seed_q4821(db)
        print(f"- generating {fleet - 1} fleet shipments with sensor histories ...")
        ships = seed_fleet(db, fleet - 1, customers, rng)
        db.commit()
        print(f"  ({time.time() - t0:.0f}s) running analysis pipeline on every shipment ...")
        for i, s in enumerate([hero] + ships):
            res = analyze(db, s, customers=customers, partners=partners)
            make_alerts(db, s, res)
            if i and i % 200 == 0:
                db.commit()
                print(f"  analysed {i}/{fleet} ({time.time() - t0:.0f}s)")
        db.add(AuditLog(username="system", role="admin", action="seed", resource="database",
                        detail=f"Seeded {fleet} synthetic shipments", ts=datetime.utcnow()))
        db.commit()
        h = analyze(db, hero, customers=customers, partners=partners, persist=False)
    print(f"Done in {time.time() - t0:.0f}s. Q4821: declared remaining {h['declared_remaining_days']} d, "
          f"estimated {h['estimated_remaining_days']} d, {h['classification']}/{h['risk_level']}, "
          f"confidence {h['confidence']:.0%}, route waste {h['recommendation']['current_route']['expected_waste_pct']}% -> "
          f"{h['recommendation']['optimized']['expected_waste_pct']}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fleet", type=int, default=FLEET_SIZE)
    ap.add_argument("--retrain", action="store_true")
    a = ap.parse_args()
    main(a.fleet, a.retrain)
