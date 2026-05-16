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
import requests

# local modules
from dte_data import MOCK_POLES, compute_risk_score
from weather_utils import get_weather_forecast, get_weather_hazard_risk
from gee_utils import get_ndvi
from ml_model import risk_model
from predictive_model import init_db, insert_sample_history, train_cost_model, predict_repair_cost, get_historical_storm_impact
from kml_generator import generate_damage_kml
from damage_assessment import detect_vegetation_loss

# IBM watsonx.ai (optional)
try:
    from ibm_watsonx_ai import Credentials, APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    WATSONX_AVAILABLE = True
except ImportError:
    WATSONX_AVAILABLE = False
    logging.warning("IBM watsonx.ai not installed")

# Load environment variables (for watsonx keys)
from dotenv import load_dotenv
load_dotenv()

# Flask setup
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# Initialize database and models
init_db()
insert_sample_history()  # first run only; comment afterwards if you want to keep data
train_cost_model()
risk_model.load_model()

# Optional watsonx client
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
        logging.info("watsonx.ai ready.")
    except Exception as e:
        logging.warning(f"watsonx init failed: {e}")

# ------------------- Helper functions -------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in {'png','jpg','jpeg'}

def analyze_image_cv(image_path):
    """Extract features using OpenCV."""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    crack_score = min(1.0, len([c for c in contours if cv2.contourArea(c) > 100]) / 1000)

    # Tilt via Hough lines
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    tilt = 0
    if lines is not None:
        angles = []
        for line in lines:
            x1,y1,x2,y2 = line[0]
            ang = np.arctan2(y2-y1, x2-x1)*180/np.pi
            angles.append(ang)
        if angles:
            tilt = abs(np.mean(angles))

    # Rust via color
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_rust = np.array([0,50,50])
    upper_rust = np.array([20,255,255])
    rust_mask = cv2.inRange(hsv, lower_rust, upper_rust)
    rust_pct = np.sum(rust_mask>0) / (img.shape[0]*img.shape[1])

    # Vegetation via green channel
    g = img[:,:,1]
    veg_pct = np.sum(g > 100) / (img.shape[0]*img.shape[1])

    return {
        'tilt_angle': tilt,
        'crack_score': crack_score,
        'rust_percentage': rust_pct,
        'vegetation_proximity': veg_pct,
        'material_guess': 'wood' if rust_pct > 0.05 else 'concrete'
    }

def get_watsonx_recommendation(prompt):
    """Call watsonx.ai or return mock."""
    if watsonx_model is not None:
        try:
            response = watsonx_model.generate_text(prompt=prompt, max_new_tokens=500)
            return response.strip()
        except Exception as e:
            logging.error(f"watsonx error: {e}")
    # Mock recommendation
    return "Based on the analysis, this pole requires inspection within the next 90 days. Estimated repair cost: $2,500-$5,000. Priority: Medium."

# ------------------- API Routes -------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/poles', methods=['GET'])
def get_poles():
    """Return all DTE poles with risk scores."""
    return jsonify(MOCK_POLES)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Upload image + location → CV + weather + GEE → risk score + cost + AI rec."""
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

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Computer vision
    cv_feat = analyze_image_cv(filepath)

    # Weather
    weather = get_weather_forecast(float(lat), float(lon))
    weather['hazard_risk'] = get_weather_hazard_risk(weather)

    # GEE vegetation
    ndvi_data = get_ndvi(float(lat), float(lon))
    veg_risk = ndvi_data.get('vegetation_risk', 'moderate')
    cv_feat['vegetation_proximity'] = max(cv_feat['vegetation_proximity'], 0.6 if veg_risk=='high' else 0.3)

    # Soil risk mock (based on lat)
    soil_risk = 1 if float(lat) < 42.5 else 0
    wind_val = weather.get('wind_speed_mph', 10)
    material_code = 0 if cv_feat['material_guess'] == 'wood' else 1

    # Risk model prediction
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

    # Cost prediction
    est_cost = predict_repair_cost(risk_score, wind_val, 0.5, age, cv_feat['material_guess'])

    # AI recommendation
    prompt = f"Pole risk score {risk_score}/100. Tilt {cv_feat['tilt_angle']:.1f}°, crack {cv_feat['crack_score']:.2f}, rust {cv_feat['rust_percentage']:.2%}. Wind {wind_val} mph. Provide maintenance action, urgency, and cost estimate."
    ai_rec = get_watsonx_recommendation(prompt)

    return jsonify({
        'success': True,
        'risk_score': risk_score,
        'risk_level': risk_level,
        'features': cv_feat,
        'weather': weather,
        'ndvi': ndvi_data,
        'estimated_repair_cost': round(est_cost, 2),
        'recommendation': ai_rec,
        'image_preview': f"/uploads/{filename}"
    })

@app.route('/api/watsonx', methods=['POST'])
def watsonx_query():
    """Generic endpoint for AI queries (used by dashboard)."""
    data = request.json
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'No prompt'}), 400
    response = get_watsonx_recommendation(prompt)
    return jsonify({'response': response})

@app.route('/api/predict_storm_impact', methods=['POST'])
def predict_storm_impact():
    data = request.json
    poles = data.get('poles', [])
    use_forecast = data.get('use_forecast', True)
    custom_wind = data.get('custom_wind', 40)
    custom_rain = data.get('custom_rain', 2)

    results = []
    for pole in poles:
        lat = pole.get('lat')
        lon = pole.get('lon')
        if use_forecast and lat and lon:
            fc = get_weather_forecast(lat, lon)
            wind = fc.get('wind_speed_mph', 20)
            rain = 1.0
        else:
            wind = custom_wind
            rain = custom_rain
        base_risk = pole.get('current_risk_score', 50)
        damage = min(100, base_risk * (1 + wind/100 + rain/10))
        cost = predict_repair_cost(damage, wind, rain, pole.get('age',20), pole.get('material','wood'))
        results.append({
            'pole_id': pole['pole_id'],
            'predicted_damage_severity': round(damage,1),
            'estimated_repair_cost': round(cost,2),
            'forecast_wind_mph': wind,
            'failure_probability': round(damage/100,2)
        })
    total_cost = sum(r['estimated_repair_cost'] for r in results)
    return jsonify({
        'storm_scenario': 'Forecast' if use_forecast else f"{custom_wind}mph / {custom_rain}in",
        'affected_poles': results,
        'total_estimated_cost': round(total_cost,2),
        'historical_avg_cost_per_storm': get_historical_storm_impact()
    })

@app.route('/api/generate_kml', methods=['POST'])
def generate_kml():
    data = request.json
    damage_data = data.get('damage_data', [])
    storm_name = data.get('storm_name', 'Storm')
    filename = f"damage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    generate_damage_kml(damage_data, storm_name, filepath)
    return jsonify({'kml_url': f"/uploads/{filename}"})

@app.route('/api/storm_alerts', methods=['GET'])
def storm_alerts():
    """Mock NOAA storm alert for Michigan."""
    return jsonify({
        'windSpeed': 58,
        'gustSpeed': 74,
        'precipIn': 2.3,
        'stormAlert': 'WIND ADVISORY',
        'stormDate': 'May 17–18, 2026'
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)