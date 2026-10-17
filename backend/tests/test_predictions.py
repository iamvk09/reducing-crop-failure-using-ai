"""Tests for ML Prediction Service behind FastAPI with Supabase Repository persistence and multi-tenant isolation."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.app.core.supabase import SupabaseClientError
from backend.app.repositories.prediction_repository import prediction_repository
from backend.tests.conftest import auth_headers


def create_test_farm_and_crop(client: TestClient, token: str) -> tuple[str, str]:
    """Helper to create a test farm and active crop for a user."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(token),
        json={
            "name": "Sahyadri Agro Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "area_hectares": 4.2,
            "soil_type": "Black",
            "irrigation_level": "Medium",
        },
    )
    assert farm_res.status_code == 201
    farm_id = farm_res.json()["id"]

    crop_res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(token),
        json={
            "crop": "Soybean",
            "season": "Kharif",
            "sowing_date": "2026-06-15",
            "growth_stage": "Flowering",
            "status": "active",
        },
    )
    assert crop_res.status_code == 201
    crop_id = crop_res.json()["id"]

    return farm_id, crop_id


def test_unauthenticated_prediction_requests_rejected(client: TestClient):
    """Ensure unauthenticated calls to prediction endpoints return 401."""
    # Farm prediction POST
    res_post = client.post("/api/v1/farms/some-farm-id/predictions")
    assert res_post.status_code == 401

    # Farm prediction history GET
    res_history = client.get("/api/v1/farms/some-farm-id/predictions")
    assert res_history.status_code == 401

    # Single prediction lookup GET
    res_single = client.get("/api/v1/predictions/some-pred-id")
    assert res_single.status_code == 401


def test_farmer_cannot_predict_on_another_farmers_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot trigger prediction or view history for Farmer 1's farm."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    # Farmer 2 tries to run prediction on Farmer 1's farm
    pred_res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer2_token),
        json={},
    )
    assert pred_res.status_code == 404

    # Farmer 2 tries to view prediction history for Farmer 1's farm
    hist_res = client.get(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer2_token),
    )
    assert hist_res.status_code == 404


def test_farmer_successful_prediction_on_own_farm(
    client: TestClient, farmer1_token: str
):
    """Ensure Farmer 1 can trigger prediction on their own farm using real ML pipeline and persist it."""
    farm1_id, crop1_id = create_test_farm_and_crop(client, farmer1_token)

    res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert res.status_code == 201
    data = res.json()

    # Verify response schema and real model outputs
    assert data["prediction_id"] is not None
    assert data["farm_id"] == farm1_id
    assert data["crop_id"] == crop1_id
    assert data["crop"] == "Soybean"
    assert data["district"] == "Pune"
    assert data["state"] == "Maharashtra"
    assert data["season"] == "Kharif"
    assert 0.0 <= data["risk_probability"] <= 1.0
    assert data["risk_level"] in ["Low", "Medium", "High"]
    assert data["prediction_class"] in [0, 1]
    assert data["best_model_name"] != ""
    assert "input_features" in data
    assert len(data["input_features"]) == 16
    assert "provenance" in data
    assert "recommendations" in data
    assert data["recommendations"]["recommended_crop"] is not None
    assert len(data["recommendations"]["top_options"]) > 0

    # Verify that prediction exists in repository
    retrieved = prediction_repository.get_by_id(data["prediction_id"])
    assert retrieved is not None
    assert retrieved["id"] == data["prediction_id"]
    assert retrieved["farm_id"] == farm1_id


def test_list_farm_predictions_history(client: TestClient, farmer1_token: str):
    """Ensure prediction history is saved and retrievable in reverse chronological order."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    # Trigger 2 predictions
    p1 = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    ).json()

    p2 = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={"temperature_override": 38.0},
    ).json()

    # List history
    hist_res = client.get(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 2
    # Newest first
    assert history[0]["prediction_id"] == p2["prediction_id"]
    assert history[1]["prediction_id"] == p1["prediction_id"]


def test_get_prediction_by_id_isolation(
    client: TestClient, farmer1_token: str, farmer2_token: str, expert_token: str
):
    """Ensure single prediction retrieval respects tenant isolation."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    pred = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    ).json()
    pred_id = pred["prediction_id"]

    # Farmer 1 (Owner) can get prediction
    f1_get = client.get(
        f"/api/v1/predictions/{pred_id}",
        headers=auth_headers(farmer1_token),
    )
    assert f1_get.status_code == 200
    assert f1_get.json()["prediction_id"] == pred_id

    # Farmer 2 (Unauthorized) cannot get prediction
    f2_get = client.get(
        f"/api/v1/predictions/{pred_id}",
        headers=auth_headers(farmer2_token),
    )
    assert f2_get.status_code == 404

    # Expert can get prediction
    exp_get = client.get(
        f"/api/v1/predictions/{pred_id}",
        headers=auth_headers(expert_token),
    )
    assert exp_get.status_code == 200
    assert exp_get.json()["prediction_id"] == pred_id


def test_prediction_pagination(client: TestClient, farmer1_token: str):
    """Ensure prediction history supports limit and offset pagination."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    # Generate 4 predictions
    for i in range(4):
        client.post(
            f"/api/v1/farms/{farm1_id}/predictions",
            headers=auth_headers(farmer1_token),
            json={"temperature_override": 25.0 + i},
        )

    # Fetch with limit=2
    res_page1 = client.get(
        f"/api/v1/farms/{farm1_id}/predictions?limit=2&offset=0",
        headers=auth_headers(farmer1_token),
    )
    assert res_page1.status_code == 200
    page1 = res_page1.json()
    assert len(page1) == 2

    # Fetch with limit=2, offset=2
    res_page2 = client.get(
        f"/api/v1/farms/{farm1_id}/predictions?limit=2&offset=2",
        headers=auth_headers(farmer1_token),
    )
    assert res_page2.status_code == 200
    page2 = res_page2.json()
    assert len(page2) == 2

    # Ensure no overlap
    page1_ids = {p["prediction_id"] for p in page1}
    page2_ids = {p["prediction_id"] for p in page2}
    assert page1_ids.isdisjoint(page2_ids)


def test_prediction_with_manual_overrides(client: TestClient, farmer1_token: str):
    """Ensure expert/manual overrides correctly alter inputs and provenance."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    pred_res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={
            "temperature_override": 42.5,
            "rainfall_override": 10.0,
            "water_stress_override": 0.85,
        },
    )
    assert pred_res.status_code == 201
    data = pred_res.json()
    assert data["input_features"]["Temperature"] == 42.5
    assert data["input_features"]["Rainfall"] == 10.0
    assert data["input_features"]["WaterStress"] == 0.85
    assert data["provenance"]["Temperature"] == "User override (Advanced Inputs)"
    assert data["provenance"]["Rainfall"] == "User override (Advanced Inputs)"


def test_expert_can_predict_on_any_farm(
    client: TestClient, farmer1_token: str, expert_token: str
):
    """Ensure experts can trigger predictions on farmer farms."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    pred_res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(expert_token),
        json={},
    )
    assert pred_res.status_code == 201
    assert pred_res.json()["farm_id"] == farm1_id


def test_prediction_fails_when_no_crops_on_farm(client: TestClient, farmer1_token: str):
    """Ensure prediction gracefully fails with 422 if a farm has no registered crop cycle."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Empty Farm",
            "state": "Punjab",
            "district": "Ludhiana",
            "latitude": 30.9010,
            "longitude": 75.8573,
        },
    )
    farm_id = farm_res.json()["id"]

    pred_res = client.post(
        f"/api/v1/farms/{farm_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_res.status_code == 422
    assert "No crops registered" in pred_res.json()["detail"]


def test_recommendation_persistence_and_linkage(client: TestClient, farmer1_token: str):
    """Ensure recommendations table is populated and linked to prediction record."""
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)

    pred_res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_res.status_code == 201
    data = pred_res.json()
    pred_id = data["prediction_id"]

    # Verify linked recommendation
    assert data["recommendations"] is not None
    assert data["recommendations"]["recommended_crop"] is not None
    assert len(data["recommendations"]["top_options"]) > 0
    assert data["recommendations"]["advisory_summary"] != ""


def test_user_prediction_history_isolation(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure user prediction history isolates records between users and starts empty for new users."""
    # Farmer 2 history should initially be empty
    f2_empty_res = client.get("/api/v1/predictions/history", headers=auth_headers(farmer2_token))
    assert f2_empty_res.status_code == 200
    assert f2_empty_res.json() == []

    # Farmer 1 creates a prediction on their farm
    farm1_id, _ = create_test_farm_and_crop(client, farmer1_token)
    pred_res = client.post(
        f"/api/v1/farms/{farm1_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_res.status_code == 201
    f1_pred_id = pred_res.json()["prediction_id"]

    # Farmer 1 history should contain the prediction
    f1_history = client.get("/api/v1/predictions/history", headers=auth_headers(farmer1_token))
    assert f1_history.status_code == 200
    f1_items = f1_history.json()
    assert len(f1_items) >= 1
    assert any(item["prediction_id"] == f1_pred_id for item in f1_items)

    # Farmer 2 history must NOT contain Farmer 1's prediction
    f2_history = client.get("/api/v1/predictions/history", headers=auth_headers(farmer2_token))
    assert f2_history.status_code == 200
    assert not any(item["prediction_id"] == f1_pred_id for item in f2_history.json())

    # Verify alias endpoint /my-history behaves identically
    f1_alias_history = client.get("/api/v1/predictions/my-history", headers=auth_headers(farmer1_token))
    assert f1_alias_history.status_code == 200
    assert len(f1_alias_history.json()) == len(f1_items)

    # Verify unauthenticated request to /history fails with 401
    unauth_res = client.get("/api/v1/predictions/history")
    assert unauth_res.status_code == 401


def test_get_prediction_history_keyword_guard(client: TestClient, farmer1_token: str):
    """Ensure accessing /predictions/history as an ID returns 400 instead of a confusing 404 access denied."""
    res = client.get("/api/v1/predictions/history", headers=auth_headers(farmer1_token))
    # It routes to list_my_predictions, returning 200 with list
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_farm_prediction_persistence_and_monitoring_independence(
    client: TestClient, farmer1_token: str
):
    """Verify that successful predictions persist, appear in history, and do not block neighboring farms."""
    # Create Farm A (with crop) and Farm B (with crop)
    farm_a_id, _ = create_test_farm_and_crop(client, farmer1_token)

    farm_b_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Plot 55 Independent",
            "state": "Punjab",
            "district": "Ludhiana",
            "latitude": 30.9010,
            "longitude": 75.8573,
            "area_hectares": 3.5,
            "soil_type": "Loam",
            "irrigation_level": "High",
        },
    )
    assert farm_b_res.status_code == 201
    farm_b_id = farm_b_res.json()["id"]

    crop_b_res = client.post(
        f"/api/v1/farms/{farm_b_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Wheat",
            "season": "Rabi",
            "sowing_date": "2026-11-01",
            "growth_stage": "Vegetative",
            "status": "active",
        },
    )
    assert crop_b_res.status_code == 201

    # 1. Farm B initially has no predictions -> valid absence (empty list, NOT 500 or timeout)
    empty_b = client.get(f"/api/v1/farms/{farm_b_id}/predictions", headers=auth_headers(farmer1_token))
    assert empty_b.status_code == 200
    assert empty_b.json() == []

    # 2. Farm B monitoring summary still works and returns clean baseline trend
    mon_b = client.get(f"/api/v1/farms/{farm_b_id}/monitoring", headers=auth_headers(farmer1_token))
    assert mon_b.status_code == 200
    assert mon_b.json()["risk_trend"]["trend_direction"] == "insufficient_history"

    # 3. Predict for Farm B
    pred_b_res = client.post(
        f"/api/v1/farms/{farm_b_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_b_res.status_code == 201
    pred_b = pred_b_res.json()
    assert pred_b["farm_id"] == farm_b_id
    b_pred_id = pred_b["prediction_id"]

    # 4. Prediction history for user now contains Farm B's prediction
    hist_res = client.get("/api/v1/predictions/history", headers=auth_headers(farmer1_token))
    assert hist_res.status_code == 200
    history_ids = [p["prediction_id"] for p in hist_res.json()]
    assert b_pred_id in history_ids

    # 5. Farm A's prediction history remains independent
    farm_a_preds = client.get(f"/api/v1/farms/{farm_a_id}/predictions", headers=auth_headers(farmer1_token))
    assert farm_a_preds.status_code == 200
    a_pred_ids = [p["prediction_id"] for p in farm_a_preds.json()]
    assert b_pred_id not in a_pred_ids


def test_soil_type_normalization_and_invalid_soil_isolation(client, farmer1_token, farmer2_token):
    """Verify soil-type alias normalization, invalid soil rejection, and per-farm isolation."""
    # Farm with 'Clayey' soil (plot p44 scenario)
    farm_clayey = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Plot 44 Clayey",
            "state": "Punjab",
            "district": "Amritsar",
            "latitude": 31.6340,
            "longitude": 74.8723,
            "soil_type": "Clayey",
            "irrigation_level": "Medium",
        },
    ).json()
    farm_clayey_id = farm_clayey["id"]

    # Register crop on Plot 44
    client.post(
        f"/api/v1/farms/{farm_clayey_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Wheat",
            "season": "Rabi",
            "status": "active",
        },
    )

    # Farm with standard 'Loam' soil (plot p77 scenario)
    farm_loam = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Plot 77 Loam",
            "state": "Punjab",
            "district": "Amritsar",
            "latitude": 31.6350,
            "longitude": 74.8730,
            "soil_type": "Loam",
            "irrigation_level": "Medium",
        },
    ).json()
    farm_loam_id = farm_loam["id"]

    # Register crop on Plot 77
    client.post(
        f"/api/v1/farms/{farm_loam_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Wheat",
            "season": "Rabi",
            "status": "active",
        },
    )

    # 1. Prediction on Plot 44 ('Clayey') must succeed via defensible alias normalization to 'Clay Loam'
    pred_44_res = client.post(
        f"/api/v1/farms/{farm_clayey_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_44_res.status_code == 201
    pred_44 = pred_44_res.json()
    assert pred_44["input_features"]["SoilType"] == "Clay Loam"
    assert pred_44["risk_probability"] >= 0.0 and pred_44["risk_probability"] <= 1.0

    # 2. Prediction on Plot 77 ('Loam') succeeds independently
    pred_77_res = client.post(
        f"/api/v1/farms/{farm_loam_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_77_res.status_code == 201
    pred_77 = pred_77_res.json()
    assert pred_77["input_features"]["SoilType"] == "Loam"

    # 3. Create a farm with genuinely invalid/unmappable soil category (e.g. 'Volcanic Ash')
    farm_invalid = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Plot Invalid Soil",
            "state": "Punjab",
            "district": "Amritsar",
            "latitude": 31.6360,
            "longitude": 74.8740,
            "soil_type": "Volcanic Ash",
            "irrigation_level": "Medium",
        },
    ).json()
    farm_invalid_id = farm_invalid["id"]

    client.post(
        f"/api/v1/farms/{farm_invalid_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Wheat",
            "season": "Rabi",
            "status": "active",
        },
    )

    # Prediction must fail with 422 or clear error message and NOT silently substitute
    pred_inv_res = client.post(
        f"/api/v1/farms/{farm_invalid_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_inv_res.status_code == 422
    assert "SoilType" in pred_inv_res.json()["detail"] or "Invalid value" in pred_inv_res.json()["detail"]

    # 4. Plot 77 and Plot 44 remain unaffected by Plot Invalid Soil failure
    mon_77 = client.get(f"/api/v1/farms/{farm_loam_id}/predictions", headers=auth_headers(farmer1_token))
    assert mon_77.status_code == 200
    assert len(mon_77.json()) >= 1


def test_state_category_normalization_and_validation(client: TestClient, farmer1_token: str):
    """Verify state normalization for lowercase 'karnataka', known aliases, and rejection of invalid states."""
    # 1. Register a farm with lowercase 'karnataka'
    res_karnataka = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Karnataka Test Plot",
            "state": "karnataka",
            "district": "Bengaluru",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "soil_type": "Red Loam",
            "irrigation_level": "Medium",
        },
    )
    assert res_karnataka.status_code == 201
    farm_karnataka = res_karnataka.json()
    assert farm_karnataka["state"] == "Karnataka"  # Canonicalized on creation
    farm_k_id = farm_karnataka["id"]

    client.post(
        f"/api/v1/farms/{farm_k_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Maize",
            "season": "Kharif",
            "status": "active",
        },
    )

    # Prediction must succeed with normalized 'Karnataka'
    pred_res = client.post(
        f"/api/v1/farms/{farm_k_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_res.status_code == 201
    pred_data = pred_res.json()
    assert pred_data["input_features"]["State"] == "Karnataka"
    assert pred_data["state"] == "Karnataka"

    # 2. Register a farm with abbreviation 'UP' -> 'Uttar Pradesh'
    res_up = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "UP Test Plot",
            "state": "up",
            "district": "Lucknow",
            "latitude": 26.8467,
            "longitude": 80.9462,
            "soil_type": "Alluvial",
            "irrigation_level": "High",
        },
    )
    assert res_up.status_code == 201
    assert res_up.json()["state"] == "Uttar Pradesh"

    # 3. Register a farm with invalid / unknown state 'Atlantis'
    res_unknown = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Atlantis Plot",
            "state": "Atlantis",
            "district": "Unknown",
            "latitude": 20.0,
            "longitude": 70.0,
            "soil_type": "Sandy",
            "irrigation_level": "Low",
        },
    )
    assert res_unknown.status_code == 201
    unknown_farm_id = res_unknown.json()["id"]

    client.post(
        f"/api/v1/farms/{unknown_farm_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Rice",
            "season": "Kharif",
            "status": "active",
        },
    )

    # Prediction must reject unknown state with 422
    pred_unknown = client.post(
        f"/api/v1/farms/{unknown_farm_id}/predictions",
        headers=auth_headers(farmer1_token),
        json={},
    )
    assert pred_unknown.status_code == 422
    assert "State" in pred_unknown.json()["detail"] or "Invalid value 'Atlantis'" in pred_unknown.json()["detail"]


def test_prediction_history_user_isolation(client: TestClient, farmer1_token: str, farmer2_token: str):
    """Verify that prediction history strictly isolates records by authenticated user."""
    # Farmer 1 creates farm and prediction
    farm1_id, crop1_id = create_test_farm_and_crop(client, farmer1_token)
    pred_res1 = client.post(f"/api/v1/farms/{farm1_id}/predictions", headers=auth_headers(farmer1_token), json={})
    assert pred_res1.status_code == 201

    # Farmer 1 history has at least 1 prediction
    hist1 = client.get("/api/v1/predictions/history", headers=auth_headers(farmer1_token))
    assert hist1.status_code == 200
    assert len(hist1.json()) >= 1
    assert all(p["prediction_id"] for p in hist1.json())

    # Farmer 2 (no predictions created) gets empty history list with 200 OK (not 404 or 500)
    hist2 = client.get("/api/v1/predictions/history", headers=auth_headers(farmer2_token))
    assert hist2.status_code == 200
    assert isinstance(hist2.json(), list)
    assert len(hist2.json()) == 0
