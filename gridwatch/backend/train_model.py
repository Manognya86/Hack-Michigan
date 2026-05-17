"""
train_model.py – Run this FIRST to generate synthetic data and train the XGBoost model.
Place this file in the project root (gridwatch/). It will:
- Create data/ and models/ folders if missing.
- Generate 3000 synthetic poles (or load existing CSV).
- Train three XGBoost models (risk score, failure classifier, storm probability).
- Save the model bundle to models/risk_model.pkl.
"""

import sys
import os

# Add backend folder to Python path so we can import its modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import pandas as pd
from synthetic_data import generate_dataset
from ml_model import train_models, save_bundle

def main():
    # Create directories if they don't exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    data_path = "data/training_poles.csv"
    if not os.path.exists(data_path):
        print("Generating synthetic training dataset (3000 poles)...")
        df = generate_dataset(3000)
        df.to_csv(data_path, index=False)
        print(f"Saved dataset to {data_path}")
    else:
        print(f"Loading existing dataset from {data_path}")
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} poles")

    print("\nTraining XGBoost models...")
    bundle = train_models(df)
    save_bundle(bundle, "models/risk_model.pkl")

    print("\n✅ Training complete!")
    print(f"  Risk Score R²  : {bundle['metrics']['risk_r2']:.3f}")
    print(f"  Risk Score MAE : {bundle['metrics']['risk_mae']:.2f} pts")
    print(f"  Failure AUC    : {bundle['metrics']['fail_auc']:.3f}")
    print(f"  Storm Prob MAE : {bundle['metrics']['storm_mae']:.4f}")
    print("\nNow start the backend:")
    print("  cd backend")
    print("  uvicorn main:app --reload --port 8000")
    print("  (or python main.py)")

if __name__ == "__main__":
    main()