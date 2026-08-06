# AI Crop Failure Project

An AI-assisted crop-failure risk analysis project with data generation, model training, predictions, recommendations, SHAP analysis, an interactive risk map, and a dashboard.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

To run the dashboard:

```bash
streamlit run dashboard_app.py
```

## Project structure

- `src/` — data generation, training, predictions, recommendations, mapping, and analysis modules
- `data/` — district datasets and prediction outputs
- `models/` — trained model outputs and evaluation artifacts
- `maps/` — generated India crop-risk map
