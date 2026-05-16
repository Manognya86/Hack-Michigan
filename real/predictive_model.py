# predictive_model.py
import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import logging

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
        material TEXT
    )''')
    conn.commit()
    conn.close()

def insert_sample_history():
    """Insert realistic synthetic data for cost model training."""
    conn = sqlite3.connect(DB_PATH)
    poles = ['DTE-7821','DTE-4512','DTE-9034','DTE-3301','DTE-6678']
    materials = ['wood','steel','wood','composite','wood']
    storms = ['StormAlpha','StormBeta',None,'StormGamma',None]
    np.random.seed(42)
    for i, pole in enumerate(poles):
        for year in range(2020, 2025):
            if np.random.rand() > 0.6:
                damage = np.random.randint(20,95)
                cost = damage * 15 + np.random.normal(0,200)
                cost = max(100, cost)
                wind = np.random.uniform(20,70) if storms[i] else np.random.uniform(5,20)
                rain = np.random.uniform(0,4) if storms[i] else np.random.uniform(0,1)
                age = 2025 - year + np.random.randint(1,10)
                conn.execute(
                    "INSERT INTO repairs (pole_id, repair_date, damage_severity, repair_cost, storm_id, wind_speed, rainfall, pole_age, material) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pole, f"{year}-{np.random.randint(1,13):02d}-01", damage, round(cost,2), storms[i], wind, rain, age, materials[i])
                )
    conn.commit()
    conn.close()

def train_cost_model():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT damage_severity, wind_speed, rainfall, pole_age, material FROM repairs", conn)
    conn.close()
    if df.empty:
        return None
    df['material_code'] = df['material'].map({'wood':0, 'steel':1, 'composite':2})
    X = df[['damage_severity','wind_speed','rainfall','pole_age','material_code']].values
    y = df['damage_severity']*18 + df['wind_speed']*5 + df['rainfall']*100 + np.random.normal(0,50,len(df))
    y = np.maximum(y,50)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    joblib.dump(model, COST_MODEL_PATH)
    return model

def load_cost_model():
    if os.path.exists(COST_MODEL_PATH):
        return joblib.load(COST_MODEL_PATH)
    return train_cost_model()

def predict_repair_cost(damage, wind, rainfall, age, material):
    model = load_cost_model()
    if model is None:
        return damage * 20 + wind * 3 + rainfall * 80
    mat_code = {'wood':0, 'steel':1, 'composite':2}.get(material.lower(), 0)
    features = np.array([[damage, wind, rainfall, age, mat_code]])
    return float(model.predict(features)[0])

def get_historical_storm_impact():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT storm_id, AVG(repair_cost) as avg_cost FROM repairs WHERE storm_id IS NOT NULL GROUP BY storm_id", conn)
    conn.close()
    return df.to_dict(orient='records')