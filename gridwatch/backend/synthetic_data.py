"""
synthetic_data.py – Generates realistic synthetic dataset for utility poles.
Includes 29 features: age, tilt, cracks, rust, vegetation, wind, flood zone, soil, material,
storm exposure, years since inspection, urban density, height, road proximity, transformers,
maintenance year, AQI, soil moisture. Outputs CSV for training.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

np.random.seed(42)
random.seed(42)

# Define districts with realistic characteristics for Metro Detroit
DISTRICTS = [
    {"name": "Southwest Detroit",   "lat_c": 42.330, "lng_c": -83.100, "urban_density": 0.9, "flood_risk": 0.7, "avg_age": 38},
    {"name": "Dearborn",            "lat_c": 42.322, "lng_c": -83.176, "urban_density": 0.8, "flood_risk": 0.4, "avg_age": 32},
    {"name": "Downriver",           "lat_c": 42.285, "lng_c": -83.070, "urban_density": 0.6, "flood_risk": 0.8, "avg_age": 42},
    {"name": "Livonia",             "lat_c": 42.368, "lng_c": -83.352, "urban_density": 0.7, "flood_risk": 0.2, "avg_age": 25},
    {"name": "Allen Park",          "lat_c": 42.257, "lng_c": -83.211, "urban_density": 0.8, "flood_risk": 0.3, "avg_age": 28},
    {"name": "Wyandotte",           "lat_c": 42.214, "lng_c": -83.149, "urban_density": 0.7, "flood_risk": 0.9, "avg_age": 48},
    {"name": "Hamtramck",           "lat_c": 42.395, "lng_c": -83.049, "urban_density": 1.0, "flood_risk": 0.5, "avg_age": 45},
    {"name": "Inkster",             "lat_c": 42.293, "lng_c": -83.314, "urban_density": 0.7, "flood_risk": 0.4, "avg_age": 35},
    {"name": "Melvindale",          "lat_c": 42.279, "lng_c": -83.178, "urban_density": 0.8, "flood_risk": 0.5, "avg_age": 40},
    {"name": "Lincoln Park",        "lat_c": 42.244, "lng_c": -83.178, "urban_density": 0.8, "flood_risk": 0.6, "avg_age": 44},
    {"name": "Ecorse",              "lat_c": 42.244, "lng_c": -83.145, "urban_density": 0.8, "flood_risk": 0.8, "avg_age": 50},
    {"name": "River Rouge",         "lat_c": 42.274, "lng_c": -83.135, "urban_density": 0.7, "flood_risk": 0.9, "avg_age": 52},
    {"name": "Taylor",              "lat_c": 42.241, "lng_c": -83.269, "urban_density": 0.6, "flood_risk": 0.3, "avg_age": 30},
    {"name": "Southgate",           "lat_c": 42.213, "lng_c": -83.193, "urban_density": 0.6, "flood_risk": 0.3, "avg_age": 27},
    {"name": "Romulus",             "lat_c": 42.222, "lng_c": -83.395, "urban_density": 0.4, "flood_risk": 0.2, "avg_age": 20},
]

MATERIALS = ["Wood", "Steel", "Concrete", "Composite"]
MATERIAL_WEIGHTS = [0.60, 0.22, 0.10, 0.08]

SOIL_TYPES = ["Clay", "Loam", "Sandy", "Bedrock"]
SOIL_WEIGHTS = [0.45, 0.30, 0.15, 0.10]

VEG_RISK = ["high", "medium", "low"]
WIND_EXP = ["high", "medium", "low"]
FLOOD_ZONES = ["AE", "A", "B", "X"]

def random_date(start_year=2015, end_year=2024):
    """Return a random date string YYYY-MM-DD within range."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    return (start + timedelta(days=random.randint(0, (end - start).days))).strftime("%Y-%m-%d")

def generate_dataset(n_poles=3000):
    """Generate a pandas DataFrame of n_poles synthetic poles with all features."""
    records = []
    for i in range(n_poles):
        district = random.choice(DISTRICTS)
        material = random.choices(MATERIALS, weights=MATERIAL_WEIGHTS)[0]
        soil = random.choices(SOIL_TYPES, weights=SOIL_WEIGHTS)[0]
        age = int(np.clip(np.random.normal(district["avg_age"], 10), 1, 70))
        tilt = float(np.clip(np.random.normal(age*0.25 + (4 if soil=="Clay" else 1), 3), 0, 35))
        crack = 1 if random.random() < (0.03 + age*0.008 + (0.10 if tilt>10 else 0)) else 0
        rust = 1 if random.random() < (0.02 + age*0.006 + (0.15 if material=="Steel" else 0)) else 0
        veg = random.choices(VEG_RISK, weights=[district["flood_risk"]*0.4, 0.35, 1-district["flood_risk"]*0.4-0.35])[0]
        wind = random.choices(WIND_EXP, weights=[0.25, 0.45, 0.30])[0]
        flood = random.choices(FLOOD_ZONES, weights=[0.15, 0.10, 0.20, 0.55])[0]  # mostly X
        storm_exp = np.clip(np.random.normal(0.4, 0.2), 0, 1)
        lat = district["lat_c"] + np.random.normal(0, 0.025)
        lng = district["lng_c"] + np.random.normal(0, 0.025)
        last_insp = random_date(2018, 2024)
        years_since = (datetime.now() - datetime.strptime(last_insp, "%Y-%m-%d")).days / 365.25
        height = round(np.clip(np.random.normal(35,5), 25,55),1)
        road = round(np.clip(random.expovariate(1/60)+5, 5,300),1)
        xfmr = random.choices([0,1,2,3], weights=[0.6,0.25,0.10,0.05])[0]
        last_maint = random.randint(2015,2023)
        aqi = random.randint(30, 150)
        soil_moisture = round(random.uniform(0.2, 0.8), 2)

        # One‑hot encoding for categorical variables
        veg_high = 1 if veg=="high" else 0
        veg_med  = 1 if veg=="medium" else 0
        veg_low  = 1 if veg=="low" else 0
        wind_high = 1 if wind=="high" else 0
        wind_med  = 1 if wind=="medium" else 0
        wind_low  = 1 if wind=="low" else 0
        flood_AE = 1 if flood=="AE" else 0
        flood_A  = 1 if flood=="A" else 0
        flood_B  = 1 if flood=="B" else 0
        flood_X  = 1 if flood=="X" else 0
        soil_Clay = 1 if soil=="Clay" else 0
        soil_Sandy = 1 if soil=="Sandy" else 0
        mat_Wood = 1 if material=="Wood" else 0
        mat_Steel = 1 if material=="Steel" else 0
        mat_Concrete = 1 if material=="Concrete" else 0
        mat_Composite = 1 if material=="Composite" else 0

        # Compute risk score (0-100) based on all features
        score = 0
        score += min(age * 0.7, 25)
        score += min(tilt * 1.0, 15)
        if crack: score += 12
        if rust: score += 7
        if veg == "high": score += 10
        elif veg == "medium": score += 4
        if wind == "high": score += 8
        elif wind == "medium": score += 3
        if flood in ["AE","A"]: score += 8
        if material == "Wood": score += 4
        elif material == "Steel": score += 2
        if soil == "Clay": score += 3
        score += min(years_since * 1.5, 8)
        score += storm_exp * 10
        score += min((height-30)*0.2,4) if height>30 else 0
        score += max(0, (100-road)*0.08) if road<100 else 0
        score += min(xfmr * 1.5, 6)
        score += min((2024-last_maint)*1.2, 12)
        score += district["urban_density"] * 6
        # Environmental penalties
        score += min(max(0, (aqi - 100) / 20), 10)
        score += soil_moisture * 5
        noise = np.random.normal(0, 6)
        risk_score = float(np.clip(score + noise, 0, 100))

        # Failure label (simulated ground truth)
        failed = 1 if random.random() < (risk_score / 100 * 0.9) else 0
        storm_prob = float(np.clip(risk_score/100 * 0.85 + storm_exp*0.1 + 0.02, 0.02, 0.96))
        design = {"Wood":40, "Steel":65, "Concrete":70, "Composite":50}[material]
        remaining = max(0.5, design - age - (risk_score/100)*10 + np.random.normal(0,1.5))

        records.append({
            "pole_id": f"DTE-{10000+i:05d}",
            "lat": round(lat,5),
            "lng": round(lng,5),
            "district": district["name"],
            "age": age,
            "material": material,
            "tilt_angle": round(tilt,2),
            "crack_detected": crack,
            "rust_detected": rust,
            "vegetation_risk": veg,
            "wind_exposure": wind,
            "flood_zone": flood,
            "soil_type": soil,
            "storm_exposure_index": round(storm_exp,3),
            "years_since_inspection": round(years_since,2),
            "urban_density": district["urban_density"],
            "last_inspection": last_insp,
            "height_ft": height,
            "road_proximity_ft": road,
            "num_transformers": xfmr,
            "last_maintenance_year": last_maint,
            "aqi": aqi,
            "soil_moisture": soil_moisture,
            # One‑hot columns (for training)
            "vegetation_risk_high": veg_high,
            "vegetation_risk_medium": veg_med,
            "vegetation_risk_low": veg_low,
            "wind_exposure_high": wind_high,
            "wind_exposure_medium": wind_med,
            "wind_exposure_low": wind_low,
            "flood_zone_AE": flood_AE,
            "flood_zone_A": flood_A,
            "flood_zone_B": flood_B,
            "flood_zone_X": flood_X,
            "soil_Clay": soil_Clay,
            "soil_Sandy": soil_Sandy,
            "material_Wood": mat_Wood,
            "material_Steel": mat_Steel,
            "material_Concrete": mat_Concrete,
            "material_Composite": mat_Composite,
            "risk_score": risk_score,
            "failed": failed,
            "storm_failure_prob": storm_prob,
            "remaining_life_years": remaining,
        })

    df = pd.DataFrame(records)
    print(f"Generated {len(df)} poles")
    print(f"Failure rate: {df['failed'].mean():.2%}")
    print(f"Avg risk score: {df['risk_score'].mean():.1f}")
    print("Risk distribution:")
    print(pd.cut(df['risk_score'], bins=[0,25,45,70,100], labels=['Low','Medium','High','Critical']).value_counts())
    return df

if __name__ == "__main__":
    import os
    os.makedirs("../data", exist_ok=True)
    df = generate_dataset(3000)
    df.to_csv("../data/training_poles.csv", index=False)
    print("\nSaved to ../data/training_poles.csv")