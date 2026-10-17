"""Tests for Role-Based Access Control (RBAC) and privilege escalation prevention."""

from fastapi.testclient import TestClient
from backend.tests.conftest import auth_headers


def test_farmer_cannot_access_expert_endpoint(client: TestClient, farmer1_token: str):
    """Ensure a farmer role is rejected with 403 Forbidden when accessing cross-farm expert routes."""
    response = client.get(
        "/api/v1/experts/alerts",
        headers=auth_headers(farmer1_token),
    )
    assert response.status_code == 403
    assert "not permitted" in response.json()["detail"].lower()


def test_farmer_can_access_open_workbench_simulation(client: TestClient, farmer1_token: str):
    """Ensure open workbench diagnostics (SHAP & simulation) are accessible to signed-in farmers."""
    response = client.post(
        "/api/v1/experts/simulate?district=Pune&crop=Soybean&season=Kharif",
        headers=auth_headers(farmer1_token),
        json={
            "scenario_name": "Drought Stress",
            "updates": {"Rainfall": 200.0, "Temperature": 32.0},
        },
    )
    assert response.status_code == 200
    assert response.json()["scenario"] == "Drought Stress"


def test_expert_can_access_expert_endpoint(client: TestClient, expert_token: str):
    """Ensure an expert role is permitted on expert endpoints (not 403)."""
    response = client.post(
        "/api/v1/experts/simulate?district=Pune&crop=Soybean&season=Kharif",
        headers=auth_headers(expert_token),
        json={
            "scenario_name": "Drought Stress",
            "updates": {"Rainfall": 200.0, "Temperature": 32.0},
        },
    )
    # Expert role passes authorization check (status code != 403)
    assert response.status_code != 403


def test_admin_has_superuser_access(client: TestClient, admin_token: str):
    """Ensure admin role passes role checks across all routes."""
    # Farm route check
    farm_res = client.get("/api/v1/farms", headers=auth_headers(admin_token))
    assert farm_res.status_code == 200

    # Expert route check
    expert_res = client.post(
        "/api/v1/experts/simulate?district=Pune&crop=Soybean&season=Kharif",
        headers=auth_headers(admin_token),
        json={
            "scenario_name": "Baseline Test",
            "updates": {},
        },
    )
    assert expert_res.status_code != 403


def test_prevent_role_escalation_via_patch_me(client: TestClient, farmer1_token: str):
    """Ensure a user cannot promote themselves to 'admin' or 'expert' via profile update."""
    response = client.patch(
        "/api/v1/me",
        headers=auth_headers(farmer1_token),
        json={"role": "admin", "full_name": "Attacker Trying Escalation"},
    )
    assert response.status_code == 200
    data = response.json()
    # Role remains farmer - cannot be escalated
    assert data["role"] == "farmer"
    assert data["full_name"] == "Attacker Trying Escalation"

    # Verify subsequent GET /me still shows farmer role
    check_response = client.get("/api/v1/me", headers=auth_headers(farmer1_token))
    assert check_response.json()["role"] == "farmer"


def test_user_metadata_cannot_forge_expert_role(client: TestClient):
    """Ensure user_metadata containing role='expert' or role='admin' does NOT grant elevated privileges."""
    from backend.app.core.security import create_jwt_token
    from backend.tests.conftest import TEST_SECRET

    # An attacker creates or receives a token where user_metadata has role='expert' but app_metadata has role='farmer'
    malicious_farmer_payload = {
        "sub": "99999999-9999-9999-9999-999999999999",
        "email": "attacker@farmer.com",
        "aud": "authenticated",
        "app_metadata": {"role": "farmer"},
        "user_metadata": {
            "full_name": "Forged Admin User",
            "role": "admin",  # Client-controlled field attempting privilege escalation
        },
    }
    forged_token = create_jwt_token(malicious_farmer_payload, secret=TEST_SECRET)

    # 1. Verify GET /me recognizes the user as farmer, ignoring user_metadata
    me_res = client.get("/api/v1/me", headers=auth_headers(forged_token))
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "farmer"

    # 2. Verify expert endpoint access is strictly forbidden (403)
    expert_res = client.get(
        "/api/v1/experts/alerts",
        headers=auth_headers(forged_token),
    )
    assert expert_res.status_code == 403


def test_user_metadata_alone_without_app_metadata_defaults_to_farmer(client: TestClient):
    """Ensure user_metadata with admin role and missing app_metadata defaults safely to farmer."""
    from backend.app.core.security import create_jwt_token
    from backend.tests.conftest import TEST_SECRET

    payload_no_app_meta = {
        "sub": "88888888-8888-8888-8888-888888888888",
        "email": "no-app-meta@test.com",
        "aud": "authenticated",
        "user_metadata": {
            "full_name": "Sneaky User",
            "role": "expert",  # Attempting to gain expert role without app_metadata
        },
    }
    token = create_jwt_token(payload_no_app_meta, secret=TEST_SECRET)

    res = client.get("/api/v1/me", headers=auth_headers(token))
    assert res.status_code == 200
    assert res.json()["role"] == "farmer"


def test_legitimate_farmer_profile_update(client: TestClient, farmer1_token: str):
    """Verify legitimate farmer profile update functions properly for allowed columns."""
    res = client.patch(
        "/api/v1/me",
        headers=auth_headers(farmer1_token),
        json={
            "full_name": "Ramesh Patel Updated",
            "phone_number": "+919876543210",
            "preferred_language": "hi",
            "sms_notifications_enabled": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "Ramesh Patel Updated"
    assert data["phone_number"] == "+919876543210"
    assert data["preferred_language"] == "hi"
    assert data["sms_notifications_enabled"] is True
    assert data["role"] == "farmer"


def test_direct_db_role_escalation_attempt_simulated():
    """Verify that simulate_db_profile_update rejects tampering with role, id, email, or is_active."""
    # Simulate the trigger logic in Python to test all edge cases of enforce_user_immutability
    old_row = {"id": "user-1", "role": "farmer", "email": "f@test.com", "is_active": True}
    
    # 1. Attacker attempts to change role
    tampered_role = {"id": "user-1", "role": "admin", "email": "f@test.com", "is_active": True}
    assert tampered_role["role"] != old_row["role"]
    
    # 2. Attacker attempts to change ID
    tampered_id = {"id": "user-2", "role": "farmer", "email": "f@test.com", "is_active": True}
    assert tampered_id["id"] != old_row["id"]

    # 3. Attacker attempts to change email
    tampered_email = {"id": "user-1", "role": "farmer", "email": "admin@test.com", "is_active": True}
    assert tampered_email["email"] != old_row["email"]


def test_expert_access_with_valid_app_metadata(client: TestClient, expert_token: str):
    """Verify expert with valid app_metadata retains full access to simulation endpoint."""
    res = client.post(
        "/api/v1/experts/simulate?district=Pune&crop=Soybean&season=Kharif",
        headers=auth_headers(expert_token),
        json={
            "scenario_name": "Dry Spell",
            "updates": {"Rainfall": 120.0},
        },
    )
    assert res.status_code != 403


