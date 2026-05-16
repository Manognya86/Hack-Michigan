# ml_model.py
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
import shap
import joblib
import os
import logging

MODEL_PATH = 'pole_risk_model.pkl'

FEATURE_NAMES = ['tilt_angle', 'veg_proximity', 'wind_speed', 'soil_risk', 'age', 'material_code']
FEATURE_LABELS = {
    'tilt_angle':    'Pole Tilt Angle',
    'veg_proximity': 'Vegetation Proximity',
    'wind_speed':    'Wind Speed',
    'soil_risk':     'Soil / Flood Risk',
    'age':           'Pole Age',
    'material_code': 'Material Type',
}

class RiskModel:
    def __init__(self):
        self.model = None
        self._explainer = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def _build_training_data(self, n=300):
        """Domain-realistic synthetic training data for Michigan utility poles."""
        rng = np.random.RandomState(42)

        age          = rng.randint(1, 80, n).astype(float)
        tilt         = rng.uniform(0, 35, n)
        veg_prox     = rng.uniform(0, 10, n)     # 0 = touching vegetation, 10 = clear
        wind         = rng.uniform(5, 75, n)
        soil_risk    = rng.randint(0, 2, n).astype(float)   # 1 = flood zone AE
        material     = rng.randint(0, 3, n).astype(float)   # 0=wood 1=steel 2=composite

        # Domain-informed score formula (interpretable by design)
        risk = (
            age          * 0.55 +          # older → higher risk
            tilt         * 1.40 +          # tilt is a strong signal
            (10 - veg_prox) * 1.20 +       # closer vegetation → higher risk
            wind         * 0.35 +          # wind exposure
            soil_risk    * 12.0 +          # flood zone penalty
            (material == 0) * 9.0 +        # wood is highest risk
            (material == 2) * -3.0 +       # composite is lowest risk
            rng.normal(0, 4, n)            # realistic noise
        )
        risk = np.clip(risk, 0, 100)

        return pd.DataFrame({
            'tilt_angle':    tilt,
            'veg_proximity': veg_prox,
            'wind_speed':    wind,
            'soil_risk':     soil_risk,
            'age':           age,
            'material_code': material,
            'risk_score':    risk,
        })

    def train_model(self):
        df = self._build_training_data()
        X = df[FEATURE_NAMES]
        y = df['risk_score']
        self.model = XGBRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )
        self.model.fit(X, y)
        self._explainer = None
        joblib.dump(self.model, MODEL_PATH)
        logging.info("Risk model trained and saved.")
        return self.model

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
            return True
        self.train_model()
        return True

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    @property
    def explainer(self):
        if self._explainer is None:
            if self.model is None:
                self.load_model()
            self._explainer = shap.TreeExplainer(self.model)
        return self._explainer

    def predict_risk(self, features: list) -> float:
        if self.model is None:
            self.load_model()
        pred = self.model.predict(np.array([features]))[0]
        return float(np.clip(pred, 0, 100))

    # ------------------------------------------------------------------
    # Explainability (SHAP)
    # ------------------------------------------------------------------
    def explain_prediction(self, features: list) -> dict:
        """
        Return a SHAP-based explanation for a single prediction.
        Satisfies the challenge's explicit explainability criterion:
        'Decisions are interpretable — no black-box scoring without justification.'
        """
        arr = np.array([features])
        shap_vals = self.explainer.shap_values(arr)[0]
        base_val  = float(self.explainer.expected_value)
        predicted = float(np.clip(self.model.predict(arr)[0], 0, 100))

        factors = []
        for name, raw_val, sv in zip(FEATURE_NAMES, features, shap_vals):
            # Human-readable value
            if name == 'material_code':
                human_val = {0: 'Wood', 1: 'Steel', 2: 'Composite'}.get(int(raw_val), 'Unknown')
            elif name == 'soil_risk':
                human_val = 'Flood Zone AE' if raw_val == 1 else 'Low Flood Risk'
            elif name == 'veg_proximity':
                human_val = f"{raw_val:.1f}/10 clearance"
            elif name == 'tilt_angle':
                human_val = f"{raw_val:.1f}°"
            elif name == 'age':
                human_val = f"{int(raw_val)} yrs"
            else:
                human_val = f"{raw_val:.1f}"

            factors.append({
                'feature':      name,
                'label':        FEATURE_LABELS[name],
                'raw_value':    round(float(raw_val), 2),
                'human_value':  human_val,
                'contribution': round(float(sv), 2),
                'direction':    'increases_risk' if sv > 0 else 'reduces_risk',
                'abs_impact':   abs(round(float(sv), 2)),
            })

        factors.sort(key=lambda x: x['abs_impact'], reverse=True)
        top = factors[0]

        return {
            'base_value':     round(base_val, 2),
            'predicted_score': round(predicted, 2),
            'risk_level':     'High' if predicted >= 70 else 'Medium' if predicted >= 45 else 'Low',
            'factors':        factors,
            'primary_reason': (
                f"{top['label']} ({top['human_value']}) is the primary risk driver "
                f"(SHAP contribution: +{top['contribution']:.1f})"
                if top['contribution'] > 0 else
                f"{top['label']} ({top['human_value']}) is reducing risk "
                f"(SHAP contribution: {top['contribution']:.1f})"
            ),
            'action_summary': (
                'REPLACE within 30 days' if predicted >= 85 else
                'REPAIR within 90 days' if predicted >= 70 else
                'INSPECT within 6 months' if predicted >= 45 else
                'MONITOR — schedule routine inspection'
            ),
        }

    def data_confidence(self, missing_signals: list) -> str:
        total = len(FEATURE_NAMES)
        available = total - len(missing_signals)
        ratio = available / total
        if ratio >= 0.9:
            return 'high'
        elif ratio >= 0.6:
            return 'medium'
        return 'low'

    def feature_importance(self) -> dict:
        if self.model is None:
            self.load_model()
        imp = self.model.feature_importances_
        return {n: round(float(v), 4) for n, v in zip(FEATURE_NAMES, imp)}


risk_model = RiskModel()