# dte_data.py
import math
from datetime import datetime

# Synthetic poles in Metro Detroit (matching React component)
MOCK_POLES = [
    {"id": "DTE-7821", "lat": 42.3314, "lng": -83.0458, "district": "Southwest Detroit", "age": 34, "material": "Wood", "tilt": 14, "cracks": True, "rust": False, "vegetation": "high", "lastInspection": "2022-08-10", "circuit": "C-SW-04", "windExposure": "high", "floodZone": "AE", "soilType": "Clay"},
    {"id": "DTE-4512", "lat": 42.3700, "lng": -83.1000, "district": "Dearborn North", "age": 12, "material": "Steel", "tilt": 2, "cracks": False, "rust": True, "vegetation": "low", "lastInspection": "2024-01-22", "circuit": "C-DN-11", "windExposure": "medium", "floodZone": "X", "soilType": "Loam"},
    {"id": "DTE-9034", "lat": 42.3100, "lng": -83.0200, "district": "Downriver", "age": 47, "material": "Wood", "tilt": 19, "cracks": True, "rust": False, "vegetation": "medium", "lastInspection": "2021-03-15", "circuit": "C-DR-02", "windExposure": "high", "floodZone": "AE", "soilType": "Sandy"},
    {"id": "DTE-3301", "lat": 42.4000, "lng": -83.0800, "district": "Livonia", "age": 8, "material": "Composite", "tilt": 1, "cracks": False, "rust": False, "vegetation": "low", "lastInspection": "2024-11-05", "circuit": "C-LV-07", "windExposure": "low", "floodZone": "X", "soilType": "Loam"},
    {"id": "DTE-6678", "lat": 42.3500, "lng": -83.1500, "district": "Allen Park", "age": 29, "material": "Wood", "tilt": 8, "cracks": False, "rust": True, "vegetation": "medium", "lastInspection": "2023-04-30", "circuit": "C-AP-03", "windExposure": "medium", "floodZone": "B", "soilType": "Clay"},
    {"id": "DTE-2290", "lat": 42.2800, "lng": -83.0700, "district": "Wyandotte", "age": 52, "material": "Wood", "tilt": 22, "cracks": True, "rust": True, "vegetation": "high", "lastInspection": "2020-06-18", "circuit": "C-WY-01", "windExposure": "high", "floodZone": "AE", "soilType": "Clay"},
    {"id": "DTE-5544", "lat": 42.4200, "lng": -83.0000, "district": "Hamtramck", "age": 18, "material": "Steel", "tilt": 4, "cracks": False, "rust": False, "vegetation": "low", "lastInspection": "2024-07-14", "circuit": "C-HM-09", "windExposure": "low", "floodZone": "X", "soilType": "Loam"},
    {"id": "DTE-8812", "lat": 42.3400, "lng": -83.1800, "district": "Inkster", "age": 41, "material": "Wood", "tilt": 11, "cracks": True, "rust": True, "vegetation": "high", "lastInspection": "2021-11-22", "circuit": "C-IK-05", "windExposure": "high", "floodZone": "AE", "soilType": "Clay"},
]

def compute_risk_score(pole):
    """Calculate risk score (0-100) based on DTE‑inspired formula."""
    score = 0
    score += min(pole["age"] * 1.2, 40)
    score += pole["tilt"] * 1.8
    if pole["cracks"]: score += 15
    if pole["rust"]: score += 10
    if pole["vegetation"] == "high": score += 12
    elif pole["vegetation"] == "medium": score += 6
    if pole["windExposure"] == "high": score += 10
    elif pole["windExposure"] == "medium": score += 5
    if pole["floodZone"] == "AE": score += 8
    elif pole["floodZone"] == "B": score += 3
    if pole["material"] == "Wood": score += 8
    # years since inspection
    last = datetime.strptime(pole["lastInspection"], "%Y-%m-%d")
    years_since = (datetime.now() - last).days / 365.25
    score += min(years_since * 3, 12)
    raw_score = min(round(score), 100)
    # additional derived values
    storm_fail_prob = min(raw_score / 100 * 0.85 + 0.05, 0.95)
    remaining_life = max(0.5, (100 - raw_score) / 10)
    replace_cost = 8500 if pole["material"] == "Steel" else (11000 if pole["material"] == "Composite" else 6200)
    repair_cost = round(replace_cost * 0.35)
    return {
        "riskScore": raw_score,
        "stormFailProb": round(storm_fail_prob, 2),
        "remainingLife": round(remaining_life, 1),
        "replaceCost": replace_cost,
        "repairCost": repair_cost
    }

# Pre‑compute for all poles
for pole in MOCK_POLES:
    pole.update(compute_risk_score(pole))