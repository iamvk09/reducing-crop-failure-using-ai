"""Tests for Farm multi-tenant isolation and ownership enforcement."""

from fastapi.testclient import TestClient
from backend.tests.conftest import auth_headers


def test_farmer_can_create_and_list_own_farm(
    client: TestClient, farmer1_token: str
):
    """Ensure a farmer can create a farm and view it in their farm list."""
    payload = {
        "name": "Green Valley Farm",
        "state": "Maharashtra",
        "district": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "area_hectares": 5.5,
        "soil_type": "Black",
        "irrigation_level": "Medium",
    }
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json=payload,
    )
    assert create_res.status_code == 201
    farm_data = create_res.json()
    assert farm_data["name"] == "Green Valley Farm"
    assert farm_data["user_id"] == "11111111-1111-1111-1111-111111111111"

    # List farms
    list_res = client.get("/api/v1/farms", headers=auth_headers(farmer1_token))
    assert list_res.status_code == 200
    farms = list_res.json()
    assert len(farms) == 1
    assert farms[0]["id"] == farm_data["id"]


def test_farmer_cannot_view_other_farmer_farm_in_list(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot see Farmer 1's farms in GET /farms."""
    # Farmer 1 creates farm
    client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Farmer 1 Plot",
            "state": "Punjab",
            "district": "Ludhiana",
            "latitude": 30.9010,
            "longitude": 75.8573,
            "area_hectares": 10.0,
        },
    )

    # Farmer 2 lists farms
    farmer2_list = client.get("/api/v1/farms", headers=auth_headers(farmer2_token))
    assert farmer2_list.status_code == 200
    assert len(farmer2_list.json()) == 0


def test_farmer_cannot_get_other_farmer_farm_by_id(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot access Farmer 1's farm via GET /farms/{id}."""
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Farmer 1 Secret Farm",
            "state": "Gujarat",
            "district": "Surat",
            "latitude": 21.1702,
            "longitude": 72.8311,
        },
    )
    farm_id = create_res.json()["id"]

    # Farmer 2 attempts direct access
    res = client.get(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer2_token))
    assert res.status_code == 404


def test_farmer_cannot_update_other_farmer_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot update Farmer 1's farm via PATCH /farms/{id}."""
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Original Name",
            "state": "Haryana",
            "district": "Karnal",
            "latitude": 29.6857,
            "longitude": 76.9905,
        },
    )
    farm_id = create_res.json()["id"]

    # Farmer 2 attempts update
    patch_res = client.patch(
        f"/api/v1/farms/{farm_id}",
        headers=auth_headers(farmer2_token),
        json={"name": "Hacked Name"},
    )
    assert patch_res.status_code == 404

    # Verify original farm is unchanged
    get_res = client.get(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer1_token))
    assert get_res.json()["name"] == "Original Name"


def test_farmer_cannot_delete_other_farmer_farm(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot delete Farmer 1's farm via DELETE /farms/{id}."""
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "To Delete",
            "state": "Rajasthan",
            "district": "Jaipur",
            "latitude": 26.9124,
            "longitude": 75.7873,
        },
    )
    farm_id = create_res.json()["id"]

    # Farmer 2 attempts delete
    del_res = client.delete(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer2_token))
    assert del_res.status_code == 404

    # Farmer 1 still has access
    check_res = client.get(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer1_token))
    assert check_res.status_code == 200


def test_expert_can_view_all_farms(
    client: TestClient, farmer1_token: str, farmer2_token: str, expert_token: str
):
    """Ensure an expert can inspect farms across different farmers for agronomic analysis."""
    client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Farm One", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9, "longitude": 75.8},
    )
    client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer2_token),
        json={"name": "Farm Two", "state": "Maharashtra", "district": "Pune", "latitude": 18.5, "longitude": 73.8},
    )

    expert_list = client.get("/api/v1/farms", headers=auth_headers(expert_token))
    assert expert_list.status_code == 200
    assert len(expert_list.json()) == 2


def test_farm_persistence_repository_integration(client: TestClient, farmer1_token: str):
    """Verify POST creates durable farm with matching ID and GET retrieves it from repository."""
    from backend.app.repositories.farm_repository import farm_repository

    payload = {
        "name": "Durable Soil Farm",
        "state": "Madhya Pradesh",
        "district": "Indore",
        "latitude": 22.7196,
        "longitude": 75.8577,
        "area_hectares": 12.0,
        "soil_type": "Loamy",
        "irrigation_level": "High",
    }
    create_res = client.post("/api/v1/farms", headers=auth_headers(farmer1_token), json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    farm_id = created_data["id"]

    # Verify ID in repository matches response ID
    repo_farm = farm_repository.get_farm_by_id(farm_id)
    assert repo_farm is not None
    assert repo_farm["id"] == farm_id
    assert repo_farm["name"] == "Durable Soil Farm"
    assert repo_farm["state"] == "Madhya Pradesh"
    assert repo_farm["user_id"] == "11111111-1111-1111-1111-111111111111"

    # GET by ID returns persisted record
    get_res = client.get(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer1_token))
    assert get_res.status_code == 200
    assert get_res.json()["id"] == farm_id

    # DELETE removes farm from repository
    del_res = client.delete(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer1_token))
    assert del_res.status_code == 204
    assert farm_repository.get_farm_by_id(farm_id) is None


def test_farm_creation_database_failure_handling(client: TestClient, farmer1_token: str, monkeypatch):
    """Verify database persistence failure returns controlled error rather than false success."""
    from backend.app.repositories.farm_repository import farm_repository
    from backend.app.core.supabase import SupabaseClientError

    def mock_failing_create(*args, **kwargs):
        raise SupabaseClientError("Supabase connection timeout", status_code=503)

    monkeypatch.setattr(farm_repository, "create_farm", mock_failing_create)

    payload = {
        "name": "Failing Farm",
        "state": "Karnataka",
        "district": "Dharwad",
        "latitude": 15.4589,
        "longitude": 75.0078,
    }

    import pytest
    with pytest.raises(SupabaseClientError):
        client.post("/api/v1/farms", headers=auth_headers(farmer1_token), json=payload)


def test_farm_create_with_valid_geojson_polygon(client: TestClient, farmer1_token: str):
    """Verify farm creation with a valid GeoJSON Polygon boundary."""
    polygon_geo = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8500, 18.5200],
                [73.8600, 18.5200],
                [73.8600, 18.5300],
                [73.8500, 18.5300],
                [73.8500, 18.5200],
            ]
        ],
    }
    payload = {
        "name": "Polygon Cadastral Farm",
        "state": "Maharashtra",
        "district": "Pune",
        "latitude": 18.5250,
        "longitude": 73.8550,
        "area_hectares": 10.0,
        "boundary_geojson": polygon_geo,
    }
    res = client.post("/api/v1/farms", headers=auth_headers(farmer1_token), json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["boundary_geojson"] == polygon_geo

    # Verify GET by ID returns the boundary
    get_res = client.get(f"/api/v1/farms/{data['id']}", headers=auth_headers(farmer1_token))
    assert get_res.status_code == 200
    assert get_res.json()["boundary_geojson"] == polygon_geo


def test_farm_create_with_invalid_geojson_rejected(client: TestClient, farmer1_token: str):
    """Verify unclosed or malformed GeoJSON boundaries return 422."""
    # Unclosed ring (first point != last point)
    unclosed_geo = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8500, 18.5200],
                [73.8600, 18.5200],
                [73.8600, 18.5300],
                [73.8500, 18.5300],
            ]
        ],
    }
    res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Bad Geo Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5250,
            "longitude": 73.8550,
            "boundary_geojson": unclosed_geo,
        },
    )
    assert res.status_code == 422

    # Invalid GeoJSON type
    bad_type_geo = {
        "type": "Point",
        "coordinates": [73.8500, 18.5200],
    }
    res2 = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Bad Type Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5250,
            "longitude": 73.8550,
            "boundary_geojson": bad_type_geo,
        },
    )
    assert res2.status_code == 422


def test_farm_patch_boundary_geojson(client: TestClient, farmer1_token: str):
    """Verify updating a farm's boundary_geojson via PATCH."""
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Initial Point Farm",
            "state": "Punjab",
            "district": "Ludhiana",
            "latitude": 30.9010,
            "longitude": 75.8573,
        },
    )
    assert create_res.status_code == 201
    farm_id = create_res.json()["id"]
    assert create_res.json().get("boundary_geojson") is None

    polygon_geo = {
        "type": "Polygon",
        "coordinates": [
            [
                [75.8500, 30.9000],
                [75.8600, 30.9000],
                [75.8600, 30.9100],
                [75.8500, 30.9100],
                [75.8500, 30.9000],
            ]
        ],
    }
    patch_res = client.patch(
        f"/api/v1/farms/{farm_id}",
        headers=auth_headers(farmer1_token),
        json={"boundary_geojson": polygon_geo},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["boundary_geojson"] == polygon_geo


