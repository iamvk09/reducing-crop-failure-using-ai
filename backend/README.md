# Crop Risk Intelligence API (FastAPI Backend)

Production-oriented backend service for agricultural risk prediction, recommendations, and digital twin simulations.

---

## Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app definition & middleware
│   ├── core/
│   │   ├── config.py        # Pydantic Settings & environment binding
│   │   ├── security.py      # Supabase JWT decoding & RBAC roles
│   │   └── logging.py       # Structured logging
│   ├── api/
│   │   ├── deps.py          # Dependency injection providers
│   │   └── routes/
│   │       ├── health.py    # Health check routes
│   │       ├── auth.py      # User authentication routes
│   │       ├── farms.py     # Farm & crop cycle management
│   │       ├── predictions.py # ML risk prediction
│   │       ├── recommendations.py # Agronomic advisories
│   │       └── experts.py   # SHAP & Digital Twin simulation
│   ├── schemas/             # Pydantic request/response models
│   ├── services/            # Model Service Boundary & wrappers
│   └── repositories/        # Database access abstractions
├── tests/                   # Backend unit and integration tests
├── requirements.txt         # Backend dependencies
└── README.md
```

---

## Running Locally

### 1. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

### 3. Start Uvicorn Server
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Key Endpoints

- `GET /health` / `GET /api/v1/health` : Service health status
- `POST /api/v1/predictions` : Predict crop failure risk using live Open-Meteo weather
- `GET /api/v1/recommendations/{district}/{crop}` : Ranked safer crop options & advisories
- `POST /api/v1/experts/explain` : Lazy SHAP feature attribution
- `POST /api/v1/experts/simulate` : Digital Twin stress testing simulation
- `GET /docs` : Interactive Swagger UI documentation
- `GET /redoc` : ReDoc documentation

---

## Running Backend Tests

```bash
pytest backend/tests -v
```
