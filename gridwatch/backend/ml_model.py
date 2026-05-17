"""
ml_model.py – XGBoost based risk prediction with 29 features.
Includes feature engineering, batch prediction, priority scoring, optimal action recommendation,
and explainability (generate_explanation).
"""

import numpy as np
import pandas as pd
import joblib
import os
from xgboost import XGBRegressor, XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from typing import Dict, Any, List

MODEL_PATH = os.environ.get("MODEL_PATH", "../models/risk_model.pkl")

# Complete list of 29 features used by the model
FEATURE_COLS = [
    "age",
    "tilt_angle",
    "crack_detected",
    "rust_detected",
    "vegetation_risk_high",
    "vegetation_risk_medium",
    "vegetation_risk_low",
    "wind_exposure_high",
    "wind_exposure_medium",
    "wind_exposure_low",
    "flood_zone_AE",
    "flood_zone_A",
    "flood_zone_B",
    "flood_zone_X",
    "soil_Clay",
    "soil_Sandy",
    "material_Wood",
    "material_Steel",
    "material_Concrete",
    "material_Composite",
    "storm_exposure_index",
    "years_since_inspection",
    "urban_density",
    "height_ft",
    "road_proximity_ft",
    "num_transformers",
    "years_since_last_maintenance",
    "aqi",
    "soil_moisture",
]

def get_feature_importance(model, feature_names: List[str]) -> Dict[str, float]:
    """Return feature importance dictionary sorted descending."""
    scores = model.feature_importances_
    return dict(sorted(zip(feature_names, scores), key=lambda x: -x[1]))

def _optimal_action(risk_score: float, remaining_life: float, replace_cost: float, repair_cost: float) -> Dict:
    """Determine optimal maintenance action and its rationale."""
    if risk_score >= 75:
        return {"action": "Immediate Replacement", "rationale": f"Risk score {risk_score} exceeds critical threshold."}
    if remaining_life < 2:
        return {"action": "Replace within 12 months", "rationale": f"Remaining life only {remaining_life:.1f} years – replacement is more cost‑effective."}
    if replace_cost > repair_cost * 3:
        return {"action": "Repair & Reinforce", "rationale": f"Repair cost (${repair_cost}) is less than one‑third of replacement (${replace_cost})."}
    return {"action": "Monitor & Schedule Inspection", "rationale": "Risk is manageable; routine inspection suffices."}

def compute_priority_score(risk_score: float, storm_prob: float, replace_cost: float) -> float:
    """Calculate a composite priority score (0-100) for prioritisation."""
    cost_norm = min(replace_cost / 20000, 1.0)
    return 0.5 * risk_score + 0.3 * (storm_prob * 100) + 0.2 * (cost_norm * 100)

def generate_explanation(pole: Dict, pred: Dict) -> Dict:
    """Generate a human‑readable explanation for the pole's condition."""
    risk = pred["risk_score"]
    level = pred["risk_level"]
    remaining_years = pred["remaining_life_years"]
    remaining_months = round(remaining_years * 12, 1)
    if risk >= 70:
        severity = f"Critical – {risk}/100. Immediate attention required."
    elif risk >= 45:
        severity = f"High – {risk}/100. Plan replacement within 12 months."
    elif risk >= 25:
        severity = f"Medium – {risk}/100. Monitor and repair as needed."
    else:
        severity = f"Low – {risk}/100. Routine inspection sufficient."
    factors = pred.get("top_risk_factors", [])
    if factors:
        main_factors = ", ".join([f"{f['factor']} (contributes {f['contribution']} pts)" for f in factors[:3]])
        damage_reason = f"Main damage drivers: {main_factors}."
    else:
        damage_reason = "No single dominant factor; overall condition is moderate."
    remaining_months_low = max(0, remaining_months - 6)
    remaining_months_high = remaining_months + 6
    if remaining_years < 1:
        time_text = f"Expected to fail within {remaining_months} months. Immediate action recommended."
    elif remaining_years < 3:
        time_text = f"Likely to fail within {remaining_months_low}–{remaining_months_high} months. Schedule repair soon."
    else:
        time_text = f"Stable for approximately {remaining_years} years. Continue routine monitoring."
    summary = f"Pole {pole['pole_id']} is in {level.lower()} condition. {damage_reason} {time_text}"
    return {
        "summary": summary,
        "severity": severity,
        "remaining_life_months": remaining_months,
        "confidence_interval_months": f"{remaining_months_low}–{remaining_months_high}",
        "top_contributing_factors": factors[:5],
        "risk_score": risk,
        "risk_level": level
    }

def train_models(df: pd.DataFrame) -> Dict:
    """Train three XGBoost models: risk score (regression), failure classifier, storm prob (regression)."""
    # Engineer derived feature
    df["years_since_last_maintenance"] = 2024 - df["last_maintenance_year"]
    # Ensure all columns exist (add defaults if missing, e.g., for aqi, soil_moisture)
    for col in ["aqi", "soil_moisture"]:
        if col not in df.columns:
            df[col] = 50 if col == "aqi" else 0.5
    X = df[FEATURE_COLS].fillna(0)
    y_risk = df["risk_score"]
    y_failed = df["failed"]
    y_storm = df["storm_failure_prob"]

    X_train, X_test, yr_train, yr_test, yf_train, yf_test, ys_train, ys_test = train_test_split(
        X, y_risk, y_failed, y_storm, test_size=0.2, random_state=42, stratify=y_failed
    )

    print("Training XGBoost Risk Score Regressor...")
    risk_model = XGBRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, n_jobs=-1, verbosity=0
    )
    risk_model.fit(X_train, yr_train)
    yr_pred = risk_model.predict(X_test)
    risk_mae = mean_absolute_error(yr_test, yr_pred)
    risk_r2 = r2_score(yr_test, yr_pred)
    print(f"  Risk Score — MAE: {risk_mae:.2f}, R²: {risk_r2:.3f}")

    print("Training XGBoost Failure Classifier...")
    fail_model = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(len(yf_train) - yf_train.sum()) / yf_train.sum(),
        random_state=42, n_jobs=-1, verbosity=0, eval_metric="logloss"
    )
    fail_model.fit(X_train, yf_train)
    yf_prob = fail_model.predict_proba(X_test)[:, 1]
    fail_auc = roc_auc_score(yf_test, yf_prob)
    print(f"  Failure Classifier — AUC: {fail_auc:.3f}")

    print("Training XGBoost Storm Probability Regressor...")
    storm_model = XGBRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbosity=0
    )
    storm_model.fit(X_train, ys_train)
    ys_pred = np.clip(storm_model.predict(X_test), 0, 1)
    storm_mae = mean_absolute_error(ys_test, ys_pred)
    print(f"  Storm Prob — MAE: {storm_mae:.4f}")

    return {
        "risk_model": risk_model,
        "fail_model": fail_model,
        "storm_model": storm_model,
        "feature_cols": FEATURE_COLS,
        "feature_importance": get_feature_importance(risk_model, FEATURE_COLS),
        "metrics": {
            "risk_mae": float(risk_mae),
            "risk_r2": float(risk_r2),
            "fail_auc": float(fail_auc),
            "storm_mae": float(storm_mae)
        }
    }

def save_bundle(bundle: Dict, path: str = MODEL_PATH):
    """Save the model bundle to disk."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(bundle, path)
    print(f"Model bundle saved to {path}")

def load_bundle(path: str = MODEL_PATH) -> Dict:
    """Load a previously saved model bundle."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found at {path}. Run train_model.py first.")
    return joblib.load(path)

def engineer_features(pole_data: Dict[str, Any]) -> pd.DataFrame:
    """Convert raw pole dictionary into a feature DataFrame expected by the model."""
    veg = pole_data.get("vegetation_risk", "medium")
    wind = pole_data.get("wind_exposure", "medium")
    flood = pole_data.get("flood_zone", "X")
    soil = pole_data.get("soil_type", "Loam")
    mat = pole_data.get("material", "Wood")

    from datetime import datetime
    last_insp = pole_data.get("last_inspection", "2022-01-01")
    try:
        years_since = (datetime.now() - datetime.strptime(last_insp, "%Y-%m-%d")).days / 365.25
    except:
        years_since = 2.0

    last_maint = pole_data.get("last_maintenance_year", 2018)
    years_since_maint = 2024 - last_maint

    row = {
        "age": float(pole_data.get("age", 20)),
        "tilt_angle": float(pole_data.get("tilt_angle", 0)),
        "crack_detected": int(pole_data.get("crack_detected", False)),
        "rust_detected": int(pole_data.get("rust_detected", False)),
        "vegetation_risk_high": int(veg == "high"),
        "vegetation_risk_medium": int(veg == "medium"),
        "vegetation_risk_low": int(veg == "low"),
        "wind_exposure_high": int(wind == "high"),
        "wind_exposure_medium": int(wind == "medium"),
        "wind_exposure_low": int(wind == "low"),
        "flood_zone_AE": int(flood == "AE"),
        "flood_zone_A": int(flood == "A"),
        "flood_zone_B": int(flood == "B"),
        "flood_zone_X": int(flood == "X"),
        "soil_Clay": int(soil == "Clay"),
        "soil_Sandy": int(soil == "Sandy"),
        "material_Wood": int(mat == "Wood"),
        "material_Steel": int(mat == "Steel"),
        "material_Concrete": int(mat == "Concrete"),
        "material_Composite": int(mat == "Composite"),
        "storm_exposure_index": float(pole_data.get("storm_exposure_index", 0.4)),
        "years_since_inspection": round(years_since, 2),
        "urban_density": float(pole_data.get("urban_density", 0.7)),
        "height_ft": float(pole_data.get("height_ft", 35.0)),
        "road_proximity_ft": float(pole_data.get("road_proximity_ft", 50.0)),
        "num_transformers": int(pole_data.get("num_transformers", 1)),
        "years_since_last_maintenance": years_since_maint,
        "aqi": float(pole_data.get("aqi", 50)),
        "soil_moisture": float(pole_data.get("soil_moisture", 0.5)),
    }
    return pd.DataFrame([row])[FEATURE_COLS]

def predict_pole(bundle: Dict, pole_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run all three models on a single pole and return enriched prediction."""
    X = engineer_features(pole_data)
    risk_score = float(np.clip(bundle["risk_model"].predict(X)[0], 0, 100))
    fail_prob = float(bundle["fail_model"].predict_proba(X)[0][1])
    storm_prob = float(np.clip(bundle["storm_model"].predict(X)[0], 0, 1))

    # Environmental adjustments (AQI and soil moisture add penalty)
    aqi = pole_data.get("aqi", 50)
    soil_moisture = pole_data.get("soil_moisture", 0.5)
    aqi_penalty = min(max(0, (aqi - 100) / 20), 10)
    soil_penalty = soil_moisture * 5
    risk_score = min(100, risk_score + aqi_penalty + soil_penalty)

    # Adjust storm failure probability based on live wind if available
    live_wind = pole_data.get("live_wind_mph", 0)
    if live_wind > 0:
        storm_prob = np.clip(storm_prob + (live_wind - 25) / 75, 0, 0.98)

    material = pole_data.get("material", "Wood")
    age = pole_data.get("age", 20)
    design_life = {"Wood":40, "Steel":65, "Concrete":70, "Composite":50}.get(material, 45)
    remaining_life = max(0.5, design_life - age - (risk_score/100)*12)

    costs = {"Wood": (6200,2100), "Steel": (9500,3200), "Concrete": (12000,4000), "Composite": (11000,3800)}
    replace_cost, repair_cost = costs.get(material, (6200,2100))

    priority_score = compute_priority_score(risk_score, storm_prob, replace_cost)
    optimal = _optimal_action(risk_score, remaining_life, replace_cost, repair_cost)

    # Get feature contributions for explanation
    fi = bundle["feature_importance"]
    X_dict = X.iloc[0].to_dict()
    contributions = {k: round(fi.get(k,0) * X_dict.get(k,0) * risk_score, 1) for k in FEATURE_COLS if X_dict.get(k,0) > 0}
    top_factors = sorted(contributions.items(), key=lambda x: -x[1])[:5]

    pred = {
        "risk_score": round(risk_score, 1),
        "risk_level": "Critical" if risk_score >=70 else "High" if risk_score >=45 else "Medium" if risk_score >=25 else "Low",
        "failure_probability": round(fail_prob, 3),
        "storm_failure_probability": round(storm_prob, 3),
        "remaining_life_years": round(remaining_life, 1),
        "replace_cost_usd": replace_cost,
        "repair_cost_usd": repair_cost,
        "recommendation": "immediate_replacement" if risk_score >=75 else "replacement_within_12_months" if risk_score >=55 else "repair_and_monitor" if risk_score >=35 else "routine_inspection",
        "priority_score": round(priority_score, 1),
        "optimal_action": optimal,
        "top_risk_factors": [{"factor": k.replace("_"," "), "contribution": v} for k,v in top_factors],
        "model_confidence": round(1.0 - bundle["metrics"]["risk_mae"] / 50, 2),
        "environmental_factors": {
            "aqi": aqi,
            "aqi_penalty": round(aqi_penalty, 1),
            "soil_moisture": round(soil_moisture, 2),
            "soil_penalty": round(soil_penalty, 1)
        }
    }
    return pred

def predict_batch(bundle: Dict, poles: List[Dict]) -> List[Dict]:
    """Run predictions on a list of poles (batch inference)."""
    results = []
    for pole in poles:
        pred = predict_pole(bundle, pole)
        results.append({"pole_id": pole.get("pole_id", "unknown"), **pole, **pred})
    return results

def get_model_metrics(bundle: Dict) -> Dict:
    """Return the metrics dictionary from the bundle."""
    return bundle.get("metrics", {})

def get_feature_importance_report(bundle: Dict) -> List[Dict]:
    """Return a list of feature importance for use in frontend charts."""
    fi = bundle.get("feature_importance", {})
    return [{"feature": k.replace("_"," ").title(), "importance": round(v,4)} for k,v in list(fi.items())[:15]]