# app.py — GridWatch AI · DTE Energy · Hack Michigan 2026
from config import config, PROJECT_ROOT   
import os
import sys
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import cv2
import numpy as np

# Local modules
from dte_config import get_flood_zone, soil_risk_from_flood_zone
from weather_utils import get_weather_forecast, get_weather_hazard_risk, get_noaa_alerts
from gee_utils import get_ndvi
from ml_model import risk_model
from predictive_model import (init_db, insert_sample_history, train_cost_model,
                               predict_repair_cost, get_historical_storm_impact)
from kml_generator import generate_damage_kml
from osm_utils import fetch_poles_from_osm, enrich_pole_proxy

# IBM watsonx.ai (optional)
try:
    from ibm_watsonx_ai import Credentials, APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    WATSONX_AVAILABLE = True
except ImportError:
    WATSONX_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

# ── App setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

# ── Initialise ML and DB ───────────────────────────────────────────────────
init_db()
insert_sample_history()
train_cost_model()
risk_model.load_model()

# ── watsonx.ai (optional) ──────────────────────────────────────────────────
watsonx_model = None
if WATSONX_AVAILABLE:
    try:
        creds = Credentials(
            url=os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
            api_key=os.getenv("WATSONX_API_KEY"),
        )
        api_client = APIClient(creds)
        watsonx_model = ModelInference(
            model_id="ibm/granite-13b-instruct-v2",
            api_client=api_client,
            project_id=os.getenv("WATSONX_PROJECT_ID"),
        )
        logging.info("watsonx.ai ready.")
    except Exception as e:
        logging.warning(f"watsonx init failed: {e}")


# ── Computer Vision ────────────────────────────────────────────────────────
def analyze_image(image_path: str) -> dict:
    img  = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    crack_score = min(1.0, len([c for c in contours if cv2.contourArea(c) > 100]) / 1000)

    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    tilt = 0.0
    if lines is not None:
        angles = [
            np.arctan2(y2-y1, x2-x1) * 180 / np.pi
            for x1, y1, x2, y2 in lines[:, 0]
        ]
        if angles:
            tilt = float(abs(np.mean(angles)))

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    rust_mask = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([20, 255, 255]))
    rust_pct = float(np.sum(rust_mask > 0) / (img.shape[0] * img.shape[1]))

    veg_pct = float(np.sum(img[:, :, 1] > 100) / (img.shape[0] * img.shape[1]))

    return {
        'tilt_angle':          round(tilt, 2),
        'crack_score':         round(crack_score, 4),
        'rust_percentage':     round(rust_pct, 4),
        'vegetation_proximity': round(veg_pct, 4),
        'material_guess':      'wood' if rust_pct > 0.05 else 'steel',
    }


def get_watsonx_recommendation(prompt: str) -> str:
    if watsonx_model:
        try:
            return watsonx_model.generate_text(prompt=prompt, max_new_tokens=300).strip()
        except Exception as e:
            logging.error(f"watsonx error: {e}")
    return "Inspect within 90 days. Estimated cost $2,500–$5,000. Priority: Medium."


# ── Helper ─────────────────────────────────────────────────────────────────
def _compute_pole_risk(pole: dict, weather_wind: float = 12.0) -> dict:
    """Compute risk score, SHAP explanation, and cost for a pole dict."""
    veg_proxy = (10 - pole.get('veg_score', 5))  # invert: low clearance = high risk
    mat_code  = pole.get('material_code', 0)
    soil      = pole.get('soil_risk', 0)

    features = [
        pole.get('tilt', 0),
        veg_proxy,
        weather_wind,
        soil,
        pole.get('age', 20),
        mat_code,
    ]

    score        = risk_model.predict_risk(features)
    int_score    = int(round(score))
    risk_level   = 'High' if score >= 70 else 'Medium' if score >= 45 else 'Low'
    explanation  = risk_model.explain_prediction(features)
    cost         = predict_repair_cost(score, weather_wind, 0.5,
                                       pole.get('age', 20), pole.get('material', 'wood'))

    return {
        'riskScore':         int_score,
        'risk_level':        risk_level,
        'stormFailProb':     round(min(0.95, score / 100 * 0.85 + 0.05), 2),
        'remainingLife':     round(max(0.5, (100 - score) / 10), 1),
        'estimated_cost':    round(cost, 0),
        'explanation':       explanation,
        'data_confidence':   risk_model.data_confidence([]),
        'features_used':     features,
    }


# ── Routes ─────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


# --- Poles ---
@app.route('/api/poles', methods=['GET'])
def get_poles():
    """Fetch real poles from OSM (SE Michigan) and enrich with proxy features + ML scores."""
    bbox = (42.0, -84.0, 43.0, -82.0)
    raw_poles = fetch_poles_from_osm(bbox, max_poles=250)

    # Fallback demo poles if OSM is unreachable
    if not raw_poles:
        raw_poles = _demo_poles()

    # Get one weather reading for the territory centre (representative)
    weather = get_weather_forecast(42.3314, -83.0458)
    wind    = weather.get('wind_speed_mph', 12)

    results = []
    for pole in raw_poles:
        p = enrich_pole_proxy(pole)
        flood_zone = get_flood_zone(p['lat'], p['lon'])
        p['floodZone']  = flood_zone
        p['soil_risk']  = soil_risk_from_flood_zone(flood_zone)

        risk_data = _compute_pole_risk(p, wind)
        p.update(risk_data)
        results.append(p)

    results.sort(key=lambda x: x['riskScore'], reverse=True)
    return jsonify(results)


# --- SHAP Explain (called on pole click) ---
@app.route('/api/explain', methods=['POST'])
def explain():
    """
    Return SHAP explanation for a set of pole features.
    Called from the frontend when a user selects a pole to see why it is risky.
    """
    data = request.json or {}
    features = [
        float(data.get('tilt_angle', 0)),
        float(data.get('veg_proximity', 5)),
        float(data.get('wind_speed', 12)),
        float(data.get('soil_risk', 0)),
        float(data.get('age', 20)),
        float(data.get('material_code', 0)),
    ]
    explanation = risk_model.explain_prediction(features)
    return jsonify(explanation)


# --- Inspection queue ---
@app.route('/api/inspection_queue', methods=['GET'])
def inspection_queue():
    """
    Return top N poles ranked by risk score with action priorities.
    Designed for field crew dispatchers.
    """
    n = int(request.args.get('n', 20))
    bbox = (42.0, -84.0, 43.0, -82.0)
    poles = fetch_poles_from_osm(bbox, max_poles=250) or _demo_poles()
    weather = get_weather_forecast(42.3314, -83.0458)
    wind = weather.get('wind_speed_mph', 12)

    queue = []
    for pole in poles:
        p = enrich_pole_proxy(pole)
        p['soil_risk'] = soil_risk_from_flood_zone(get_flood_zone(p['lat'], p['lon']))
        rd = _compute_pole_risk(p, wind)
        queue.append({
            'pole_id':        str(p['id']),
            'lat':            p['lat'],
            'lon':            p['lon'],
            'risk_score':     rd['riskScore'],
            'risk_level':     rd['risk_level'],
            'age':            p['age'],
            'material':       p['material'],
            'tilt':           p['tilt'],
            'primary_reason': rd['explanation']['primary_reason'],
            'action':         rd['explanation']['action_summary'],
            'estimated_cost': rd['estimated_cost'],
            'data_confidence': rd['data_confidence'],
        })

    queue.sort(key=lambda x: x['risk_score'], reverse=True)
    return jsonify({
        'total_poles_assessed': len(queue),
        'top_priority_poles':   queue[:n],
        'generated_at':         datetime.utcnow().isoformat() + 'Z',
        'weather_conditions':   weather,
    })


# --- Circuit risk (geographic segment aggregation) ---
@app.route('/api/circuit_risk', methods=['GET'])
def circuit_risk():
    """
    Aggregate pole risk into ~1km² geographic grid cells (circuit segments).
    Returns segments ranked by max/avg risk — useful for network-level planning.
    """
    bbox = (42.0, -84.0, 43.0, -82.0)
    poles = fetch_poles_from_osm(bbox, max_poles=250) or _demo_poles()
    weather = get_weather_forecast(42.3314, -83.0458)
    wind = weather.get('wind_speed_mph', 12)

    grid = {}  # key = (lat_cell, lon_cell)
    for pole in poles:
        p = enrich_pole_proxy(pole)
        p['soil_risk'] = soil_risk_from_flood_zone(get_flood_zone(p['lat'], p['lon']))
        rd = _compute_pole_risk(p, wind)
        cell = (round(p['lat'], 2), round(p['lon'], 2))
        if cell not in grid:
            grid[cell] = {'poles': [], 'lat': cell[0], 'lon': cell[1]}
        grid[cell]['poles'].append(rd['riskScore'])

    segments = []
    for cell, data in grid.items():
        scores = data['poles']
        segments.append({
            'cell_id':       f"{cell[0]:.2f},{cell[1]:.2f}",
            'lat':           cell[0],
            'lon':           cell[1],
            'pole_count':    len(scores),
            'max_risk':      max(scores),
            'avg_risk':      round(sum(scores) / len(scores), 1),
            'high_risk_count': sum(1 for s in scores if s >= 70),
            'segment_level': 'Critical' if max(scores) >= 70 else
                             'High' if max(scores) >= 45 else 'Low',
        })

    segments.sort(key=lambda x: x['max_risk'], reverse=True)
    return jsonify({'segments': segments, 'total_segments': len(segments)})


# --- Image analysis ---
@app.route('/api/analyze', methods=['POST'])
def analyze():
    lat = request.form.get('lat')
    lon = request.form.get('lon')
    age = int(request.form.get('age', 20))
    if not lat or not lon:
        return jsonify({'error': 'Location required'}), 400
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400
    file = request.files['image']
    if not file.filename:
        return jsonify({'error': 'Invalid file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    cv_feat    = analyze_image(filepath)
    weather    = get_weather_forecast(float(lat), float(lon))
    weather['hazard_risk'] = get_weather_hazard_risk(weather)
    ndvi       = get_ndvi(float(lat), float(lon))
    flood_zone = get_flood_zone(float(lat), float(lon))
    soil_risk  = soil_risk_from_flood_zone(flood_zone)

    cv_feat['vegetation_proximity'] = max(
        cv_feat['vegetation_proximity'],
        0.6 if ndvi.get('vegetation_risk') == 'high' else 0.3
    )

    mat_code  = 0 if cv_feat['material_guess'] == 'wood' else 1
    veg_proxy = (10 - cv_feat['vegetation_proximity'] * 10)
    features  = [
        cv_feat['tilt_angle'],
        veg_proxy,
        weather.get('wind_speed_mph', 12),
        soil_risk,
        age,
        mat_code,
    ]

    risk_score  = risk_model.predict_risk(features)
    explanation = risk_model.explain_prediction(features)
    cost        = predict_repair_cost(risk_score, weather.get('wind_speed_mph', 12),
                                      0.5, age, cv_feat['material_guess'])

    missing = [] if ndvi['source'] != 'mock_spatial' else ['ndvi']
    confidence = risk_model.data_confidence(missing)

    prompt = (
        f"Pole risk score {risk_score:.0f}/100, tilt {cv_feat['tilt_angle']:.1f}°, "
        f"wind {weather.get('wind_speed_mph',12)} mph, flood zone {flood_zone}. "
        f"Primary driver: {explanation['primary_reason']}. "
        f"Recommend action and urgency."
    )
    rec = get_watsonx_recommendation(prompt)

    return jsonify({
        'success':             True,
        'risk_score':          round(risk_score, 1),
        'risk_level':          explanation['risk_level'],
        'explanation':         explanation,
        'data_confidence':     confidence,
        'features':            cv_feat,
        'weather':             weather,
        'ndvi':                ndvi,
        'flood_zone':          flood_zone,
        'estimated_repair_cost': round(cost, 2),
        'recommendation':      rec,
        'image_preview':       f"/uploads/{filename}",
    })


# --- Storm impact simulation ---
@app.route('/api/predict_storm_impact', methods=['POST'])
def predict_storm_impact():
    data       = request.json or {}
    poles      = data.get('poles', [])
    wind       = float(data.get('custom_wind', 40))
    rain       = float(data.get('custom_rain', 2))
    results    = []
    for pole in poles:
        base    = float(pole.get('current_risk_score', 50))
        damage  = min(100, base * (1 + wind / 100 + rain / 10))
        cost    = predict_repair_cost(damage, wind, rain,
                                      pole.get('age', 20), pole.get('material', 'wood'))
        results.append({
            'pole_id':                  pole['pole_id'],
            'predicted_damage_severity': round(damage, 1),
            'estimated_repair_cost':    round(cost, 2),
            'failure_probability':      round(damage / 100, 2),
            'risk_level':               'High' if damage >= 70 else 'Medium' if damage >= 45 else 'Low',
        })

    results.sort(key=lambda x: x['failure_probability'], reverse=True)
    total = sum(r['estimated_repair_cost'] for r in results)
    return jsonify({
        'storm_scenario':       f"{wind:.0f}mph / {rain:.1f}in",
        'affected_poles':       results,
        'total_estimated_cost': round(total, 2),
        'high_failure_count':   sum(1 for r in results if r['failure_probability'] >= 0.7),
        'historical':           get_historical_storm_impact(),
    })


# --- KML export ---
@app.route('/api/generate_kml', methods=['POST'])
def generate_kml():
    data   = request.json or {}
    damage = data.get('damage_data', [])
    storm  = data.get('storm_name', 'Assessment')
    fname  = f"damage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    fpath  = os.path.join(app.config['UPLOAD_FOLDER'], fname)
    generate_damage_kml(damage, storm, fpath)
    return jsonify({'kml_url': f"/uploads/{fname}"})


# --- NOAA storm alerts (real API) ---
@app.route('/api/storm_alerts', methods=['GET'])
def storm_alerts():
    """Fetch live NOAA NWS alerts for SE Michigan (Detroit area)."""
    result = get_noaa_alerts(42.3314, -83.0458)
    # Augment with current weather for the UI
    weather = get_weather_forecast(42.3314, -83.0458)
    result['current_wind_mph']  = weather.get('wind_speed_mph', 0)
    result['current_precip_in'] = weather.get('precip_24h_in', 0)
    return jsonify(result)


# --- Feature importance ---
@app.route('/api/feature_importance', methods=['GET'])
def feature_importance():
    """Return XGBoost feature importances for the model explainability panel."""
    return jsonify(risk_model.feature_importance())


# --- Static uploads ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Demo pole fallback ─────────────────────────────────────────────────────
def _demo_poles() -> list:
    """Fallback poles used when OSM is unreachable (e.g. during demo)."""
    coords = [
        (42.3314, -83.0458), (42.3700, -83.1000), (42.3100, -83.0200),
        (42.4000, -83.0800), (42.2800, -83.0700), (42.3400, -83.1800),
        (42.4200, -83.0000), (42.3450, -83.1500), (42.3600, -83.0600),
        (42.3200, -83.0900), (42.3800, -83.1200), (42.2900, -83.0400),
    ]
    return [
        {'id': f'DTE-DEMO-{i:04d}', 'lat': lat, 'lon': lon, 'tags': {}}
        for i, (lat, lon) in enumerate(coords)
    ]


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)