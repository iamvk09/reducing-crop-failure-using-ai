# Sentinel-2 & Google Earth Engine Farm-Level Vegetation Pipeline Architecture

## 1. Executive Summary

This document describes the architectural design and implementation of the Sentinel-2 Level-2A satellite vegetation telemetry pipeline for the AI Crop Failure Decision-Support Platform.

The satellite subsystem provides farm-level vegetation index (NDVI) monitoring via Google Earth Engine (GEE) spatial reductions while adhering to strict cloud production constraints (512 MB RAM footprint, zero uncompressed raster downloads to API servers, build-first credentials-later safety, and non-blocking offline mock drivers).

---

## 2. Architecture & Data Flow

```
+-------------------------------------------------------------------------------+
|                             FARM REGISTRATION                                 |
|  - Latitude, Longitude, Area (Hectares)                                      |
|  - Optional: GeoJSON Polygon Boundaries                                       |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                             FARM GEOMETRY LAYER                               |
|  - Point Buffer: r = sqrt(area_ha * 10,000 / pi)                              |
|  - Polygon: Exact MultiPoint/Polygon boundary                                 |
|  - Converts to ee.Geometry with strict validation                             |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                       GOOGLE EARTH ENGINE (GEE) REDUCER                       |
|  - Collection: COPERNICUS/S2_SR_HARMONIZED (Sentinel-2 L2A BOA Reflectance)   |
|  - Filter: Date Range (30-day window) + Spatial Intersect + Cloud < 30%       |
|  - Cloud Mask: SCL band (classes 3, 8, 9, 10, 11) + QA60 (cirrus / opaque)    |
|  - NDVI Formula: (B8 - B4) / (B8 + B4)  [NIR: 842nm, Red: 665nm]              |
|  - Multi-Reducer: Mean, Median, Min, Max, StdDev, Count                      |
|  - ZERO raster downloads: only compact JSON statistics returned to server     |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                       SATELLITE SERVICE & CACHING LAYER                       |
|  - In-memory TTL Cache (24-hour cache for farm telemetry)                     |
|  - Status Normalizer: REAL_SATELLITE_DATA, SATELLITE_NOT_CONFIGURED, etc.    |
|  - Farmer Vegetation Summary Builder (Healthy, Moderate, Low Greenness)      |
+---------------------------------------+---------------------------------------+
                                        |
          +-----------------------------+-----------------------------+
          |                                                           |
          v                                                           v
+---------------------------------------+   +---------------------------------------+
|          SUPABASE POSTGRESQL          |   |            FASTAPI ENDPOINTS          |
|  - Table: satellite_observations      |   |  - GET /farms/{id}/satellite/latest   |
|  - RLS Tenant Isolation               |   |  - GET /farms/{id}/satellite/history  |
|  - Historical Query Support           |   |  - GET /farms/{id}/vegetation         |
+---------------------------------------+   +-------------------+-------------------+
                                                                |
                                        +-----------------------+-----------------------+
                                        |                                               |
                                        v                                               v
                        +-------------------------------+               +-------------------------------+
                        |        FARMER DASHBOARD       |               |        EXPERT WORKBENCH       |
                        |  - Simplified Health Badge    |               |  - Spatial Reducer Breakdown  |
                        |  - Latest Mean NDVI           |               |  - Median/Min/Max/Std Stats   |
                        |  - Plain-Language Advisory    |               |  - Cloud Cover & Pixel Quality|
                        |  - Clear Telemetry Source     |               |  - Historical Trend Table     |
                        +-------------------------------+               +-------------------------------+
```

---

## 3. Key Architectural Design Decisions

### 3.1 Server-Side Spatial Reductions in Earth Engine
* **Constraint:** The FastAPI backend runs within a 512 MB RAM Render tier. Downloading raw Sentinel-2 GeoTIFFs (~500 MB per scene) would cause immediate memory exhaustion (OOM crashes).
* **Implementation:** All spatial filtering, cloud masking, band math, and statistical reductions (`ee.Reducer.mean().combine(ee.Reducer.median(), ...).combine(ee.Reducer.minMax(), ...)`) occur directly inside Google's cloud infrastructure via `ee.Image.reduceRegion()`.
* **Result:** Only a ~200-byte JSON dictionary of summary numbers is transferred across the network to FastAPI.

### 3.2 Geometry Handling & Fallback Buffers
* For farms where only center coordinates (`latitude`, `longitude`) and `area_hectares` are recorded, the system computes an equivalent circular bounding radius:
  $$r = \sqrt{\frac{\text{area\_hectares} \times 10000}{\pi}}$$
* The metadata explicitly records `geometry_type = "buffered_point"` and `is_fallback = true` to preserve scientific transparency and avoid misrepresenting estimated buffers as surveyed farm boundaries.

### 3.3 Build-First, Credentials-Later Philosophy
* If GEE service account credentials (`GEE_SERVICE_ACCOUNT_EMAIL`, `GEE_PRIVATE_KEY` / `GEE_PROJECT_ID`) are absent:
  - The provider immediately returns a clean, structured `SatelliteObservationResponse` with `status: SATELLITE_NOT_CONFIGURED`.
  - The system logs an unconfigured notice without throwing unhandled 500 exceptions or blocking server startup.
  - Development and unit tests use `MockSatelliteProvider` for deterministic, offline testing.
  - Fake data is never presented as real satellite telemetry.

### 3.4 Quality & Cloud Masking
* **Scene-level filter:** `CLOUDY_PIXEL_PERCENTAGE < 30`.
* **Pixel-level cloud masking:**
  - `SCL` (Scene Classification Layer): Masks out Cloud Shadows (3), Cloud Medium Probability (8), Cloud High Probability (9), Thin Cirrus (10), and Snow/Ice (11).
  - `QA60`: Masks bits 10 (Opaque Clouds) and 11 (Cirrus Clouds).

### 3.5 ML Model Boundary
* In Step 7, NDVI telemetry is exposed as an observational decision-support metric on Farmer and Expert portals.
* In accordance with project requirements, the active ML model prediction vector is **not modified** and models are **not retrained** in this milestone.

---

## 4. API Endpoints Reference

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/api/v1/farms/{farm_id}/satellite/latest` | Bearer (Farmer/Expert) | Fetches latest Sentinel-2 observation and NDVI reduction metrics for a farm. |
| `GET` | `/api/v1/farms/{farm_id}/satellite/history` | Bearer (Farmer/Expert) | Returns time-series history of persisted satellite observations. |
| `GET` | `/api/v1/farms/{farm_id}/vegetation` | Bearer (Farmer/Expert) | Provides simplified farmer-oriented canopy health status and advisory message. |

---

## 5. Security and Environment Variables

The following environment variables configure the Google Earth Engine provider:

| Variable | Required | Description |
|---|---|---|
| `GEE_PROJECT_ID` | Optional in dev | Google Cloud / Earth Engine Project ID. |
| `GEE_SERVICE_ACCOUNT_EMAIL` | Optional in dev | Service Account email with Earth Engine Viewer role. |
| `GEE_PRIVATE_KEY` | Optional in dev | PEM or JSON-encoded private key for Earth Engine authentication. |
| `GEE_SERVICE_ACCOUNT_KEY_PATH` | Optional in dev | Path to service account JSON file (for local development, never committed). |
| `SATELLITE_PROVIDER` | Optional (default: `gee`) | Selects satellite provider backend (`gee` or `mock`). |
| `SATELLITE_CACHE_TTL_HOURS` | Optional (default: `24`) | In-memory cache retention duration in hours. |
