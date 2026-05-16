# ml_model.py
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib
import os

MODEL_PATH = 'pole_risk_model.pkl'

class RiskModel:
    def __init__(self):
        self.model = None

    def train_model(self):
        # Synthetic but representative training data
        data = {
            'tilt': [1,25,45,5,60,12,30,2,55,35],
            'veg_prox': [10,1,0.5,8,0.2,5,2,9,0.3,3],
            'wind': [15,30,55,18,65,42,28,20,60,45],
            'soil_risk': [0,1,1,0,1,1,0,0,1,1],
            'age': [5,30,45,10,70,25,15,8,80,40],
            'material_code': [0,1,0,1,0,1,0,1,0,1],
            'risk_score': [15,75,95,25,99,65,50,18,98,80]
        }
        df = pd.DataFrame(data)
        X = df.drop('risk_score', axis=1)
        y = df['risk_score']
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        return self.model

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
            return True
        return False

    def predict_risk(self, features):
        if self.model is None and not self.load_model():
            self.train_model()
        pred = self.model.predict([features])[0]
        return max(0, min(100, pred))

risk_model = RiskModel()