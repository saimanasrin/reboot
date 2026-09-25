"""End-to-end analysis: SENSE -> RECONSTRUCT -> PREDICT -> EXPLAIN -> CLASSIFY -> OPTIMIZE.

Every numerical decision is produced here by deterministic functions. The LLM agent only narrates the result.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import compliance as compliance_engine
from . import explain, ml, optimizer
from .config import DEMO_NOW
from .data_quality import assess
from .features import compute_features
from .models import Customer, JourneyEvent, Prediction, Product, Recommendation, RescuePartner, SensorReading, Shipment
from .physics import FACTOR_LABELS, deterioration, deterioration_score
from .reference import nearest_place

PHYSICS_WEIGHT = 0.6  # blend: 60% physics layer, 40% ML layer
CLASS_META = {
    "GOOD": {"action": "NORMAL", "color": "GREEN", "label": "Good - normal distribution"},
    "MID": {"action": "ACCELERATE", "color": "YELLOW", "label": "Mid - prioritise faster-moving customers"},
    "LOW": {"action": "RESCUE", "color": "ORANGE", "label": "Low - rapid-sale / eligible rescue channels"},
    "HOLD": {"action": "HOLD", "color": "DARKRED", "label": "Hold - inspection / compliance review"},
}


def product_dict(p: Product) -> dict:
    return dict(p.demo_parameters)


def customer_dict(c: Customer) -> dict:
    return {k: getattr(c, k) for k in ("customer_id", "name", "type", "location_name", "lat", "lon", "distance_km",
                                        "delivery_hours", "downstream_lag_hours", "min_receipt_days", "max_receive_kg",
                                        "discount_channel", "accepts", "demand_profile", "current_inventory",
                                        "historical_demand")}


def partner_dict(p: RescuePartner) -> dict:
    return {k: getattr(p, k) for k in ("partner_id", "name", "location_name", "lat", "lon", "distance_km",
                                        "collection_hours", "capacity_kg_per_day", "available_capacity_kg",
                                        "min_window_days", "accepts", "social_value_qar_per_kg")}


def reading_dicts(db: Session, shipment_id: str) -> list[dict]:
    rows = db.execute(select(SensorReading).where(SensorReading.shipment_id == shipment_id)
                      .order_by(SensorReading.ts)).scalars().all()
    return [{"ts": r.ts, "temperature_c": r.temperature_c, "humidity_pct": r.humidity_pct, "lat": r.lat, "lon": r.lon,
             "door_open": r.door_open, "motion": r.motion, "battery_pct": r.battery_pct, "device_id": r.device_id}
            for r in rows]


def event_dicts(db: Session, shipment_id: str) -> list[dict]:
    rows = db.execute(select(JourneyEvent).where(JourneyEvent.shipment_id == shipment_id)
                      .order_by(JourneyEvent.seq)).scalars().all()
    return [{"seq": e.seq, "stage": e.stage, "segment_type": e.segment_type, "label": e.label,
             "location_name": e.location_name, "lat": e.lat, "lon": e.lon, "start_ts": e.start_ts, "end_ts": e.end_ts}
            for e in rows]


def classify(product: dict, est_days: float, compliance: dict) -> str:
    if compliance["status"] == "HOLD":
        return "HOLD"
    if est_days >= product["normal_channel_days"]:
        return "GOOD"
    if est_days >= product["rapid_channel_days"]:
        return "MID"
    if est_days >= product["min_window_days"]:
        return "LOW"
    return "HOLD"


def risk_level(classification: str, loss_days: float, declared_remaining: float) -> str:
    frac = loss_days / declared_remaining if declared_remaining > 0 else 1.0
    if classification == "HOLD":
        return "CRITICAL"
    if classification == "LOW" or frac >= 0.5:
        return "HIGH"
    if classification == "MID" or frac >= 0.2:
        return "MEDIUM"
    return "LOW"


def confidence_score(phys_loss: float, ml_out: dict, declared_life: float, dq_score: float,
                     unverified_h: float) -> tuple[float, dict]:
    """Heuristic confidence: narrow model interval, physics/ML agreement and good sensor data -> higher."""
    scale = max(declared_life, 1.0)
    spread = (ml_out["loss_hi_days"] - ml_out["loss_lo_days"]) / scale
    disagreement = abs(phys_loss - ml_out["loss_days"]) / scale
    base = 0.97 - 0.25 * spread - 0.4 * disagreement
    dq = 0.55 + 0.45 * dq_score / 100
    conf = float(np.clip(base * dq - 0.03 * unverified_h, 0.3, 0.97))
    return conf, {"model_interval_width_days": round(ml_out["loss_hi_days"] - ml_out["loss_lo_days"], 2),
                  "physics_ml_disagreement_days": round(abs(phys_loss - ml_out["loss_days"]), 2),
                  "data_quality_factor": round(dq, 3), "unverified_hours": unverified_h}


def analyze(db: Session, shipment: Shipment, *, customers: list[dict] | None = None,
            partners: list[dict] | None = None, as_of: datetime | None = None, persist: bool = True,
            with_optimizer: bool = True) -> dict:
    as_of = as_of or DEMO_NOW
    prod_row = db.get(Product, shipment.product_id)
    product = product_dict(prod_row)
    raw = reading_dicts(db, shipment.shipment_id)
    events = event_dicts(db, shipment.shipment_id)
    info_ok = all(product.get(k) is not None for k in ("required_max_temperature", "declared_shelf_life_days", "q10"))

    # SENSE + data quality
    q = assess(raw, product_info_complete=info_ok)
    # RECONSTRUCT
    feats, trace = compute_features(q.clean, events, product, shipment.production_date, as_of)
    declared_remaining = (shipment.declared_expiry - as_of).total_seconds() / 86400
    # PREDICT
    phys = deterioration(feats, trace, product)
    phys_total = max(0.0, sum(phys.values()))
    ml_out = ml.predict(feats, product)
    blended = PHYSICS_WEIGHT * phys_total + (1 - PHYSICS_WEIGHT) * ml_out["loss_days"]
    est = float(np.clip(declared_remaining - blended, 0.0, max(0.0, declared_remaining)))
    final_loss = max(0.0, declared_remaining - est)
    conf, conf_detail = confidence_score(phys_total, ml_out, product["declared_shelf_life_days"], q.report["score"],
                                         q.report["unverified_hours"])
    # Uncertainty band on the estimate (ML quantiles blended the same way)
    est_lo = float(np.clip(declared_remaining - (PHYSICS_WEIGHT * phys_total + (1 - PHYSICS_WEIGHT) * ml_out["loss_hi_days"]), 0, None))
    est_hi = float(np.clip(declared_remaining - (PHYSICS_WEIGHT * phys_total + (1 - PHYSICS_WEIGHT) * ml_out["loss_lo_days"]), 0, max(0.0, declared_remaining)))
    # COMPLIANCE (separate layer)
    comp = compliance_engine.evaluate(product, feats, trace, q.report, declared_remaining, est)
    # CLASSIFY
    cls = classify(product, est, comp)
    risk = risk_level(cls, final_loss, declared_remaining)
    # EXPLAIN
    episodes = explain.excursion_episodes(q.clean, product)
    expl = explain.build(product, feats, phys, final_loss, episodes, declared_remaining, est, q.report)

    result = {
        "shipment_id": shipment.shipment_id,
        "as_of": as_of.isoformat(timespec="minutes"),
        "declared_shelf_life_days": product["declared_shelf_life_days"],
        "elapsed_days": round(feats["time_since_production_h"] / 24, 2),
        "declared_remaining_days": round(declared_remaining, 2),
        "estimated_remaining_days": round(est, 2),
        "estimated_range_days": [round(est_lo, 2), round(est_hi, 2)],
        "loss_days": round(final_loss, 2),
        "physics_loss_days": round(phys_total, 2),
        "ml_loss_days": round(ml_out["loss_days"], 2),
        "physics_factors": {FACTOR_LABELS[k]: round(v, 3) for k, v in phys.items()},
        "deterioration_score": round(deterioration_score(phys, product), 1),
        "risk_level": risk,
        "confidence": round(conf, 3),
        "confidence_detail": conf_detail,
        "classification": cls,
        **{k: v for k, v in CLASS_META[cls].items()},
        "data_quality": q.report,
        "compliance": comp,
        "explanation": expl,
        "features": {k: round(v, 3) for k, v in feats.items()},
        "model_version": f"physics-v1 + {ml_out['version']}",
        "label": "Prototype prediction",
    }

    if with_optimizer:
        customers = customers if customers is not None else [customer_dict(c) for c in db.execute(select(Customer)).scalars()]
        partners = partners if partners is not None else [partner_dict(p) for p in db.execute(select(RescuePartner)).scalars()]
        dests = optimizer.destinations(customers, partners, product)
        opt = optimizer.optimize(product, shipment.quantity_kg, est, comp, cls, dests, shipment.original_customer_id,
                                 declared_remaining)
        result["recommendation"] = opt

    if persist:
        db.execute(update(Prediction).where(Prediction.shipment_id == shipment.shipment_id,
                                            Prediction.is_current.is_(True)).values(is_current=False))
        pred = Prediction(shipment_id=shipment.shipment_id, as_of=as_of, created_at=datetime.utcnow(),
                          declared_remaining_days=result["declared_remaining_days"],
                          estimated_remaining_days=result["estimated_remaining_days"],
                          physics_days=round(declared_remaining - phys_total, 2),
                          ml_days=round(declared_remaining - ml_out["loss_days"], 2),
                          loss_days=result["loss_days"], deterioration_score=result["deterioration_score"],
                          risk_level=risk, confidence=result["confidence"], classification=cls,
                          action=CLASS_META[cls]["action"], data_quality_score=q.report["score"],
                          compliance_status=comp["status"],
                          detail={k: v for k, v in result.items() if k != "recommendation"},
                          model_version=result["model_version"], is_current=True)
        db.add(pred)
        db.flush()
        if with_optimizer:
            db.execute(update(Recommendation).where(Recommendation.shipment_id == shipment.shipment_id,
                                                    Recommendation.is_current.is_(True)).values(is_current=False))
            opt = result["recommendation"]
            cur = opt["current_route"]
            o = opt["optimized"]
            rec = Recommendation(shipment_id=shipment.shipment_id, prediction_id=pred.id, created_at=datetime.utcnow(),
                                 action_label=opt["action_label"],
                                 original_waste_kg=cur["expected_waste_kg"] if cur else 0.0,
                                 optimized_waste_kg=o["expected_waste_kg"] if o.get("expected_waste_kg") is not None else shipment.quantity_kg,
                                 food_saved_kg=opt["food_saved_kg"], revenue_recovered_qar=opt["revenue_recovered_qar"],
                                 plan=opt, is_current=True)
            db.add(rec)
            db.flush()
            result["recommendation_id"] = rec.id
        result["prediction_id"] = pred.id

    # Current position
    if q.clean:
        last = q.clean[-1]
        shipment.current_lat, shipment.current_lon = last.get("lat"), last.get("lon")
        shipment.last_reading_at = last["ts"]
    result["current_location"] = nearest_place(shipment.current_lat, shipment.current_lon) if shipment.current_lat else "Unknown"
    return result
