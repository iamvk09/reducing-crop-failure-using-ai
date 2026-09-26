# REST API Contract Specification

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Base URL:** `/api/v1`  
**Specification Standard:** OpenAPI 3.1 / RESTful JSON  
**Authentication Scheme:** `Authorization: Bearer <Supabase_JWT_Token>`  

---

## 1. Authentication & User Profile

### 1.1 GET `/api/v1/auth/me`
* **Purpose:** Retrieve the profile and role metadata of the currently authenticated user.
* **HTTP Method:** `GET`
* **Authentication:** Required (`Bearer JWT`)
* **Role Requirement:** `farmer`, `expert`, or `admin`
* **Request Schema:** None (Headers only)
* **Response Schema (200 OK):**
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "farmer@example.com",
    "full_name": "Ramesh Kumar",
    "role": "farmer",
    "phone_number": "+919876543210",
    "preferred_language": "hi"
  }
  ```
* **Possible Errors:**
  * `401 Unauthorized`: Missing or invalid JWT token.
  * `404 Not Found`: User profile not found in database.

---

## 2. Farm & Crop Management

### 2.1 GET `/api/v1/farms`
* **Purpose:** List all farm plots registered by the authenticated farmer (or all farms if expert/admin).
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer`, `expert`, `admin`
* **Request Schema:** None
* **Response Schema (200 OK):**
  ```json
  [
    {
      "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "North Field Plot 1",
      "state": "Maharashtra",
      "district": "Pune",
      "region": "Western Plateau",
      "latitude": 18.5204,
      "longitude": 73.8567,
      "area_hectares": 2.5,
      "soil_type": "Medium Black",
      "irrigation_level": "Medium",
      "created_at": "2026-09-26T10:00:00Z"
    }
  ]
  ```
* **Possible Errors:**
  * `401 Unauthorized`

### 2.2 POST `/api/v1/farms`
* **Purpose:** Register a new farm plot.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer`, `admin`
* **Request Schema:**
  ```json
  {
    "name": "North Field Plot 1",
    "state": "Maharashtra",
    "district": "Pune",
    "latitude": 18.5204,
    "longitude": 73.8567,
    "area_hectares": 2.5,
    "soil_type": "Medium Black",
    "irrigation_level": "Medium"
  }
  ```
* **Response Schema (201 Created):** Same as `FarmResponse`
* **Possible Errors:**
  * `400 Bad Request`: Invalid coordinates or location outside supported agro-climatic boundaries.
  * `422 Unprocessable Entity`: Validation failure on required fields.

### 2.3 GET `/api/v1/farms/{farm_id}`
* **Purpose:** Retrieve specific farm details by UUID.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `expert`, `admin`
* **Response Schema (200 OK):** `FarmResponse` object
* **Possible Errors:**
  * `403 Forbidden`: Attempting to access another farmer's plot.
  * `404 Not Found`: Farm ID not found.

### 2.4 POST `/api/v1/farms/{farm_id}/crops`
* **Purpose:** Record an active crop planting cycle on a farm.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer` (owner), `admin`
* **Request Schema:**
  ```json
  {
    "crop": "Soybean",
    "season": "Kharif",
    "sowing_date": "2026-06-15",
    "expected_harvest_date": "2026-10-15"
  }
  ```
* **Response Schema (201 Created):**
  ```json
  {
    "id": "f8e7d6c5-b4a3-2109-8765-4321fedcba98",
    "farm_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "crop": "Soybean",
    "season": "Kharif",
    "sowing_date": "2026-06-15",
    "expected_harvest_date": "2026-10-15",
    "status": "active",
    "is_active": true,
    "created_at": "2026-09-26T10:05:00Z"
  }
  ```

### 2.5 GET `/api/v1/farms/{farm_id}/weather`
* **Purpose:** Retrieve current live weather conditions and 7-day precipitation for a farm plot.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (owner), `expert`, `admin`
* **Response Schema (200 OK):**
  ```json
  {
    "farm_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "temperature_c": 28.4,
    "humidity_pct": 72.0,
    "precipitation_mm": 2.5,
    "soil_moisture_pct": 46.5,
    "weather_code": 3,
    "source": "Open-Meteo (Meteorological Model Estimate)",
    "timestamp": "2026-09-26 15:30",
    "is_estimate": true
  }
  ```

### 2.6 GET `/api/v1/farms/{farm_id}/satellite`
* **Purpose:** Retrieve vegetation and crop moisture indices derived from Sentinel-2 satellite observations.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (owner), `expert`, `admin`
* **Response Schema (200 OK):**
  ```json
  {
    "farm_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "observation_date": "2026-09-24",
    "ndvi_mean": 0.68,
    "ndvi_min": 0.52,
    "ndvi_max": 0.74,
    "water_stress_index": 0.22,
    "source": "Sentinel-2 / Derived"
  }
  ```

---

## 3. Crop Failure Prediction & Recommendations

### 3.1 POST `/api/v1/predictions`
* **Purpose:** Generate a real-time crop failure risk evaluation for a field profile.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer`, `expert`, `admin`
* **Request Schema:**
  ```json
  {
    "farm_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "state": "Maharashtra",
    "district": "Pune",
    "crop": "Soybean",
    "season": "Kharif",
    "soil_type": "Medium Black",
    "irrigation_level": "Medium",
    "rainfall_override": null,
    "temperature_override": null,
    "humidity_override": null,
    "soil_moisture_override": null,
    "ndvi_override": null,
    "water_stress_override": null,
    "pest_risk_override": null,
    "suitability_score_override": null,
    "yield_index_override": null
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "prediction_id": "99e8d7c6-b5a4-3210-fedc-ba9876543210",
    "crop": "Soybean",
    "district": "Pune",
    "state": "Maharashtra",
    "season": "Kharif",
    "risk_probability": 0.4297,
    "risk_percentage": "43.0%",
    "risk_level": "Low",
    "prediction_class": 0,
    "best_model_name": "logistic_regression",
    "global_risk": 0.4297,
    "region_risk": 0.4150,
    "crop_risk": 0.4410,
    "consensus_risk": 0.4297,
    "input_features": {
      "Year": 2026,
      "Rainfall": 140.56,
      "Temperature": 27.5,
      "Humidity": 74.0,
      "SoilMoisture": 48.0,
      "NDVI_Flowering": 0.696,
      "WaterStress": 0.193,
      "PestRisk": 0.462,
      "SuitabilityScore": 0.764,
      "YieldIndex": 78.9,
      "State": "Maharashtra",
      "Region": "Western Plateau",
      "Season": "Kharif",
      "Crop": "Soybean",
      "SoilType": "Medium Black",
      "IrrigationLevel": "Medium"
    },
    "provenance": {
      "Temperature": "Live weather estimate (Open-Meteo)",
      "Humidity": "Live weather estimate (Open-Meteo)",
      "SoilMoisture": "Live weather estimate (Open-Meteo root-zone moisture)",
      "Rainfall": "Historical seasonal baseline (District-Crop-Season median)",
      "NDVI_Flowering": "Historical baseline (District-Crop-Season median)"
    },
    "disclaimer": "This is a machine-learning estimate based on available meteorological and agronomic data and is not a guarantee of crop failure.",
    "created_at": "2026-09-26T15:30:00Z"
  }
  ```
* **Possible Errors:**
  * `422 Unprocessable Entity`: Input validation failure (e.g. invalid state/crop, out-of-bounds numeric).
  * `500 Internal Server Error`: Model execution exception.

### 3.2 GET `/api/v1/recommendations/{district}/{crop}`
* **Purpose:** Retrieve ranked safer crop alternatives and plain-language advisory guidance.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Response Schema (200 OK):**
  ```json
  {
    "recommended_crop": "Soybean",
    "top_options": [
      { "crop": "Soybean", "probability": 0.624, "percentage": "62.4%" },
      { "crop": "Maize", "probability": 0.215, "percentage": "21.5%" },
      { "crop": "Cotton", "probability": 0.161, "percentage": "16.1%" }
    ],
    "advisory_summary": "Low alert: maintain the current crop plan with routine monitoring.",
    "farmer_notes": []
  }
  ```

---

## 4. Expert Analytics & Diagnostics

### 4.1 POST `/api/v1/experts/explain`
* **Purpose:** Compute SHAP feature attributions for a given crop profile.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `expert`, `admin`
* **Response Schema (200 OK):**
  ```json
  {
    "explainer_type": "LinearExplainer",
    "summary": "Risk is mitigated primarily by: SoilMoisture, NDVI_Flowering.",
    "top_features": [
      {
        "feature": "num__SoilMoisture",
        "display_name": "SoilMoisture",
        "impact": -0.1452,
        "abs_impact": 0.1452,
        "direction": "Decreases Risk"
      },
      {
        "feature": "num__WaterStress",
        "display_name": "WaterStress",
        "impact": 0.0894,
        "abs_impact": 0.0894,
        "direction": "Increases Risk"
      }
    ]
  }
  ```

### 4.2 POST `/api/v1/experts/simulate`
* **Purpose:** Execute Digital Twin custom stress scenarios on an agricultural profile.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `expert`, `admin`
* **Request Schema:**
  ```json
  {
    "scenario_name": "Severe Drought Test",
    "updates": {
      "Rainfall": -40.0,
      "Temperature": 3.5,
      "SoilMoisture": -20.0
    }
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "scenario": "Severe Drought Test",
    "risk_score": 0.7420,
    "risk_percentage": "74.2%",
    "adjusted_features": {
      "Rainfall": 100.56,
      "Temperature": 31.0,
      "Humidity": 74.0,
      "SoilMoisture": 28.0,
      "NDVI_Flowering": 0.696,
      "WaterStress": 0.193
    }
  }
  ```

---

## 5. Health & Diagnostic Endpoints

### 5.1 GET `/health` and GET `/api/v1/health`
* **Purpose:** Unauthenticated liveness and readiness probe for load balancers and container orchestrators.
* **HTTP Method:** `GET`
* **Authentication:** None (Public)
* **Response Schema (200 OK):**
  ```json
  {
    "status": "ok",
    "service": "crop-risk-api",
    "version": "0.1.0"
  }
  ```
