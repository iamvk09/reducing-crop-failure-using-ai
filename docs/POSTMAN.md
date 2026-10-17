# Postman API Testing & Collection Guide

## 1. Overview

The `postman/` directory contains an automated Postman Collection and Environment template designed for testing and developing against the **AI Crop Failure Decision-Support Platform** FastAPI backend.

- **Collection File:** [`postman/crop-risk-api.postman_collection.json`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/postman/crop-risk-api.postman_collection.json)
- **Environment File:** [`postman/crop-risk-local.postman_environment.json`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/postman/crop-risk-local.postman_environment.json)

---

## 2. Importing & Environment Setup

1. Open Postman desktop or web client.
2. Click **Import** and select both files from `postman/`.
3. Select the imported environment: **Crop Risk AI - Local Environment**.
4. Configure environment variables:

| Variable | Description | Default Local Value |
| :--- | :--- | :--- |
| `base_url` | Root address of running FastAPI instance | `http://127.0.0.1:8000` |
| `access_token` | JWT token for authenticated requests | *(Paste token or leave empty in local mock mode)* |
| `farmer_token` | Farmer-scoped JWT token for RBAC testing | *(Paste farmer token)* |
| `expert_token` | Expert-scoped JWT token for Workbench testing | *(Paste expert token)* |
| `farm_id` | Auto-populated by Create Farm request | Dynamic |
| `crop_id` | Auto-populated by Create Crop request | Dynamic |
| `prediction_id` | Auto-populated by Execute Prediction request | Dynamic |

---

## 3. Endpoints Covered in Collection

### 1. Health & Status
- `GET {{base_url}}/health` — Root health check (`status: ok`)
- `GET {{base_url}}/api/v1/health` — API v1 health and version info

### 2. Authentication & User Profile
- `GET {{base_url}}/api/v1/me` — Read authenticated user identity and role
- `PATCH {{base_url}}/api/v1/me` — Update full name, preferred language, or contact details

### 3. Farm Management
- `GET {{base_url}}/api/v1/farms` — List tenant-isolated farms
- `POST {{base_url}}/api/v1/farms` — Create farm and store `farm_id`
- `GET {{base_url}}/api/v1/farms/{{farm_id}}` — Get farm details by ID

### 4. Crop Management
- `POST {{base_url}}/api/v1/farms/{{farm_id}}/crops` — Register crop cycle (Soybean, Kharif)
- `GET {{base_url}}/api/v1/farms/{{farm_id}}/crops` — List crops for target farm

### 5. ML Live Inference & Predictions
- `POST {{base_url}}/api/v1/farms/{{farm_id}}/predictions` — Execute live prediction pipeline with real-time weather & baseline feature assembly
- `GET {{base_url}}/api/v1/farms/{{farm_id}}/predictions` — List farm prediction history
- `GET {{base_url}}/api/v1/predictions/{{prediction_id}}` — Retrieve persisted inference record

### 6. Weather & Telemetry
- `GET {{base_url}}/api/v1/farms/{{farm_id}}/weather/current` — Current meteorological observation
- `GET {{base_url}}/api/v1/farms/{{farm_id}}/weather/forecast?days=7` — 7-day agronomic forecast
- `GET {{base_url}}/api/v1/farms/{{farm_id}}/weather/history?limit=10` — Persisted weather observations log
- `GET {{base_url}}/api/v1/weather/current?latitude=18.5204&longitude=73.8567` — Coordinate weather lookup

### 7. Expert Workbench
- `POST {{base_url}}/api/v1/experts/simulate` — Parametric Digital Twin stress test
- `POST {{base_url}}/api/v1/experts/explain` — SHAP feature attribution calculation

### 8. Security & Negative Test Cases
- Missing Authorization header $\to$ HTTP 401
- Malformed Bearer token $\to$ HTTP 401
- Invalid coordinates ($>90^\circ$ latitude) $\to$ HTTP 422
- Non-positive farm area ($\le 0$ hectares) $\to$ HTTP 422
- Privilege escalation attempt ($\text{role} \to \text{admin}$) $\to$ Rejected / Role unchanged

---

## 4. Running Automated API Tests via Newman CLI

To run the automated smoke test locally:

```bash
# Ensure dependencies are installed
pip install -r backend/requirements.txt -r requirements.txt

# Execute automated runner (spins up local server, runs Newman, tears down server)
python scripts/run_api_smoke_test.py
```
