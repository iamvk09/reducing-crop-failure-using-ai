# Step 2 Implementation & Audit Report: Real Identity, RBAC, Farm & Crop Isolation

**Project:** Reducing Crop Failure Using AI Under Unfavorable Weather Conditions  
**Repository:** `iamvk09/reducing-crop-failure-using-ai`  
**Report Date:** 2026-09-26  
**Implementation Stage:** Step 2 Complete (Supabase JWT Verification, User Profile, Farm Registration, Crop Registration, RBAC & Isolation Tests)

---

## 1. Files Created in Step 2

1. [`supabase/migrations/002_auth_and_rls_hardening.sql`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/supabase/migrations/002_auth_and_rls_hardening.sql): SQL migration hardening RLS policies across `farm_crops`, `weather_observations`, `satellite_observations`, `recommendations`, and `audit_logs`, and adding the `public.current_user_role()` helper function.
2. [`backend/app/services/audit_service.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/services/audit_service.py): Reusable audit logging service with automated redaction of sensitive credentials, tokens, and passwords.
3. [`backend/app/services/farm_service.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/services/farm_service.py): Farm and crop domain service enforcing multi-tenant isolation and ownership checks.
4. [`backend/app/services/user_service.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/services/user_service.py): User profile domain service preventing privilege escalation.
5. [`backend/tests/conftest.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/conftest.py): Pytest fixtures and cryptographic JWT token minting helpers for testing.
6. [`backend/tests/test_auth.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_auth.py): Unit tests for JWT signature verification, expiration, malformed headers, and user profile retrieval/update.
7. [`backend/tests/test_rbac.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_rbac.py): Unit tests for role guards, expert endpoint restriction, admin access, and role escalation prevention.
8. [`backend/tests/test_farm_isolation.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_farm_isolation.py): Unit tests for multi-tenant farm isolation (farmers cannot read, modify, or delete another farmer's plot).
9. [`backend/tests/test_crop_isolation.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_crop_isolation.py): Unit tests for crop cycle isolation and farm ownership verification.
10. [`backend/tests/test_validation.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_validation.py): Boundary and schema validation tests (latitude [-90, 90], longitude [-180, 180], positive area, string lengths).
11. [`backend/tests/test_audit.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/tests/test_audit.py): Unit tests for audit record creation and sensitive metadata redaction.
12. [`docs/STEP_2_IMPLEMENTATION_REPORT.md`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/docs/STEP_2_IMPLEMENTATION_REPORT.md): This comprehensive audit and verification document.

---

## 2. Files Modified in Step 2

1. [`backend/requirements.txt`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/requirements.txt): Added `pyjwt[crypto]>=2.8.0` and `cryptography>=42.0.0`.
2. [`backend/app/core/security.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/core/security.py): Implemented cryptographic JWT verification (`PyJWT`), signature checks against `SUPABASE_JWT_SECRET`, claim extraction, and role resolution.
3. [`backend/app/api/deps.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/api/deps.py): Implemented Bearer token extraction, authentication exception handling, RBAC dependency factories (`get_farmer_user`, `get_expert_user`, `get_admin_user`, `get_any_authenticated_user`), and service injection.
4. [`backend/app/schemas/auth.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/schemas/auth.py): Added `UserProfileUpdateRequest` (strictly omitting role field to prevent escalation) and enriched `UserProfileResponse`.
5. [`backend/app/schemas/farm.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/schemas/farm.py): Added `FarmUpdateRequest`, `CropUpdateRequest`, and comprehensive validation limits (`ge`, `le`, `gt`, `min_length`).
6. [`backend/app/api/routes/auth.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/api/routes/auth.py): Implemented `GET /api/v1/me`, `GET /api/v1/auth/me`, and `PATCH /api/v1/me`.
7. [`backend/app/api/routes/farms.py`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/backend/app/api/routes/farms.py): Implemented complete CRUD endpoints for farms and crops with ownership validation.
8. [`docs/API_CONTRACT.md`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/docs/API_CONTRACT.md): Updated with implemented status tags and exact request/response schemas.
9. [`docs/SECURITY_MODEL.md`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/docs/SECURITY_MODEL.md): Updated implementation status table, JWT verification details, and frontend OAuth architecture.

---

## 3. Authentication Architecture & JWT Verification

The platform uses **Supabase Auth** as the identity provider:
* **Token Verification Approach:** The backend in `backend/app/core/security.py` uses `PyJWT` with HMAC-SHA256 signature verification against `SUPABASE_JWT_SECRET`.
* **Verified Claims:**
  * `sub`: Verified as non-empty UUID string representing the authenticated user ID.
  * `exp`: Verified against current Unix epoch; expired tokens return HTTP 401 with `"Authentication token has expired."`.
  * `aud`: Verified against `["authenticated", "supabase"]`.
  * `signature`: Verified cryptographically; invalid signatures return HTTP 401.
* **Token Safety:** Access tokens and secret keys are never logged in application logs or audit records.

---

## 4. Role Architecture & Privilege Escalation Prevention

Three roles exist: `farmer`, `expert`, and `admin`.
* **Role Derivation:** Derived strictly from the verified JWT claims (`app_metadata.role` $\rightarrow$ `user_metadata.role` $\rightarrow$ default `'farmer'`).
* **Privilege Escalation Guard:** `PATCH /api/v1/me` only accepts mutable profile fields (`full_name`, `phone_number`, `preferred_language`). Any client payload attempting to submit `{"role": "admin"}` is ignored by Pydantic and cannot modify the user's role.

---

## 5. Farm and Crop Ownership & Tenant Isolation

* **Farm Isolation:**
  * When a farmer creates a farm (`POST /api/v1/farms`), `user_id` is automatically set to `current_user.id`.
  * When a farmer lists farms (`GET /api/v1/farms`), only farms where `farm.user_id == current_user.id` are returned.
  * When Farmer B attempts to get, update, or delete Farmer A's farm (`/api/v1/farms/{farm_a_id}`), the service returns HTTP 404.
  * Experts and Admins can view all registered farms across districts for agricultural monitoring.
* **Crop Isolation:**
  * When a farmer attempts to register or modify a crop cycle (`/api/v1/farms/{farm_id}/crops`), the backend validates that `farm.user_id == current_user.id`. If Farmer B targets Farmer A's `farm_id`, HTTP 404 is returned.

---

## 6. Database Row Level Security (RLS) Review & Migration

* Migration [`supabase/migrations/001_initial_schema.sql`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/supabase/migrations/001_initial_schema.sql) and new migration [`supabase/migrations/002_auth_and_rls_hardening.sql`](file:///c:/Users/kumar/OneDrive/Desktop/Project/ai-crop-failure-project/supabase/migrations/002_auth_and_rls_hardening.sql) enforce isolation directly in PostgreSQL:
  * `farm_crops` has explicit RLS policies for `SELECT`, `INSERT`, `UPDATE`, and `DELETE` enforcing `EXISTS (SELECT 1 FROM public.farms f WHERE f.id = farm_crops.farm_id AND f.user_id = auth.uid())`.
  * `public.current_user_role()` function provides fast, non-recursive role checking without trigger recursion.
  * `weather_observations`, `satellite_observations`, `recommendations`, and `audit_logs` are protected by corresponding RLS policies.

---

## 7. Audit Logging

* Implemented in `backend/app/services/audit_service.py`.
* Logs security actions: `farm:create`, `farm:update`, `farm:delete`, `crop:create`, `crop:update`, `crop:delete`, `user:profile_update`.
* Sanitization filter (`sanitize_metadata`) automatically redacts any dictionary keys containing `password`, `token`, `access_token`, `refresh_token`, `secret`, `supabase_jwt_secret`, or `api_key`.

---

## 8. Test Execution & Results

### 8.1 Backend Test Suite (32 tests)
Command: `py -3.13 -m pytest backend/tests -v`
```
============================= test session starts =============================
platform win32 -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\kumar\OneDrive\Desktop\Project\ai-crop-failure-project
plugins: anyio-4.11.0
collected 32 items

backend/tests/test_audit.py::test_audit_log_on_farm_operations PASSED    [  3%]
backend/tests/test_audit.py::test_sanitize_metadata_redacts_sensitive_keys PASSED [  6%]
backend/tests/test_auth.py::test_auth_missing_token PASSED               [  9%]
backend/tests/test_auth.py::test_auth_malformed_token PASSED             [ 12%]
backend/tests/test_auth.py::test_auth_missing_bearer_prefix PASSED       [ 15%]
backend/tests/test_auth.py::test_auth_expired_token PASSED               [ 18%]
backend/tests/test_auth.py::test_auth_invalid_signature PASSED           [ 21%]
backend/tests/test_auth.py::test_auth_valid_token_me_endpoint PASSED     [ 25%]
backend/tests/test_auth.py::test_auth_update_profile PASSED              [ 28%]
backend/tests/test_config.py::test_default_settings PASSED               [ 31%]
backend/tests/test_config.py::test_cors_origins_parsing PASSED           [ 34%]
backend/tests/test_crop_isolation.py::test_farmer_can_register_and_list_crops_on_own_farm PASSED [ 37%]
backend/tests/test_crop_isolation.py::test_farmer_cannot_register_crop_on_another_farmers_farm PASSED [ 40%]
backend/tests/test_crop_isolation.py::test_farmer_cannot_list_crops_on_another_farmers_farm PASSED [ 43%]
backend/tests/test_crop_isolation.py::test_farmer_cannot_update_or_delete_crop_on_another_farmers_farm PASSED [ 46%]
backend/tests/test_farm_isolation.py::test_farmer_can_create_and_list_own_farm PASSED [ 50%]
backend/tests/test_farm_isolation.py::test_farmer_cannot_view_other_farmer_farm_in_list PASSED [ 53%]
backend/tests/test_farm_isolation.py::test_farmer_cannot_get_other_farmer_farm_by_id PASSED [ 56%]
backend/tests/test_farm_isolation.py::test_farmer_cannot_update_other_farmer_farm PASSED [ 59%]
backend/tests/test_farm_isolation.py::test_farmer_cannot_delete_other_farmer_farm PASSED [ 62%]
backend/tests/test_farm_isolation.py::test_expert_can_view_all_farms PASSED [ 65%]
backend/tests/test_health.py::test_root_health_check PASSED              [ 68%]
backend/tests/test_health.py::test_versioned_health_check PASSED         [ 71%]
backend/tests/test_rbac.py::test_farmer_cannot_access_expert_endpoint PASSED [ 75%]
backend/tests/test_rbac.py::test_expert_can_access_expert_endpoint PASSED [ 78%]
backend/tests/test_rbac.py::test_admin_has_superuser_access PASSED       [ 81%]
backend/tests/test_rbac.py::test_prevent_role_escalation_via_patch_me PASSED [ 84%]
backend/tests/test_validation.py::test_invalid_latitude_rejected PASSED  [ 87%]
backend/tests/test_validation.py::test_invalid_longitude_rejected PASSED [ 90%]
backend/tests/test_validation.py::test_non_positive_area_rejected PASSED [ 93%]
backend/tests/test_validation.py::test_short_farm_name_rejected PASSED   [ 96%]
backend/tests/test_validation.py::test_missing_required_crop_field_rejected PASSED [100%]

======================= 32 passed in 1.57s ========================
```

### 8.2 Existing Live ML System Regression Tests (14 tests)
Command: `py -3.13 -m unittest tests/test_live_system.py`
```
[MEMORY DIAGNOSTIC] Before bundle load                     | RSS:  106.0 MB
[MEMORY DIAGNOSTIC] After bundle load                      | RSS:  187.8 MB (bundle=agri_ai_runtime_bundle.pkl)
............[MEMORY DIAGNOSTIC] Before SHAP explanation                | RSS:  241.9 MB
[MEMORY DIAGNOSTIC] After SHAP explanation                 | RSS:  242.8 MB
..
----------------------------------------------------------------------
Ran 14 tests in 3.556s

OK
```

### 8.3 Streamlit Dashboard Verification
Command: `py -3.13 -c "import dashboard_app; print('Streamlit dashboard loaded successfully!')"`
```
Streamlit dashboard loaded successfully!
```

---

## 9. Security Risks Remaining & Mitigations

| Identified Risk | Impact | Step 2 Mitigation | Future Step Mitigation |
| :--- | :--- | :--- | :--- |
| **API Denial-of-Service** | High request rate could stress backend | CORS domain restriction; Pydantic limits | Add SlowAPI / Redis rate-limiting middleware (Step 3) |
| **User Role Assignment** | Client could attempt to set role on signup | Backend ignores client role; defaults to `'farmer'` | Supabase custom claims trigger on `auth.users` insert |
| **Token Theft via XSS** | Attacker extracts token from localStorage | Strict CORS and standard HTTPS transport | Recommend `httpOnly` secure cookies / Supabase PKCE in frontend |

---

## 10. Manual Supabase Dashboard Configuration Required

When connecting a real Supabase project:
1. **Apply Migrations:** Run `001_initial_schema.sql` and `002_auth_and_rls_hardening.sql` in the Supabase SQL Editor.
2. **Retrieve JWT Secret:** In Supabase Dashboard $\rightarrow$ Project Settings $\rightarrow$ API $\rightarrow$ Config $\rightarrow$ `JWT Secret`, copy value into `.env` as `SUPABASE_JWT_SECRET`.
3. **Configure Auth Providers:** Enable Email / Phone OTP / Google OAuth under Supabase Dashboard $\rightarrow$ Authentication $\rightarrow$ Providers.
4. **Environment File:** Copy `.env.example` to `.env` and configure `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_JWT_SECRET`.
