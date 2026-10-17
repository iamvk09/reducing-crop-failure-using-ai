"""Tests for audit logging and secret redaction."""

from fastapi.testclient import TestClient
from backend.app.services.audit_service import audit_service, sanitize_metadata
from backend.tests.conftest import auth_headers


def test_audit_log_on_farm_operations(client: TestClient, farmer1_token: str):
    """Ensure farm create, update, delete generate audit log records with user_id."""
    audit_service.clear()

    # Create farm
    create_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={"name": "Audit Test Farm", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9, "longitude": 75.8},
    )
    farm_id = create_res.json()["id"]

    # Update farm
    client.patch(
        f"/api/v1/farms/{farm_id}",
        headers=auth_headers(farmer1_token),
        json={"name": "Audit Updated Farm"},
    )

    # Delete farm
    client.delete(
        f"/api/v1/farms/{farm_id}",
        headers=auth_headers(farmer1_token),
    )

    records = audit_service.list_records()
    assert len(records) >= 3

    actions = [r.action for r in records]
    assert "farm:create" in actions
    assert "farm:update" in actions
    assert "farm:delete" in actions

    for r in records:
        assert r.user_id == "11111111-1111-1111-1111-111111111111"


def test_sanitize_metadata_redacts_sensitive_keys():
    """Ensure secret keys, passwords, and tokens are redacted from audit metadata."""
    raw = {
        "user_id": "123",
        "farm_name": "Test Farm",
        "password": "super-secret-password",
        "access_token": "bearer-ey123456",
        "supabase_jwt_secret": "my-secret-key",
        "nested": {
            "api_key": "secret-api-key",
            "safe_value": "hello",
        },
    }
    cleaned = sanitize_metadata(raw)
    assert cleaned["user_id"] == "123"
    assert cleaned["farm_name"] == "Test Farm"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["access_token"] == "[REDACTED]"
    assert cleaned["supabase_jwt_secret"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["safe_value"] == "hello"
