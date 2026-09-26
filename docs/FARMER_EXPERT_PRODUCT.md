# Agricultural Decision-Support Platform: Farmer vs. Expert Product Specification

**Document Version:** 1.0.0  
**Status Classification Legend:**
* `[VERIFIED FROM REPOSITORY]`: Logic, feature, or asset that currently exists and functions in the codebase.
* `[IMPLEMENTED IN THIS STEP]`: Architecture, backend schemas, API contracts, or database DDL created in Step 1.
* `[PLANNED]`: Target production capabilities designed for subsequent implementation phases.
* `[NOT VERIFIED]`: Third-party external integrations or assumptions requiring empirical validation.

---

## 1. Executive Summary & Vision

The platform transitions from a monolithic academic dashboard (`dashboard_app.py`) `[VERIFIED FROM REPOSITORY]` into a dual-persona decision support platform:
1. **Farmer Experience (`/app/farmer`):** Ultra-lightweight, accessible, low-bandwidth, and actionable decision assistance designed for individual farm plots.
2. **Expert & Agronomist Experience (`/app/expert`):** Analytical, multi-dimensional, explainable AI workbench with Digital Twin simulation capabilities for researchers, extension workers, and agronomists.

Both interfaces consume a unified, authenticated FastAPI backend `[IMPLEMENTED IN THIS STEP]` and Supabase database `[IMPLEMENTED IN THIS STEP]` while sharing the underlying validated ML pipeline (`src/live_prediction.py`, `src/digital_twin.py`, `src/recommendation_engine.py`) `[VERIFIED FROM REPOSITORY]`.

---

## 2. Persona 1: Farmer Experience

### 2.1 Target Audience & Context
* **Audience:** Smallholder farmers, farm managers, and local agricultural producers.
* **Device Profiles:** Android mobile devices, low-bandwidth 3G/4G connectivity, intermittent internet access.
* **Primary Goal:** Know immediately whether their current crop is at risk of failure, why, and what specific action to take today and in the coming week.

### 2.2 Key Principles
1. **Zero Cognitive Overload:** No technical ML jargon (no standard deviations, SHAP values, or raw pipeline names).
2. **Action-Oriented Output:** Every risk rating must be paired with clear agronomic mitigation steps.
3. **Automated Context:** Minimize required inputs by automatically fetching real-time weather (`src/weather_service.py`) and empirical district baselines `[VERIFIED FROM REPOSITORY]`.
4. **Multilingual Accessibility:** Support regional Indian languages (Hindi, Marathi, Telugu, Tamil, Punjabi, Bengali, Kannada, Gujarati, English) `[PLANNED]`.

### 2.3 User Workflow

```
[Login / OTP Auth] 
       ↓
[Select / Add Farm Plot] (State, District, Soil Type, Irrigation)
       ↓
[Select Current Crop & Season]
       ↓
[One-Tap Risk Assessment]
       ↓
[Live Weather Fetch (Open-Meteo API)]
       ↓
[Result: Risk Card + Top 3 Contributing Factors + Actionable Advice]
       ↓
[7-Day Outlook & Alert Subscription (SMS / WhatsApp)]
```

### 2.4 Functional Capabilities

| Feature | Description | Technical Backing | Status |
| :--- | :--- | :--- | :--- |
| **Simple Farm Registration** | Save farm name, location (State, District), soil type, and irrigation level. | `farms` table in Supabase | `[IMPLEMENTED IN THIS STEP]` |
| **Instant Live Prediction** | One-click risk assessment using Open-Meteo real-time temperature, humidity, rainfall, and soil moisture. | `POST /api/v1/predictions/live` calling `src/live_prediction.py` | `[IMPLEMENTED IN THIS STEP]` |
| **Traffic Light Risk Indicator** | Clear color badge: Green (Low Risk < 35%), Amber (Medium Risk 35–65%), Red (High Risk > 65%). | `classify_risk()` in `src/live_prediction.py` | `[VERIFIED FROM REPOSITORY]` |
| **Plain-Language Explanations** | Translates model drivers (e.g. "NDVI below normal", "Water stress elevated") into plain text. | `explain_prediction_heuristic()` in `src/live_prediction.py` | `[VERIFIED FROM REPOSITORY]` |
| **Actionable Recommendations** | Targeted advice categorized into Irrigation, Soil, Protection, and Practice. | `generate_live_recommendations()` in `src/recommendation_engine.py` | `[VERIFIED FROM REPOSITORY]` |
| **7-Day Risk Trajectory** | 7-day weather trend with anticipated risk movement. | `get_weather_forecast()` | `[PLANNED]` |
| **Automated Alerts** | Proactive notifications when risk shifts from Low/Med to High. | `alerts` table & Notification Worker | `[PLANNED]` |

---

## 3. Persona 2: Expert / Agronomist / Policy Workbench

### 3.1 Target Audience & Context
* **Audience:** Agricultural extension officers, research agronomists, crop insurance underwriters, district agricultural authorities.
* **Device Profiles:** Desktop browsers, tablets, high-resolution multi-monitor setups.
* **Primary Goal:** Deep inspection of risk distributions across regions, explainable AI attribution, scenario stress-testing ("what-if" modeling), and crop suitability comparison.

### 3.2 Key Principles
1. **Full Transparency & Auditability:** Raw feature vectors, confidence scores, probability distributions, and provenance metadata visible.
2. **Interactive Simulation:** What-if parameter tuning without altering permanent farm records.
3. **Multi-Crop Benchmarking:** Compare risk profiles across 10+ crops simultaneously for a given climate scenario.
4. **Spatial Analytics:** National and district-level risk mapping with layer filtering.

### 3.3 User Workflow

```
[Expert Login (JWT / RBAC)]
       ↓
[Dashboard: Regional Heatmaps & High-Risk Alert Queue]
       ↓
[Deep-Dive Inspection: Select District / Crop / Climate Vector]
       ↓
[SHAP Explainability Waterfall & Feature Importance]
       ↓
[Digital Twin Simulation: Adjust Temperature (+2°C), Drought (-30% Rain)]
       ↓
[Evaluate Multi-Crop Resilience & Generate Extension Advisory]
```

### 3.4 Functional Capabilities

| Feature | Description | Technical Backing | Status |
| :--- | :--- | :--- | :--- |
| **National Risk Heatmap** | Interactive geospatial visualization of crop failure vulnerability across Indian districts. | Pre-generated Folium maps & GeoJSON layers | `[VERIFIED FROM REPOSITORY]` |
| **Model Explainability (SHAP)** | TreeExplainer waterfall plots and feature contribution rankings for Random Forest / Gradient Boosting models. | `src/shap_analysis.py` (lazy imported on demand) | `[VERIFIED FROM REPOSITORY]` |
| **Digital Twin Simulator** | Real-time parametric simulation adjusting temperature (+/- 5°C), rainfall (+/- 50%), soil moisture, and water stress. | `src/digital_twin.py` (`DigitalTwinSimulator`) | `[VERIFIED FROM REPOSITORY]` |
| **Crop Resilience Comparison** | Multi-crop vulnerability matrix identifying resilient alternatives for distressed zones. | `simulate_all_crops()` in `src/digital_twin.py` | `[VERIFIED FROM REPOSITORY]` |
| **Baseline Provenance Viewer** | Full visibility into whether a feature originated from Open-Meteo live observation, district empirical baseline, or expert override. | `provenance` metadata in `src/live_prediction.py` | `[VERIFIED FROM REPOSITORY]` |
| **Model Governance & Auditing** | Model versioning, feature schemas, training metrics, and inference audit logging. | `model_versions` & `audit_logs` tables | `[IMPLEMENTED IN THIS STEP]` |
| **Batch District Analysis** | Run predictions and scenario simulations across an entire state or agro-climatic region. | `POST /api/v1/experts/scenarios/batch` | `[PLANNED]` |

---

## 4. Shared Backend & Data Services Architecture

```
                                  ┌───────────────────────────┐
                                  │   Web Clients (Next.js)   │
                                  ├─────────────┬─────────────┤
                                  │ Farmer View │ Expert View │
                                  └──────┬──────┴──────┬──────┘
                                         │             │
                                         ▼             ▼
                                  ┌───────────────────────────┐
                                  │   FastAPI Gateway (v1)    │
                                  │  - Auth & RBAC Middleware │
                                  │  - Schema Validation      │
                                  │  - Service Orchestration  │
                                  └─────────────┬─────────────┘
                                                │
                      ┌─────────────────────────┼─────────────────────────┐
                      ▼                         ▼                         ▼
        ┌──────────────────────────┐ ┌────────────────────┐ ┌──────────────────────────┐
        │    Supabase PostgreSQL   │ │ ML Runtime Service │ │   External Weather API   │
        │ - users, farms, crops    │ │ - live_prediction  │ │ - Open-Meteo REST API    │
        │ - predictions, alerts    │ │ - digital_twin     │ │ - Real-time meteo feeds  │
        │ - recommendations, logs  │ │ - shap_analysis    │ │                          │
        └──────────────────────────┘ └────────────────────┘ └──────────────────────────┘
```

---

## 5. Migration Roadmap & Feature Matrix

| Capability | Streamlit App (`dashboard_app.py`) `[VERIFIED]` | Target Farmer Portal `[PLANNED]` | Target Expert Workbench `[PLANNED]` | Backend API `[IMPLEMENTED]` |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication** | None (Public) | Phone OTP / Supabase Auth | Email + MFA / RBAC | JWT Auth Middleware |
| **Live Prediction** | Form-based (Tabs) | Mobile Card Flow | Advanced Matrix Form | `POST /api/v1/predictions/live` |
| **Saved Farms** | Ephemeral (Session) | Persistent in Supabase | Multi-tenant Client Farms | `GET/POST /api/v1/farms` |
| **Weather Fetch** | Synchronous Open-Meteo | Cached Background Poll | Real-time + Historical | `POST /api/v1/weather/fetch` |
| **SHAP Analysis** | Matplotlib in Streamlit | Simplified Badges | Interactive Force/Waterfall | `POST /api/v1/predictions/{id}/explain` |
| **Digital Twin** | Sliders in Streamlit | Not Exposed | Full Simulation Suite | `POST /api/v1/experts/scenarios/simulate` |
| **Recommendations** | Markdown Cards | Action Checklist / Audio | Extension Advisory Generator | `GET /api/v1/recommendations` |
| **Offline Support** | No | PWA Cache + SMS Sync | No | PWA Service Worker |
