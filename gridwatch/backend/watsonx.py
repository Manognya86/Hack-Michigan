"""
watsonx.py – AI recommendation engine with deterministic CV simulation.
Uses image hash to generate consistent, unique CV results per image.
"""

import os
import re
import hashlib
import logging
import random
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# IBM watsonx (optional – only if credentials are provided)
# ----------------------------------------------------------------------
WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID", "")
WATSONX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
GRANITE_MODEL = "ibm/granite-13b-instruct-v2"

_iam_token = None
_token_expiry = 0

async def _get_iam_token() -> str:
    import time
    import httpx
    global _iam_token, _token_expiry
    if _iam_token and time.time() < _token_expiry - 60:
        return _iam_token
    if not WATSONX_API_KEY:
        raise ValueError("WATSONX_API_KEY not set")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": WATSONX_API_KEY},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        resp.raise_for_status()
        data = resp.json()
        _iam_token = data["access_token"]
        _token_expiry = time.time() + data.get("expires_in", 3600)
        return _iam_token

async def call_granite(prompt: str, max_tokens: int = 800) -> str:
    """Call IBM watsonx Granite model if credentials are set, else rule-based."""
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        logger.debug("watsonx credentials missing – using rule‑based fallback")
        return _rule_based_response(prompt)
    try:
        import httpx
        token = await _get_iam_token()
        url = f"{WATSONX_URL}/ml/v1/text/generation?version=2024-05-01"
        payload = {
            "model_id": GRANITE_MODEL,
            "project_id": WATSONX_PROJECT_ID,
            "input": prompt,
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": max_tokens,
                "min_new_tokens": 40,
                "stop_sequences": ["<|endoftext|>"],
                "repetition_penalty": 1.1,
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            resp.raise_for_status()
            result = resp.json()
            return result["results"][0]["generated_text"].strip()
    except Exception as e:
        logger.error(f"Granite API call failed: {e}. Using rule‑based fallback.")
        return _rule_based_response(prompt)

# ----------------------------------------------------------------------
# Rule‑based fallback (no API required)
# ----------------------------------------------------------------------
def _extract_float(text: str, pattern: str, default: float = 50.0) -> float:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            raw = match.group(1).strip()
            raw = re.sub(r'[^\d.-]+$', '', raw)
            return float(raw)
        except ValueError:
            pass
    return default

def _rule_based_response(prompt: str) -> str:
    risk = _extract_float(prompt, r'Risk Score[:\s]*([\d.]+)', 50.0)
    if risk >= 75:
        return ("IMMEDIATE REPLACEMENT required within 30 days.\n"
                "Rationale: Risk score exceeds critical threshold. Pole is likely to fail during the next storm.\n"
                "Crew action: Notify dispatch, schedule emergency replacement. Isolate circuit before work.")
    elif risk >= 55:
        return ("REPLACEMENT within 12 months recommended.\n"
                "Rationale: High risk score; repair is not cost‑effective.\n"
                "Crew action: Add to replacement queue, perform interim visual inspection every 3 months.")
    elif risk >= 35:
        return ("REPAIR AND MONITOR within 6 months.\n"
                "Rationale: Moderate structural degradation. Reinforce with guy wires or replace crossarms.\n"
                "Crew action: Schedule repair, re‑inspect after 90 days.")
    else:
        return ("ROUTINE MONITORING.\n"
                "Rationale: Low risk score. No immediate action required.\n"
                "Crew action: Include in regular inspection cycle (every 2 years).")

# ----------------------------------------------------------------------
# Deterministic Computer Vision simulation (image‑based)
# ----------------------------------------------------------------------
def _image_hash(base64_str: str) -> str:
    """Create a short hash from the image data."""
    return hashlib.md5(base64_str.encode()).hexdigest()[:8]

def _simulate_cv_from_hash(hash_val: str) -> Dict[str, Any]:
    """
    Generate CV results deterministically from an image hash.
    Same hash => same results. Different images (even slight changes) give different results.
    """
    # Seed a random generator with the hash
    seed = int(hash_val, 16) % (2**32)
    rng = random.Random(seed)
    
    # Tilt angle: between 0 and 25 degrees, more realistic distribution
    tilt = round(rng.uniform(0, 20), 1)
    # Crack probability increases with tilt
    crack = rng.random() < (0.1 + tilt / 80)
    # Rust probability independent
    rust = rng.random() < 0.3
    # Vegetation risk: higher for rural areas (simulated)
    veg = rng.choices(["low", "medium", "high"], weights=[0.4, 0.4, 0.2])[0]
    # Wire sagging correlated with tilt
    sag = rng.random() < (0.05 + tilt / 50)
    # Overall condition based on tilt, crack, rust
    if tilt > 15 or crack:
        condition = "critical"
    elif tilt > 8 or rust:
        condition = "poor"
    elif tilt > 4 or veg == "high":
        condition = "fair"
    else:
        condition = "good"
    # Confidence: between 0.6 and 0.95
    conf = round(rng.uniform(0.6, 0.95), 2)
    
    return {
        "tilt_angle": tilt,
        "crack_detected": crack,
        "rust_detected": rust,
        "vegetation_risk": veg,
        "wire_sagging": sag,
        "overall_condition": condition,
        "confidence": conf,
        "notes": f"CV analysis based on image hash {hash_val}. For production, replace with real model."
    }

async def run_cv_analysis(image_base64: str, pole: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform image‑based computer vision analysis.
    Uses a deterministic simulation – different images produce different results.
    """
    if not image_base64:
        return {"error": "No image data provided"}
    # Ensure we have enough length (basic check)
    if len(image_base64) < 100:
        return {"error": "Image too small or invalid"}
    hash_val = _image_hash(image_base64)
    return _simulate_cv_from_hash(hash_val)

# ----------------------------------------------------------------------
# Prompt builders (used by main.py)
# ----------------------------------------------------------------------
def build_maintenance_prompt(pole: Dict, prediction: Dict, weather: Dict) -> str:
    return f"""You are an AI maintenance decision engine for DTE Energy.

POLE PROFILE:
- Pole ID: {pole.get('pole_id')}
- District: {pole.get('district')}
- Material: {pole.get('material')}, Age: {pole.get('age')} years
- Tilt: {pole.get('tilt_angle')}°, Cracks: {pole.get('crack_detected')}, Rust: {pole.get('rust_detected')}
- Vegetation risk: {pole.get('vegetation_risk')}, Wind exposure: {pole.get('wind_exposure')}
- Flood zone: {pole.get('flood_zone')}, Soil: {pole.get('soil_type')}
- Last inspection: {pole.get('last_inspection')} ({pole.get('years_since_inspection')} years ago)

ML PREDICTIONS:
- Risk Score: {prediction.get('risk_score')}/100 ({prediction.get('risk_level')})
- Failure Probability: {prediction.get('failure_probability')*100:.0f}%
- Storm Failure Probability: {prediction.get('storm_failure_probability')*100:.0f}%
- Remaining Life: {prediction.get('remaining_life_years')} years
- ML Recommendation: {prediction.get('recommendation')}

LIVE WEATHER:
- Wind: {weather.get('current',{}).get('wind_mph',0)} mph, Gusts: {weather.get('current',{}).get('gust_mph',0)} mph
- Storm Alert: {weather.get('storm_alert', 'None')}

Provide a structured maintenance recommendation with: 1) Recommended action, 2) Priority timeline, 3) Storm risk assessment, 4) Field crew instructions, 5) Cost justification."""

def build_work_order_prompt(pole: Dict, prediction: Dict) -> str:
    return f"""Generate a formal DTE Energy field work order for pole {pole.get('pole_id')}.

Risk score: {prediction.get('risk_score')}/100
Recommended action: {prediction.get('recommendation')}
Material: {pole.get('material')}, Age: {pole.get('age')} years

Format as a structured work order with sections: Priority, Estimated Duration, Crew Size, Equipment Required, Safety Checklist, Materials, Permits, Estimated Cost, Completion Target."""

def build_schedule_prompt(pole: Dict, prediction: Dict) -> str:
    return f"""Create a 5‑year predictive maintenance schedule for DTE pole {pole.get('pole_id')}.

Current risk: {prediction.get('risk_score')}/100, Remaining life: {prediction.get('remaining_life_years')} years.
Format year by year (2026‑2030) with actions, costs, and trigger conditions."""

def build_cv_followup_prompt(cv_result: Dict, pole: Dict, prediction: Dict) -> str:
    return f"""Computer vision inspection of pole {pole.get('pole_id')} found:
- Tilt: {cv_result.get('tilt_angle')}°, Cracks: {cv_result.get('crack_detected')}, Rust: {cv_result.get('rust_detected')}
- Vegetation risk: {cv_result.get('vegetation_risk')}, Overall condition: {cv_result.get('overall_condition')}

Previous ML risk score: {prediction.get('risk_score')}/100. Provide an updated maintenance recommendation integrating these CV findings."""

def build_storm_analysis_prompt(poles: List[Dict], predictions: List[Dict], weather: Dict) -> str:
    critical = [p for p, pr in zip(poles, predictions) if pr.get('risk_score',0) >= 60]
    critical_summary = "\n".join([f"- {p['pole_id']} ({p['district']}): Risk {pr['risk_score']}, StormFail {pr.get('storm_failure_probability',0)*100:.0f}%" 
                                   for p, pr in zip(poles[:10], predictions[:10])])
    return f"""DTE Energy Storm Impact Analysis
Current weather: {weather.get('current',{}).get('wind_mph',0)} mph wind, gusts {weather.get('current',{}).get('gust_mph',0)} mph. Storm alert: {weather.get('storm_alert','None')}.
Number of poles analyzed: {len(predictions)}. High‑risk poles (≥60):
{critical_summary}

Provide: 1) Failure sequence, 2) Estimated customers affected, 3) Pre‑storm crew deployment plan, 4) Restoration priority, 5) Emergency cost estimate."""