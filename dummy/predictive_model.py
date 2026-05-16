import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import logging
from datetime import datetime
from data_sources import get_soil_type, get_flood_zone

logger = logging.getLogger(__name__)

DB_PATH = 'pole_history.db'
COST_MODEL_PATH = 'cost_predictor.pkl'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS repairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pole_id TEXT,
        repair_date TEXT,
        damage_severity INTEGER,
        repair_cost REAL,
        storm_id TEXT,
        wind_speed REAL,
        rainfall REAL,
        pole_age INTEGER,
        material TEXT,
        soil_type TEXT,
        flood_zone TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS storms (
        storm_id TEXT PRIMARY KEY,
        storm_date TEXT,
        avg_wind_speed REAL,
        max_gust REAL,
        rainfall_total REAL,
        affected_poles TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS real_poles (
        pole_id TEXT PRIMARY KEY,
        lat REAL,
        lng REAL,
        osm_tags TEXT,
        first_seen TEXT,
        last_updated TEXT
    )''')
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def insert_sample_history():
    """Insert sample historical data if database is empty."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM repairs")
    if cursor.fetchone()[0] == 0:
        poles = ['DTE-7821','DTE-4512','DTE-9034','DTE-3301','DTE-6678']
        materials = ['wood','steel','wood','composite','wood']
        soil_types = ['clay','loam','sandy','loam','clay']
        flood_zones = ['AE','X','AE','X','B']
        np.random.seed(42)
        for i, pole in enumerate(poles):
            for year in range(2020, 2025):
                if np.random.rand() > 0.6:
                    damage = np.random.randint(20,95)
                    cost = damage * 15 + np.random.normal(0,200)
                    cost = max(100, cost)
                    wind = np.random.uniform(20,70)
                    rain = np.random.uniform(0,4)
                    age = 2025 - year + np.random.randint(1,10)
                    conn.execute(
                        "INSERT INTO repairs (pole_id, repair_date, damage_severity, repair_cost, storm_id, wind_speed, rainfall, pole_age, material, soil_type, flood_zone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (pole, f"{year}-{np.random.randint(1,13):02d}-01", damage, round(cost,2), f"Storm{year}", wind, rain, age, materials[i], soil_types[i], flood_zones[i])
                    )
        conn.commit()
        logger.info("Sample history inserted.")
    conn.close()

def train_cost_model():
    """Train cost prediction model on historical data."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT damage_severity, wind_speed, rainfall, pole_age, material, soil_type, flood_zone FROM repairs", conn)
    conn.close()
    if df.empty:
        logger.warning("No historical data; using default model")
        return None
    
    # Encode categorical variables
    material_map = {'wood':0, 'steel':1, 'composite':2}
    df['material_code'] = df['material'].map(material_map).fillna(0)
    soil_map = {'clay':2, 'loam':1, 'sandy':0, 'silty':1}
    df['soil_code'] = df['soil_type'].map(soil_map).fillna(1)
    flood_map = {'AE':2, 'A':2, 'V':2, 'B':1, 'X500':1, 'X':0}
    df['flood_code'] = df['flood_zone'].map(flood_map).fillna(0)
    
    X = df[['damage_severity','wind_speed','rainfall','pole_age','material_code','soil_code','flood_code']].values
    y = df['damage_severity']*18 + df['wind_speed']*5 + df['rainfall']*100 + np.random.normal(0,50,len(df))
    y = np.maximum(y, 50)
    
    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X, y)
    joblib.dump(model, COST_MODEL_PATH)
    logger.info("Cost model trained.")
    return model

def load_cost_model():
    if os.path.exists(COST_MODEL_PATH):
        return joblib.load(COST_MODEL_PATH)
    return train_cost_model()

def predict_repair_cost(damage_severity, wind_speed, rainfall, pole_age, material, lat=None, lon=None):
    """Enhanced cost prediction with soil and flood data."""
    model = load_cost_model()
    if model is None:
        return damage_severity * 20 + wind_speed * 3 + rainfall * 80
    
    material_code = {'wood':0, 'steel':1, 'composite':2}.get(material.lower(), 0)
    
    # Get real soil and flood data if coordinates provided
    soil_code = 1
    flood_code = 0
    if lat and lon:
        try:
            soil = get_soil_type(lat, lon)
            soil_map = {'clay':2, 'loam':1, 'sandy':0, 'silty':1}
            soil_code = soil_map.get(soil.get('soil_class', 'loam'), 1)
            
            flood = get_flood_zone(lat, lon)
            flood_map = {'AE':2, 'A':2, 'V':2, 'B':1, 'X500':1, 'X':0}
            flood_code = flood_map.get(flood.get('flood_zone', 'X'), 0)
        except Exception as e:
            logger.warning(f"Failed to get soil/flood data for cost: {e}")
    
    features = np.array([[damage_severity, wind_speed, rainfall, pole_age, material_code, soil_code, flood_code]])
    return float(model.predict(features)[0])

def get_historical_storm_impact():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT storm_id, AVG(repair_cost) as avg_cost, COUNT(*) as repairs FROM repairs WHERE storm_id IS NOT NULL GROUP BY storm_id", conn)
    conn.close()
    return df.to_dict(orient='records')