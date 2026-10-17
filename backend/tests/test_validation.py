"""Tests for request payload schema validation and boundary checks."""

from fastapi.testclient import TestClient
from backend.tests.conftest import auth_headers


def test_invalid_latitude_rejected(client: TestClient, farmer1_token: str):
    """Ensure latitude > 90 or < -90 is rejected with 422."""
    res_high = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "High Lat", "state": "Punjab", "district": "Ludhiana", "latitude": 95.0, "longitude": 75.0},
    )
    assert res_high.status_code == 422

    res_low = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Low Lat", "state": "Punjab", "district": "Ludhiana", "latitude": -95.0, "longitude": 75.0},
    )
    assert res_low.status_code == 422


def test_invalid_longitude_rejected(client: TestClient, farmer1_token: str):
    """Ensure longitude > 180 or < -180 is rejected with 422."""
    res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Out of Range Lon", "state": "Punjab", "district": "Ludhiana", "latitude": 30.0, "longitude": 185.0},
    )
    assert res.status_code == 422


def test_non_positive_area_rejected(client: TestClient, farmer1_token: str):
    """Ensure area_hectares <= 0 is rejected with 422."""
    res_zero = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Zero Area", "state": "Punjab", "district": "Ludhiana", "latitude": 30.0, "longitude": 75.0, "area_hectares": 0.0},
    )
    assert res_zero.status_code == 422

    res_neg = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Neg Area", "state": "Punjab", "district": "Ludhiana", "latitude": 30.0, "longitude": 75.0, "area_hectares": -5.0},
    )
    assert res_neg.status_code == 422


def test_short_farm_name_rejected(client: TestClient, farmer1_token: str):
    """Ensure farm name with length < 2 is rejected."""
    res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "A", "state": "Punjab", "district": "Ludhiana", "latitude": 30.0, "longitude": 75.0},
    )
    assert res.status_code == 422


def test_missing_required_crop_field_rejected(client: TestClient, farmer1_token: str):
    """Ensure crop creation missing 'season' is rejected with 422."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Valid Farm", "state": "Punjab", "district": "Ludhiana", "latitude": 30.0, "longitude": 75.0},
    )
    farm_id = farm_res.json()["id"]

    res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer1_token),
        json={"crop": "Wheat"},  # missing season
    )
    assert res.status_code == 422
