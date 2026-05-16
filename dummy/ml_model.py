import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import logging

logger = logging.getLogger(__name__)
MODEL_PATH = 'pole_risk_model.pkl'

class RiskModel:
    def __init__(self):
        self.model = None

    def train_model(self):
        """Train model on 6 features: tilt, veg_prox, wind, soil_risk, age, material_code"""
        data = {
            'tilt': [1,25,45,5,60,12,30,2,55,35,8,18,3,42,15,20,10,33,48,22],
            'veg_prox': [10,1,0.5,8,0.2,5,2,9,0.3,3,6,4,0.8,7,1.5,3.5,2.2,0.6,4.5,1.2],
            'wind': [15,30,55,18,65,42,28,20,60,45,35,25,40,50,22,38,32,48,55,28],
            'soil_risk': [0,1,1,0,1,1,0,0,1,1,0,1,1,1,0,0,1,0,1,1],
            'age': [5,30,45,10,70,25,15,8,80,40,12,55,20,65,35,18,50,6,42,28],
            'material_code': [0,1,0,1,0,1,0,1,0,1,0,0,1,0,1,1,0,1,0,1],
            'risk_score': [15,75,95,25,99,65,50,18,98,80,35,88,42,92,55,28,70,38,85,60]
        }
        df = pd.DataFrame(data)
        X = df[['tilt','veg_prox','wind','soil_risk','age','material_code']]
        y = df['risk_score']
        self.model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        logger.info("Risk model trained with 6 features.")
        return self.model

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info(f"Risk model loaded from disk (expects {self.model.n_features_in_} features)")
                return True
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
        return False

    def predict_risk(self, features):
        """features must contain 6 values: [tilt, veg_prox, wind, soil_risk, age, material_code]"""
        if self.model is None:
            if not self.load_model():
                self.train_model()
        
        # Validate and fix feature length
        expected = self.model.n_features_in_
        if len(features) != expected:
            logger.warning(f"Expected {expected} features, got {len(features)}. Truncating/padding.")
            if len(features) > expected:
                features = features[:expected]
            else:
                features = features + [0] * (expected - len(features))
        
        pred = self.model.predict([features])[0]
        return max(0, min(100, pred))

risk_model = RiskModel()