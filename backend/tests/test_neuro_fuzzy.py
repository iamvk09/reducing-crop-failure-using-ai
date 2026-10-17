"""Integration and unit tests for the Experimental Neuro-Fuzzy Crop Failure Risk Model."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import create_jwt_token
from backend.app.main import app
from src.neuro_fuzzy import NeuroFuzzyCropFailureModel, FEATURE_NAMES

TEST_SECRET = "test-jwt-secret-key-32-bytes-long!!"


def make_auth_headers(user_id: str = "test-farmer-1", role: str = "farmer") -> dict:
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
        "app_metadata": {"role": role},
        "user_metadata": {"full_name": "Test User", "role": role},
    }
    token = create_jwt_token(payload, secret=TEST_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "APP_ENV", "testing")
    return TestClient(app)


def test_neuro_fuzzy_model_training_and_inference():
    """Verify membership functions, normalization, and inference behavior."""
    import numpy as np

    np.random.seed(42)
    N = 100
    X = np.random.uniform(0.1, 0.9, size=(N, len(FEATURE_NAMES)))
    y = (X[:, 4] < 0.5).astype(int)  # simple pattern on NDVI

    model = NeuroFuzzyCropFailureModel(n_rules=4, spread_scale=1.2, random_state=42)
    meta = model.fit(X, y, validation_split=0.20)

    assert model.is_trained is True
    assert meta["n_rules"] == 4
    assert 0.0 <= model.optimal_threshold <= 1.0

    # Test predict_proba bounds
    probs = model.predict_proba(X)
    assert probs.shape == (N,)
    assert (probs >= 0.0).all() and (probs <= 1.0).all()

    # Test binary prediction
    preds = model.predict(X)
    assert set(preds).issubset({0, 1})


def test_target_leakage_prevention():
    """Verify that yield and post-outcome columns are strictly excluded from FEATURE_NAMES."""
    forbidden = ["Yield", "YieldIndex", "DES_Yield", "Production", "Failure"]
    for f in forbidden:
        assert f not in FEATURE_NAMES, f"Target leakage detected! {f} found in Neuro-Fuzzy feature list."


def test_neuro_fuzzy_status_endpoint(client):
    """Test /api/v1/experimental/neuro-fuzzy/status endpoint with authentication."""
    headers = make_auth_headers(role="farmer")
    res = client.get("/api/v1/experimental/neuro-fuzzy/status", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "is_available" in data
    assert "version" in data
    assert "feature_names" in data
    assert data["n_rules"] == 6


def test_neuro_fuzzy_status_unauthenticated(client):
    """Verify that unauthenticated requests are rejected."""
    res = client.get("/api/v1/experimental/neuro-fuzzy/status")
    assert res.status_code == 401


def test_neuro_fuzzy_predict_endpoint(client):
    """Test /api/v1/experimental/neuro-fuzzy/predict endpoint with realistic agronomic telemetry."""
    headers = make_auth_headers(role="farmer")
    payload = {
        "rainfall": 60.0,
        "temperature": 32.5,
        "humidity": 45.0,
        "soil_moisture": 28.0,
        "ndvi_flowering": 0.45,
        "water_stress": 0.70,
        "pest_risk": 0.50,
        "suitability_score": 0.55,
    }
    res = client.post("/api/v1/experimental/neuro-fuzzy/predict", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["risk_band"] in ["Low", "Medium", "High"]
    assert "dominant_rule" in data
    assert len(data["activated_rules"]) == 6
    assert data["dominant_rule"]["firing_strength"] >= 0.0
    assert "antecedent_memberships" in data["dominant_rule"]


def test_neuro_fuzzy_predict_validation_errors(client):
    """Verify input validation handles out-of-range parameters cleanly."""
    headers = make_auth_headers(role="farmer")
    # Negative humidity
    payload = {
        "rainfall": 60.0,
        "temperature": 32.5,
        "humidity": -10.0,
        "soil_moisture": 28.0,
        "ndvi_flowering": 0.45,
        "water_stress": 0.70,
        "pest_risk": 0.50,
        "suitability_score": 0.55,
    }
    res = client.post("/api/v1/experimental/neuro-fuzzy/predict", json=payload, headers=headers)
    assert res.status_code == 422


def test_neuro_fuzzy_comparison_rbac(client):
    """Verify that comparison endpoint requires authentication and is accessible to authenticated users."""
    # Unauthenticated should be denied (401)
    res_anon = client.get("/api/v1/experimental/neuro-fuzzy/comparison")
    assert res_anon.status_code in (401, 403)

    # Farmer role is granted (200) under open expert workbench design
    farmer_headers = make_auth_headers(role="farmer")
    res_farmer = client.get("/api/v1/experimental/neuro-fuzzy/comparison", headers=farmer_headers)
    assert res_farmer.status_code == 200
    comp_list = res_farmer.json()
    assert isinstance(comp_list, list)
    assert len(comp_list) >= 4
    model_names = [m["Model"] for m in comp_list]
    assert "Neuro-Fuzzy (TSK)" in model_names
    assert "Logistic Regression" in model_names

    # Expert role is also granted (200)
    expert_headers = make_auth_headers(role="expert")
    res_expert = client.get("/api/v1/experimental/neuro-fuzzy/comparison", headers=expert_headers)
    assert res_expert.status_code == 200


def test_production_prediction_endpoint_unchanged(client):
    """Verify that production /predictions endpoint continues to function without alteration."""
    headers = make_auth_headers(role="farmer")
    req = {
        "district": "Pune",
        "state": "Maharashtra",
        "crop": "Soybean",
        "season": "Kharif",
        "soil_type": "Black",
        "irrigation_level": "Medium",
    }
    res = client.post("/api/v1/predictions", json=req, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "risk_probability" in data
    assert "best_model_name" in data
    assert "recommendations" in data
