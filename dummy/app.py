# app.py
import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import cv2
import numpy as np

# Local modules
from dte_config import get_flood_zone
from weather_utils import get_weather_forecast, get_weather_hazard_risk
from gee_utils import get_ndvi
from ml_model import risk_model
from predictive_model import init_db, insert_sample_history, train_cost_model, predict_repair_cost, get_historical_storm_impact
from kml_generator import generate_damage_kml
from osm_utils import fetch_poles_from_osm

# IBM watsonx.ai (optional)
try:
    from ibm_watsonx_ai import Credentials, APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    WATSONX_AVAILABLE = True
except ImportError:
    WATSONX_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# Initialize database and models
init_db()
insert_sample_history()
train_cost_model()
risk_model.load_model()

# watsonx client (optional)
watsonx_model = None
if WATSONX_AVAILABLE:
    try:
        creds = Credentials(
            url=os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
            api_key=os.getenv("WATSONX_API_KEY")
        )
        api_client = APIClient(creds)
        watsonx_model = ModelInference(
            model_id="ibm/granite-13b-instruct-v2",
            api_client=api_client,
            project_id=os.getenv("WATSONX_PROJECT_ID")
        )
        logging.info("watsonx.ai ready")
    except Exception as e:
        logging.warning(f"watsonx init failed: {e}")

# ------------------- Computer Vision -------------------
def analyze_image(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    crack_score = min(1.0, len([c for c in contours if cv2.contourArea(c) > 100]) / 1000)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    tilt = 0
    if lines is not None:
        angles = []
        for line in lines:
            x1,y1,x2,y2 = line[0]
            angles.append(np.arctan2(y2-y1, x2-x1)*180/np.pi)
        if angles:
            tilt = abs(np.mean(angles))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_rust = np.array([0,50,50])
    upper_rust = np.array([20,255,255])
    rust_mask = cv2.inRange(hsv, lower_rust, upper_rust)
    rust_pct = np.sum(rust_mask>0) / (img.shape[0]*img.shape[1])
    g = img[:,:,1]
    veg_pct = np.sum(g > 100) / (img.shape[0]*img.shape[1])
    return {
        'tilt_angle': tilt,
        'crack_score': crack_score,
        'rust_percentage': rust_pct,
        'vegetation_proximity': veg_pct,
        'material_guess': 'wood' if rust_pct > 0.05 else 'steel'
    }

def get_watsonx_recommendation(prompt):
    if watsonx_model:
        try:
            return watsonx_model.generate_text(prompt=prompt, max_new_tokens=300).strip()
        except Exception as e:
            logging.error(f"watsonx error: {e}")
    # Fallback
    return "Inspect within 90 days. Estimated cost $2,500–$5,000. Priority: Medium."

# ------------------- API Routes -------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/poles', methods=['GET'])
def get_poles():
    """Fetch real poles from OpenStreetMap for Detroit area."""
    bbox = (42.0, -84.0, 43.0, -82.0)  # SE Michigan
    real_poles = fetch_poles_from_osm(bbox)
    # Enrich with mock age/material for demo (in real system you'd join asset DB)
    for i, pole in enumerate(real_poles):
        pole['age'] = 20 + (i % 40)
        pole['material'] = 'wood' if (i % 3) == 0 else 'steel' if (i % 3) == 1 else 'composite'
        pole['tilt'] = (i % 15) * 2
        pole['cracks'] = (i % 4) == 0
        pole['rust'] = (i % 5) == 0
        pole['vegetation'] = 'high' if (i % 3) == 0 else 'medium' if (i % 3) == 1 else 'low'
        pole['windExposure'] = 'high' if (i % 3) == 0 else 'medium'
        # Compute risk
        score = min(100, pole['age'] * 1.2 + pole['tilt'] * 1.8 + (15 if pole['cracks'] else 0) + (10 if pole['rust'] else 0))
        pole['riskScore'] = int(score)
        pole['risk_level'] = 'High' if score >= 70 else 'Medium' if score >= 45 else 'Low'
        pole['stormFailProb'] = round(min(0.95, score/100 * 0.85 + 0.05), 2)
        pole['remainingLife'] = round(max(0.5, (100 - score) / 10), 1)
    return jsonify(real_poles)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    lat = request.form.get('lat')
    lon = request.form.get('lon')
    age = int(request.form.get('age', 20))
    if not lat or not lon:
        return jsonify({'error': 'Location required'}), 400
    if 'image' not in request.files:
        return jsonify({'error': 'No image'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Invalid file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # CV
    cv_feat = analyze_image(filepath)

    # Weather
    weather = get_weather_forecast(float(lat), float(lon))
    weather['hazard_risk'] = get_weather_hazard_risk(weather)

    # Vegetation
    ndvi = get_ndvi(float(lat), float(lon))
    cv_feat['vegetation_proximity'] = max(cv_feat['vegetation_proximity'], 0.6 if ndvi.get('vegetation_risk') == 'high' else 0.3)

    # Soil / flood
    flood_zone = get_flood_zone(float(lat), float(lon))
    soil_risk = 1 if flood_zone == 'AE' else 0

    # Risk score
    features = [
        cv_feat['tilt_angle'],
        cv_feat['vegetation_proximity'] * 10,
        weather.get('wind_speed_mph', 10),
        soil_risk,
        age,
        0 if cv_feat['material_guess'] == 'wood' else 1
    ]
    risk = risk_model.predict_risk(features)
    risk_level = 'High' if risk > 70 else 'Medium' if risk > 40 else 'Low'

    # Cost estimation
    cost = predict_repair_cost(risk, weather.get('wind_speed_mph', 10), 0.5, age, cv_feat['material_guess'])

    # AI recommendation
    prompt = f"Pole risk score {risk}/100, tilt {cv_feat['tilt_angle']:.1f}°, wind {weather.get('wind_speed_mph',10)} mph. Recommend action and urgency."
    rec = get_watsonx_recommendation(prompt)

    return jsonify({
        'success': True,
        'risk_score': risk,
        'risk_level': risk_level,
        'features': cv_feat,
        'weather': weather,
        'ndvi': ndvi,
        'estimated_repair_cost': round(cost, 2),
        'recommendation': rec,
        'image_preview': f"/uploads/{filename}"
    })

@app.route('/api/predict_storm_impact', methods=['POST'])
def predict_storm_impact():
    data = request.json
    poles = data.get('poles', [])
    custom_wind = data.get('custom_wind', 40)
    custom_rain = data.get('custom_rain', 2)
    results = []
    for pole in poles:
        wind = custom_wind
        rain = custom_rain
        base_risk = pole.get('current_risk_score', 50)
        damage = min(100, base_risk * (1 + wind/100 + rain/10))
        cost = predict_repair_cost(damage, wind, rain, pole.get('age',20), pole.get('material','wood'))
        results.append({
            'pole_id': pole['pole_id'],
            'predicted_damage_severity': round(damage,1),
            'estimated_repair_cost': round(cost,2),
            'failure_probability': round(damage/100,2)
        })
    total = sum(r['estimated_repair_cost'] for r in results)
    return jsonify({
        'storm_scenario': f"{custom_wind}mph / {custom_rain}in",
        'affected_poles': results,
        'total_estimated_cost': round(total,2),
        'historical': get_historical_storm_impact()
    })

@app.route('/api/generate_kml', methods=['POST'])
def generate_kml():
    data = request.json
    damage = data.get('damage_data', [])
    storm = data.get('storm_name', 'Storm')
    filename = f"damage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    generate_damage_kml(damage, storm, filepath)
    return jsonify({'kml_url': f"/uploads/{filename}"})

@app.route('/api/storm_alerts', methods=['GET'])
def storm_alerts():
    # In real system fetch from NOAA's API; for demo mock a warning
    return jsonify({
        'windSpeed': 58,
        'gustSpeed': 74,
        'precipIn': 2.3,
        'stormAlert': 'WIND ADVISORY',
        'stormDate': 'May 17–18, 2026'
    })

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)