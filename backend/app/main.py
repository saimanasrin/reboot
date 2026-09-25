"""Q-Chain AI API (FastAPI)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, insert, inspect, select
from sqlalchemy.orm import Session

from . import agent, ml, optimizer
from .auth import OPERATE, audit, authenticate, current_user, device_or_admin, issue_token, require_roles
from .compliance import RULES
from .config import CORS_ORIGINS, DEMO_NOW, FLEET_SIZE
from .data_quality import assess
from .db import engine, get_db
from .models import (Alert, AuditLog, Customer, DemandForecast, JourneyEvent, Prediction, Product, Recommendation,
                     RescuePartner, SensorReading, Shipment, Simulation)
from .pipeline import CLASS_META, analyze, customer_dict, partner_dict, product_dict
from .reference import (OFFICIAL_REGULATORY_THRESHOLDS, PRODUCT_STATEMENT, RESCUE_STATEMENT, SIMULATION_DISCLAIMER,
                        SOURCES, nearest_place)
from .schemas import AgentIn, IngestIn, LoginIn, NewShipmentIn, SimulateIn
from .simulator import SCENARIOS, build_plan, generate_readings

log = logging.getLogger("qchain")
CLASS_ORDER = {"HOLD": 0, "LOW": 1, "MID": 2, "GOOD": 3}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not inspect(engine).has_table("shipments") or _count_shipments() == 0:
        log.warning("Database empty - seeding synthetic demo data (this takes a few minutes) ...")
        from .seed import main as seed_main
        seed_main(FLEET_SIZE)
    ml.load()
    yield


def _count_shipments() -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Shipment)) or 0


app = FastAPI(title="Q-Chain AI", version="0.9.0", lifespan=lifespan,
              description="Cold-chain remaining-life intelligence and dynamic shelf-life routing. "
                          "Decision-support prototype running on SYNTHETIC data.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------------------------------------ helpers

def _get_shipment(db: Session, sid: str) -> Shipment:
    s = db.get(Shipment, sid.upper())
    if not s:
        raise HTTPException(404, f"Shipment {sid} not found")
    return s


def _current(db: Session, sid: str) -> tuple[Prediction | None, Recommendation | None]:
    p = db.scalar(select(Prediction).where(Prediction.shipment_id == sid, Prediction.is_current.is_(True))
                  .order_by(Prediction.id.desc()))
    r = db.scalar(select(Recommendation).where(Recommendation.shipment_id == sid, Recommendation.is_current.is_(True))
                  .order_by(Recommendation.id.desc()))
    return p, r


def _row(s: Shipment, p: Prediction | None, r: Recommendation | None, pname: str) -> dict:
    return {
        "shipment_id": s.shipment_id, "product_id": s.product_id, "product": pname, "quantity_kg": s.quantity_kg,
        "status": s.status, "scenario": s.scenario, "featured": s.featured,
        "lat": s.current_lat, "lon": s.current_lon,
        "location": nearest_place(s.current_lat, s.current_lon) if s.current_lat is not None else "Unknown",
        "declared_remaining_days": p.declared_remaining_days if p else None,
        "estimated_remaining_days": p.estimated_remaining_days if p else None,
        "loss_days": p.loss_days if p else None,
        "risk_level": p.risk_level if p else None, "classification": p.classification if p else None,
        "color": CLASS_META[p.classification]["color"] if p else None,
        "confidence": p.confidence if p else None, "data_quality": p.data_quality_score if p else None,
        "compliance_status": p.compliance_status if p else None,
        "recommended_action": r.action_label if r else None,
        "food_saved_kg": r.food_saved_kg if r else 0, "original_waste_kg": r.original_waste_kg if r else 0,
    }


def _all_rows(db: Session) -> list[dict]:
    names = {p.product_id: p.name for p in db.execute(select(Product)).scalars()}
    preds = {p.shipment_id: p for p in db.execute(select(Prediction).where(Prediction.is_current.is_(True))).scalars()}
    recs = {r.shipment_id: r for r in db.execute(select(Recommendation).where(Recommendation.is_current.is_(True))).scalars()}
    return [_row(s, preds.get(s.shipment_id), recs.get(s.shipment_id), names[s.product_id])
            for s in db.execute(select(Shipment)).scalars()]


def _dests(db: Session, product: dict) -> list[dict]:
    customers = [customer_dict(c) for c in db.execute(select(Customer)).scalars()]
    partners = [partner_dict(p) for p in db.execute(select(RescuePartner)).scalars()]
    return optimizer.destinations(customers, partners, product)


def _what_if(db: Session, s: Shipment, analysis: dict, keys: list[str] | None = None) -> list[dict]:
    product = product_dict(db.get(Product, s.product_id))
    opts = optimizer.what_if(product, s.quantity_kg, analysis["estimated_remaining_days"], analysis["compliance"],
                             analysis["classification"], _dests(db, product), s.original_customer_id,
                             analysis["confidence"], analysis["declared_remaining_days"])
    return [o for o in opts if not keys or o["key"] in keys]


def _shipment_info(db: Session, s: Shipment) -> dict:
    prod = db.get(Product, s.product_id)
    cust = db.get(Customer, s.original_customer_id) if s.original_customer_id else None
    return {
        "shipment_id": s.shipment_id, "product_id": s.product_id, "product_name": prod.name,
        "quantity_kg": s.quantity_kg, "production_date": s.production_date.isoformat(timespec="minutes"),
        "declared_expiry": s.declared_expiry.isoformat(timespec="minutes"), "origin": s.origin,
        "transport_mode": s.transport_mode, "status": s.status, "scenario": s.scenario,
        "scenario_label": SCENARIOS.get(s.scenario, {}).get("label", s.scenario), "device_id": s.device_id,
        "original_customer_id": s.original_customer_id, "original_customer": cust.name if cust else None,
        "current_lat": s.current_lat, "current_lon": s.current_lon,
        "current_location": nearest_place(s.current_lat, s.current_lon) if s.current_lat is not None else "Unknown",
        "last_reading_at": s.last_reading_at.isoformat(timespec="minutes") if s.last_reading_at else None,
    }


def _analysis(db: Session, s: Shipment) -> dict:
    p, r = _current(db, s.shipment_id)
    if not p:
        res = analyze(db, s)
        db.commit()
        return res
    return {**p.detail, "recommendation": r.plan if r else None, "prediction_id": p.id,
            "recommendation_id": r.id if r else None, "recommendation_status": r.status if r else None,
            "recommendation_accepted_by": r.accepted_by if r else None}


# ------------------------------------------------------------------------------------------------ auth

@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    u = authenticate(body.username, body.password)
    if not u:
        audit(db, {"sub": body.username, "role": "?"}, "login_failed", "auth", request=request)
        raise HTTPException(401, "Invalid username or password")
    audit(db, {"sub": u["username"], "role": u["role"]}, "login", "auth", request=request)
    return {"token": issue_token(u["username"], u["role"], u["name"]), "user": u}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["sub"], "role": user["role"], "name": user["name"]}


# ------------------------------------------------------------------------------------------------ reference

@app.get("/api/reference")
def reference(db: Session = Depends(get_db), _: dict = Depends(current_user)):
    return {
        "product_statement": PRODUCT_STATEMENT, "simulation_disclaimer": SIMULATION_DISCLAIMER,
        "rescue_statement": RESCUE_STATEMENT, "sources": SOURCES,
        "official_regulatory_thresholds": OFFICIAL_REGULATORY_THRESHOLDS,
        "demo_product_parameters": [p.demo_parameters for p in db.execute(select(Product)).scalars()],
        "compliance_rules": RULES, "scenarios": SCENARIOS, "model_card": ml.model_card(),
        "optimizer_weights": optimizer.WEIGHTS, "demo_now": DEMO_NOW.isoformat(timespec="minutes"),
    }


# ------------------------------------------------------------------------------------------------ dashboard

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), _: dict = Depends(current_user)):
    rows = _all_rows(db)
    fresh = [r for r in rows if r["product_id"] != "P-FROZMEAT" and r["estimated_remaining_days"] is not None]
    at_risk = [r for r in rows if r["classification"] in ("MID", "LOW", "HOLD")]
    by_class = {k: sum(1 for r in rows if r["classification"] == k) for k in CLASS_ORDER}
    products: dict[str, dict] = {}
    for r in rows:
        d = products.setdefault(r["product"], {"product": r["product"], "shipments": 0, "at_risk": 0, "kg": 0.0,
                                               "loss_pct_sum": 0.0})
        d["shipments"] += 1
        d["kg"] += r["quantity_kg"]
        d["at_risk"] += r["classification"] in ("MID", "LOW", "HOLD")
        if r["declared_remaining_days"]:
            d["loss_pct_sum"] += 100 * (r["loss_days"] or 0) / max(r["declared_remaining_days"], 0.01)
    for d in products.values():
        d["avg_loss_pct"] = round(d.pop("loss_pct_sum") / d["shipments"], 1)
        d["kg"] = round(d["kg"])
    # Rescuable lots first (a decision can still save food), then compliance holds (QA workflow).
    act_order = {"LOW": 0, "MID": 1, "HOLD": 2}
    table = sorted(at_risk, key=lambda r: (not r["featured"], act_order[r["classification"]],
                                           r["estimated_remaining_days"] or 0))
    featured_ids = [r["shipment_id"] for r in rows if r["featured"]]
    pinned = db.execute(select(Alert).where(Alert.shipment_id.in_(featured_ids))).scalars().all()
    recent = db.execute(select(Alert).where(Alert.shipment_id.not_in(featured_ids))
                        .order_by(Alert.ts.desc()).limit(400)).scalars().all()
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    kind_order = {"TEMP_EXCURSION": 0, "COMPLIANCE_HOLD": 1, "DWELL": 2, "DATA_QUALITY": 3}
    pinned = sorted(pinned, key=lambda a: (kind_order.get(a.kind, 9), -a.ts.timestamp()))
    recent = sorted(recent, key=lambda a: (-a.ts.timestamp(), sev.get(a.severity, 9), kind_order.get(a.kind, 9)))
    # interleave kinds so the feed isn't one alert type repeated
    by_kind: dict[str, list] = {}
    for a in recent:
        by_kind.setdefault(a.kind, []).append(a)
    mixed = []
    while len(mixed) < 14 and any(by_kind.values()):
        for k in sorted(by_kind, key=lambda k: kind_order.get(k, 9)):
            if by_kind[k]:
                mixed.append(by_kind[k].pop(0))
    alerts = (pinned + mixed)[:14]
    return {
        "as_of": DEMO_NOW.isoformat(timespec="minutes"),
        "kpis": {
            "total_shipments": len(rows),
            "at_risk_shipments": len(at_risk),
            "hold_shipments": by_class["HOLD"],
            "food_saved_kg": round(sum(r["food_saved_kg"] or 0 for r in rows)),
            "potential_food_waste_kg": round(sum(r["original_waste_kg"] or 0 for r in rows)),
            "revenue_recovered_qar": round(db.scalar(select(func.sum(Recommendation.revenue_recovered_qar))
                                                     .where(Recommendation.is_current.is_(True))) or 0),
            "avg_remaining_days_fresh": round(float(np.mean([r["estimated_remaining_days"] for r in fresh])), 2) if fresh else None,
            "avg_declared_remaining_days_fresh": round(float(np.mean([r["declared_remaining_days"] for r in fresh])), 2) if fresh else None,
            "monitored_kg": round(sum(r["quantity_kg"] for r in rows)),
        },
        "by_class": by_class,
        "by_product": sorted(products.values(), key=lambda d: -d["at_risk"]),
        "map": [{k: r[k] for k in ("shipment_id", "product", "lat", "lon", "classification", "color", "risk_level",
                                   "estimated_remaining_days", "quantity_kg", "location", "featured")}
                for r in rows if r["lat"] is not None],
        "attention": table[:40],
        "alerts": [{"id": a.id, "shipment_id": a.shipment_id, "ts": a.ts.isoformat(timespec="minutes"), "kind": a.kind,
                    "severity": a.severity, "message": a.message} for a in alerts],
        "disclaimer": SIMULATION_DISCLAIMER,
    }


# ------------------------------------------------------------------------------------------------ shipments

@app.get("/api/shipments")
def list_shipments(db: Session = Depends(get_db), _: dict = Depends(current_user),
                   classification: str | None = Query(None, pattern="^(GOOD|MID|LOW|HOLD)$"),
                   product_id: str | None = Query(None, max_length=16), q: str | None = Query(None, max_length=32),
                   sort: str = Query("priority", pattern="^(priority|remaining|id|quantity)$"),
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    rows = _all_rows(db)
    if classification:
        rows = [r for r in rows if r["classification"] == classification]
    if product_id:
        rows = [r for r in rows if r["product_id"] == product_id]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["shipment_id"].lower() or ql in r["product"].lower()
                or ql in (r["location"] or "").lower()]
    key = {
        "priority": lambda r: (not r["featured"], CLASS_ORDER.get(r["classification"], 9), r["estimated_remaining_days"] or 0),
        "remaining": lambda r: r["estimated_remaining_days"] or 0,
        "id": lambda r: r["shipment_id"],
        "quantity": lambda r: -r["quantity_kg"],
    }[sort]
    rows.sort(key=key)
    return {"total": len(rows), "items": rows[offset:offset + limit]}


@app.get("/api/shipments/{sid}")
def get_shipment(sid: str, db: Session = Depends(get_db), _: dict = Depends(current_user)):
    s = _get_shipment(db, sid)
    prod = db.get(Product, s.product_id)
    events = db.execute(select(JourneyEvent).where(JourneyEvent.shipment_id == s.shipment_id)
                        .order_by(JourneyEvent.seq)).scalars().all()
    return {
        "shipment": _shipment_info(db, s),
        "product": {**prod.demo_parameters, "parameter_label": "demo_product_parameters (prototype, not legal rules)",
                    "official_threshold": OFFICIAL_REGULATORY_THRESHOLDS[prod.storage_class]},
        "journey": [{"seq": e.seq, "stage": e.stage, "segment_type": e.segment_type, "label": e.label,
                     "location_name": e.location_name, "lat": e.lat, "lon": e.lon,
                     "start_ts": e.start_ts.isoformat(timespec="minutes"),
                     "end_ts": e.end_ts.isoformat(timespec="minutes") if e.end_ts else None,
                     "hours": round((e.end_ts - e.start_ts).total_seconds() / 3600, 1) if e.end_ts else None}
                    for e in events],
        "analysis": _analysis(db, s),
        "alerts": [{"ts": a.ts.isoformat(timespec="minutes"), "kind": a.kind, "severity": a.severity, "message": a.message}
                   for a in db.execute(select(Alert).where(Alert.shipment_id == s.shipment_id)
                                       .order_by(Alert.ts)).scalars()],
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.get("/api/shipments/{sid}/sensor-history")
def sensor_history(sid: str, db: Session = Depends(get_db), _: dict = Depends(current_user),
                   max_points: int = Query(700, ge=50, le=5000)):
    s = _get_shipment(db, sid)
    prod = db.get(Product, s.product_id)
    rows = db.execute(select(SensorReading).where(SensorReading.shipment_id == s.shipment_id)
                      .order_by(SensorReading.ts, SensorReading.id)).scalars().all()
    raw = [{"ts": r.ts, "temperature_c": r.temperature_c, "humidity_pct": r.humidity_pct, "lat": r.lat, "lon": r.lon,
            "door_open": r.door_open, "motion": r.motion, "battery_pct": r.battery_pct} for r in rows]
    q = assess(raw)
    p = prod.demo_parameters
    lo, hi = p["required_min_temperature"], p["required_max_temperature"]
    items = []
    for r, flag in zip(q.raw_sorted, q.flags):
        t = r["temperature_c"]
        items.append({"ts": r["ts"].isoformat(timespec="minutes"), "temperature_c": t, "humidity_pct": r["humidity_pct"],
                      "lat": r["lat"], "lon": r["lon"], "door_open": r["door_open"], "motion": r["motion"],
                      "battery_pct": r["battery_pct"], "flag": flag,
                      "out_of_band": flag is None and t is not None and (t > hi or (lo is not None and t < lo))})
    if len(items) > max_points:
        k = int(np.ceil(len(items) / max_points))
        items = [it for i, it in enumerate(items)
                 if i % k == 0 or it["flag"] or it["door_open"] or it["out_of_band"] or it["motion"] == "shock"
                 or i == len(items) - 1]
    return {"shipment_id": s.shipment_id, "band": {"min_c": lo, "max_c": hi, "ref_c": p["ref_c"]},
            "humidity_band": {"min": p["humidity_min"], "max": p["humidity_max"]},
            "official_threshold": OFFICIAL_REGULATORY_THRESHOLDS[prod.storage_class],
            "readings": items, "quality": q.report, "disclaimer": SIMULATION_DISCLAIMER,
            "label": "SYNTHETIC simulation data"}


@app.post("/api/shipments/{sid}/predict")
def predict(sid: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(current_user)):
    s = _get_shipment(db, sid)
    res = analyze(db, s)
    db.commit()
    audit(db, user, "predict", s.shipment_id, f"estimated {res['estimated_remaining_days']} d", request)
    return res


@app.get("/api/shipments/{sid}/explanation")
def explanation(sid: str, db: Session = Depends(get_db), _: dict = Depends(current_user)):
    s = _get_shipment(db, sid)
    a = _analysis(db, s)
    return {"shipment_id": s.shipment_id, **a["explanation"], "physics_factors": a["physics_factors"],
            "model_version": a["model_version"], "confidence": a["confidence"],
            "confidence_detail": a["confidence_detail"]}


@app.post("/api/shipments/{sid}/optimize")
def save_this_shipment(sid: str, request: Request, db: Session = Depends(get_db),
                       user: dict = Depends(require_roles(*OPERATE))):
    """SAVE THIS SHIPMENT: re-analyse, simulate alternatives, recommend the lowest-waste compliant action."""
    s = _get_shipment(db, sid)
    a = analyze(db, s)
    db.commit()
    rec = a["recommendation"]
    options = _what_if(db, s, a)
    cur, opt = rec["current_route"], rec["optimized"]
    elig = [c for c in rec["candidates"] if c["eligible"]]
    hold = a["classification"] == "HOLD"
    steps = [
        {"step": 1, "title": "Analyze current condition",
         "detail": f"Data quality {a['data_quality']['score']:.0f}%, compliance {a['compliance']['status']}, "
                   f"{len(a['explanation']['episodes'])} temperature excursion(s) on record."},
        {"step": 2, "title": "Estimate remaining usable shelf life",
         "detail": f"{a['estimated_remaining_days']} d usable vs {a['declared_remaining_days']} d declared "
                   f"(confidence {a['confidence']:.0%})."},
        {"step": 3, "title": "Identify affected quantity",
         "detail": (f"{rec['affected_qty_kg']:.0f} kg of {s.quantity_kg:.0f} kg would not sell inside the usable window "
                    "on the current route." if cur else "No current route on file.")},
        {"step": 4, "title": "Identify candidate destinations",
         "detail": f"{len(elig)} of {len(rec['candidates'])} destinations eligible after compliance and receipt-window checks."},
        {"step": 5, "title": "Calculate expected loss under current route",
         "detail": (f"{cur['expected_waste_pct']}% expected waste ({cur['expected_waste_kg']:.0f} kg)." if cur else "n/a")},
        {"step": 6, "title": "Simulate alternative routes",
         "detail": f"{sum(o['available'] for o in options)} scenarios simulated."},
        {"step": 7, "title": "Recommend lowest-waste compliant action",
         "detail": ("Hold for inspection - no sale or redistribution while a compliance rule is triggered." if hold else
                    f"{rec['action_label']}: {opt['expected_waste_pct']}% expected waste.")},
    ]
    audit(db, user, "save_this_shipment", s.shipment_id,
          f"{rec['action_label']}; saved {rec['food_saved_kg']} kg", request)
    return {"shipment_id": s.shipment_id, "steps": steps, "analysis": {k: v for k, v in a.items() if k != "recommendation"},
            "recommendation": rec, "what_if": options, "recommendation_id": a.get("recommendation_id"),
            "note": "All figures are prototype calculations on the synthetic demo dataset."}


@app.post("/api/shipments/{sid}/simulate")
def simulate(sid: str, body: SimulateIn, request: Request, db: Session = Depends(get_db),
             user: dict = Depends(current_user)):
    s = _get_shipment(db, sid)
    a = _analysis(db, s)
    options = _what_if(db, s, a, body.options)
    db.add(Simulation(shipment_id=s.shipment_id, created_at=datetime.utcnow(), created_by=user["sub"],
                      options=[{k: v for k, v in o.items() if k != "lines"} for o in options]))
    db.commit()
    audit(db, user, "simulate", s.shipment_id, f"{len(options)} options", request)
    return {"shipment_id": s.shipment_id, "estimated_remaining_days": a["estimated_remaining_days"],
            "options": options, "note": "Prototype calculations on the synthetic demo dataset."}


@app.post("/api/shipments/{sid}/agent-explanation")
def agent_explanation(sid: str, body: AgentIn, request: Request, db: Session = Depends(get_db),
                      user: dict = Depends(current_user)):
    s = _get_shipment(db, sid)
    a = _analysis(db, s)
    out = agent.explain(_shipment_info(db, s), a, _what_if(db, s, a), body.question)
    audit(db, user, "agent_explanation", s.shipment_id,
          f"engine={out['_meta']['engine']} q={body.question or ''}", request)
    return out


@app.post("/api/shipments/{sid}/recommendation/accept")
def accept(sid: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(require_roles(*OPERATE))):
    s = _get_shipment(db, sid)
    _, r = _current(db, s.shipment_id)
    if not r:
        raise HTTPException(404, "No recommendation")
    r.status, r.accepted_by, r.accepted_at = "accepted", user["sub"], datetime.utcnow()
    db.commit()
    audit(db, user, "accept_recommendation", s.shipment_id, r.action_label, request)
    return {"status": r.status, "accepted_by": r.accepted_by, "accepted_at": r.accepted_at.isoformat(timespec="minutes")}


# ------------------------------------------------------------------------------------------------ sensors / simulator

@app.post("/api/sensors/ingest")
def ingest(body: IngestIn, request: Request, db: Session = Depends(get_db), caller: dict = Depends(device_or_admin)):
    s = _get_shipment(db, body.shipment_id)
    if s.device_id != body.device_id:
        raise HTTPException(409, "Device is not assigned to this shipment")
    db.execute(insert(SensorReading), [{**r.model_dump(), "ts": r.ts.replace(tzinfo=None), "shipment_id": s.shipment_id,
                                        "device_id": body.device_id} for r in body.readings])
    db.commit()
    result = None
    if body.reanalyze:
        res = analyze(db, s, as_of=max(DEMO_NOW, max(r.ts.replace(tzinfo=None) for r in body.readings)))
        db.commit()
        result = {k: res[k] for k in ("estimated_remaining_days", "classification", "risk_level", "confidence")}
    audit(db, caller, "sensor_ingest", s.shipment_id, f"{len(body.readings)} readings", request)
    return {"accepted": len(body.readings), "shipment_id": s.shipment_id, "analysis": result}


@app.get("/api/simulator/scenarios")
def scenarios(_: dict = Depends(current_user)):
    return SCENARIOS


@app.post("/api/simulator/shipments")
def create_simulated_shipment(body: NewShipmentIn, request: Request, db: Session = Depends(get_db),
                              user: dict = Depends(require_roles("admin", "warehouse_manager"))):
    prod = db.get(Product, body.product_id)
    if not prod:
        raise HTTPException(404, "Unknown product")
    if body.original_customer_id and not db.get(Customer, body.original_customer_id):
        raise HTTPException(404, "Unknown customer")
    product = product_dict(prod)
    seed = body.seed if body.seed is not None else int(datetime.utcnow().timestamp() * 1000) % 10_000_000
    rng = np.random.default_rng(seed)
    plan, mode = build_plan(product, body.scenario, rng)
    start = DEMO_NOW - timedelta(hours=plan.total_hours)
    n = (db.scalar(select(func.count()).select_from(Shipment).where(Shipment.shipment_id.like("S%"))) or 0) + 1
    sid = f"S{n:04d}"
    device = f"SIM-{sid}"
    readings, events = generate_readings(plan, start, 10, rng, device)
    production = start - (timedelta(days=60) if product["category"] == "frozen" else timedelta(hours=6))
    cust_id = body.original_customer_id or "C-RA"
    s = Shipment(shipment_id=sid, product_id=body.product_id, quantity_kg=body.quantity_kg, production_date=production,
                 declared_expiry=production + timedelta(days=product["declared_shelf_life_days"]),
                 origin=events[0]["location_name"], transport_mode=mode, status="simulated", scenario=body.scenario,
                 original_customer_id=cust_id, device_id=device, featured=False, created_at=datetime.utcnow())
    db.add(s)
    db.flush()
    db.execute(insert(SensorReading), [{**r, "shipment_id": sid} for r in readings])
    db.execute(insert(JourneyEvent), [{**e, "shipment_id": sid} for e in events])
    res = analyze(db, s)
    db.commit()
    audit(db, user, "simulate_shipment", sid, f"{body.product_id} {body.scenario} seed={seed}", request)
    return {"shipment_id": sid, "seed": seed, "classification": res["classification"],
            "estimated_remaining_days": res["estimated_remaining_days"]}


# ------------------------------------------------------------------------------------------------ master data

@app.get("/api/customers")
def customers(db: Session = Depends(get_db), _: dict = Depends(current_user)):
    return [customer_dict(c) for c in db.execute(select(Customer)).scalars()]


@app.get("/api/rescue-partners")
def rescue_partners(db: Session = Depends(get_db), _: dict = Depends(current_user)):
    return [partner_dict(p) for p in db.execute(select(RescuePartner)).scalars()]


@app.get("/api/demand")
def demand(product_id: str = Query(..., max_length=16), db: Session = Depends(get_db), _: dict = Depends(current_user)):
    rows = db.execute(select(DemandForecast).where(DemandForecast.product_id == product_id)
                      .order_by(DemandForecast.customer_id, DemandForecast.forecast_date)).scalars().all()
    custs = {c.customer_id: c for c in db.execute(select(Customer)).scalars()}
    out: dict[str, dict] = {}
    for r in rows:
        c = custs[r.customer_id]
        d = out.setdefault(r.customer_id, {
            "customer_id": c.customer_id, "name": c.name, "type": c.type, "location": c.location_name,
            "delivery_hours": c.delivery_hours, "distance_km": c.distance_km,
            "inventory_kg": c.current_inventory.get(product_id, 0), "daily_kg": c.demand_profile[product_id]["daily_kg"],
            "history": c.historical_demand.get(product_id, []), "forecast": [], "method": r.method})
        d["forecast"].append({"date": r.forecast_date.date().isoformat(), "expected_kg": r.expected_kg, "std_kg": r.std_kg})
    for d in out.values():
        d["expected_sell_through_days_per_100kg"] = round((d["inventory_kg"] + 100) / d["daily_kg"], 2) if d["daily_kg"] else None
    return list(out.values())


@app.get("/api/alerts")
def alerts(db: Session = Depends(get_db), _: dict = Depends(current_user), limit: int = Query(50, ge=1, le=500)):
    rows = db.execute(select(Alert).order_by(Alert.ts.desc()).limit(limit)).scalars().all()
    return [{"id": a.id, "shipment_id": a.shipment_id, "ts": a.ts.isoformat(timespec="minutes"), "kind": a.kind,
             "severity": a.severity, "message": a.message} for a in rows]


@app.get("/api/audit")
def audit_log(db: Session = Depends(get_db), _: dict = Depends(require_roles("admin")),
              limit: int = Query(100, ge=1, le=1000)):
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).scalars().all()
    return [{"ts": r.ts.isoformat(timespec="seconds"), "username": r.username, "role": r.role, "action": r.action,
             "resource": r.resource, "detail": r.detail, "ip": r.ip} for r in rows]


@app.get("/api/health")
def health():
    return {"status": "ok", "demo_now": DEMO_NOW.isoformat(timespec="minutes")}


# ------------------------------------------------------------------------------------------------ static frontend

_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if path and f.is_file() else _DIST / "index.html")
