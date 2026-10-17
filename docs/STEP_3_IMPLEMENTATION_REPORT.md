# Step 3 Implementation & Audit Report: Dual Frontend (Farmer & Expert Dashboards)

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Repository:** `iamvk09/reducing-crop-failure-using-ai`  
**Report Date:** 2026-09-26  
**Implementation Stage:** Step 3 Complete (Next.js Farmer Dashboard, Expert Workbench, Supabase Auth Integration, Multilingual Localization, Accessible Mobile-First UI)

---

## 1. Executive Summary

This report documents the completion of **Step 3: Dual Frontend Architecture (Farmer & Expert Dashboards)**. The monolithic Streamlit dashboard is augmented with a modern, responsive, TypeScript-powered Next.js frontend split cleanly into two distinct personas:
1. **Farmer Experience (`apps/farmer`):** Ultra-simple, mobile-first, high-contrast, plain-language decision guide for smallholder farmers with one-tap risk evaluation, GPS plot registration, and actionable agronomic advisories across 8 Indian languages.
2. **Expert Workbench (`apps/expert`):** Analytical workbench for agronomists, extension officers, and policy researchers with live parametric Digital Twin stress simulations, SHAP explainability feature attribution, and national/district farm monitoring.

Both applications communicate strictly with the authenticated FastAPI backend gateway via `Authorization: Bearer <token>` without bypassing server-side authorization or database RLS policies.

---

## 2. Frontend Architecture & Directory Layout

```
apps/
├── shared/
│   ├── api/
│   │   ├── client.ts              # Base fetch wrapper with Bearer token injection & timeout control
│   │   ├── auth.ts                # User profile retrieval and update endpoints
│   │   ├── farms.ts               # Farm CRUD API client
│   │   ├── crops.ts               # Crop cycle CRUD API client
│   │   └── experts.ts             # Digital Twin simulation & SHAP explainability client
│   ├── components/
│   │   ├── LanguageSelector.tsx   # 8-language switcher dropdown
│   │   ├── Navbar.tsx             # Responsive header with profile metadata and sign out
│   │   └── RiskBadge.tsx          # Accessible high-contrast Low/Medium/High risk badge
│   ├── context/
│   │   └── AuthContext.tsx        # React Auth provider managing session, tokens, and role routing
│   ├── supabase/
│   │   └── client.ts              # Browser Supabase client (uses only public anon key)
│   ├── translations/
│   │   └── index.ts               # Localization dictionary (EN, HI, MR, BN, TE, TA, KN, GU)
│   └── types/
│       └── index.ts               # Shared TypeScript domain models matching FastAPI schemas
├── farmer/
│   ├── app/
│   │   ├── auth/callback/page.tsx # OAuth callback handler
│   │   ├── farmer/
│   │   │   ├── farms/
│   │   │   │   ├── [farmId]/
│   │   │   │   │   ├── crop/page.tsx # Crop cycle registration & management
│   │   │   │   │   └── page.tsx      # Farm details view
│   │   │   │   ├── new/page.tsx   # Farm registration with GPS / manual coords
│   │   │   │   └── page.tsx       # My Farms listing
│   │   │   └── page.tsx           # Main Farmer Dashboard
│   │   ├── login/page.tsx         # Accessible login page with Google & dev switcher
│   │   ├── globals.css            # Tailwind base & accessibility focus outlines
│   │   ├── layout.tsx             # Root layout with AuthProvider
│   │   └── page.tsx               # Root role-based redirection
│   ├── next.config.js
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
└── expert/
    ├── app/
    │   ├── layout.tsx             # Root layout with AuthProvider
    │   └── page.tsx               # Expert Workbench (Overview, Digital Twin, SHAP, Farms)
    ├── next.config.js
    ├── package.json
    ├── tailwind.config.js
    └── tsconfig.json
```

---

## 3. Persona UX Design & Workflows

### 3.1 Farmer Dashboard Experience (`apps/farmer`)
* **Core Philosophy:** Zero cognitive clutter, high readability, large tap targets, and actionable advice.
* **Key Components:**
  * **Header:** "Welcome, {name}" with instant language switcher.
  * **Current Farm:** Plot name, village, district, state.
  * **Risk Card:** Color + Icon indicator (🟢 Low Risk, ⚡ Medium Risk, ⚠️ High Risk) paired with a plain-language summary.
  * **Live Weather Card:** Real-time temperature, humidity, rainfall, and soil moisture labeled with `Source: Open-Meteo`.
  * **Actionable Advice:** Bulleted next steps (Irrigation timing, pest monitoring).
  * **Farm Registration:** Includes `📍 Use My Current GPS Location` browser geolocation button and manual lat/long fallback.
  * **Crop Management:** Sowing date, growth stage (Sowing, Vegetative, Flowering, Maturity), and season (Kharif, Rabi, Zaid).

### 3.2 Expert Workbench Experience (`apps/expert`)
* **Core Philosophy:** Full transparency, interactive simulation, and explainable AI attribution.
* **Key Components:**
  * **System Telemetry:** Live stats on monitored farms, active ML pipeline (`agri_ai_runtime_bundle`), and weather service status.
  * **Digital Twin Simulator:** Real-time sliders adjusting temperature (-5°C to +5°C) and rainfall (-50% to +50%), instantly recalculating failure probability via `POST /api/v1/experts/simulate`.
  * **SHAP Feature Attribution:** Calculates feature importance ranks (NDVI, Rainfall, Temperature, Water Stress) via `POST /api/v1/experts/explain`.
  * **District Explorer:** View all farms across districts via `GET /api/v1/farms`.
  * **Future Modules:** Satellite ingestion, batch inference, and model version registry clearly badged as *"Coming in a later development phase"* (no mock numbers).

---

## 4. Authentication Flow & Role Routing

```
   [Browser Client]
          │
          │ 1. User clicks "Sign in with Google" or Selects Persona
          ▼
   [Supabase Auth / Google OAuth]
          │
          │ 2. Issues JWT token containing 'sub', 'email', 'app_metadata.role'
          ▼
   [AuthContext.tsx]
          │
          │ 3. Stores session & extracts user profile
          ▼
   [Route Redirection]
          ├─ Role: 'farmer' ──────► Redirects to /farmer
          ├─ Role: 'expert' ──────► Redirects to /expert
          ├─ Role: 'admin'  ──────► Redirects to /expert
          └─ Unauthenticated ─────► Redirects to /login
          │
          │ 4. Makes API Request:
          │    `fetch('/api/v1/farms', { headers: { Authorization: 'Bearer <token>' } })`
          ▼
   [FastAPI Backend Gateway] ──► Validates JWT ──► Enforces RBAC & RLS
```

---

## 5. Multilingual Localization Architecture

Ported and extended from `src/translations.py` into `apps/shared/translations/index.ts`:
* **Supported Languages (8):**
  1. `en`: English
  2. `hi`: हिन्दी (Hindi)
  3. `mr`: मराठी (Marathi)
  4. `bn`: বাংলা (Bengali)
  5. `te`: తెలుగు (Telugu)
  6. `ta`: தமிழ் (Tamil)
  7. `kn`: ಕನ್ನಡ (Kannada)
  8. `gu`: ગુજરાતી (Gujarati)
* **Design Invariant:** Changing the language changes presentation only; ML risk calculations, feature schemas, and database values remain identical.

---

## 6. Verification & Test Execution Results

### 6.1 Frontend Test Suite Execution (Farmer & Expert)
```bash
node apps/farmer/test_farmer.js
node apps/expert/test_expert.js
```
**Output:**
```
=== RUNNING FRONTEND TEST SUITE (FARMER & SHARED) ===
✔ Test 1 Passed: Localization and 8-language translations verified.
✔ Test 2 Passed: Farm input validation and boundary checks verified.
✔ Test 3 Passed: Crop input validation verified.
✔ Test 4 Passed: Role-based routing resolution verified.
✔ Test 5 Passed: ApiError structure verified.
=======================================================
ALL FRONTEND TESTS PASSED SUCCESSFULLY! (5/5 suites)
=======================================================

=== RUNNING FRONTEND TEST SUITE (EXPERT APP) ===
✔ Test 1 Passed: Digital Twin parametric calculation verified.
✔ Test 2 Passed: SHAP feature formatting verified.
=======================================================
ALL EXPERT FRONTEND TESTS PASSED! (2/2 suites)
=======================================================
```

### 6.2 Backend Pytest Suite Execution (32/32 tests passed)
```bash
py -3.13 -m pytest backend/tests -v
```
**Output:**
```
======================= 32 passed, 6 warnings in 1.57s ========================
```

### 6.3 Existing ML System & Digital Twin Regression Suite (14/14 tests passed)
```bash
py -3.13 -m unittest tests/test_live_system.py
```
**Output:**
```
Ran 14 tests in 3.556s
OK
```

### 6.4 Existing Streamlit Dashboard Check
```bash
py -3.13 -c "import dashboard_app; print('Streamlit dashboard loaded successfully!')"
```
**Output:**
```
Streamlit dashboard loaded successfully!
```

---

## 7. Categorical Classification & Status Matrix

| Component / Capability | Status Classification | Details |
| :--- | :--- | :--- |
| **Farmer Next.js Application** | `[IMPLEMENTED IN THIS STEP]` | Mobile-first dashboard, farm/crop registration, risk display. |
| **Expert Next.js Application** | `[IMPLEMENTED IN THIS STEP]` | Technical workbench, Digital Twin sliders, SHAP attribution. |
| **Supabase Auth Integration** | `[IMPLEMENTED IN THIS STEP]` | Frontend OAuth client + Bearer token injection. |
| **Multilingual Localization** | `[IMPLEMENTED IN THIS STEP]` | 8 Indian languages supported with verified translations. |
| **FastAPI Backend Gateway** | `[VERIFIED FROM STEP 1 & 2]` | REST routes, JWT verification, RBAC guards, and services. |
| **ML Runtime Model Bundle** | `[VERIFIED FROM REPOSITORY]` | `models/agri_ai_runtime_bundle.pkl` (RF / CalibratedClassifierCV). |
| **Live Open-Meteo Weather** | `[VERIFIED FROM REPOSITORY]` | `src/weather_service.py` real-time weather feed. |
| **Satellite Imagery Ingestion** | `[PLANNED (Step 4)]` | Google Earth Engine / Sentinel-2 NDVI pipeline. |
| **SMS / WhatsApp Alerts** | `[PLANNED (Step 4)]` | Automated SMS notifications for high-risk alerts. |
| **AI Voice Assistant** | `[PLANNED (Step 4)]` | Speech-to-text / text-to-speech advisory interaction. |
| **7-Day / 14-Day Model** | `[PLANNED (Step 4)]` | Multi-step temporal crop risk trajectory models. |

---

## 8. Local Run Commands

### To run the Farmer Frontend:
```bash
cd apps/farmer
npm run dev
# Accessible at http://localhost:3000
```

### To run the Expert Frontend:
```bash
cd apps/expert
npm run dev
# Accessible at http://localhost:3001
```

### To run the FastAPI Backend:
```bash
uvicorn backend.app.main:app --reload --port 8000
# API documentation at http://localhost:8000/docs
```

### To run the Streamlit Dashboard (Unchanged):
```bash
streamlit run dashboard_app.py
```
