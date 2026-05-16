# predictive_model.py
import sqlite3
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import joblib
import os
import logging

DB_PATH = 'pole_history.db'
COST_MODEL_PATH = 'cost_predictor.pkl'


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS repairs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        pole_id          TEXT,
        repair_date      TEXT,
        damage_severity  INTEGER,
        repair_cost      REAL,
        storm_id         TEXT,
        wind_speed       REAL,
        rainfall         REAL,
        pole_age         INTEGER,
        material         TEXT
    )''')
    conn.commit()
    conn.close()


def insert_sample_history():
    """Synthetic but realistic DTE repair history (200 records)."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM repairs").fetchone()[0]
    if count >= 100:
        conn.close()
        return  # already populated

    rng = np.random.RandomState(42)
    poles     = [f'DTE-{i:04d}' for i in range(20)]
    materials = ['wood', 'steel', 'wood', 'composite', 'wood',
                 'steel', 'wood', 'composite', 'steel', 'wood'] * 2
    storm_pool = ['StormAlpha2021', 'StormBeta2022', 'StormGamma2023', None, None]

    for i, pole in enumerate(poles):
        mat = materials[i]
        for year in range(2019, 2025):
            if rng.rand() > 0.45:  # ~55% chance of repair event
                storm = storm_pool[rng.randint(len(storm_pool))]
                damage   = int(rng.randint(15, 95))
                wind     = rng.uniform(25, 72) if storm else rng.uniform(5, 22)
                rain     = rng.uniform(0.5, 4.5) if storm else rng.uniform(0, 0.8)
                age      = (2025 - year) + rng.randint(1, 15)
                mat_mult = {'wood': 1.0, 'steel': 1.35, 'composite': 1.55}[mat]
                base     = damage * 14 + wind * 6 + rain * 90
                cost     = max(200, base * mat_mult + rng.normal(0, 150))
                conn.execute(
                    "INSERT INTO repairs "
                    "(pole_id,repair_date,damage_severity,repair_cost,storm_id,"
                    "wind_speed,rainfall,pole_age,material) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pole, f"{year}-{rng.randint(1,13):02d}-01",
                     damage, round(cost, 2), storm, round(wind, 1),
                     round(rain, 2), int(age), mat)
                )
    conn.commit()
    conn.close()
    logging.info("Sample repair history inserted.")


def train_cost_model():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT damage_severity, wind_speed, rainfall, pole_age, material, repair_cost "
        "FROM repairs", conn)
    conn.close()
    if df.empty:
        return None

    df['material_code'] = df['material'].map({'wood': 0, 'steel': 1, 'composite': 2}).fillna(0)
    X = df[['damage_severity', 'wind_speed', 'rainfall', 'pole_age', 'material_code']].values
    y = df['repair_cost'].values

    model = XGBRegressor(n_estimators=200, max_depth=4,
                         learning_rate=0.05, random_state=42, verbosity=0)
    model.fit(X, y)
    joblib.dump(model, COST_MODEL_PATH)
    logging.info("Cost model trained and saved.")
    return model


def _load_cost_model():
    if os.path.exists(COST_MODEL_PATH):
        return joblib.load(COST_MODEL_PATH)
    return train_cost_model()


def predict_repair_cost(damage: float, wind: float, rainfall: float,
                        age: int, material: str) -> float:
    model = _load_cost_model()
    mat_code = {'wood': 0, 'steel': 1, 'composite': 2}.get(str(material).lower(), 0)
    if model is None:
        return damage * 20 + wind * 4 + rainfall * 85
    features = np.array([[damage, wind, rainfall, age, mat_code]])
    return float(model.predict(features)[0])


def get_historical_storm_impact() -> list:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT storm_id, COUNT(*) as pole_count, AVG(repair_cost) as avg_cost, "
        "SUM(repair_cost) as total_cost "
        "FROM repairs WHERE storm_id IS NOT NULL GROUP BY storm_id",
        conn)
    conn.close()
    return df.round(2).to_dict(orient='records')