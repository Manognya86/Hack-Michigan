import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local modules
from dte_data import get_real_poles, MOCK_POLES
from weather_utils import get_weather_forecast, get_weather_hazard_risk, get_storm_alerts
from gee_utils import get_ndvi
from ml_model import risk_model
from predictive_model import init_db, insert_sample_history, train_cost_model, predict_repair_cost, get_historical_storm_impact
from kml_generator import generate_damage_kml
from damage_assessment import detect_vegetation_loss
from data_sources import get_soil_type, get_flood_zone

# IBM watsonx.ai
try:
    from ibm_watsonx_ai import Credentials, APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    WATSONX_AVAILABLE = True
except ImportError:
    WATSONX_AVAILABLE = False
    logging.warning("IBM watsonx.ai not installed")

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_FOLDER = 'uploads'
    DATABASE_URL = os.getenv('DATABASE_URL', 'pole_history.db')
    WATSONX_URL = os.getenv('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')
    WATSONX_API_KEY = os.getenv('WATSONX_API_KEY')
    WATSONX_PROJECT_ID = os.getenv('WATSONX_PROJECT_ID')
    WEATHER_CACHE_TTL = 300
    POLE_UPDATE_INTERVAL = 600  # 10 minutes
    OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize database and models
init_db()
insert_sample_history()
train_cost_model()
risk_model.load_model()

# watsonx client
watsonx_model = None
if WATSONX_AVAILABLE and Config.WATSONX_API_KEY:
    try:
        creds = Credentials(
            url=Config.WATSONX_URL,
            api_key=Config.WATSONX_API_KEY
        )
        api_client = APIClient(creds)
        watsonx_model = ModelInference(
            model_id="ibm/granite-13b-instruct-v2",
            api_client=api_client,
            project_id=Config.WATSONX_PROJECT_ID
        )
        logger.info("watsonx.ai ready.")
    except Exception as e:
        logger.warning(f"watsonx init failed: {e}")

# Cache for poles
poles_cache = {"data": None, "timestamp": 0, "lat": None, "lon": None}
poles_cache_lock = threading.Lock()

def fetch_real_poles(lat, lon, radius_km=5.0):
    with poles_cache_lock:
        cache_age = (datetime.now() - poles_cache["timestamp"]).total_seconds() if poles_cache["timestamp"] else 3600
        if (poles_cache["data"] is not None and 
            cache_age < Config.POLE_UPDATE_INTERVAL and
            poles_cache["lat"] == lat and 
            poles_cache["lon"] == lon):
            return poles_cache["data"]
    poles = get_real_poles(lat, lon, radius_km)
    with poles_cache_lock:
        poles_cache["data"] = poles
        poles_cache["timestamp"] = datetime.now()
        poles_cache["lat"] = lat
        poles_cache["lon"] = lon
    return poles

def background_pole_updater():
    while True:
        time.sleep(Config.POLE_UPDATE_INTERVAL)
        if poles_cache["lat"] and poles_cache["lon"]:
            logger.info(f"Refreshing poles for {poles_cache['lat']}, {poles_cache['lon']}")
            fetch_real_poles(poles_cache["lat"], poles_cache["lon"])

thread = threading.Thread(target=background_pole_updater, daemon=True)
thread.start()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def analyze_image_cv(image_path):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    crack_score = min(1.0, len([c for c in contours if cv2.contourArea(c) > 100]) / 1000)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    tilt = 0
    if lines is not None:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            ang = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            angles.append(ang)
        if angles:
            tilt = abs(np.mean(angles))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_rust = np.array([0, 50, 50])
    upper_rust = np.array([20, 255, 255])
    rust_mask = cv2.inRange(hsv, lower_rust, upper_rust)
    rust_pct = np.sum(rust_mask > 0) / (img.shape[0] * img.shape[1])
    g = img[:, :, 1]
    veg_pct = np.sum(g > 100) / (img.shape[0] * img.shape[1])
    return {
        'tilt_angle': tilt,
        'crack_score': crack_score,
        'rust_percentage': rust_pct,
        'vegetation_proximity': veg_pct,
        'material_guess': 'wood' if rust_pct > 0.05 else 'concrete'
    }

def get_watsonx_recommendation(prompt):
    if watsonx_model is not None:
        try:
            response = watsonx_model.generate_text(prompt=prompt, max_new_tokens=500)
            return response.strip()
        except Exception as e:
            logger.error(f"watsonx error: {e}")
    return "Based on the analysis, this pole requires inspection within the next 90 days. Estimated repair cost: $2,500-$5,000. Priority: Medium."

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/poles', methods=['GET'])
def get_poles():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    radius = request.args.get('radius', 5, type=float)
    if lat and lon:
        try:
            poles = fetch_real_poles(float(lat), float(lon), radius)
            return jsonify(poles if poles else [])
        except Exception as e:
            logger.error(f"Error fetching real poles: {e}")
            return jsonify([])
    return jsonify([])

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        age = int(request.form.get('age', 20))
        if not lat or not lon:
            return jsonify({'error': 'Location required'}), 400
        if 'image' not in request.files:
            return jsonify({'error': 'No image'}), 400
        file = request.files['image']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file'}), 400

        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            cv_feat = analyze_image_cv(filepath)
        except Exception as e:
            return jsonify({'error': f'Image analysis failed: {str(e)}'}), 400

        try:
            weather = get_weather_forecast(float(lat), float(lon))
            weather['hazard_risk'] = get_weather_hazard_risk(weather)
        except Exception as e:
            weather = {'temperature': 60, 'wind_speed_mph': 10, 'conditions': 'Unknown', 'source': 'fallback', 'hazard_risk': 'low'}

        try:
            ndvi_data = get_ndvi(float(lat), float(lon))
            veg_risk = ndvi_data.get('vegetation_risk', 'moderate')
            cv_feat['vegetation_proximity'] = max(cv_feat['vegetation_proximity'], 0.6 if veg_risk == 'high' else 0.3)
        except Exception as e:
            ndvi_data = {'vegetation_risk': 'moderate', 'source': 'fallback'}

        try:
            soil_data = get_soil_type(float(lat), float(lon))
            soil_risk = soil_data.get('soil_risk', 0.5)
        except Exception as e:
            soil_data = {'soil_class': 'loam', 'soil_risk': 0.3}
            soil_risk = 0.3

        wind_val = weather.get('wind_speed_mph', 10)
        material_code = 0 if cv_feat['material_guess'] == 'wood' else 1

        features_for_risk = [
            cv_feat['tilt_angle'],
            cv_feat['vegetation_proximity'] * 10,
            wind_val,
            soil_risk,
            age,
            material_code
        ]
        risk_score = risk_model.predict_risk(features_for_risk)
        risk_level = 'High' if risk_score > 70 else 'Medium' if risk_score > 40 else 'Low'

        est_cost = predict_repair_cost(risk_score, wind_val, 0.5, age, cv_feat['material_guess'], float(lat), float(lon))

        prompt = f"Pole risk score {risk_score:.1f}/100. Tilt {cv_feat['tilt_angle']:.1f}°, crack {cv_feat['crack_score']:.2f}, rust {cv_feat['rust_percentage']:.2%}. Wind {wind_val} mph. Soil: {soil_data.get('soil_class', 'unknown')}. Provide maintenance action, urgency, and cost estimate."
        ai_rec = get_watsonx_recommendation(prompt)

        return jsonify({
            'success': True,
            'risk_score': round(risk_score, 2),
            'risk_level': risk_level,
            'features': cv_feat,
            'weather': weather,
            'ndvi': ndvi_data,
            'soil': soil_data,
            'estimated_repair_cost': round(est_cost, 2),
            'recommendation': ai_rec,
            'image_preview': f"/uploads/{filename}"
        })
    except Exception as e:
        logger.error(f"Unhandled error in /api/analyze: {e}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/watsonx', methods=['POST'])
def watsonx_query():
    data = request.json
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'No prompt'}), 400
    response = get_watsonx_recommendation(prompt)
    return jsonify({'response': response})

@app.route('/api/predict_storm_impact', methods=['POST'])
def predict_storm_impact():
    try:
        data = request.json
        poles = data.get('poles', [])
        use_forecast = data.get('use_forecast', True)
        custom_wind = data.get('custom_wind', 40)
        custom_rain = data.get('custom_rain', 2)

        results = []
        for pole in poles:
            lat = pole.get('lat')
            lon = pole.get('lng')
            if use_forecast and lat and lon:
                fc = get_weather_forecast(lat, lon)
                wind = float(fc.get('wind_speed_mph', 20))
                rain = 1.0
            else:
                wind = float(custom_wind)
                rain = float(custom_rain)
            base_risk = float(pole.get('current_risk_score', 50))
            damage = min(100, base_risk * (1 + wind/100 + rain/10))
            cost = predict_repair_cost(damage, wind, rain, pole.get('age', 20), pole.get('material', 'wood'), lat, lon)
            risk_level = 'High' if damage > 70 else 'Medium' if damage > 40 else 'Low'
            results.append({
                'pole_id': pole.get('id', pole.get('pole_id', 'Unknown')),
                'latitude': lat,
                'longitude': lon,
                'predicted_damage_severity': round(damage, 1),
                'estimated_repair_cost': round(cost, 2),
                'forecast_wind_mph': wind,
                'failure_probability': round(damage/100, 2),
                'risk_level': risk_level
            })
        total_cost = sum(r['estimated_repair_cost'] for r in results)
        return jsonify({
            'storm_scenario': 'Forecast' if use_forecast else f"{custom_wind}mph / {custom_rain}in",
            'affected_poles': results,
            'total_estimated_cost': round(total_cost, 2),
            'historical_avg_cost_per_storm': get_historical_storm_impact()
        })
    except Exception as e:
        logger.error(f"Error in predict_storm_impact: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_kml', methods=['POST'])
def generate_kml():
    try:
        data = request.json
        damage_data = data.get('damage_data', [])
        storm_name = data.get('storm_name', 'Storm')
        filename = f"damage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        generate_damage_kml(damage_data, storm_name, filepath)
        return jsonify({'kml_url': f"/uploads/{filename}"})
    except Exception as e:
        logger.error(f"Error in generate_kml: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/storm_alerts', methods=['GET'])
def storm_alerts():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    alerts = get_storm_alerts(lat, lon)
    return jsonify(alerts)

@app.route('/api/weather/now', methods=['GET'])
def weather_now():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({'error': 'Missing lat/lon'}), 400
    weather = get_weather_forecast(float(lat), float(lon))
    return jsonify(weather)

@app.route('/api/soil', methods=['GET'])
def soil_info():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({'error': 'Missing lat/lon'}), 400
    soil = get_soil_type(float(lat), float(lon))
    return jsonify(soil)

@app.route('/api/flood', methods=['GET'])
def flood_info():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({'error': 'Missing lat/lon'}), 400
    flood = get_flood_zone(float(lat), float(lon))
    return jsonify(flood)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)