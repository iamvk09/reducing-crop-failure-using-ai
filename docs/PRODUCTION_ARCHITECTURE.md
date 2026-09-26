# Production Architecture & Migration Blueprint

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Repository:** `https://github.com/iamvk09/reducing-crop-failure-using-ai`  
**Phase:** Step 1 — Production Foundation & Architectural Blueprint  

---

## 1. Executive Summary

This document establishes the production architecture, service boundaries, database design, and migration strategy to evolve the existing academic/demo crop failure risk application into a reliable, enterprise-grade agricultural decision-support platform.

---

## 2. Current Architecture (As-Is Code Audit)

The current system operates as a monolithic Streamlit application with embedded ML pipelines, in-memory caching, and external REST calls:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Monolithic Streamlit UI                           │
│                              (dashboard_app.py)                             │
│  - Farmer Interface (Field, Crop, Season, Weather, Advice)                  │
│  - Expert Mode (SHAP Feature Attribution, Digital Twin Simulator)           │
│  - Multi-lingual Localization (8 Indian Languages via src/translations.py)  │
└──────────────┬──────────────────────────────┬───────────────────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌────────────────────────────────────────────┐
│      Open-Meteo Weather      │ │            Core ML Pipeline                │
│    (src/weather_service.py)  │ │         (src/live_prediction.py)           │
│ - Free REST API endpoint     │ │ - Slim Runtime Bundle                      │
│ - Timezone: Asia/Kolkata     │ │   (models/agri_ai_runtime_bundle.pkl)      │
│ - In-Memory Cache (TTL=1800) │ │ - LogisticRegression Classifier            │
│ - Graceful Fallback Strategy │ │ - Lazy Specialized Regional & Crop Models  │
└──────────────┬───────────────┘ │   (_LazyModelDict -> models/specialized/)  │
               │                 │ - Lazy SHAP LinearExplainer                │
               │                 │ - Crop Recommendation Model                │
               │                 └─────────────────────┬──────────────────────┘
               │                                       │
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Empirical Baseline Dataset                            │
│                       (data/district_dataset.csv)                           │
│ - 93 Districts across 32 States and 11 Agro-Climatic Regions                │
│ - Historical Crop Cycles, Soil Types, Irrigation Levels, Yield Indices      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Current Architectural Characteristics:
1. **Frontend + Backend Couplings:** Streamlit executes directly inside the Python runtime, sharing process memory with model artifacts.
2. **State Management:** Transient in-memory state (`st.session_state`), with no persistent multi-tenant database.
3. **Authentication:** None currently (public web application).
4. **Memory Constraint:** Operates under a 512 MB Render memory budget, successfully optimized down to ~175–245 MB RSS via slim runtime bundles and lazy imports.

---

## 3. Target Architecture (Production Platform)

The target architecture decouples presentation, business orchestration, ML inference, data ingestion, and multi-tenant persistence:

```
          Farmer Web / Mobile UI                    Expert & Agronomist Dashboard
             (Next.js / PWA)                               (Next.js / React)
                    │                                              │
                    └──────────────────────┬───────────────────────┘
                                           │ HTTPS / JWT Bearer
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │               FastAPI Gateway                │
                    │               (backend/app/)                 │
                    │ - JWT Verification (Supabase Auth)           │
                    │ - Role-Based Access Control (RBAC)           │
                    │ - Rate Limiting & Input Validation           │
                    │ - Structured Error Handling & Audit Logs     │
                    └──────┬───────────────┬───────────────┬───────┘
                           │               │               │
        ┌──────────────────┘               │               └──────────────────┐
        ▼                                  ▼                                  ▼
┌───────────────────────┐      ┌───────────────────────┐      ┌───────────────────────┐
│ Supabase PostgreSQL   │      │  ML Prediction Engine │      │ External Data Engine  │
│ (Multi-Tenant & RLS)  │      │ (PredictionService)   │      │ (WeatherService & ETL)│
│                       │      │                       │      │                       │
│ - Users & Profiles    │      │ - Pipeline Scikit     │      │ - Open-Meteo Live API │
│ - Farms & Crop Cycles │      │ - Regional/Crop Mod.  │      │ - Sentinel-2 Satellite│
│ - Weather Cache       │      │ - SHAP Explainer      │      │   Vegetation Indices  │
│ - Predictions History │      │ - Digital Twin Sim.   │      │ - Historical Baselines│
│ - Agronomic Advisories│      │ - Recommendation Mod. │      │ - India District GIS  │
│ - Alert Notifications │      └───────────┬───────────┘      └───────────┬───────────┘
└───────────┬───────────┘                  │                              │
            │                              └──────────────┬───────────────┘
            │                                             │
            ▼                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               Proactive Alert Engine                                │
│ - Environmental Stress Evaluator (Drought, Heatwave, Pest Incursion)                │
│ - In-App Notification Dispatcher                                                    │
│ - Farmer SMS / WhatsApp Push Adapters (Future)                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Migration Matrix

Every file and component in the repository is classified into one of five migration categories:
- **`KEEP`**: Retain as-is or as part of existing baseline logic.
- **`MODIFY`**: Enhance to align with production standards.
- **`MOVE`**: Relocate into the clean backend/service boundary.
- **`REPLACE LATER`**: Maintain for backward compatibility during transition, then replace.
- **`NEW`**: Newly created foundation component.

| Component / File | Current Role | Target Classification | Target Disposition & Rationale |
|---|---|---|---|
| `dashboard_app.py` | Streamlit Monolith UI | `REPLACE LATER` | **KEEP** during transition to maintain existing deployment. Eventually superseded by decoupled Next.js Farmer & Expert frontends. |
| `main.py` | CLI Entrypoint & Pipeline Runner | `KEEP` | Retain as offline pipeline execution and operational CLI tool. |
| `src/live_prediction.py` | Core Prediction Engine & Schema Validation | `MOVE` / `KEEP` | Wrapped by `PredictionService` in `backend/app/services/prediction_service.py`. Pure algorithmic logic retained intact. |
| `src/weather_service.py` | Open-Meteo Integration with Fallbacks | `MOVE` / `KEEP` | Wrapped by `WeatherService` behind the backend service boundary. |
| `src/recommendation_engine.py` | Agronomic Advisory & Risk Band Logic | `KEEP` | Referenced directly by prediction service boundary. |
| `src/digital_twin.py` | Environmental Stress Simulator | `KEEP` | Accessible via `/api/v1/experts/simulate` endpoint. |
| `src/shap_analysis.py` | Global Batch SHAP Analysis | `KEEP` | Retained for offline model diagnostics and image generation. |
| `src/train_model.py` | Model Training Pipeline | `KEEP` | Retained for reproducible offline retraining workflows. |
| `src/generate_predictions.py` | Batch District Risk Prediction | `KEEP` | Retained for batch district ranking and offline map generation. |
| `src/create_map.py` | Folium GeoJSON Map Generator | `KEEP` | Retained for offline spatial risk layer generation. |
| `src/translations.py` | 8-Language Localized Dictionaries | `MOVE` | Will serve as backend i18n dictionary for localized notifications. |
| `src/memory_diagnostics.py` | Lightweight Memory RSS Logger | `KEEP` | Retained for resource monitoring on memory-constrained servers. |
| `models/agri_ai_runtime_bundle.pkl` | Slim Production Model Bundle | `KEEP` | Primary serialized model artifact used by `PredictionService`. |
| `models/specialized/` | 20 Lazy Regional & Crop Models | `KEEP` | Retained for on-demand lazy loading via `_LazyModelDict`. |
| `data/district_dataset.csv` | Baseline District Dataset | `KEEP` | Retained as empirical baseline data source and DB seed data. |
| `data/district_predictions.csv` | Pre-computed District Risk Table | `KEEP` | Retained for historical comparison and district search. |
| `data/district_summary.csv` | District Risk Leaderboard Table | `KEEP` | Retained for macro analytics. |
| `maps/india_risk_map.html` | Pre-generated Folium Map HTML | `KEEP` | Retained for interactive spatial visualization. |
| `backend/app/main.py` | FastAPI Application Core | `NEW` | Production HTTP API gateway with routing, CORS, and exception shielding. |
| `backend/app/core/config.py` | Pydantic Settings & Env Binding | `NEW` | Centralized environment variable parsing and configuration. |
| `backend/app/core/security.py` | JWT Decoding & RBAC Helpers | `NEW` | Supabase Auth validation and role enforcement. |
| `backend/app/api/deps.py` | Dependency Injection | `NEW` | Provides user auth, service singletons, and role guards. |
| `backend/app/api/routes/` | REST Endpoints | `NEW` | Modular routers for health, auth, farms, predictions, recommendations, and experts. |
| `backend/app/services/` | Service Layer Abstraction | `NEW` | Clean Python boundary wrapping existing ML code without algorithm duplication. |
| `supabase/migrations/001_initial_schema.sql` | Supabase DB Schema | `NEW` | PostgreSQL tables, foreign keys, indexes, triggers, and RLS policies. |
| `.env.example` | Environment Configuration Template | `NEW` | Clean template with zero committed secrets. |
| `docs/SECURITY_MODEL.md` | Security & RBAC Specification | `NEW` | Complete security, auth, RLS, and data protection specification. |
| `docs/API_CONTRACT.md` | OpenAPI REST Contracts | `NEW` | Comprehensive API contract definitions for all endpoints. |
| `docs/FARMER_EXPERT_PRODUCT.md` | Product Requirements Document | `NEW` | Farmer vs Expert interface workflows, telemetry, and capabilities. |
| `docs/STEP_1_IMPLEMENTATION_REPORT.md` | Implementation Audit Report | `NEW` | Rigorous classification and verification report for Step 1. |

---

## 5. Phased Implementation Roadmap

```
Step 1 (CURRENT) ────► Step 2 ───────────────► Step 3 ───────────────► Step 4
• Backend Foundation   • Supabase Live Conn    • Next.js Frontends     • Satellite Ingestion
• Schema Migrations    • Farm Persistence      • Farmer PWA (Offline)  • Push Notifications
• Model Service Layer  • Prediction History    • Expert Analytics UI   • 14-day Weather Models
• Architecture Specs   • Live Weather Ingest   • Visual Risk Maps      • Voice Interface
```
