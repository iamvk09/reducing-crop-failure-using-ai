# AI Crop Failure Project: Reducing Crop Failure Using AI Under Unfavorable Weather Conditions

An AI-driven decision-support platform designed to assist farmers, agricultural officers, and researchers in estimating crop failure risks, exploring resilient crop options, and simulating climate stress scenarios.

**Live Application**: [https://reducecropfailure.onrender.com/](https://reducecropfailure.onrender.com/)

---

## 🔮 Live Crop Risk Prediction

The project features a **Live Crop Risk Prediction** system that combines real-time meteorological conditions with the trained agricultural machine learning pipeline.

### How It Works:
1. **Location & Crop Selection**: The user selects their State, District, and Crop from verified project data.
2. **Free Live Weather Fetching**: Real-time ambient weather (Temperature, Relative Humidity, Precipitation, and Root-zone Soil Moisture) is automatically fetched for the district's exact geographic coordinates from the **Open-Meteo Forecast API**. No API keys, paid services, or secret tokens are required.
3. **ML Pipeline Prediction**: The input row is assembled and fed directly into the saved scikit-learn pipeline (`models/agri_ai_bundle.pkl`). The pipeline performs automatic imputation, scaling, and one-hot encoding, producing a failure risk probability and classification into calibrated risk bands (**Low**, **Medium**, **High**).
4. **Crop Recommendation**: The trained multi-crop recommendation model ranks alternative crop options based on soil-climate compatibility.
5. **SHAP Explainability**: Prediction drivers are interpreted using SHAP (`LinearExplainer` for linear models, `TreeExplainer` for tree ensembles), explaining why a specific prediction has elevated or mitigated risk.
6. **Digital Twin Integration**: The live case seamlessly connects to the environmental Digital Twin, allowing users to simulate drought, heatwave, irrigation changes, or custom weather stress adjustments and observe risk deltas.

---

### Data Provenance & Feature Distinctions

To maintain absolute data integrity, the system clearly separates and documents feature sources:
- **Live Weather**: Instantaneous temperature, humidity, precipitation, and root-zone soil moisture retrieved directly from Open-Meteo.
- **Historical Dataset Baselines**: Seasonal variables that cannot be determined from instantaneous weather readings alone (e.g., cumulative seasonal rainfall, soil type, irrigation level, baseline greenness NDVI, water stress, pest risk) are populated using empirical medians derived from historical district-crop records.
- **User Inputs & Overrides**: The crop selected by the user, plus any manual adjustments made under the **Advanced Inputs** panel in Expert Mode.
- **Derived Values**: Consensus weighting and risk-band classifications computed from specialized regional and crop models.

---

### Farmer Mode vs. Expert Mode

The dashboard provides two tailored interfaces:
- **Farmer Mode**: Minimal, clear, action-oriented guidance in multiple Indian languages (English, Hindi, Marathi, Bengali, Telugu, Tamil, Kannada, Gujarati). Displays current weather, risk percentage, plain-language advisory, and recommended alternative crops without model jargon.
- **Expert Mode**: Full technical diagnostics, model architecture specifications, global/regional/crop consensus breakdowns, SHAP attribution scores, a comprehensive feature provenance audit table, and interactive Digital Twin sliders.

---

### ⚠️ Advisory Disclaimer

> **Academic Prototype & Advisory Notice**: This platform is an academic decision-support prototype. Predictions and risk scores are machine-learning estimates based on available historical and meteorological data and **do not guarantee crop failure or success**. Field decisions should always be cross-referenced with local agricultural authorities, extension officers, and ground observations.

---

## Setup & Local Installation

### Prerequisites
- Python 3.10+
- Virtual environment (`venv`)

### Installation
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Running the Dashboard
```bash
streamlit run dashboard_app.py
```

### CLI Options
```bash
python main.py
```
Menu options:
1. Run existing dataset pipeline
2. Search district summary
3. Run district digital twin simulation
4. **Predict crop failure risk with live weather**

### Running the Automated Tests
```bash
python -m unittest tests/test_live_system.py
```

---

## Project Structure

- `dashboard_app.py` — Streamlit interactive web dashboard featuring the Live Risk Prediction tab.
- `main.py` — Command-line interface for pipeline execution, summaries, simulation, and live prediction.
- `src/live_prediction.py` — Real new-input prediction, feature baseline derivation, recommendation, and SHAP explainability.
- `src/weather_service.py` — Open-Meteo live weather client with caching, error resilience, and coordinate validation.
- `src/digital_twin.py` — Environmental scenario simulator and stress testing engine.
- `src/recommendation_engine.py` — Agronomic advice generator and risk band mapping.
- `src/train_model.py` — Model training pipeline and bundle artifact generation.
- `src/generate_predictions.py` — Precomputed district risk prediction and consensus generation.
- `src/shap_analysis.py` — Model explainability module.
- `src/create_map.py` — Folium-based India interactive crop failure risk map.
- `src/translations.py` — Multilingual localization dictionaries.
- `tests/test_live_system.py` — Automated unit test suite.
- `data/` — District datasets, observed weather/DES data, and prediction summaries.
- `models/` — Trained model bundle (`agri_ai_bundle.pkl`) and evaluation metrics.
- `Dockerfile` — Container deployment configuration for Render and Docker environments.
