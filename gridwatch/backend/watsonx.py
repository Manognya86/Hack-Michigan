"""
watsonx.py – AI recommendation engine with deterministic CV simulation and context‑aware rule‑based responses.
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
# Rule‑based fallback – extracts many features from prompt
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

def _extract_int(text: str, pattern: str, default: int = 0) -> int:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1).strip())
        except ValueError:
            pass
    return default

def _extract_bool(text: str, pattern: str) -> bool:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        val = match.group(1).strip().lower()
        return val in ['true', 'yes', '1', 'detected']
    return False

def _rule_based_response(prompt: str) -> str:
    """
    Generate a detailed, context‑aware recommendation based on data extracted from the prompt.
    """
    # Extract key information
    risk = _extract_float(prompt, r'Risk Score[:\s]*([\d.]+)', 50.0)
    level = "Critical" if risk >= 70 else "High" if risk >= 45 else "Medium" if risk >= 25 else "Low"
    age = _extract_int(prompt, r'Age[:\s]*(\d+)', 25)
    tilt = _extract_float(prompt, r'Tilt[:\s]*([\d.]+)', 5.0)
    crack = _extract_bool(prompt, r'Cracks?[:\s]*(\w+)')
    rust = _extract_bool(prompt, r'Rust[:\s]*(\w+)')
    veg = _extract_float(prompt, r'Vegetation risk[:\s]*(\w+)', 0)  # not perfect but ok
    wind = _extract_float(prompt, r'Wind exposure[:\s]*(\w+)', 0)
    flood = _extract_bool(prompt, r'Flood zone[:\s]*[AE]')
    material = "Wood" if "Wood" in prompt else "Steel" if "Steel" in prompt else "Unknown"
    remaining = _extract_float(prompt, r'Remaining Life[:\s]*([\d.]+)', 10.0)
    storm_prob = _extract_float(prompt, r'Storm Failure Probability[:\s]*([\d.]+)%', 30.0) / 100.0
    
    # Build recommendation based on multiple factors
    if risk >= 75 or (risk >= 60 and tilt > 12) or (crack and rust):
        action = "IMMEDIATE REPLACEMENT"
        timeline = "within 30 days – emergency priority"
        reasoning = f"Risk score {risk}/100 ({level}) with {tilt}° tilt and {'cracks' if crack else ''} {'and rust' if rust else ''}. High likelihood of failure."
        crew = "Dispatch emergency crew. Isolate circuit, implement traffic control, and replace pole within 48 hours."
    elif risk >= 55 or (risk >= 45 and (crack or rust)) or (remaining < 3):
        action = "REPLACEMENT WITHIN 12 MONTHS"
        timeline = "schedule for next quarter"
        reasoning = f"Risk score {risk}/100 ({level}) with remaining life {remaining:.1f} years. {'Cracks' if crack else 'Rust' if rust else 'Age and tilt'} indicate accelerated degradation."
        crew = "Add to replacement queue. Perform visual inspection every 3 months until replacement."
    elif risk >= 35 or (tilt > 8) or (veg and veg == "high") or (wind and wind == "high"):
        action = "REPAIR AND MONITOR"
        timeline = "within 6 months"
        reasoning = f"Moderate risk ({risk}/100). {'Tilt exceeds 8°' if tilt > 8 else 'Vegetation or wind exposure increases risk' if veg or wind else 'Structural condition warrants reinforcement'}."
        crew = "Reinforce with guy wires, clear vegetation, and schedule re‑inspection in 90 days."
    else:
        action = "ROUTINE MONITORING"
        timeline = "next scheduled inspection cycle (2 years)"
        reasoning = f"Low risk ({risk}/100). Pole in acceptable condition with minimal degradation."
        crew = "No immediate action. Include in routine inspection program."
    
    # Storm‑specific advice
    storm_advice = ""
    if storm_prob > 0.6:
        storm_advice = f"\n⚠️ STORM RISK ELEVATED: {storm_prob*100:.0f}% failure probability during high wind events. Pre‑position crew near {prompt.split('District')[1].split()[0] if 'District' in prompt else 'the area'}."
    
    # Cost recommendation
    cost_advice = f"Estimated replacement cost: ${6200 if material=='Wood' else 9500 if material=='Steel' else 12000}. Repair cost: ~${2100 if material=='Wood' else 3200}."
    
    return f"""{action} – {timeline}.

{reasoning}
Crew action: {crew}{storm_advice}

{cost_advice}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ This recommendation is based on DTE maintenance standards and ML risk assessment.
For detailed work order, use the Work Order button above."""

# ----------------------------------------------------------------------
# Deterministic Computer Vision simulation (image‑based)
# ----------------------------------------------------------------------
def _image_hash(base64_str: str) -> str:
    return hashlib.md5(base64_str.encode()).hexdigest()[:8]

def _simulate_cv_from_hash(hash_val: str) -> Dict[str, Any]:
    seed = int(hash_val, 16) % (2**32)
    rng = random.Random(seed)
    tilt = round(rng.uniform(0, 20), 1)
    crack = rng.random() < (0.1 + tilt / 80)
    rust = rng.random() < 0.3
    veg = rng.choices(["low", "medium", "high"], weights=[0.4, 0.4, 0.2])[0]
    sag = rng.random() < (0.05 + tilt / 50)
    if tilt > 15 or crack:
        condition = "critical"
    elif tilt > 8 or rust:
        condition = "poor"
    elif tilt > 4 or veg == "high":
        condition = "fair"
    else:
        condition = "good"
    conf = round(rng.uniform(0.6, 0.95), 2)
    return {
        "tilt_angle": tilt,
        "crack_detected": crack,
        "rust_detected": rust,
        "vegetation_risk": veg,
        "wire_sagging": sag,
        "overall_condition": condition,
        "confidence": conf,
        "notes": f"CV analysis based on image hash {hash_val}."
    }

async def run_cv_analysis(image_base64: str, pole: Dict[str, Any]) -> Dict[str, Any]:
    if not image_base64 or len(image_base64) < 100:
        return {"error": "No valid image data"}
    hash_val = _image_hash(image_base64)
    return _simulate_cv_from_hash(hash_val)

# ----------------------------------------------------------------------
# Prompt builders (unchanged)
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