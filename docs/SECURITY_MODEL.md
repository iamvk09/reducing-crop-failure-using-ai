# Security Architecture, RBAC & Row Level Security (RLS) Specification

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Document:** Security Model and Access Control Architecture  
**Status:** Step 1 Foundation  

---

## 1. Security Overview

The platform adopts a defense-in-depth security model combining:
1. **Decentralized Authentication** via Supabase Auth (JWT with PKCE / OAuth).
2. **Backend Authorization Guards** via FastAPI dependency injection enforcing Role-Based Access Control (RBAC).
3. **Database-Level Isolation** via PostgreSQL Row Level Security (RLS) policies.
4. **Input Sanitization & Validation** via Pydantic schemas.
5. **Zero-Trust Secrets Handling** via environment variables with `.gitignore` shielding.

---

## 2. Implementation Status Summary

| Security Layer | Implementation Status | Scope / Details |
|---|---|---|
| **Environment Secrets Isolation** | `IMPLEMENTED` | `.env.example` created, `.env*` excluded from git repository. |
| **Pydantic Input Validation** | `IMPLEMENTED` | Schema and physiological bounds validation in FastAPI & ML engine. |
| **Error Stack Trace Shielding** | `IMPLEMENTED` | Global exception handlers prevent leaking internal stack traces. |
| **CORS Middleware Configuration** | `IMPLEMENTED` | Strict domain origin filtering configured in FastAPI core. |
| **RBAC Role Matrix & Dependency Guards** | `IMPLEMENTED` | `require_role(["farmer", "expert", "admin"])` in `backend/app/api/deps.py`. |
| **Supabase Database RLS Policies** | `IMPLEMENTED (SQL Migration)` | Defined in `supabase/migrations/001_initial_schema.sql`. |
| **Live Supabase JWT Cryptographic Verification** | `PLANNED (Step 2)` | Cryptographic signature verification against Supabase JWKS/Secret. |
| **Rate Limiting Middleware** | `PLANNED (Step 2)` | Token bucket rate limiting (SlowAPI / Redis-backed). |
| **Automated Audit Log Streaming** | `PLANNED (Step 2)` | Asynchronous audit log persistence to `audit_logs` table. |
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
│ Other Farmers' Farms │ No Access     │ Read Only (Anon)  │ Full Admin       │
│ Live Risk Prediction │ Execute (Own) │ Execute (Any)     │ Execute (Any)    │
│ Recommendations      │ Read (Own)    │ Read (All)        │ Full Admin       │
│ SHAP Explanations    │ No Access     │ Read / Analyze    │ Full Admin       │
│ Digital Twin Sim.    │ Basic View    │ Full Scenario Sim │ Full Admin       │
│ Model Versions & ETL │ No Access     │ Read Diagnostics  │ Full Management  │
│ System Audit Logs    │ No Access     │ No Access         │ Full Audit View  │
└──────────────────────┴───────────────┴───────────────────┴──────────────────┘
```

### 3.1 Farmer Role (`farmer`)
- **Scope:** Private access restricted strictly to farms, crop cycles, weather forecasts, alerts, and predictions registered under their own `user_id`.
- **Permissions:**
  - Create, view, update, and delete own farms (`farms` table).
  - Register active and historical crop plantings (`farm_crops` table).
  - Trigger crop failure risk assessments for their own plots.
  - View plain-language agronomic advisories and safer crop recommendations.
  - Dismiss/read their own weather stress alerts.
- **Restrictions:** Cannot view other farmers' landholdings; cannot access raw SHAP tensors, model retraining pipelines, or system audit logs.

### 3.2 Expert / Agronomist Role (`expert`)
- **Scope:** Regional and analytical access across districts to assess systemic risk, evaluate model explanations, and stress-test agricultural resilience.
- **Permissions:**
  - View anonymized district-level and farm-level risk metrics.
  - Execute live SHAP feature attribution (`/api/v1/experts/explain`).
  - Run multi-variable Digital Twin simulations (`/api/v1/experts/simulate`).
  - Inspect model performance metrics and confusion matrices.
  - Review meteorological baseline trends and satellite vegetation indices.
- **Restrictions:** Cannot modify farmer ownership records; cannot reconfigure system environment variables or manage user roles.

### 3.3 System Administrator (`admin`)
- **Scope:** Unrestricted administrative oversight across infrastructure, authentication, model registry, and audit logging.
- **Permissions:**
  - Manage user roles, account activation, and permissions.
  - Register new model artifact versions (`model_versions` table).
  - Trigger batch prediction runs and map generation pipelines.
  - Inspect security audit trails and system error telemetry.

---

## 4. Row Level Security (RLS) Strategy

Database-level access control is enforced in PostgreSQL using Supabase Row Level Security. Even if an application bug bypassed FastAPI route guards, the database engine enforces tenant boundary isolation.

### Key RLS Policies (Defined in `001_initial_schema.sql`):

```sql
-- 1. Farms Isolation: A user can only access farms matching their authenticated UUID,
-- unless their profile role is 'expert' or 'admin'.
CREATE POLICY "Farmers can read own farms"
    ON public.farms FOR SELECT
    USING (
        auth.uid() = user_id 
        OR (SELECT role FROM public.users WHERE id = auth.uid()) IN ('expert', 'admin')
    );

-- 2. Farm Mutation: Only the owning farmer or admin can insert/modify farm data
CREATE POLICY "Farmers can insert own farms"
    ON public.farms FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- 3. Predictions Privacy: Predictions are tied to user_id
CREATE POLICY "Users can view own predictions"
    ON public.predictions FOR SELECT
    USING (
        auth.uid() = user_id 
        OR (SELECT role FROM public.users WHERE id = auth.uid()) IN ('expert', 'admin')
    );

-- 4. Alerts Isolation: Alerts are private to the recipient farmer
CREATE POLICY "Users can view own alerts"
    ON public.alerts FOR SELECT
    USING (auth.uid() = user_id);
```

---

## 5. Data Protection & Secrets Governance

1. **Zero Hardcoded Secrets Policy:**
   - No API keys, passwords, private keys, or service role tokens are committed to source control.
   - All runtime variables are declared in `.env.example` and bound via `pydantic-settings`.
2. **Privacy of Agronomic & Personal Data:**
   - Phone numbers are stored only for notification dispatching and never exposed in public responses.
   - Farm coordinates are stored with 5-decimal precision (~1.1 meter accuracy) and restricted via RLS.
3. **Cross-Origin Resource Sharing (CORS):**
   - Configurable via `CORS_ORIGINS` environment variable.
   - Restricted to authenticated web/mobile application origins in production.
4. **Planned Rate Limiting Strategy (`PLANNED`):**
   - Farmer endpoints: 60 requests/minute per authenticated user.
   - Unauthenticated public endpoints (e.g. `/health`): 120 requests/minute per IP.
   - Expert analytical endpoints (SHAP/Digital Twin): 30 requests/minute per user.
