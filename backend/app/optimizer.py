"""Demand-aware routing optimizer and what-if simulator (deterministic; all figures are prototype calculations).

Objective (QAR-equivalent, demo weights):
    maximise  revenue + social value of rescued food
    minimise  waste cost + transport cost + delay risk
Greedy marginal allocation in lots: each lot goes to the eligible destination with the highest marginal net value.
Because expected sales are concave in quantity (the usable window fills up), greedy allocation is near-optimal here.
"""
from __future__ import annotations

from .demand import CHANNEL_PRICE_FACTOR, UPLIFT_PER_10PCT, expected_sold

WEIGHTS = {
    "waste_cost_qar_per_kg": 3.0,      # disposal + environmental cost of food waste (demo)
    "trip_fixed_qar": 40.0,
    "trip_qar_per_km": 1.1,
    "express_surcharge_qar": 350.0,
    "delay_risk_qar_per_kg_day": 0.5,  # penalty on time-to-arrival (exposure risk)
    "handling_loss_pct": 1.5,
    "rescue_utilisation_pct": 95.0,
}


def destinations(customers: list[dict], partners: list[dict], product: dict) -> list[dict]:
    out = []
    pid = product["product_id"]
    for c in customers:
        if pid not in c["accepts"]:
            continue
        prof = c["demand_profile"].get(pid, {"daily_kg": 0, "cv": 0.2})
        out.append({
            "id": c["customer_id"], "name": c["name"], "kind": "customer", "type": c["type"],
            "location_name": c["location_name"], "lat": c["lat"], "lon": c["lon"], "distance_km": c["distance_km"],
            "hours": c["delivery_hours"], "lag_hours": c["downstream_lag_hours"],
            "min_receipt_days": c["min_receipt_days"], "max_kg": c["max_receive_kg"],
            "daily_kg": prof["daily_kg"], "cv": prof.get("cv", 0.2),
            "inventory_kg": c["current_inventory"].get(pid, 0.0),
            "price_per_kg": product["price_qar_per_kg"] * CHANNEL_PRICE_FACTOR[c["type"]],
            "discount_channel": c["discount_channel"],
            "channel_discount": 0.25 if c["discount_channel"] else 0.0,
        })
    for p in partners:
        if pid not in p["accepts"]:
            continue
        out.append({
            "id": p["partner_id"], "name": p["name"], "kind": "rescue", "type": "food_rescue",
            "location_name": p["location_name"], "lat": p["lat"], "lon": p["lon"], "distance_km": p["distance_km"],
            "hours": p["collection_hours"], "lag_hours": 0.0, "min_receipt_days": p["min_window_days"],
            "max_kg": p["available_capacity_kg"], "social_value_per_kg": p["social_value_qar_per_kg"],
            "price_per_kg": 0.0, "discount_channel": False, "channel_discount": 0.0,
        })
    return out


def eligibility(dest: dict, compliance: dict) -> tuple[bool, str | None]:
    el = compliance["eligibility"]
    if dest["kind"] == "rescue":
        return (True, None) if el["rescue_review"] else (False, "Not eligible for rescue review (compliance)")
    if dest["discount_channel"]:
        return (True, None) if el["discount_sale"] else (False, "Discount sale not permitted (compliance)")
    return (True, None) if el["normal_sale"] else (False, "Sale not permitted while on hold")


def evaluate(dest: dict, qty: float, est_days: float, product: dict, *, discount: float = 0.0,
             speedup: float = 1.0, express: bool = False, accept_days: float | None = None) -> dict:
    """Expected outcome of sending `qty` kg to `dest`.

    `accept_days` is the remaining life the BUYER checks at receipt. Without Q-Chain, buyers only see the declared
    expiry, so status-quo routes pass the declared remaining life here; sales still depend on the usable window.
    """
    w = WEIGHTS
    arrival_h = dest["hours"] * speedup
    at_arrival = est_days - arrival_h / 24
    accepted = ((accept_days if accept_days is not None else est_days) - arrival_h / 24) >= dest["min_receipt_days"]
    sold = social = revenue = 0.0
    if qty > 0 and accepted:
        if dest["kind"] == "rescue":
            window = at_arrival - dest["min_receipt_days"]
            sold = min(qty, dest["max_kg"]) * w["rescue_utilisation_pct"] / 100 if window > 0 else 0.0
            social = sold * dest["social_value_per_kg"]
        else:
            window = at_arrival - dest["lag_hours"] * speedup / 24 - product["min_window_days"] * 0.5
            disc = max(discount, dest["channel_discount"])
            uplift = UPLIFT_PER_10PCT * (disc * 10) if disc else 0.0
            sold = expected_sold(qty, dest["daily_kg"] * (1 + uplift), dest["cv"], window, dest["inventory_kg"])
            sold *= 1 - w["handling_loss_pct"] / 100
            revenue = sold * dest["price_per_kg"] * (1 - disc)
    waste = max(0.0, qty - sold)
    transport = (w["trip_fixed_qar"] + w["trip_qar_per_km"] * dest["distance_km"]) if qty > 0 else 0.0
    if express and qty > 0:
        transport += w["express_surcharge_qar"]
    delay = w["delay_risk_qar_per_kg_day"] * qty * arrival_h / 24
    value = revenue + social - w["waste_cost_qar_per_kg"] * waste - transport - delay
    return {
        "qty_kg": qty, "sold_kg": sold, "waste_kg": waste, "revenue_qar": revenue, "social_value_qar": social,
        "transport_qar": transport, "delay_risk_qar": delay, "value": value, "accepted": accepted,
        "arrival_hours": arrival_h, "remaining_at_arrival_days": at_arrival,
    }


def _reason(dest: dict, ev: dict, est_days: float) -> str:
    if dest["kind"] == "rescue":
        return (f"Approved rescue partner, collection in {dest['hours']:.1f} h; {dest['max_kg']:.0f} kg capacity available. "
                "Eligible for food-rescue review, subject to applicable food-safety and organisational acceptance requirements.")
    base = (f"{dest['daily_kg']:.0f} kg/day demand, {dest['inventory_kg']:.0f} kg on hand, delivery {dest['hours']:.1f} h; "
            f"{ev['remaining_at_arrival_days']:.1f} d usable window on arrival")
    if dest["discount_channel"]:
        return f"Rapid discounted sale ({int(dest['channel_discount'] * 100)}% off): " + base
    return base


def allocate(dests: list[dict], qty: float, est_days: float, product: dict, compliance: dict) -> dict:
    eligible = []
    for d in dests:
        ok, why = eligibility(d, compliance)
        if ok and est_days - d["hours"] / 24 < d["min_receipt_days"]:
            ok, why = False, f"Needs >= {d['min_receipt_days']:.1f} d remaining on receipt"
        d["eligible"], d["ineligible_reason"] = ok, why
        if ok:
            eligible.append(d)

    lot = max(10.0, round(qty / 50 / 10) * 10)
    alloc = {d["id"]: 0.0 for d in eligible}
    cur = {d["id"]: evaluate(d, 0.0, est_days, product) for d in eligible}
    remaining = qty
    wc = WEIGHTS["waste_cost_qar_per_kg"]
    while remaining > 1e-6 and eligible:
        step = min(lot, remaining)
        best, best_gain, best_ev = None, 0.0, None
        for d in eligible:
            if alloc[d["id"]] + step > d["max_kg"] + 1e-6:
                continue
            ev = evaluate(d, alloc[d["id"]] + step, est_days, product)
            gain = ev["value"] - cur[d["id"]]["value"] + wc * step
            if gain > best_gain:
                best, best_gain, best_ev = d, gain, ev
        if best is None:
            break
        alloc[best["id"]] += step
        cur[best["id"]] = best_ev
        remaining -= step

    lines = []
    for d in eligible:
        q = alloc[d["id"]]
        if q <= 0:
            continue
        ev = cur[d["id"]]
        lines.append({"destination_id": d["id"], "destination": d["name"], "kind": d["kind"], "type": d["type"],
                      "channel": _channel(d), "location_name": d["location_name"], "lat": d["lat"], "lon": d["lon"],
                      **_round(ev), "reason": _reason(d, ev, est_days)})
    lines.sort(key=lambda l: -l["qty_kg"])
    totals = _totals(lines, qty, unallocated=remaining)
    return {"lines": lines, "unallocated_kg": round(remaining, 1), **totals}


def _channel(d: dict) -> str:
    if d["kind"] == "rescue":
        return "rescue"
    if d["discount_channel"]:
        return "discount"
    return "sale"


def _round(ev: dict) -> dict:
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in ev.items() if k != "value"}


def _totals(lines: list[dict], qty: float, unallocated: float = 0.0) -> dict:
    sold = sum(l["sold_kg"] for l in lines)
    waste = sum(l["waste_kg"] for l in lines) + unallocated
    return {
        "total_qty_kg": round(qty, 1),
        "used_kg": round(sold, 1),
        "expected_waste_kg": round(waste, 1),
        "expected_waste_pct": round(100 * waste / qty, 1) if qty else 0.0,
        "revenue_qar": round(sum(l["revenue_qar"] for l in lines), 0),
        "social_value_qar": round(sum(l["social_value_qar"] for l in lines), 0),
        "transport_qar": round(sum(l["transport_qar"] for l in lines), 0),
    }


def single_route(dest: dict, qty: float, est_days: float, product: dict, **kw) -> dict:
    ev = evaluate(dest, qty, est_days, product, **kw)
    line = {"destination_id": dest["id"], "destination": dest["name"], "kind": dest["kind"], "type": dest["type"],
            "channel": _channel(dest), "location_name": dest["location_name"], "lat": dest["lat"], "lon": dest["lon"],
            **_round(ev), "reason": _reason(dest, ev, est_days)}
    if not ev["accepted"]:
        line["reason"] = (f"Below the {dest['min_receipt_days']:.1f} d remaining life the buyer requires on receipt; "
                          "lot likely rejected.")
    elif ev["waste_kg"] > 0.2 * qty and dest["kind"] == "customer":
        line["reason"] += (f". Buyer accepts on the declared date, but only ~{ev['sold_kg']:.0f} kg is expected to "
                           "sell inside the usable window")
    return {"lines": [line], "unallocated_kg": 0.0, **_totals([line], qty)}


def action_label(classification: str, plan: dict, original_id: str | None) -> str:
    if classification == "HOLD":
        return "Hold for review"
    channels = {l["channel"] for l in plan["lines"]}
    ids = {l["destination_id"] for l in plan["lines"]}
    if classification == "GOOD" and ids <= {original_id}:
        return "Normal route"
    parts = []
    if "sale" in channels:
        parts.append("Accelerate" if classification != "GOOD" else "Reroute")
    if channels & {"rescue", "discount"}:
        parts.append("Rescue" if parts else "Rapid sale / Rescue")
    return " + ".join(parts) or "No eligible channel - QA review"


def optimize(product: dict, qty: float, est_days: float, compliance: dict, classification: str,
             dests: list[dict], original_id: str | None, declared_days: float | None = None) -> dict:
    by_id = {d["id"]: d for d in dests}
    original = by_id.get(original_id)
    current = single_route(original, qty, est_days, product, accept_days=declared_days) if original else None

    if classification == "HOLD":
        opt = {"lines": [], "unallocated_kg": qty, **_totals([], qty, unallocated=qty)}
        opt["expected_waste_kg"] = None
        opt["expected_waste_pct"] = None
        for d in dests:
            d["eligible"], d["ineligible_reason"] = False, "Shipment on compliance hold"
    else:
        opt = allocate(dests, qty, est_days, product, compliance)
        # Don't reroute a healthy shipment unless it clearly reduces waste.
        if classification == "GOOD" and current and current["expected_waste_pct"] <= opt["expected_waste_pct"] + 5:
            opt = current

    saved = revenue_rec = 0.0
    if current and opt.get("expected_waste_kg") is not None:
        saved = max(0.0, current["expected_waste_kg"] - opt["expected_waste_kg"])
        revenue_rec = max(0.0, opt["revenue_qar"] - current["revenue_qar"])
    candidates = [{
        "id": d["id"], "name": d["name"], "kind": d["kind"], "type": d["type"], "channel": _channel(d),
        "location_name": d["location_name"], "distance_km": d["distance_km"], "hours": d["hours"],
        "daily_kg": d.get("daily_kg"), "inventory_kg": d.get("inventory_kg"), "max_kg": d["max_kg"],
        "remaining_at_arrival_days": round(est_days - d["hours"] / 24, 2),
        "eligible": d.get("eligible", False), "ineligible_reason": d.get("ineligible_reason"),
        "is_original": d["id"] == original_id,
    } for d in dests]
    return {
        "current_route": current,
        "optimized": opt,
        "food_saved_kg": round(saved, 1),
        "revenue_recovered_qar": round(revenue_rec, 0),
        "social_value_qar": opt.get("social_value_qar", 0),
        "waste_avoided_kg": round(saved, 1),
        "affected_qty_kg": round(current["expected_waste_kg"], 1) if current else None,
        "action_label": action_label(classification, opt, original_id),
        "candidates": candidates,
        "weights": WEIGHTS,
        "note": "Prototype calculation on the synthetic demo dataset.",
    }


def what_if(product: dict, qty: float, est_days: float, compliance: dict, classification: str,
            dests: list[dict], original_id: str | None, confidence: float,
            declared_days: float | None = None) -> list[dict]:
    by_id = {d["id"]: d for d in dests}
    acc = {"accept_days": declared_days}
    original = by_id.get(original_id)
    retail = [d for d in dests if d["kind"] == "customer" and d["type"] in ("supermarket", "small_retailer")
              and not d["discount_channel"] and d["id"] != original_id]
    retail.sort(key=lambda d: -d["daily_kg"])
    # Named demo retailers when present; otherwise the fastest- and slowest-moving alternatives.
    ret_a = by_id.get("C-RA") if "C-RA" in by_id and original_id != "C-RA" else (retail[0] if retail else None)
    ret_b = by_id.get("C-RB") if "C-RB" in by_id and original_id != "C-RB" else (retail[-1] if len(retail) > 1 else None)
    rescue = sorted([d for d in dests if d["kind"] == "rescue"], key=lambda d: d["hours"])
    hold = classification == "HOLD"
    el = compliance["eligibility"]

    options: list[dict] = []

    def add(key, label, plan, conf_factor, blocked: str | None = None, delivery_h=None, extra=None):
        base = {"key": key, "label": label, "blocked_reason": blocked}
        if blocked or plan is None:
            options.append({**base, "available": False})
            return
        lines = plan["lines"]
        dh = delivery_h if delivery_h is not None else (max(l["arrival_hours"] for l in lines) if lines else None)
        rem = min((l["remaining_at_arrival_days"] for l in lines), default=None)
        options.append({**base, "available": True,
                        "expected_waste_kg": plan["expected_waste_kg"], "expected_waste_pct": plan["expected_waste_pct"],
                        "revenue_qar": plan["revenue_qar"], "social_value_qar": plan["social_value_qar"],
                        "delivery_hours": round(dh, 1) if dh is not None else None,
                        "remaining_at_destination_days": round(rem, 2) if rem is not None else None,
                        "quantity_saved_kg": round(qty - plan["expected_waste_kg"], 1),
                        "confidence": round(confidence * conf_factor, 3), "lines": lines, **(extra or {})})

    hold_msg = "Shipment is on compliance hold - no sale or redistribution scenario is permitted."
    orig_name = original["name"] if original else "original customer"
    add("keep", f"Keep original route ({orig_name})",
        single_route(original, qty, est_days, product, **acc) if original else None, 1.0,
        blocked=hold_msg if hold else (None if original else "No original customer"))
    if ret_a:
        add("retailer_a", f"Reroute to Retailer A - {ret_a['name']}",
            single_route(ret_a, qty, est_days, product, **acc), 0.97, blocked=hold_msg if hold else None)
    if ret_b:
        add("retailer_b", f"Reroute to Retailer B - {ret_b['name']}",
            single_route(ret_b, qty, est_days, product, **acc), 0.97, blocked=hold_msg if hold else None)
    for pct in (10, 20):
        add(f"discount_{pct}", f"Discount {pct}% at {orig_name}",
            single_route(original, qty, est_days, product, discount=pct / 100, **acc) if original else None, 0.9,
            blocked=hold_msg if hold else (None if el["discount_sale"] else "Discount sale not permitted"),
            extra={"discount_pct": pct})
    add("accelerate", f"Accelerate delivery to {orig_name} (express, -50% time)",
        single_route(original, qty, est_days, product, speedup=0.5, express=True, **acc) if original else None, 0.95,
        blocked=hold_msg if hold else None)
    if rescue:
        r = rescue[0]
        add("rescue", f"Send to rescue channel - {r['name']}",
            single_route(r, qty, est_days, product), 0.92,
            blocked=hold_msg if hold else (None if el["rescue_review"] else "Not eligible for rescue review"))
    opt = optimize(product, qty, est_days, compliance, classification, [dict(d) for d in dests], original_id,
                   declared_days)["optimized"]
    add("optimized", "Q-Chain optimized split", opt if not hold else None, 0.93, blocked=hold_msg if hold else None)
    if hold:
        options.append({"key": "hold", "label": "Hold for inspection / compliance review", "available": True,
                        "blocked_reason": None, "expected_waste_kg": None, "expected_waste_pct": None,
                        "revenue_qar": 0, "social_value_qar": 0, "delivery_hours": None,
                        "remaining_at_destination_days": None, "quantity_saved_kg": None,
                        "confidence": round(confidence, 3), "lines": [],
                        "note": "Outcome depends on QA inspection; Q-Chain does not estimate it."})
    return options
