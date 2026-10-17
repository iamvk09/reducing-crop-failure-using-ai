# CI/CD Pipeline Architecture & Automated Validation

## 1. Overview

The **AI Crop Failure Decision-Support Platform** employs an automated Continuous Integration (CI) pipeline configured via GitHub Actions. The pipeline enforces rigorous software quality gates, regression testing, secret detection, and multi-tenant security verification across the Python backend, core machine learning bundle, and Next.js frontend applications.

---

## 2. GitHub Actions Workflow Architecture

```
                       [Push / Pull Request]
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
  [Backend & ML Job]      [Farmer App Job]        [Expert App Job]
  ├─ Python 3.12 Setup    ├─ Node 20 Setup        ├─ Node 20 Setup
  ├─ Pip Cache            ├─ Npm Cache            ├─ Npm Cache
  ├─ Secret Scanner       ├─ Farmer Tests (6/6)   ├─ Expert Tests (2/2)
  ├─ Pytest (52 tests)    └─ Production Build     └─ Production Build
  └─ ML Tests (15 tests)
         │
         ▼
  [API Smoke Test Job]
  ├─ Spin up FastAPI
  ├─ Execute Newman Postman Suite
  └─ Clean Server Teardown
```

### Workflow Trigger Matrix
- **Triggers:** `push` and `pull_request` on `main`, `master`, and `develop` branches.
- **Concurrency:** `cancel-in-progress: true` to prevent redundant runner time on rapid subsequent commits.

---

## 3. Pipeline Stages & Verification Commands

| Stage | Execution Command | Gate Criteria |
| :--- | :--- | :--- |
| **Security / Secret Scan** | `python scripts/security_check.py` | 0 tracked secret files or raw credential patterns |
| **Backend API Tests** | `pytest backend/tests -v` | 52/52 tests passing (Auth, RBAC, RLS, Persistence, Weather) |
| **ML Regression Tests** | `python -m unittest tests/test_live_system.py` | 15/15 tests passing (Memory limits, Bundle integrity, SHAP, Twin) |
| **Farmer Frontend Tests** | `node apps/farmer/test_farmer.js` | 6/6 test suites passing (I18n, Validations, Routing, Risk bands) |
| **Expert Frontend Tests** | `node apps/expert/test_expert.js` | 2/2 test suites passing (Parametric simulations, SHAP formatting) |
| **Farmer Production Build** | `npm --prefix apps/farmer run build` | Zero TypeScript/linting errors, optimized static generation |
| **Expert Production Build** | `npm --prefix apps/expert run build` | Zero TypeScript/linting errors, optimized static generation |
| **Newman API Smoke Test** | `python scripts/run_api_smoke_test.py` | 100% assertions passing on health & negative security suites |

---

## 4. Secret & Credential Protection Policy

1. **Static Scanner:** `scripts/security_check.py` scans tracked repository files for disallowed file patterns (`.env`, `.env.local`, `*.key`, `credentials.json`) and raw credential signatures.
2. **Safe Log Handling:** Scanner never outputs detected secret values into terminal or CI logs.
3. **Environment Injection:** All external URLs and non-sensitive dev placeholders are supplied exclusively via environment variables during CI.

---

## 5. Deployment Boundary

> [!IMPORTANT]
> This stage implements **CI (Continuous Integration) only**.
> Automated production deployments to hosting platforms (Render / Vercel) remain gated behind manual approval and will be configured in subsequent milestones after end-to-end integration stability is verified.
