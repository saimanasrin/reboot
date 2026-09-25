"""Reference data.

Two strictly separated groups:

* OFFICIAL_REGULATORY_THRESHOLDS: storage temperatures published by Qatar MOPH (cited).
* DEMO_PRODUCT_PARAMETERS: prototype parameters invented for this hackathon demo. They are NOT legal
  shelf-life rules and NOT scientifically validated; they exist so the pipeline can run end-to-end.
"""
from __future__ import annotations

import math

SOURCES = {
    "vodafone_iot": {
        "title": "Vodafone Qatar - IoT Asset Tracking",
        "url": "https://www.vodafone.qa/en/business/services/iot/asset-tracking",
        "used_for": "Sensor variables: location, temperature, humidity, mishandling, movement/motion; platform-side analytics and dashboards.",
    },
    "moph_watheq": {
        "title": "MOPH Users Guidebook Part 1 - Registration of Company Related Products (Watheq System)",
        "url": "https://emsfsa.moph.gov.qa/en/MOPH_Documents/Registration%20Documents/Users%20Guidebook-Part%201-Regestration%20of%20Company%20%20Related%20Products%20by%20Watheq%20System.pdf",
        "used_for": "Storage temperature classes: frozen <= -18 C, chilled 0-5 C, ambient <= 25 C.",
    },
    "moph_food_service": {
        "title": "MOPH Food Service Establishment Guidelines",
        "url": "https://www.moph.gov.qa/_layouts/15/download.aspx?SourceUrl=%2FAdmin%2FLists%2FPublicationsAttachments%2FAttachments%2F140%2FFood-service-establishment-Guidelines-English.pdf",
        "used_for": "Temperature checks/records requirement; frozen food stored at -18 C or less.",
    },
    "infotech_qatar": {
        "title": "Infotech Qatar - IoT Cold Chain Management",
        "url": "https://infotech.qa/services/iot/cold-chain-management/",
        "used_for": "Cold-storage monitoring variables: temperature, humidity, real-time conditions, automated alerts.",
    },
}

SIMULATION_DISCLAIMER = (
    "Prototype sensor simulation based on sensor variables and operating ranges documented by "
    "Qatar cold-chain/IoT providers and MOPH guidance."
)
PRODUCT_STATEMENT = (
    "Q-Chain is a decision-support prototype that estimates remaining usable shelf life using simulated IoT data "
    "grounded in sensor variables documented by Qatar-based cold-chain providers and temperature requirements "
    "documented by Qatar MOPH."
)
RESCUE_STATEMENT = (
    "Eligible for food-rescue review, subject to applicable food-safety and organizational acceptance requirements."
)

OFFICIAL_REGULATORY_THRESHOLDS = {
    "frozen": {"min_c": None, "max_c": -18.0, "label": "Frozen food: <= -18 C", "sources": ["moph_watheq", "moph_food_service"]},
    "chilled": {"min_c": 0.0, "max_c": 5.0, "label": "Chilled food: 0 C to 5 C", "sources": ["moph_watheq"]},
    "ambient": {"min_c": None, "max_c": 25.0, "label": "Ambient food: <= 25 C under appropriate storage conditions", "sources": ["moph_watheq"]},
}

# ---------------------------------------------------------------------------------------------------------------
# DEMO PRODUCT PARAMETERS - illustrative values for the prototype only.
#   q10                   temperature sensitivity of quality loss (rate multiplies by q10 per +10 C)
#   ref_c                 temperature at which the declared shelf life is assumed to hold
#   excursion_days_per_ch extra quality loss (days) per degree-hour outside the target band (abuse / condensation)
#   dwell_allowance_h     warehouse dwell considered normal handling; dwell beyond it is penalised
#   *_days                channel timing assumptions used by the classifier
# ---------------------------------------------------------------------------------------------------------------
DEMO_PRODUCT_PARAMETERS = [
    {
        "product_id": "P-STRAW", "name": "Fresh strawberries", "category": "produce", "storage_class": "chilled",
        "required_min_temperature": 0.0, "required_max_temperature": 5.0, "ref_c": 4.0,
        "humidity_min": 70.0, "humidity_max": 95.0, "declared_shelf_life_days": 8.0,
        "sensitivity": "high", "q10": 3.2, "excursion_days_per_ch": 0.44, "below_days_per_ch": 0.05,
        "dwell_allowance_h": 6.0, "dwell_days_per_h": 0.1, "door_days_per_event": 0.035, "shock_days_per_event": 0.06,
        "humidity_days_per_h": 0.02, "transit_allowance_h": 14.0, "transit_days_per_h": 0.045,
        "min_window_days": 0.5, "rapid_channel_days": 1.2, "normal_channel_days": 3.0,
        "price_qar_per_kg": 22.0, "high_risk": False,
        "notes": "Highly perishable soft fruit; condensation after warm exposure accelerates mould (demo assumption).",
    },
    {
        "product_id": "P-FISH", "name": "Fresh fish (whole, chilled)", "category": "seafood", "storage_class": "chilled",
        "required_min_temperature": 0.0, "required_max_temperature": 2.0, "ref_c": 1.0,
        "humidity_min": 85.0, "humidity_max": 100.0, "declared_shelf_life_days": 5.0,
        "sensitivity": "very high", "q10": 4.0, "excursion_days_per_ch": 0.18, "below_days_per_ch": 0.01,
        "dwell_allowance_h": 4.0, "dwell_days_per_h": 0.05, "door_days_per_event": 0.02, "shock_days_per_event": 0.0,
        "humidity_days_per_h": 0.0, "transit_allowance_h": 12.0, "transit_days_per_h": 0.02,
        "min_window_days": 0.75, "rapid_channel_days": 1.0, "normal_channel_days": 2.0,
        "price_qar_per_kg": 45.0, "high_risk": True,
        "notes": "High-risk raw protein. Any documented temperature abuse routes to compliance review.",
    },
    {
        "product_id": "P-CHICK", "name": "Fresh chicken", "category": "meat", "storage_class": "chilled",
        "required_min_temperature": 0.0, "required_max_temperature": 4.0, "ref_c": 2.0,
        "humidity_min": 80.0, "humidity_max": 100.0, "declared_shelf_life_days": 7.0,
        "sensitivity": "very high", "q10": 3.6, "excursion_days_per_ch": 0.14, "below_days_per_ch": 0.0,
        "dwell_allowance_h": 6.0, "dwell_days_per_h": 0.04, "door_days_per_event": 0.02, "shock_days_per_event": 0.0,
        "humidity_days_per_h": 0.0, "transit_allowance_h": 12.0, "transit_days_per_h": 0.02,
        "min_window_days": 1.0, "rapid_channel_days": 1.5, "normal_channel_days": 3.0,
        "price_qar_per_kg": 18.0, "high_risk": True,
        "notes": "High-risk raw protein. Rescue channels require an unbroken cold chain (prototype policy).",
    },
    {
        "product_id": "P-MILK", "name": "Fresh milk", "category": "dairy", "storage_class": "chilled",
        "required_min_temperature": 1.0, "required_max_temperature": 5.0, "ref_c": 4.0,
        "humidity_min": None, "humidity_max": None, "declared_shelf_life_days": 7.0,
        "sensitivity": "high", "q10": 3.0, "excursion_days_per_ch": 0.12, "below_days_per_ch": 0.02,
        "dwell_allowance_h": 8.0, "dwell_days_per_h": 0.03, "door_days_per_event": 0.01, "shock_days_per_event": 0.0,
        "humidity_days_per_h": 0.0, "transit_allowance_h": 10.0, "transit_days_per_h": 0.015,
        "min_window_days": 1.5, "rapid_channel_days": 2.0, "normal_channel_days": 3.5,
        "price_qar_per_kg": 6.5, "high_risk": True,
        "notes": "Pasteurised dairy; sensitive to warm exposure.",
    },
    {
        "product_id": "P-YOG", "name": "Yogurt", "category": "dairy", "storage_class": "chilled",
        "required_min_temperature": 1.0, "required_max_temperature": 5.0, "ref_c": 4.0,
        "humidity_min": None, "humidity_max": None, "declared_shelf_life_days": 21.0,
        "sensitivity": "medium", "q10": 2.5, "excursion_days_per_ch": 0.08, "below_days_per_ch": 0.02,
        "dwell_allowance_h": 12.0, "dwell_days_per_h": 0.03, "door_days_per_event": 0.01, "shock_days_per_event": 0.0,
        "humidity_days_per_h": 0.0, "transit_allowance_h": 24.0, "transit_days_per_h": 0.01,
        "min_window_days": 3.0, "rapid_channel_days": 4.0, "normal_channel_days": 8.0,
        "price_qar_per_kg": 9.0, "high_risk": False,
        "notes": "Fermented dairy; comparatively robust.",
    },
    {
        "product_id": "P-LEAFY", "name": "Leafy vegetables", "category": "produce", "storage_class": "chilled",
        "required_min_temperature": 0.0, "required_max_temperature": 4.0, "ref_c": 2.0,
        "humidity_min": 90.0, "humidity_max": 100.0, "declared_shelf_life_days": 7.0,
        "sensitivity": "high", "q10": 3.0, "excursion_days_per_ch": 0.2, "below_days_per_ch": 0.15,
        "dwell_allowance_h": 6.0, "dwell_days_per_h": 0.06, "door_days_per_event": 0.02, "shock_days_per_event": 0.02,
        "humidity_days_per_h": 0.04, "transit_allowance_h": 16.0, "transit_days_per_h": 0.02,
        "min_window_days": 1.0, "rapid_channel_days": 1.5, "normal_channel_days": 3.0,
        "price_qar_per_kg": 12.0, "high_risk": False,
        "notes": "Wilting under low humidity; freeze damage below 0 C.",
    },
    {
        "product_id": "P-FROZMEAT", "name": "Frozen meat", "category": "frozen", "storage_class": "frozen",
        "required_min_temperature": -30.0, "required_max_temperature": -18.0, "ref_c": -20.0,
        "humidity_min": None, "humidity_max": None, "declared_shelf_life_days": 270.0,
        "sensitivity": "low", "q10": 2.0, "excursion_days_per_ch": 1.2, "below_days_per_ch": 0.0,
        "dwell_allowance_h": 72.0, "dwell_days_per_h": 0.05, "door_days_per_event": 0.05, "shock_days_per_event": 0.0,
        "humidity_days_per_h": 0.0, "transit_allowance_h": 240.0, "transit_days_per_h": 0.0,
        "min_window_days": 30.0, "rapid_channel_days": 45.0, "normal_channel_days": 90.0,
        "price_qar_per_kg": 28.0, "high_risk": True,
        "notes": "Must remain <= -18 C (MOPH). Readings above -12 C indicate possible partial thaw (prototype policy).",
    },
    {
        "product_id": "P-TOM", "name": "Fresh tomatoes", "category": "produce", "storage_class": "ambient",
        "required_min_temperature": 10.0, "required_max_temperature": 13.0, "ref_c": 12.0,
        "humidity_min": 85.0, "humidity_max": 95.0, "declared_shelf_life_days": 14.0,
        "sensitivity": "medium", "q10": 2.2, "excursion_days_per_ch": 0.03, "below_days_per_ch": 0.06,
        "dwell_allowance_h": 12.0, "dwell_days_per_h": 0.02, "door_days_per_event": 0.01, "shock_days_per_event": 0.05,
        "humidity_days_per_h": 0.01, "transit_allowance_h": 24.0, "transit_days_per_h": 0.01,
        "min_window_days": 2.0, "rapid_channel_days": 3.0, "normal_channel_days": 6.0,
        "price_qar_per_kg": 5.0, "high_risk": False,
        "notes": "Chilling injury below ~10 C (demo band 10-13 C). Official ambient ceiling <= 25 C applies.",
    },
]
PRODUCTS_BY_ID = {p["product_id"]: p for p in DEMO_PRODUCT_PARAMETERS}

# Named places used for GPS reverse-lookup and synthetic routing.
LOCATIONS = {
    "Hamad Port": (24.985, 51.610),
    "Hamad Intl Airport Cargo": (25.2867, 51.6110),
    "Doha Industrial Area": (25.195, 51.445),
    "Abu Hamour": (25.235, 51.495),
    "Al Wakrah Logistics": (25.150, 51.575),
    "Doha (Al Sadd)": (25.285, 51.510),
    "Doha (West Bay)": (25.320, 51.530),
    "Doha (Old Airport)": (25.255, 51.560),
    "Lusail": (25.420, 51.490),
    "Al Rayyan": (25.290, 51.420),
    "Umm Salal": (25.410, 51.400),
    "Al Khor": (25.680, 51.500),
    "Mesaieed": (24.990, 51.550),
    "Abu Samra Border": (24.745, 50.840),
    "Dukhan": (25.430, 50.785),
    "Al Shamal": (26.120, 51.210),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def nearest_place(lat: float, lon: float) -> str:
    name, coords = min(LOCATIONS.items(), key=lambda kv: haversine_km((lat, lon), kv[1]))
    if haversine_km((lat, lon), coords) > 60:
        return "In transit (outside Qatar)"
    return name
