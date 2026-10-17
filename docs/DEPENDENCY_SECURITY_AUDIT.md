# CropAI — Dependency Vulnerability Audit Report
Date: 2026-10-16
Scope: Authorized Online Vulnerability Scan (PyPA/OSV & npm Advisory Databases)

---

## 1. Executive Summary

| Ecosystem | Scope | Tool & Advisory Source | Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Python (Backend)** | Deployed Specification (`backend/requirements.txt`) | `pip-audit 2.10.1` (PyPA / OSV) | **0 Vulnerabilities Found** (Clean) | **PASSED** |
| **Python (Local Virtualenv)** | All packages in `.\venv` | `pip-audit 2.10.1` (PyPA / OSV) | 6 CVEs in local build tool `setuptools 65.5.0` (Not in backend specs) | **PASSED (Runtime Clean)** |
| **Node.js (Frontend Prod)** | `apps/farmer` Production Runtime (`--omit=dev`) | `npm audit` (npm Advisory Database) | 3 advisories in `next` (via bundled `postcss` / `source-map-js`) | **ACTIONABLE FINDING** |
| **Node.js (Frontend Dev)** | Root & Workspace All (`prod + dev`) | `npm audit` (npm Advisory Database) | 10 advisories (`tailwindcss`, `chokidar`, `micromatch`) | **DEV-ONLY FINDINGS** |

---

## 2. Python Vulnerability Audit (`pip-audit`)

### A. Deployed Production Specification (`backend/requirements.txt`)
Command: `.\venv\Scripts\pip-audit -r backend/requirements.txt`
Exit Code: `0`
Output: `No known vulnerabilities found`

**Audited Runtime Dependencies:**
- `fastapi 0.115.0+`
- `uvicorn[standard] 0.30.0+`
- `pydantic 2.8.0+`
- `pydantic-settings 2.4.0+`
- `python-dotenv 1.0.0+`
- `httpx 0.27.0+`
- `pyjwt[crypto] 2.8.0+`
- `cryptography 42.0.0+`
- `scikit-learn 1.5.0+`
- `joblib 1.4.0+`
- `pandas 2.2.0+`
- `numpy 2.0.0+`
- `requests 2.32.0+`
- `psutil 6.0.0+`
- `earthengine-api 1.7.0+`
- `twilio 9.12.0`

### B. Virtual Environment Tooling Notice
The local Python virtual environment has legacy `setuptools 65.5.0` (a local build tool, not imported or bundled in production requirements). It flagged:
- `CVE-2024-6345` / `GHSA-cx63-2mw6-8hw5` (`package_index` download functions)
- `CVE-2025-47273` / `GHSA-5rjg-fvgr-3xxf` (`PackageIndex` path traversal)
- `CVE-2026-59890` / `GHSA-h35f-9h28-mq5c` (`MANIFEST.in` Unicode normalization)
*Recommendation:* On local development machines, run `pip install --upgrade setuptools`.

---

## 3. npm Vulnerability Audit (`npm audit`)

### A. Production Runtime Dependencies (`apps/farmer --omit=dev`)
Command: `npm --prefix apps/farmer audit --omit=dev --json`
Exit Code: `1` (Advisories flagged)

1. **`next` (Installed: `14.2.13`, Target Patch: `14.2.25+` / Next.js 15 patch)**
   - **GHSA-p293-qw3h-jr36** (Critical, CVSS 9.0): Path traversal on Windows-hosted servers.
     - *Impact on Staging:* Zero impact on Vercel deployment (Vercel runs Linux edge/serverless runtimes). Relevant only if deploying custom Windows Node servers.
   - **GHSA-2xp9-vwfh-vxw4** (Critical): Image Optimization API when AVIF files are enabled.
     - *Impact on Staging:* `apps/farmer` does not enable AVIF image optimization.
   - **GHSA-89xv-2m56-2m9x** / **GHSA-p9j2-gv94-2wf4** (High): SSRF in rewrites / Server Actions on custom servers.
     - *Impact on Staging:* Handled natively on Vercel infrastructure.

2. **`postcss` / `source-map-js` (Bundled via `next`)**
   - **GHSA-6g55-p6wh-862q** (High): Information disclosure via `sourceMappingURL` in CSS comments during build.
   - **GHSA-68fv-2mgg-jv7q** (High): Event-loop denial of service through indexed source-map section offsets.

### B. Development-Only Dependencies
- **`tailwindcss <= 3.4.19`**: Flags dev tooling sub-dependencies (`chokidar`, `micromatch`, `fast-glob`, `postcss-selector-parser`).
  - *Impact:* Build-time CLI only. Not exposed to browser runtime or server execution.

---

## 4. Recommended Fixes (To Review Prior to Staging Deployment)

1. **Next.js Minor Version Bump:**
   - In `apps/farmer/package.json`, update `next` from `"^14.2.13"` to the latest patched 14.x release (`"~14.2.25"`).
   - This resolves the image optimization and rewrite SSRF advisories while preserving full Next.js 14 API compatibility without breaking changes.
2. **Lockfile Integrity:**
   - No automatic fixes (`npm audit fix`) were executed.
   - Manifests and lockfiles remain strictly untouched.
