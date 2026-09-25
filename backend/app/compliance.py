"""Compliance / eligibility rule engine.

Deliberately separate from the quality model: the quality model estimates remaining USABLE QUALITY; this layer
decides which channels a lot may be offered to. It never declares food "safe" - it can only restrict. Official
thresholds (MOPH) are cited; everything else is a clearly-labelled prototype policy that a real operator would
replace with its own HACCP / regulatory procedures.
"""
from __future__ import annotations

from .features import Trace
from .reference import OFFICIAL_REGULATORY_THRESHOLDS, RESCUE_STATEMENT, SOURCES

SENSOR_TOLERANCE_C = 0.5  # prototype policy: typical logger accuracy; readings within it are not treated as breaches

RULES = [
    {"rule_id": "POL-TOL", "name": "Sensor accuracy tolerance", "rule_type": "prototype_policy",
     "applies_to": "official threshold checks", "outcome": "INFO",
     "description": f"Official thresholds are checked beyond a +/-{SENSOR_TOLERANCE_C} C sensor-accuracy tolerance so that "
                    "logger noise at the limit is not reported as a breach.",
     "source": "Prototype policy (demo) - set to the calibrated accuracy of the deployed loggers"},
    {"rule_id": "OFF-FROZEN", "name": "Frozen storage at or below -18 C", "rule_type": "official_threshold",
     "applies_to": "storage_class=frozen", "outcome": "REVIEW",
     "description": "Any validated reading above -18 C is an official storage-threshold breach and must be recorded and reviewed.",
     "source": SOURCES["moph_watheq"]["url"]},
    {"rule_id": "OFF-CHILLED", "name": "Chilled storage between 0 C and 5 C", "rule_type": "official_threshold",
     "applies_to": "storage_class=chilled", "outcome": "REVIEW",
     "description": "Validated readings above 5 C (or below 0 C) breach the official chilled range and must be recorded and reviewed.",
     "source": SOURCES["moph_watheq"]["url"]},
    {"rule_id": "OFF-AMBIENT", "name": "Ambient storage at or below 25 C", "rule_type": "official_threshold",
     "applies_to": "storage_class=ambient", "outcome": "REVIEW",
     "description": "Validated readings above 25 C breach the official ambient ceiling.",
     "source": SOURCES["moph_watheq"]["url"]},
    {"rule_id": "POL-HIGHRISK", "name": "High-risk product with official-threshold breach", "rule_type": "prototype_policy",
     "applies_to": "high_risk products (raw protein, dairy, frozen)", "outcome": "HOLD",
     "description": "High-risk products with >= 30 min above the official ceiling (or frozen product above -12 C) are held for inspection. No sale or redistribution until released by QA.",
     "source": "Prototype policy (demo) - replace with operator HACCP plan"},
    {"rule_id": "POL-QA", "name": "QA sign-off after documented excursion", "rule_type": "prototype_policy",
     "applies_to": "all products", "outcome": "CONDITIONAL",
     "description": "Lower-risk products with a documented official-threshold breach may be released only after QA sign-off; the excursion is recorded in the lot file.",
     "source": "Prototype policy (demo)"},
    {"rule_id": "POL-EXPIRY", "name": "Declared expiry is never extended", "rule_type": "prototype_policy",
     "applies_to": "all products", "outcome": "HOLD",
     "description": "If the manufacturer's declared expiry has passed, no sale or redistribution is recommended, regardless of estimates.",
     "source": "Prototype policy (demo); consistent with declared-date labelling"},
    {"rule_id": "POL-WINDOW", "name": "Minimum usable window", "rule_type": "prototype_policy",
     "applies_to": "all products", "outcome": "HOLD",
     "description": "If the estimated usable quality window is below the product's minimum window, the lot is held for review.",
     "source": "Prototype policy (demo parameters)"},
    {"rule_id": "POL-DATA", "name": "Unverifiable cold chain", "rule_type": "prototype_policy",
     "applies_to": "all products", "outcome": "HOLD",
     "description": "Data-quality score below 60, more than 3 h without sensor data, or incomplete product information: hold until the cold chain can be verified.",
     "source": "Prototype policy (demo)"},
    {"rule_id": "POL-RESCUE", "name": "Food-rescue review eligibility", "rule_type": "prototype_policy",
     "applies_to": "all products", "outcome": "RESTRICT_RESCUE",
     "description": "Rescue channels are offered only for review, and only when the lot is not on hold, high-risk products had no excursion above their band, and the partner's minimum window is met. Acceptance remains subject to food-safety and organisational requirements.",
     "source": "Prototype policy (demo)"},
]
RULES_BY_ID = {r["rule_id"]: r for r in RULES}


def _hit(rule_id: str, detail: str) -> dict:
    r = RULES_BY_ID[rule_id]
    return {"rule_id": rule_id, "name": r["name"], "rule_type": r["rule_type"], "outcome": r["outcome"],
            "detail": detail, "source": r["source"]}


def evaluate(product: dict, feats: dict, trace: Trace, quality: dict, declared_remaining_days: float,
             estimated_remaining_days: float) -> dict:
    hits: list[dict] = []
    hold = conditional = False
    rescue_ok = True
    cls = product["storage_class"]
    official = OFFICIAL_REGULATORY_THRESHOLDS[cls]

    # --- official threshold check on validated readings (beyond the sensor-accuracy tolerance) -----------------
    breach_h, peak = 0.0, float(feats.get("max_temp", 0.0))
    if trace.dt_h.size:
        over = trace.temp > official["max_c"] + SENSOR_TOLERANCE_C
        if official["min_c"] is not None:
            over |= trace.temp < official["min_c"] - SENSOR_TOLERANCE_C
        breach_h = float(trace.dt_h[over].sum())
    if breach_h >= 1 / 12:
        rid = {"frozen": "OFF-FROZEN", "chilled": "OFF-CHILLED", "ambient": "OFF-AMBIENT"}[cls]
        hits.append(_hit(rid, f"{breach_h:.2f} h outside the official {official['label']} range (peak {peak:.1f} C)."))
        partial_thaw = cls == "frozen" and peak > -12
        if product["high_risk"] and (breach_h >= 0.5 or partial_thaw):
            hold = True
            hits.append(_hit("POL-HIGHRISK", f"High-risk product; {breach_h:.2f} h above official ceiling"
                                              + (", possible partial thaw" if partial_thaw else "") + "."))
        else:
            conditional = True
            hits.append(_hit("POL-QA", "Documented excursion - release requires QA sign-off."))

    if declared_remaining_days <= 0:
        hold = True
        hits.append(_hit("POL-EXPIRY", "Declared expiry has passed."))
    if estimated_remaining_days < product["min_window_days"]:
        hold = True
        hits.append(_hit("POL-WINDOW", f"Estimated usable window {estimated_remaining_days:.1f} d is below the "
                                       f"{product['min_window_days']:.1f} d minimum."))
    if quality["score"] < 60 or quality["unverified_hours"] > 3 or not quality["product_info_complete"]:
        hold = True
        hits.append(_hit("POL-DATA", f"Data quality {quality['score']:.0f}%, {quality['unverified_hours']:.1f} h without data."))

    if hold:
        rescue_ok = False
    elif product["high_risk"] and feats.get("hours_above", 0) > 1 / 6:
        rescue_ok = False
        hits.append(_hit("POL-RESCUE", "High-risk product had time above its target band - not offered to rescue channels."))

    status = "HOLD" if hold else "CONDITIONAL" if conditional else "CLEAR"
    return {
        "status": status,
        "eligibility": {
            "normal_sale": not hold,
            "discount_sale": not hold,
            "rescue_review": rescue_ok,
        },
        "official_threshold": official["label"],
        "official_breach_hours": round(breach_h, 2),
        "triggered_rules": hits,
        "rescue_statement": RESCUE_STATEMENT if rescue_ok else None,
        "statement": ("Compliance status is a rule-based eligibility screen. It does not certify food safety; "
                      "release decisions remain with the operator's QA / food-safety team."),
    }


def evaluate_hold_reason(result: dict) -> str | None:
    holds = [h for h in result["triggered_rules"] if h["outcome"] == "HOLD"]
    return holds[0]["detail"] if holds else None
