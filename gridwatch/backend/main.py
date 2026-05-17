"""
main.py – FastAPI backend for GridWatch AI.
All endpoints: region, predict, storm, CV, AI, analytics, heatmap, PDF, priority,
historical storms, feedback, savings, cost optimization, fleet assignment, 3D,
explainability, CSV export, risk history, model retraining.
"""

import os
import asyncio
import logging
import base64
import json
import csv
import numpy as np
import webbrowser
import threading
import time
from datetime import datetime, date
from typing import Dict, List, Any, Optional
from collections import defaultdict
from io import StringIO

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

load_dotenv()

from ml_model import (
    load_bundle, predict_pole, predict_batch, get_model_metrics,
    get_feature_importance_report, train_models, save_bundle,
    generate_explanation
)
from data_pipeline import fetch_region_data, fetch_weather, fetch_historical_storms
from watsonx import (
    call_granite, run_cv_analysis,
    build_maintenance_prompt, build_storm_analysis_prompt,
    build_work_order_prompt, build_schedule_prompt,
    build_cv_followup_prompt
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GridWatch AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

def convert_numpy(obj):
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy(i) for i in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy(i) for i in obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    else:
        return obj

# ── Cache and model ──────────────────────────────────────────────────────────
_cache: Dict[str, Any] = {
    "region_data": None,
    "weather": None,
    "predictions": [],
    "last_refresh": None,
    "historical_storms": [],
}
_model_bundle = None

def get_model():
    global _model_bundle
    if _model_bundle is None:
        try:
            _model_bundle = load_bundle(os.environ.get("MODEL_PATH", "../models/risk_model.pkl"))
            logger.info("Model loaded successfully")
        except FileNotFoundError:
            logger.warning("Model not found — run train_model.py first. Using rule-based fallback.")
    return _model_bundle

# ── Pydantic models ──────────────────────────────────────────────────────────
class PoleInput(BaseModel):
    pole_id: str = "CUSTOM-001"
    lat: float = 42.33
    lng: float = -83.05
    district: str = "Detroit"
    age: int = 25
    material: str = "Wood"
    tilt_angle: float = 5.0
    crack_detected: bool = False
    rust_detected: bool = False
    vegetation_risk: str = "medium"
    wind_exposure: str = "medium"
    flood_zone: str = "X"
    soil_type: str = "Loam"
    storm_exposure_index: float = 0.4
    urban_density: float = 0.7
    last_inspection: str = "2022-01-01"
    years_since_inspection: float = 2.0
    live_wind_mph: float = 0.0
    height_ft: float = 35.0
    road_proximity_ft: float = 50.0
    num_transformers: int = 1
    last_maintenance_year: int = 2018
    aqi: int = 50
    soil_moisture: float = 0.5

class WatsonxRequest(BaseModel):
    pole_id: str
    prompt_type: str = "maintenance"
    cv_result: Optional[Dict] = None

class StormSimRequest(BaseModel):
    wind_mph: float = 60.0
    gust_mph: float = 75.0
    precipitation_in: float = 2.0

class CostOptimizeRequest(BaseModel):
    budget_usd: float = 100000
    max_poles: int = 20

class FleetAssignmentRequest(BaseModel):
    crew_count: int = 3
    max_poles_per_crew: int = 5

# ── Background refresh and helpers ──────────────────────────────────────────
async def _refresh_region_data(n_poles: int = 150):
    logger.info("Fetching region data...")
    try:
        data = await fetch_region_data(n_poles=n_poles)
        bundle = get_model()
        poles = data["poles"]
        if bundle:
            preds = predict_batch(bundle, poles)
        else:
            preds = [_rule_based_predict(p) for p in poles]
        _cache["region_data"] = data
        _cache["weather"] = data["weather"]
        _cache["predictions"] = preds
        _cache["last_refresh"] = datetime.utcnow().isoformat()
        # Update risk history after each refresh
        update_risk_history(preds)
        logger.info(f"Region data refreshed: {len(poles)} poles")
    except Exception as e:
        logger.error(f"Region refresh failed: {e}")
        _cache["predictions"] = []

async def _refresh_historical_storms():
    try:
        storms = await fetch_historical_storms(days_back=30)
        _cache["historical_storms"] = storms
        logger.info(f"Fetched {len(storms)} historical storms")
    except Exception as e:
        logger.error(f"Historical storms failed: {e}")

def _rule_based_predict(pole: Dict) -> Dict:
    score = 0
    score += min(pole.get("age", 20) * 0.7, 25)
    score += min(pole.get("tilt_angle", 0) * 1.0, 15)
    if pole.get("crack_detected"): score += 12
    if pole.get("rust_detected"): score += 7
    veg = pole.get("vegetation_risk", "medium")
    if veg == "high": score += 10
    elif veg == "medium": score += 4
    wind = pole.get("wind_exposure", "medium")
    if wind == "high": score += 8
    elif wind == "medium": score += 3
    if pole.get("flood_zone") in ["AE","A"]: score += 8
    if pole.get("material") == "Wood": score += 4
    elif pole.get("material") == "Steel": score += 2
    if pole.get("soil_type") == "Clay": score += 3
    score += min(pole.get("years_since_inspection", 2) * 1.5, 8)
    score += pole.get("storm_exposure_index", 0.4) * 10
    height = pole.get("height_ft", 35)
    score += min((height - 30) * 0.2, 4) if height > 30 else 0
    road = pole.get("road_proximity_ft", 50)
    score += max(0, (100 - road) * 0.08) if road < 100 else 0
    score += min(pole.get("num_transformers", 1) * 1.5, 6)
    last_maint = pole.get("last_maintenance_year", 2018)
    score += min((2024 - last_maint) * 1.2, 12)
    aqi = pole.get("aqi", 50)
    soil_moisture = pole.get("soil_moisture", 0.5)
    score += min(max(0, (aqi - 100) / 20), 10)
    score += soil_moisture * 5
    risk_score = float(np.clip(score, 0, 100))
    storm_prob = min(0.3 + risk_score/100 * 0.6, 0.95)
    costs = {"Wood": (6200,2100), "Steel": (9500,3200), "Concrete": (12000,4000), "Composite": (11000,3800)}
    rc, rpc = costs.get(pole.get("material","Wood"), (6200,2100))
    design = {"Wood":40, "Steel":65, "Concrete":70, "Composite":50}.get(pole.get("material","Wood"),45)
    remaining = max(0.5, design - pole.get("age",20) - (risk_score/100)*10)
    level = "Critical" if risk_score >=70 else "High" if risk_score >=45 else "Medium" if risk_score >=25 else "Low"
    rec = "immediate_replacement" if risk_score >=75 else "replacement_within_12_months" if risk_score >=55 else "repair_and_monitor" if risk_score >=35 else "routine_inspection"
    priority = 0.5 * risk_score + 0.3 * (storm_prob * 100) + 0.2 * (rc / 20000 * 100)
    optimal = {
        "action": "Immediate Replacement" if risk_score>=75 else "Replace within 12 months" if remaining<2 else "Repair & Reinforce" if rc>rpc*3 else "Monitor & Schedule Inspection",
        "rationale": f"Risk {risk_score}, remaining life {remaining:.1f}y"
    }
    return {**pole, "risk_score": round(risk_score,1), "risk_level": level,
            "failure_probability": round(risk_score/100*0.8+0.05,3),
            "storm_failure_probability": round(storm_prob,3),
            "remaining_life_years": round(remaining,1), "replace_cost_usd": rc, "repair_cost_usd": rpc,
            "recommendation": rec, "priority_score": round(priority,1), "optimal_action": optimal,
            "top_risk_factors": [], "model_confidence": 0.72,
            "environmental_factors": {"aqi": aqi, "soil_moisture": soil_moisture}}

def _get_predictions_map() -> Dict[str, Dict]:
    return {p["pole_id"]: p for p in (_cache.get("predictions") or [])}

# ── Risk history storage (JSON file) ──────────────────────────────────────────
HISTORY_FILE = "risk_history.json"

def load_risk_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_risk_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def update_risk_history(preds: List[Dict]):
    """Store current risk scores for all poles with today's date."""
    if not preds:
        return
    today = date.today().isoformat()
    history = load_risk_history()
    for pole in preds:
        pid = pole["pole_id"]
        if pid not in history:
            history[pid] = {}
        history[pid][today] = pole["risk_score"]
    # Keep only last 90 days (optional cleanup)
    for pid in history:
        if len(history[pid]) > 90:
            # remove oldest entries
            sorted_dates = sorted(history[pid].keys())
            for old_date in sorted_dates[:-90]:
                del history[pid][old_date]
    save_risk_history(history)

# ── Feedback and savings storage ──────────────────────────────────────────────
FEEDBACK_FILE = "feedback.json"
SAVINGS_FILE = "savings.json"

def load_feedback():
    try:
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_feedback(feedback):
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(feedback, f, indent=2)

def load_savings():
    try:
        with open(SAVINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"total_savings": 0, "actions": []}

def save_savings(savings):
    with open(SAVINGS_FILE, "w") as f:
        json.dump(savings, f, indent=2)

# ── Startup tasks ────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    get_model()
    asyncio.create_task(_refresh_region_data(150))
    asyncio.create_task(_refresh_historical_storms())
    async def periodic():
        while True:
            await asyncio.sleep(3600)
            await _refresh_region_data(150)
            await _refresh_historical_storms()
    asyncio.create_task(periodic())

# ── Health and status ────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return convert_numpy({"status": "ok", "model_loaded": _model_bundle is not None,
                          "poles_cached": len(_cache.get("predictions") or []),
                          "last_refresh": _cache.get("last_refresh")})

@app.get("/api/status")
async def system_status():
    preds = _cache.get("predictions") or []
    metrics = get_model_metrics(get_model()) if get_model() else {}
    return convert_numpy({
        "status": "operational",
        "model_loaded": _model_bundle is not None,
        "total_poles": len(preds),
        "critical_poles": sum(1 for p in preds if p.get("risk_score",0)>=70),
        "last_refresh": _cache.get("last_refresh"),
        "model_metrics": metrics,
        "historical_storms_count": len(_cache.get("historical_storms", [])),
        "uptime_seconds": (datetime.utcnow() - datetime.fromisoformat(_cache.get("last_refresh","2024-01-01T00:00:00"))).total_seconds() if _cache.get("last_refresh") else 0,
    })

# ── Region data ──────────────────────────────────────────────────────────────
@app.get("/api/region")
async def get_region(background_tasks: BackgroundTasks):
    preds = _cache.get("predictions")
    if not preds:
        await _refresh_region_data(150)
        preds = _cache.get("predictions") or []
    else:
        background_tasks.add_task(_refresh_region_data, 150)
    weather = _cache.get("weather", {})
    stats = {
        "total": len(preds),
        "critical": sum(1 for p in preds if p.get("risk_score",0)>=70),
        "high": sum(1 for p in preds if 45<=p.get("risk_score",0)<70),
        "medium": sum(1 for p in preds if 25<=p.get("risk_score",0)<45),
        "low": sum(1 for p in preds if p.get("risk_score",0)<25),
        "avg_risk": round(sum(p.get("risk_score",0) for p in preds)/max(len(preds),1),1),
        "total_replace_cost_usd": sum(p.get("replace_cost_usd",0) for p in preds),
        "priority_cost_usd": sum(p.get("replace_cost_usd",0) for p in preds if p.get("risk_score",0)>=70),
    }
    return convert_numpy({"poles": preds, "weather": weather, "stats": stats,
                          "last_refresh": _cache.get("last_refresh")})

@app.post("/api/refresh")
async def force_refresh():
    await _refresh_region_data(150)
    await _refresh_historical_storms()
    return {"status": "refreshed", "poles": len(_cache.get("predictions",[]))}

# ── Single pole predictions ──────────────────────────────────────────────────
@app.post("/api/predict")
async def predict_single(pole: PoleInput):
    bundle = get_model()
    pole_dict = pole.dict()
    if bundle:
        result = predict_pole(bundle, pole_dict)
    else:
        result = _rule_based_predict(pole_dict)
    return convert_numpy({**pole_dict, **result})

@app.get("/api/pole/{pole_id}")
async def get_pole(pole_id: str):
    pmap = _get_predictions_map()
    if pole_id not in pmap:
        raise HTTPException(404, f"Pole {pole_id} not found")
    return convert_numpy(pmap[pole_id])

# ── Weather ─────────────────────────────────────────────────────────────────
@app.get("/api/weather")
async def get_weather(lat: float = 42.33, lng: float = -83.05):
    return convert_numpy(await fetch_weather(lat, lng))

# ── Heatmap (for frontend) ──────────────────────────────────────────────────
@app.get("/api/heatmap")
async def get_heatmap_data():
    preds = _cache.get("predictions") or []
    points = [{"lat": p["lat"], "lng": p["lng"], "risk": p["risk_score"], "priority": p.get("priority_score",0)}
              for p in preds if "lat" in p and "lng" in p]
    return convert_numpy({"points": points})

# ── PDF report ───────────────────────────────────────────────────────────────
@app.get("/api/report")
async def generate_pdf_report():
    preds = _cache.get("predictions") or []
    if not preds:
        raise HTTPException(404, "No data available")
    sorted_poles = sorted(preds, key=lambda p: p.get("priority_score", 0), reverse=True)
    top_poles = sorted_poles[:20]
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "GridWatch AI - Priority Maintenance Report")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, height - 85, f"Total poles analyzed: {len(preds)}")
    c.drawString(50, height - 100, "Top 20 poles by Priority Score (higher = more urgent):")
    y = height - 120
    for i, p in enumerate(top_poles):
        if y < 50:
            c.showPage()
            y = height - 50
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{i+1}. {p['pole_id']} - {p['district']}")
        c.setFont("Helvetica", 9)
        c.drawString(70, y - 12, f"Risk: {p['risk_score']} | Priority: {p.get('priority_score',0)}")
        c.drawString(70, y - 24, f"Optimal action: {p.get('optimal_action',{}).get('action','N/A')}")
        c.drawString(70, y - 36, f"Remaining life: {p.get('remaining_life_years',0)} yrs | Replace cost: ${p.get('replace_cost_usd',0):,}")
        y -= 50
    c.save()
    buffer.seek(0)
    return Response(buffer.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=gridwatch_priority_report.pdf"})

# ── Priority list (for priority tab) ────────────────────────────────────────
@app.get("/api/priority")
async def get_priority_list():
    preds = _cache.get("predictions") or []
    if not preds:
        return {"error": "No data – please refresh or wait for initial load."}
    sorted_poles = sorted(preds, key=lambda p: p.get("priority_score", 0), reverse=True)
    top20 = [{
        "pole_id": p["pole_id"],
        "district": p["district"],
        "priority_score": p.get("priority_score"),
        "risk_score": p["risk_score"],
        "storm_failure_probability": p.get("storm_failure_probability"),
        "recommendation": p["recommendation"],
        "optimal_action": p.get("optimal_action", {}).get("action", ""),
    } for p in sorted_poles[:20]]
    return convert_numpy({"top_priority_poles": top20, "total_poles": len(preds)})

# ── Historical storm prediction ──────────────────────────────────────────────
@app.get("/api/storm/historical")
async def get_historical_storm_predictions():
    preds = _cache.get("predictions") or []
    if not preds:
        await _refresh_region_data(150)
        preds = _cache.get("predictions") or []
    historical = _cache.get("historical_storms", [])
    weather = _cache.get("weather", {})
    current_gust = weather.get("current", {}).get("gust_mph", 0)
    similar = [s for s in historical if abs(s["gust_mph"] - current_gust) < 10]
    avg_fail_rate = 0.45 if similar else 0.25
    for p in preds:
        p["historical_storm_risk"] = round(avg_fail_rate + p.get("risk_score",50)/100 * 0.3, 3)
    return convert_numpy({
        "similar_storms": similar,
        "average_storm_failure_rate": avg_fail_rate,
        "poles_updated": len(preds),
        "recommendation": "High alert" if current_gust > 40 else "Normal"
    })

# ── Storm simulation ────────────────────────────────────────────────────────
@app.post("/api/storm/simulate")
async def simulate_storm(req: StormSimRequest):
    preds = _cache.get("predictions") or []
    if not preds:
        await _refresh_region_data(150)
        preds = _cache.get("predictions") or []
    storm_idx = min(req.gust_mph / 80, 1.0)
    simulated = []
    for p in preds:
        base = p.get("storm_failure_probability", 0.3)
        risk = p.get("risk_score", 50)
        adj = min(base + storm_idx * 0.25 + (risk/100)*0.15, 0.98)
        simulated.append({**p, "storm_failure_probability": round(adj,3), "will_fail": adj > 0.65,
                          "storm_wind_mph": req.wind_mph, "storm_gust_mph": req.gust_mph})
    failing = [p for p in simulated if p.get("will_fail")]
    return convert_numpy({"poles": simulated, "storm_params": req.dict(),
                          "impact": {"poles_failing": len(failing), "total_poles": len(simulated),
                                     "failure_rate": round(len(failing)/max(len(simulated),1),3),
                                     "estimated_customers_affected": len(failing)*85,
                                     "emergency_cost_usd": sum(p.get("replace_cost_usd",6200)*1.4 for p in failing),
                                     "districts_affected": list({p.get("district") for p in failing})}})

# ── Computer vision ─────────────────────────────────────────────────────────
@app.post("/api/cv/analyze")
async def analyze_image(file: UploadFile = File(...), pole_id: Optional[str] = None):
    contents = await file.read()
    if len(contents) > 10*1024*1024:
        raise HTTPException(413, "Image too large")
    image_b64 = base64.b64encode(contents).decode()
    pmap = _get_predictions_map()
    pole = pmap.get(pole_id, {"pole_id": pole_id or "unknown"})
    cv_result = await run_cv_analysis(image_b64, pole)
    if "error" not in cv_result:
        bundle = get_model()
        merged = {**pole}
        merged["tilt_angle"] = cv_result.get("tilt_angle", pole.get("tilt_angle",5))
        merged["crack_detected"] = int(cv_result.get("crack_detected", pole.get("crack_detected",False)))
        merged["rust_detected"] = int(cv_result.get("rust_detected", pole.get("rust_detected",False)))
        veg_map = {"high":"high","medium":"medium","low":"low"}
        merged["vegetation_risk"] = veg_map.get(cv_result.get("vegetation_risk","medium"),"medium")
        updated = predict_pole(bundle, merged) if bundle else _rule_based_predict(merged)
        return convert_numpy({"pole_id": pole_id, "cv_result": cv_result, "updated_prediction": updated,
                              "original_prediction": pmap.get(pole_id,{}),
                              "risk_delta": round(updated["risk_score"] - pmap.get(pole_id,{}).get("risk_score",updated["risk_score"]),1)})
    return convert_numpy({"pole_id": pole_id, "cv_result": cv_result, "updated_prediction": None})

# ── watsonx.ai endpoints ─────────────────────────────────────────────────────
@app.post("/api/ai/recommend")
async def ai_recommend(req: WatsonxRequest):
    pmap = _get_predictions_map()
    pole = pmap.get(req.pole_id)
    if not pole:
        raise HTTPException(404, f"Pole {req.pole_id} not found")
    weather = _cache.get("weather", {})
    bundle = get_model()
    pred = pole if "risk_score" in pole else (predict_pole(bundle, pole) if bundle else _rule_based_predict(pole))
    if req.prompt_type == "maintenance":
        prompt = build_maintenance_prompt(pole, pred, weather)
    elif req.prompt_type == "work_order":
        prompt = build_work_order_prompt(pole, pred)
    elif req.prompt_type == "schedule":
        prompt = build_schedule_prompt(pole, pred)
    elif req.prompt_type == "cv_followup" and req.cv_result:
        prompt = build_cv_followup_prompt(req.cv_result, pole, pred)
    else:
        prompt = build_maintenance_prompt(pole, pred, weather)
    ai_text = await call_granite(prompt)
    return convert_numpy({"pole_id": req.pole_id, "prompt_type": req.prompt_type,
                          "ai_response": ai_text, "model": "ibm/granite-13b-instruct-v2 (rule-based fallback)",
                          "generated_at": datetime.utcnow().isoformat()})

@app.post("/api/ai/storm-analysis")
async def ai_storm_analysis():
    preds = _cache.get("predictions") or []
    if not preds:
        await _refresh_region_data(150)
        preds = _cache.get("predictions") or []
    weather = _cache.get("weather", {})
    prompt = build_storm_analysis_prompt([], preds, weather)
    ai_text = await call_granite(prompt, max_tokens=1000)
    return convert_numpy({"ai_response": ai_text, "poles_analyzed": len(preds), "weather": weather})

@app.post("/api/ai/region-report")
async def ai_region_report():
    preds = _cache.get("predictions") or []
    weather = _cache.get("weather", {})
    critical = [p for p in preds if p.get("risk_score",0)>=70]
    high = [p for p in preds if 45<=p.get("risk_score",0)<70]
    prompt = f"""DTE Energy Metro Detroit — Full Territory Maintenance Priority Report
Date: {datetime.now().strftime('%B %d, %Y')} | Poles Analyzed: {len(preds)}
Weather: {weather.get('current',{}).get('wind_mph',0)} mph wind, Alert: {weather.get('storm_alert','None')}
CRITICAL POLES ({len(critical)}):
{chr(10).join([f"  {p['pole_id']} ({p['district']}): Score {p['risk_score']}, {p['material']}, Age {p['age']}yr" for p in critical[:6]])}
HIGH RISK ({len(high)}):
{chr(10).join([f"  {p['pole_id']} ({p['district']}): Score {p['risk_score']}" for p in high[:4]])}
Total Budget Required: ${sum(p.get('replace_cost_usd',0) for p in critical):,} (critical) + ${sum(p.get('replace_cost_usd',0) for p in high):,} (high)
Provide:
1. EXECUTIVE SUMMARY
2. TOP 5 PRIORITY POLES
3. Q3 2026 BUDGET ALLOCATION
4. CREW DEPLOYMENT PLAN
5. 90-DAY ACTION PLAN
6. RISK REDUCTION PROJECTION"""
    ai_text = await call_granite(prompt, max_tokens=1000)
    return convert_numpy({"ai_response": ai_text, "poles_analyzed": len(preds)})

# ── Analytics ────────────────────────────────────────────────────────────────
@app.get("/api/analytics")
async def get_analytics():
    preds = _cache.get("predictions") or []
    if not preds:
        return {"error": "No data"}
    district_stats = defaultdict(lambda: {"count":0, "total_risk":0})
    for p in preds:
        d = p.get("district","Unknown")
        district_stats[d]["count"] += 1
        district_stats[d]["total_risk"] += p.get("risk_score",0)
    district_data = [{"district":d, "avg_risk": round(v["total_risk"]/v["count"],1)} for d,v in district_stats.items()]
    bins = [0,10,20,30,40,50,60,70,80,90,100]
    hist = [0]*(len(bins)-1)
    for p in preds:
        s = p.get("risk_score",0)
        for i in range(len(bins)-1):
            if bins[i] <= s < bins[i+1]:
                hist[i]+=1
                break
    material_risk = defaultdict(list)
    for p in preds:
        material_risk[p.get("material","Unknown")].append(p.get("risk_score",0))
    material_data = [{"material":m, "avg_risk": round(sum(v)/len(v),1)} for m,v in material_risk.items()]
    age_risk = [{"age":p.get("age",0), "risk":p.get("risk_score",0)} for p in preds[:100]]
    return convert_numpy({"district_data": district_data,
                          "risk_histogram": [{"range": f"{bins[i]}-{bins[i+1]}", "count": hist[i]} for i in range(len(hist))],
                          "material_data": material_data, "age_risk_scatter": age_risk,
                          "feature_importance": get_feature_importance_report(get_model()) if get_model() else [],
                          "model_metrics": get_model_metrics(get_model()) if get_model() else {},
                          "total_poles": len(preds), "total_replacement_cost": sum(p.get("replace_cost_usd",0) for p in preds),
                          "avg_remaining_life": round(sum(p.get("remaining_life_years",10) for p in preds)/max(len(preds),1),1)})

@app.get("/api/model/info")
async def model_info():
    bundle = get_model()
    if not bundle:
        return convert_numpy({"status": "not_loaded", "message": "Run train_model.py first"})
    return convert_numpy({
        "status": "loaded",
        "features": bundle.get("feature_cols", []),
        "metrics": get_model_metrics(bundle),
        "feature_importance": get_feature_importance_report(bundle),
        "models": ["XGBRegressor (risk_score)", "XGBClassifier (failure)", "XGBRegressor (storm_prob)"],
    })

# ── Explainability ──────────────────────────────────────────────────────────
@app.get("/api/explain/{pole_id}")
async def get_explanation(pole_id: str):
    pmap = _get_predictions_map()
    pole = pmap.get(pole_id)
    if not pole:
        raise HTTPException(404, f"Pole {pole_id} not found")
    if "risk_score" not in pole:
        bundle = get_model()
        if bundle:
            pred = predict_pole(bundle, pole)
        else:
            pred = _rule_based_predict(pole)
        pole.update(pred)
    explanation = generate_explanation(pole, pole)
    return convert_numpy(explanation)

# ── Feedback and savings ─────────────────────────────────────────────────────
@app.post("/api/feedback/{pole_id}")
async def add_feedback(pole_id: str, feedback: str):
    data = load_feedback()
    data.append({"pole_id": pole_id, "feedback": feedback, "timestamp": datetime.now().isoformat()})
    save_feedback(data)
    return {"status": "feedback recorded", "total_feedback": len(data)}

@app.post("/api/record_action/{pole_id}")
async def record_action(pole_id: str, action: str):
    pmap = _get_predictions_map()
    pole = pmap.get(pole_id)
    if not pole:
        raise HTTPException(404, "Pole not found")
    cost = pole.get("repair_cost_usd", 2100) if action == "repaired" else pole.get("replace_cost_usd", 6200)
    outage_cost = 5000  # simulated average outage cost per pole
    savings = outage_cost - cost
    savings_data = load_savings()
    savings_data["total_savings"] += savings
    savings_data["actions"].append({
        "pole_id": pole_id,
        "action": action,
        "cost": cost,
        "savings": savings,
        "timestamp": datetime.now().isoformat()
    })
    save_savings(savings_data)
    return {"savings": savings, "total_savings": savings_data["total_savings"]}

@app.get("/api/savings")
async def get_savings():
    return load_savings()

# ── Risk history endpoint ────────────────────────────────────────────────────
@app.get("/api/risk_history/{pole_id}")
async def get_risk_history(pole_id: str, days: int = 30):
    history = load_risk_history()
    if pole_id not in history:
        return {"history": []}
    hist = history[pole_id]
    sorted_items = sorted(hist.items(), key=lambda x: x[0])
    # limit to last `days`
    if len(sorted_items) > days:
        sorted_items = sorted_items[-days:]
    return {"pole_id": pole_id, "history": [{"date": d, "risk": r} for d, r in sorted_items]}

# ── CSV Export ───────────────────────────────────────────────────────────────
@app.get("/api/export/csv")
async def export_csv():
    preds = _cache.get("predictions", [])
    if not preds:
        raise HTTPException(404, "No data to export")
    output = StringIO()
    writer = csv.writer(output)
    # Write header
    headers = ["pole_id", "lat", "lng", "district", "age", "material", "tilt_angle", "crack_detected",
               "rust_detected", "vegetation_risk", "wind_exposure", "flood_zone", "soil_type",
               "storm_exposure_index", "years_since_inspection", "urban_density", "last_inspection",
               "height_ft", "road_proximity_ft", "num_transformers", "last_maintenance_year",
               "aqi", "soil_moisture", "risk_score", "risk_level", "failure_probability",
               "storm_failure_probability", "remaining_life_years", "replace_cost_usd",
               "repair_cost_usd", "recommendation", "priority_score"]
    writer.writerow(headers)
    for p in preds:
        row = [p.get(h, "") for h in headers]
        writer.writerow(row)
    response = Response(output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=gridwatch_export.csv"
    return response

# ── Cost optimization ────────────────────────────────────────────────────────
@app.post("/api/cost/optimize")
async def cost_optimization(req: CostOptimizeRequest):
    preds = _cache.get("predictions") or []
    if not preds:
        raise HTTPException(404, "No pole data available")
    items = []
    for p in preds:
        if p.get("priority_score",0) >= 70:
            cost = p["replace_cost_usd"]
            benefit = p["priority_score"] * 2
            action = "replace"
        else:
            cost = p["repair_cost_usd"]
            benefit = p["priority_score"]
            action = "repair"
        items.append({"pole_id": p["pole_id"], "cost": cost, "benefit": benefit, "action": action, "priority": p.get("priority_score",0)})
    items.sort(key=lambda x: x["benefit"]/max(x["cost"],1), reverse=True)
    selected = []
    remaining_budget = req.budget_usd
    for item in items[:req.max_poles]:
        if item["cost"] <= remaining_budget:
            selected.append(item)
            remaining_budget -= item["cost"]
    return convert_numpy({
        "budget_usd": req.budget_usd,
        "remaining_budget": round(remaining_budget,2),
        "selected_poles": selected,
        "total_benefit": sum(s["benefit"] for s in selected),
        "total_cost": sum(s["cost"] for s in selected)
    })

# ── Fleet assignment ────────────────────────────────────────────────────────
@app.post("/api/fleet/assignment")
async def fleet_assignment(req: FleetAssignmentRequest):
    preds = _cache.get("predictions") or []
    if not preds:
        raise HTTPException(404, "No pole data available")
    sorted_poles = sorted(preds, key=lambda p: p.get("priority_score",0), reverse=True)
    assignments = {f"Crew {i+1}": [] for i in range(req.crew_count)}
    for idx, pole in enumerate(sorted_poles[:req.crew_count * req.max_poles_per_crew]):
        crew_idx = idx % req.crew_count
        assignments[f"Crew {crew_idx+1}"].append({
            "pole_id": pole["pole_id"],
            "district": pole["district"],
            "priority_score": pole.get("priority_score",0),
            "action": pole.get("optimal_action",{}).get("action","Inspect"),
            "lat": pole.get("lat"),
            "lng": pole.get("lng")
        })
    return convert_numpy({
        "crew_count": req.crew_count,
        "max_poles_per_crew": req.max_poles_per_crew,
        "assignments": assignments,
        "total_poles_assigned": sum(len(v) for v in assignments.values())
    })

# ── 3D model endpoint ───────────────────────────────────────────────────────
@app.get("/api/3d_model/{pole_id}")
async def get_3d_model(pole_id: str):
    pmap = _get_predictions_map()
    pole = pmap.get(pole_id)
    if not pole:
        raise HTTPException(404, "Pole not found")
    color = "red" if pole.get("risk_score",0) >= 70 else "orange" if pole.get("risk_score",0) >= 45 else "yellow" if pole.get("risk_score",0) >= 25 else "green"
    return convert_numpy({
        "pole_id": pole_id,
        "height": pole.get("height_ft", 35),
        "radius": 0.5,
        "color": color,
        "damage": {
            "crack": pole.get("crack_detected", False),
            "rust": pole.get("rust_detected", False),
            "tilt": pole.get("tilt_angle", 0)
        }
    })

# ── Model retraining (manual and with feedback) ─────────────────────────────
@app.post("/api/model/retrain")
async def retrain_model(background_tasks: BackgroundTasks):
    def _retrain():
        import pandas as pd
        df = pd.read_csv("../data/training_poles.csv")
        bundle = train_models(df)
        save_bundle(bundle, "../models/risk_model.pkl")
        global _model_bundle
        _model_bundle = bundle
        logger.info("Model retrained and reloaded")
    background_tasks.add_task(_retrain)
    return {"status": "retraining started"}

@app.post("/api/model/retrain_with_feedback")
async def retrain_with_feedback(background_tasks: BackgroundTasks):
    def _retrain_with_feedback():
        import pandas as pd
        df = pd.read_csv("../data/training_poles.csv")
        feedback = load_feedback()
        logger.info(f"Retraining with {len(feedback)} feedback entries")
        # In a real system, merge feedback labels into dataset
        bundle = train_models(df)
        save_bundle(bundle, "../models/risk_model.pkl")
        global _model_bundle
        _model_bundle = bundle
        logger.info("Model retrained with feedback")
    background_tasks.add_task(_retrain_with_feedback)
    return {"status": "retraining with feedback scheduled"}

# ── Run with auto‑open Chrome ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    def open_chrome():
        time.sleep(1.5)
        try:
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            if os.path.exists(chrome_path):
                webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))
                webbrowser.get('chrome').open('http://localhost:8000')
            else:
                webbrowser.open('http://localhost:8000')
        except Exception as e:
            logger.warning(f"Browser open failed: {e}")
    threading.Thread(target=open_chrome, daemon=True).start()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)