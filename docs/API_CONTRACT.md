# REST API Contract Specification

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Base URL:** `/api/v1`  
**Specification Standard:** OpenAPI 3.1 / RESTful JSON  
**Authentication Scheme:** `Authorization: Bearer <Supabase_JWT_Token>`  
**Status Legend:** `[IMPLEMENTED]` | `[PLANNED]`

---

## 1. Authentication & User Profile

### 1.1 GET `/api/v1/me` (and `/api/v1/auth/me`) `[IMPLEMENTED]`
* **Purpose:** Retrieve the profile and role metadata of the currently authenticated user.
* **HTTP Method:** `GET`
* **Authentication:** Required (`Authorization: Bearer <JWT>`)
* **Role Requirement:** `farmer`, `expert`, or `admin`
* **Request Schema:** None (Headers only)
* **Response Schema (200 OK):**
  ```json
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "email": "farmer@example.com",
    "full_name": "Ramesh Patel",
    "role": "farmer",
    "phone_number": "+919876543210",
    "preferred_language": "hi",
    "created_at": "2026-09-26T10:00:00Z",
    "updated_at": "2026-09-26T10:00:00Z"
  }
  ```
* **Possible Errors:**
  * `401 Unauthorized`: Missing, expired, or cryptographically invalid JWT token.

### 1.2 PATCH `/api/v1/me` `[IMPLEMENTED]`
* **Purpose:** Update mutable profile fields (full name, phone number, preferred language).
* **HTTP Method:** `PATCH`
* **Authentication:** Required (`Authorization: Bearer <JWT>`)
* **Role Requirement:** `farmer`, `expert`, or `admin`
* **Security Guard:** Role, user ID, email, and active status are strictly immutable via this endpoint (prevents privilege escalation).
* **Request Schema:**
  ```json
  {
    "full_name": "Ramesh K. Patel",
    "phone_number": "+919876543210",
    "preferred_language": "hi"
  }
  ```
* **Response Schema (200 OK):** `UserProfileResponse`
* **Possible Errors:**
  * `401 Unauthorized`: Invalid credentials.
  * `422 Unprocessable Entity`: Validation failure on phone or length fields.

---

## 2. Farm & Crop Management

### 2.1 GET `/api/v1/farms` `[IMPLEMENTED]`
* **Purpose:** List all farm plots accessible to the user (farmers see only own plots; experts/admins see all plots).
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer`, `expert`, `admin`
* **Response Schema (200 OK):** Array of `FarmResponse`

### 2.2 POST `/api/v1/farms` `[IMPLEMENTED]`
* **Purpose:** Register a new farm plot. Automatically binds `user_id` to the authenticated user.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer`, `admin`
* **Response Schema (201 Created):** `FarmResponse`

### 2.3 GET `/api/v1/farms/{farm_id}` `[IMPLEMENTED]`
* **Purpose:** Retrieve specific farm details. Enforces strict ownership isolation for farmers.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `expert`, `admin`

### 2.4 PATCH `/api/v1/farms/{farm_id}` `[IMPLEMENTED]`
* **Purpose:** Update farm attributes. Only the owner or an admin may modify.
* **HTTP Method:** `PATCH`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `admin`

### 2.5 DELETE `/api/v1/farms/{farm_id}` `[IMPLEMENTED]`
* **Purpose:** Delete a farm and its associated crops. Only the owner or an admin may delete.
* **HTTP Method:** `DELETE`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `admin`

### 2.6 POST `/api/v1/farms/{farm_id}/crops` `[IMPLEMENTED]`
* **Purpose:** Record an active crop planting cycle on a farm owned by the user.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `admin`
* **Response Schema (201 Created):** `CropResponse`

### 2.7 GET `/api/v1/farms/{farm_id}/crops` `[IMPLEMENTED]`
* **Purpose:** List all crop cycles recorded for a specific farm.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `expert`, `admin`
* **Response Schema (200 OK):** Array of `CropResponse`

### 2.8 PATCH `/api/v1/farms/{farm_id}/crops/{crop_id}` `[IMPLEMENTED]`
* **Purpose:** Update crop stage or harvest status. Enforces farm ownership.
* **HTTP Method:** `PATCH`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `admin`

### 2.9 DELETE `/api/v1/farms/{farm_id}/crops/{crop_id}` `[IMPLEMENTED]`
* **Purpose:** Delete a crop cycle record. Enforces farm ownership.
* **HTTP Method:** `DELETE`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `admin`

---

## 3. ML Risk Prediction Engine

### 3.1 POST `/api/v1/farms/{farm_id}/predictions` `[IMPLEMENTED]`
* **Purpose:** Execute live crop failure prediction for a farm with registered crop & live Open-Meteo weather.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `expert`, `admin`
* **Request Schema:** `FarmPredictionRequest` (optional overrides & crop_id)
* **Response Schema (201 Created):**
  ```json
  {
    "prediction_id": "c1f727b1-5e74-4bf8-bfa9-1582e309cb41",
    "farm_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "crop_id": "87f3e820-bcf5-4cf4-a957-c834a362f6b5",
    "crop": "Soybean",
    "district": "Pune",
    "state": "Maharashtra",
    "season": "Kharif",
    "risk_probability": 0.184,
    "risk_percentage": "18.4%",
    "risk_level": "Low",
    "prediction_class": 0,
    "best_model_name": "agri_ai_runtime_bundle",
    "global_risk": 0.184,
    "region_risk": 0.192,
    "crop_risk": 0.178,
    "consensus_risk": 0.184,
    "input_features": {
      "Year": 2026,
      "Rainfall": 120.0,
      "Temperature": 28.5,
      "Humidity": 64.0,
      "SoilMoisture": 45.0,
      "NDVI_Flowering": 0.55,
      "WaterStress": 0.45,
      "PestRisk": 0.40,
      "SuitabilityScore": 0.65,
      "YieldIndex": 60.0,
      "State": "Maharashtra",
      "Region": "Central Plateau",
      "Season": "Kharif",
      "Crop": "Soybean",
      "SoilType": "Black",
      "IrrigationLevel": "Medium"
    },
    "provenance": {
      "Temperature": "Live weather estimate (Open-Meteo)",
      "Humidity": "Live weather estimate (Open-Meteo)",
      "SoilMoisture": "Live weather estimate (Open-Meteo root-zone moisture)",
      "Rainfall": "Historical seasonal baseline (District-Crop-Season median)"
    },
    "recommendations": {
      "recommended_crop": "Soybean",
      "top_options": [
        {"crop": "Soybean", "probability": 0.78, "percentage": "78.0%"},
        {"crop": "Maize", "probability": 0.14, "percentage": "14.0%"}
      ],
      "advisory_summary": "Low alert: maintain the current crop plan with routine monitoring."
    },
    "created_at": "2026-09-26T10:30:00Z"
  }
  ```

### 3.2 GET `/api/v1/farms/{farm_id}/predictions` `[IMPLEMENTED]`
* **Purpose:** Retrieve all historical risk assessments recorded for a farm in reverse chronological order.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own farm), `expert`, `admin`
* **Response Schema (200 OK):** Array of `PredictionResponse`

### 3.3 GET `/api/v1/predictions/{prediction_id}` `[IMPLEMENTED]`
* **Purpose:** Retrieve a single prediction record by ID with tenant isolation enforcement.
* **HTTP Method:** `GET`
* **Authentication:** Required
* **Role Requirement:** `farmer` (own prediction/farm), `expert`, `admin`
* **Response Schema (200 OK):** `PredictionResponse`

### 3.4 POST `/api/v1/predictions` `[IMPLEMENTED]`
* **Purpose:** Direct crop risk prediction with explicit or custom parameters.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Response Schema (200 OK):** `PredictionResponse`

---

## 4. Expert Analytics & Digital Twin Simulations

### 4.1 POST `/api/v1/experts/simulate` `[IMPLEMENTED]`
* **Purpose:** Run Digital Twin parametric stress simulation.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `expert`, `admin` (Farmers receive 403 Forbidden)

### 4.2 POST `/api/v1/experts/explain` `[IMPLEMENTED]`
* **Purpose:** Generate SHAP feature importance and waterfall attribution.
* **HTTP Method:** `POST`
* **Authentication:** Required
* **Role Requirement:** `expert`, `admin`

---

## 5. System Health Checks

### 5.1 GET `/health` & GET `/api/v1/health` `[IMPLEMENTED]`
* **Purpose:** Lightweight liveness and readiness probe.
* **HTTP Method:** `GET`
* **Authentication:** None (Public)
* **Response Schema (200 OK):**
  ```json
  {
    "status": "ok",
    "service": "crop-risk-api",
    "version": "0.1.0",
    "environment": "development"
  }
  ```
