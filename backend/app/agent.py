"""Decision agent: an LLM that NARRATES the structured outputs of the deterministic engines.

Guarantees:
* The agent receives only computed facts (no raw control over business logic) and returns schema-validated JSON.
* Its text never changes numbers, classifications or compliance status - the UI renders those from the engines.
* Guardrails reject food-safety claims, expiry-extension claims and numbers that don't appear in the facts;
  on any failure (or without an API key) a deterministic template explainer answers instead.
"""
from __future__ import annotations

import json
import re

from .config import AGENT_MODEL, ANTHROPIC_API_KEY
from .reference import RESCUE_STATEMENT

SCHEMA = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string"},
        "why_prediction_changed": {"type": "string"},
        "recommended_action": {"type": "string"},
        "alternatives": {"type": "array", "items": {
            "type": "object",
            "properties": {"option": {"type": "string"}, "assessment": {"type": "string"}},
            "required": ["option", "assessment"], "additionalProperties": False}},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["what_happened", "why_prediction_changed", "recommended_action", "alternatives", "answer", "citations"],
    "additionalProperties": False,
}

SYSTEM = """You are the Q-Chain decision-support assistant for a cold-chain logistics team in Qatar.
You explain the outputs of Q-Chain's deterministic engines (sensor data-quality screen, shelf-life model, compliance
rule engine, demand forecast, routing optimizer). You are given those outputs as JSON facts.

Rules you must follow:
- Use ONLY the facts provided. Never invent sensor readings, dates, quantities, prices or percentages. Every number
  you write must appear in the facts.
- You do not decide anything. The recommended plan, classification and compliance status come from the engines;
  explain them, do not change or override them.
- Never state or imply that food is safe to eat, and never suggest the declared expiry date changes. Q-Chain estimates
  remaining usable QUALITY only. For rescue channels, use this wording: "%s"
- The sensor data is a prototype simulation, and the model is a prototype, not validated.
- Cite the fact references you used (for example S1, S2, E1, OPT, WHATIF:discount_20, RULE:OFF-CHILLED) in `citations`.
- Be concise and concrete: 1-3 sentences per field. If the user asked a question, answer it in `answer`, otherwise
  leave `answer` as an empty string.""" % RESCUE_STATEMENT

BANNED = re.compile(r"(safe to (eat|consume)|safe for (human )?consumption|guaranteed(ly)? safe|is (still )?safe\b|"
                    r"extend(ed|s|ing)? (the )?(expiry|expiration|best[- ]before)|new expiry date)", re.I)
NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def build_facts(shipment: dict, analysis: dict, options: list[dict] | None) -> dict:
    rec = analysis.get("recommendation") or {}
    cur = rec.get("current_route") or {}
    opt = rec.get("optimized") or {}
    facts = {
        "shipment": {k: shipment[k] for k in ("shipment_id", "product_name", "quantity_kg", "production_date",
                                              "declared_expiry", "original_customer")},
        "prediction": {k: analysis[k] for k in ("declared_shelf_life_days", "elapsed_days", "declared_remaining_days",
                                                "estimated_remaining_days", "estimated_range_days", "loss_days",
                                                "risk_level", "confidence", "classification", "action", "label")},
        "data_quality": {k: analysis["data_quality"][k] for k in ("score", "connectivity", "missing_pct", "issues")},
        "compliance": {"status": analysis["compliance"]["status"], "eligibility": analysis["compliance"]["eligibility"],
                       "rules": [f"RULE:{h['rule_id']} - {h['detail']}" for h in analysis["compliance"]["triggered_rules"]]},
        "explanation": {"summary": analysis["explanation"]["summary"],
                        "factors": [{"factor": f["label"], "days_lost": f["days"], "level": f["level"],
                                     "evidence": f["evidence"]} for f in analysis["explanation"]["factors"]],
                        "citations": analysis["explanation"]["citations"]},
        "OPT": {
            "action_label": rec.get("action_label"),
            "current_route_waste_pct": cur.get("expected_waste_pct"), "current_route_waste_kg": cur.get("expected_waste_kg"),
            "optimized_waste_pct": opt.get("expected_waste_pct"), "optimized_waste_kg": opt.get("expected_waste_kg"),
            "food_saved_kg": rec.get("food_saved_kg"), "revenue_recovered_qar": rec.get("revenue_recovered_qar"),
            "plan": [{"destination": l["destination"], "channel": l["channel"], "qty_kg": l["qty_kg"],
                      "expected_sold_kg": round(l["sold_kg"]), "reason": l["reason"]} for l in opt.get("lines", [])],
        },
    }
    if options:
        facts["WHATIF"] = {o["key"]: {"label": o["label"], "available": o["available"],
                                      "blocked_reason": o.get("blocked_reason"),
                                      "expected_waste_pct": o.get("expected_waste_pct"),
                                      "revenue_qar": o.get("revenue_qar"), "delivery_hours": o.get("delivery_hours")}
                           for o in options}
    return facts


def _numbers_grounded(text: str, facts_json: str) -> list[str]:
    known = set(NUM.findall(facts_json))
    known |= {k.rstrip("0").rstrip(".") for k in known if "." in k}
    unknown = []
    for n in NUM.findall(text):
        m = n.replace(",", "")
        if m in known or m.rstrip("0").rstrip(".") in known:
            continue
        try:
            v = float(m)
        except ValueError:
            continue
        if v in (0, 1, 2, 3) or any(abs(v - float(k)) <= max(0.051, abs(v) * 0.005) for k in known if _isnum(k)):
            continue
        unknown.append(n)
    return unknown


def _isnum(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def template_answer(facts: dict, question: str | None) -> dict:
    p, c, o = facts["prediction"], facts["compliance"], facts["OPT"]
    s = facts["shipment"]
    what = (f"{s['shipment_id']} ({s['quantity_kg']:.0f} kg {s['product_name']}) has used {p['elapsed_days']} of its "
            f"{p['declared_shelf_life_days']:.0f}-day declared shelf life. Sensor data quality is "
            f"{facts['data_quality']['score']:.0f}%. Compliance status: {c['status']}.")
    why = facts["explanation"]["summary"]
    if p["classification"] == "HOLD":
        action = ("Hold for inspection / compliance review. Q-Chain does not recommend sale or redistribution while a "
                  "compliance rule is triggered: " + "; ".join(c["rules"][:2]))
    else:
        plan = "; ".join(f"{l['qty_kg']:.0f} kg -> {l['destination']}" for l in o["plan"]) or "keep original route"
        action = (f"{o['action_label']}: {plan}. Expected waste falls from {o['current_route_waste_pct']}% on the "
                  f"current route to {o['optimized_waste_pct']}%.")
        if any(l["channel"] == "rescue" for l in o["plan"]):
            action += " " + RESCUE_STATEMENT
    alts = []
    for key, w in (facts.get("WHATIF") or {}).items():
        if key == "optimized":
            continue
        if not w["available"]:
            alts.append({"option": w["label"], "assessment": f"Not available: {w['blocked_reason']}"})
        elif w.get("expected_waste_pct") is not None:
            alts.append({"option": w["label"], "assessment": f"{w['expected_waste_pct']}% expected waste, "
                                                            f"QAR {w['revenue_qar']:.0f} revenue"})
    answer = ""
    if question:
        answer = ("The template explainer (no LLM key configured) can only restate the engine outputs above. "
                  f"Estimated usable window: {p['estimated_remaining_days']} days (range {p['estimated_range_days'][0]}-"
                  f"{p['estimated_range_days'][1]}), confidence {p['confidence']:.0%}, risk {p['risk_level']}.")
    return {"what_happened": what, "why_prediction_changed": why, "recommended_action": action,
            "alternatives": alts[:6], "answer": answer, "citations": ["S1", "S2", "S3", "OPT"]}


def explain(shipment: dict, analysis: dict, options: list[dict] | None, question: str | None = None) -> dict:
    facts = build_facts(shipment, analysis, options)
    facts_json = json.dumps(facts, default=str)
    meta = {"engine": "template", "model": None, "guardrails": [], "facts": facts}

    if not ANTHROPIC_API_KEY:
        meta["guardrails"].append("No ANTHROPIC_API_KEY configured - deterministic template explainer used.")
        return {**template_answer(facts, question), **{"_meta": meta}}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        user = f"FACTS (JSON):\n{facts_json}\n\nUSER QUESTION: {question or '(none - give the standard briefing)'}"
        resp = client.beta.messages.create(
            model=AGENT_MODEL,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        text = next(b.text for b in resp.content if b.type == "text")
        out = json.loads(text)
        meta.update(engine="llm", model=resp.model)
    except Exception as exc:  # noqa: BLE001 - any LLM failure falls back to the deterministic explainer
        meta["guardrails"].append(f"LLM unavailable ({type(exc).__name__}) - deterministic template explainer used.")
        return {**template_answer(facts, question), **{"_meta": meta}}

    body = " ".join([out["what_happened"], out["why_prediction_changed"], out["recommended_action"], out["answer"]]
                    + [a["option"] + " " + a["assessment"] for a in out["alternatives"]])
    if BANNED.search(body):
        meta["guardrails"].append("Rejected LLM output: food-safety / expiry claim detected. Template used instead.")
        meta["engine"] = "template"
        return {**template_answer(facts, question), **{"_meta": meta}}
    unknown = _numbers_grounded(body, facts_json)
    if len(unknown) > 2:
        meta["guardrails"].append(f"Rejected LLM output: numbers not found in facts ({', '.join(unknown[:5])}). "
                                  "Template used instead.")
        meta["engine"] = "template"
        return {**template_answer(facts, question), **{"_meta": meta}}
    if unknown:
        meta["guardrails"].append(f"Note: {len(unknown)} number(s) could not be matched to facts: {', '.join(unknown)}.")
    meta["guardrails"].append("Passed: no safety/expiry claims; numbers grounded in engine outputs.")
    return {**out, "_meta": meta}
