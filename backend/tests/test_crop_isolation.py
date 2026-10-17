"""Tests for Crop cycle multi-tenant isolation and farm ownership enforcement."""

from fastapi.testclient import TestClient
from backend.tests.conftest import auth_headers


def test_farmer_can_register_and_list_crops_on_own_farm(
    client: TestClient, farmer1_token: str
):
    """Ensure a farmer can register a crop cycle on their farm and list it."""
    # Create farm
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Wheat Farm", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9, "longitude": 75.8},
    )
    farm_id = farm_res.json()["id"]

    # Register crop
    crop_res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer1_token),
        json={
            "crop": "Wheat",
            "season": "Rabi",
            "sowing_date": "2026-11-01",
            "growth_stage": "Sowing",
        },
    )
    assert crop_res.status_code == 201
    crop_data = crop_res.json()
    assert crop_data["crop"] == "Wheat"
    assert crop_data["farm_id"] == farm_id

    # List crops
    list_res = client.get(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer1_token),
    )
    assert list_res.status_code == 200
    crops = list_res.json()
    assert len(crops) == 1
    assert crops[0]["id"] == crop_data["id"]


def test_farmer_cannot_register_crop_on_another_farmers_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot register a crop on Farmer 1's farm."""
    # Farmer 1 creates farm
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Farmer 1 Plot", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9, "longitude": 75.8},
    )
    farm_id = farm_res.json()["id"]

    # Farmer 2 attempts to register crop
    res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer2_token),
        json={"crop": "Sugarcane", "season": "Kharif"},
    )
    assert res.status_code == 404


def test_farmer_cannot_list_crops_on_another_farmers_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot list crops on Farmer 1's farm."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Rice Paddy", "state": "West Bengal", "district": "Bardhaman", "latitude": 23.2, "longitude": 87.8},
    )
    farm_id = farm_res.json()["id"]

    client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer1_token),
        json={"crop": "Rice", "season": "Kharif"},
    )

    # Farmer 2 attempts to list crops
    list_res = client.get(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer2_token),
    )
    assert list_res.status_code == 404


def test_farmer_cannot_update_or_delete_crop_on_another_farmers_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot update or delete crops on Farmer 1's farm."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Cotton Plot", "state": "Gujarat", "district": "Rajkot", "latitude": 22.3, "longitude": 70.8},
    )
    farm_id = farm_res.json()["id"]

    crop_res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        headers=auth_headers(farmer1_token),
        json={"crop": "Cotton", "season": "Kharif"},
    )
    crop_id = crop_res.json()["id"]

    # Farmer 2 attempts patch
    patch_res = client.patch(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}",
        headers=auth_headers(farmer2_token),
        json={"growth_stage": "Flowering"},
    )
    assert patch_res.status_code == 404

    # Farmer 2 attempts delete
    del_res = client.delete(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}",
        headers=auth_headers(farmer2_token),
    )
    assert del_res.status_code == 404

    # Farmer 1 can still update and delete
    patch_ok = client.patch(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}",
        headers=auth_headers(farmer1_token),
        json={"growth_stage": "Flowering"},
    )
    assert patch_ok.status_code == 200
    assert patch_ok.json()["growth_stage"] == "Flowering"

    del_ok = client.delete(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}",
        headers=auth_headers(farmer1_token),
    )
    assert del_ok.status_code == 204
