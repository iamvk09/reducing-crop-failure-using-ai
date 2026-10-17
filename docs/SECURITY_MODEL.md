# Security Architecture, RBAC & Row Level Security (RLS) Specification

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Document:** Security Model and Access Control Architecture  
**Status:** Step 2 Complete (Authentication, Multi-Tenant Isolation, RBAC & Audit Logging Implemented)

---

## 1. Security Overview

The platform adopts a defense-in-depth security model combining:
1. **Decentralized Authentication** via Supabase Auth (JWT with PKCE / OAuth).
2. **Cryptographic JWT Verification** using `PyJWT` validating signature, expiration, subject, and audience.
3. **Backend Authorization Guards** via FastAPI dependency injection enforcing Role-Based Access Control (RBAC).
4. **Database-Level Isolation** via PostgreSQL Row Level Security (RLS) policies in `001_initial_schema.sql` and `002_auth_and_rls_hardening.sql`.
5. **Input Sanitization & Validation** via Pydantic schemas enforcing geographic and numerical limits.
6. **Audit Trail Logging** with automatic redaction of secrets, tokens, and passwords.
7. **Zero-Trust Secrets Handling** via environment variables with `.gitignore` shielding.

---

## 2. Implementation Status Summary

| Security Layer | Implementation Status | Scope / Details |
|---|---|---|
| **Environment Secrets Isolation** | `IMPLEMENTED` | `.env.example` created, `.env*` excluded from git repository. |
| **Pydantic Input Validation** | `IMPLEMENTED` | Schema and boundary checks on coordinates (Lat: [-90, 90], Lon: [-180, 180]) and positive areas. |
| **Error Stack Trace Shielding** | `IMPLEMENTED` | Global exception handlers prevent leaking internal stack traces. |
| **CORS Middleware Configuration** | `IMPLEMENTED` | Strict domain origin filtering configured in FastAPI core (`backend/app/core/config.py`). |
| **RBAC Role Matrix & Dependency Guards** | `IMPLEMENTED` | `require_role(["farmer", "expert", "admin"])` in `backend/app/api/deps.py`. |
| **Live Supabase JWT Verification** | `IMPLEMENTED` | Cryptographic signature and claim verification in `backend/app/core/security.py`. |
| **Farm & Crop Tenant Isolation** | `IMPLEMENTED` | Ownership verified in domain service and enforced in backend routes (`backend/app/services/farm_service.py`). |
| **Privilege Escalation Protection** | `IMPLEMENTED` | `PATCH /api/v1/me` strictly prevents role modification; role escalation rejected. |
| **Security Audit Logging** | `IMPLEMENTED` | `backend/app/services/audit_service.py` with automatic secret/token redaction. |
| **Supabase Database RLS Policies** | `IMPLEMENTED` | Defined in `supabase/migrations/001_initial_schema.sql` and `002_auth_and_rls_hardening.sql`. |
| **Rate Limiting Strategy** | `PLANNED (Step 3)` | Token bucket rate limiting (SlowAPI / Redis-backed) on auth and prediction endpoints. |
| **SMS/WhatsApp Phone Verification** | `PLANNED (Step 3)` | Supabase OTP phone authentication for farmers. |

---

## 3. Role-Based Access Control (RBAC)

Three distinct authorization roles govern access across the platform:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             RBAC Privilege Matrix                           │
├──────────────────────┬───────────────┬───────────────────┬──────────────────┤
│ Resource / Action    │ Farmer        │ Expert / Agronomist │ System Admin    │
├──────────────────────┼───────────────┼───────────────────┼──────────────────┤
│ Own Farms & Crops    │ Read / Write  │ Read Only         │ Full Admin       │
│ Other Farmers' Farms │ No Access     │ Read Only (All)   │ Full Admin       │
│ Live Risk Prediction │ Execute (Own) │ Execute (Any)     │ Execute (Any)    │
│ Recommendations      │ Read (Own)    │ Read (All)        │ Full Admin       │
│ SHAP Explanations    │ No Access     │ Read / Analyze    │ Full Admin       │
│ Digital Twin Sim.    │ Basic View    │ Full Scenario Sim │ Full Admin       │
│ Model Versions & ETL │ No Access     │ Read Diagnostics  │ Full Management  │
│ System Audit Logs    │ Read (Own)    │ No Access         │ Full Audit View  │
└──────────────────────┴───────────────┴───────────────────┴──────────────────┘
```

### 3.1 Farmer Role (`farmer`)
- **Scope:** Private access restricted strictly to farms, crop cycles, weather forecasts, alerts, and predictions registered under their own `user_id`.
- **Permissions:**
  - Create, view, update, and delete own farms (`POST/GET/PATCH/DELETE /api/v1/farms`).
  - Register active crop plantings (`POST/GET/PATCH/DELETE /api/v1/farms/{id}/crops`).
  - Access own profile (`GET /api/v1/me`, `PATCH /api/v1/me`).
- **Restrictions:** Cannot view other farmers' landholdings; cannot access expert simulations (`/api/v1/experts/simulate` $\rightarrow$ 403 Forbidden); cannot escalate role.

### 3.2 Expert / Agronomist Role (`expert`)
- **Scope:** Regional and analytical access across districts to assess systemic risk, evaluate model explanations, and stress-test agricultural resilience.
- **Permissions:**
  - View all registered farms across districts (`GET /api/v1/farms`).
  - Execute live SHAP feature attribution (`POST /api/v1/experts/explain`).
  - Run multi-variable Digital Twin simulations (`POST /api/v1/experts/simulate`).
- **Restrictions:** Cannot modify farmer ownership records; cannot delete farms or crops owned by farmers.

### 3.3 System Administrator (`admin`)
- **Scope:** Unrestricted administrative oversight across infrastructure, authentication, farm management, and audit logging.

---

## 4. Frontend Authentication & OAuth Flow

```
   [Farmer / User Browser]
              │
              │  1. Initiate Google Login / Email Login
              ▼
   [Supabase Auth (Cloud)]
              │
              │  2. Authenticate & Issue JWT Access Token
              ▼
   [Frontend Client]
              │
              │  3. API Request with Header
              │     `Authorization: Bearer <Supabase_JWT>`
              ▼
   [FastAPI Backend Gateway]
              │
              │  4. Cryptographically verify signature using SUPABASE_JWT_SECRET
              │  5. Validate exp, aud, sub claims
              │  6. Extract user identity and role
              ▼
   [Protected Business Services & PostgreSQL with RLS]
```

---

## 5. Audit Logging Architecture

Security-sensitive events are captured via `backend/app/services/audit_service.py`.

### Logged Operations:
* `farm:create`, `farm:update`, `farm:delete`
* `crop:create`, `crop:update`, `crop:delete`
* `user:profile_update`

### Sanitization & Data Protection:
The audit logger applies `sanitize_metadata()`, ensuring that any field containing `password`, `token`, `access_token`, `refresh_token`, `secret`, `api_key`, `supabase_jwt_secret`, or `authorization` is automatically redacted before persistence.

---

## 6. Rate Limiting Strategy (Specification)

Rate limiting will be enforced at the API gateway layer to prevent denial-of-service and brute-force token exhaustion.

### Target Rate Limits by Endpoint Tier:
1. **Authentication & Identity (`/api/v1/me`):** 60 requests / minute / IP.
2. **Farm & Crop Mutations (`POST/PATCH/DELETE /api/v1/farms`):** 30 requests / minute / user.
3. **ML Prediction & Weather (`/api/v1/predictions/live`):** 20 requests / minute / user.
4. **Expert Simulation & SHAP (`/api/v1/experts/*`):** 10 requests / minute / user.
