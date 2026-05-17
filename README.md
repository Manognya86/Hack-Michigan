# ⚡ GridWatch AI
### Predictive Utility Pole Risk Profiling for DTE Energy
**HackMI 2026 · DTE Energy AI Challenge · TechTown Detroit**

---

## What It Does

GridWatch AI turns reactive utility pole maintenance into a proactive, data-driven workflow. It pulls real GPS-located poles from OpenStreetMap across Metro Detroit, enriches each one with live weather, FEMA flood zones, AQI, and soil moisture, runs three simultaneous XGBoost models to score every pole's risk, and surfaces actionable work orders via IBM watsonx.ai — all in a single operational dashboard.

**A maintenance planner can go from storm warning to poles identified, crews assigned, and work orders generated in under 60 seconds.**

---

## Features

- 🗺️ **Live Risk Map** — Real OSM poles on Leaflet, color-coded by severity, with satellite and heatmap overlays
- 🤖 **3 XGBoost Models** — Risk score, failure probability, and storm failure probability across 29 features
- 💬 **watsonx.ai** — IBM Granite 13B generates maintenance recommendations, work orders, and 5-year schedules
- 📷 **Computer Vision** — Upload a pole photo; tilt, cracks, rust, and vegetation feed back into the ML pipeline
- ⛈️ **Storm Simulator** — Dial in wind/gusts/precip and instantly see failures, customers affected, and emergency cost
- 📊 **Priority Engine** — Composite scoring ranks every pole by risk, storm exposure, and replacement cost
- 💰 **Budget Optimizer** — Knapsack algorithm maximizes risk reduction within a spend cap
- 👷 **Fleet Assignment** — Distributes priority poles across field crews by district
- 🔍 **Explainability** — Top contributing factors shown for every prediction, no black boxes

---

## Quickstart

### 1. Clone and install
```bash
git clone https://github.com/YOUR_USERNAME/gridwatch-ai.git
cd gridwatch-ai
pip install -r requirements.txt
```

### 2. Train the models
```bash
python train_model.py
```

### 3. Start the backend
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open the dashboard
Go to `http://localhost:8000` — on first load the backend fetches live OSM poles, weather, and FEMA flood zones (15–30 seconds).

### 5. Configure watsonx.ai (optional)
Create `backend/.env`:
```env
WATSONX_API_KEY=your_ibm_cloud_api_key
WATSONX_PROJECT_ID=your_watsonx_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
```
Without these, the AI Report tab uses the built-in rule-based fallback and remains fully functional.

---

## ML Models

| Model | Type | Target | Performance |
|-------|------|--------|-------------|
| Risk Score | XGBRegressor | 0–100 score | R² ≈ 0.85, MAE ≈ 6 pts |
| Failure Classifier | XGBClassifier | Fail / no-fail | AUC ≈ 0.92 |
| Storm Probability | XGBRegressor | 0–1 probability | MAE ≈ 0.031 |

**29 features** spanning physical condition (age, tilt, cracks, rust), environmental exposure (vegetation, wind, flood zone, soil), operational history (inspection recency, maintenance gap), infrastructure context (height, road proximity, transformers), and environmental quality (AQI, soil moisture).

### Risk Levels

| Score | Level | Action |
|-------|-------|--------|
| 70–100 | 🔴 Critical | Immediate replacement |
| 45–69 | 🟠 High | Replace within 12 months |
| 25–44 | 🔵 Medium | Repair and monitor |
| 0–24 | 🟢 Low | Routine inspection |

---

## Data Sources

All public. No proprietary DTE data required.

| Source | Data |
|--------|------|
| OpenStreetMap Overpass API | Real pole GPS locations |
| Open-Meteo | Live weather + 7-day forecast |
| FEMA NFHL ArcGIS REST | Flood zone per coordinate |
| Synthetic generator | 3,000 calibrated training poles |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/region` | All poles with predictions + weather |
| POST | `/api/predict` | Single pole prediction |
| POST | `/api/storm/simulate` | Storm scenario simulation |
| POST | `/api/cv/analyze` | Computer vision image analysis |
| POST | `/api/ai/recommend` | watsonx.ai recommendation |
| GET | `/api/priority` | Top 20 poles by priority score |
| GET | `/api/analytics` | District, material, age analytics |
| GET | `/api/explain/{id}` | Plain-language pole explanation |
| POST | `/api/cost/optimize` | Budget optimization |
| POST | `/api/fleet/assignment` | Crew assignment |
| GET | `/api/risk_history/{id}` | 90-day risk trend |
| GET | `/api/export/csv` | Full dataset CSV export |
| GET | `/api/report` | PDF priority report |
| POST | `/api/feedback/{id}` | Record field action |
| POST | `/api/refresh` | Force live data refresh |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| ML | XGBoost, scikit-learn, pandas, numpy |
| AI | IBM watsonx.ai — `ibm/granite-13b-instruct-v2` |
| Frontend | Vanilla JS, Leaflet.js, Chart.js, Three.js |
| Data | OpenStreetMap, Open-Meteo, FEMA NFHL |
| Export | ReportLab (PDF), CSV |

---

## Built At

**HackMI 2026** · May 15–17 · TechTown Detroit
**DTE Energy AI Challenge** - Utility Pole Risk Profiling Track
