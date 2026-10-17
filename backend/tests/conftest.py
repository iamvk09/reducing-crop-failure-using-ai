"""Pytest fixtures and test helpers for backend API test suite."""

import time
from typing import Dict
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import create_jwt_token, jwks_manager
from backend.app.main import app
from backend.app.repositories.alert_repository import alert_repository
from backend.app.repositories.feedback_repository import feedback_repository
from backend.app.repositories.weather_repository import weather_repository
from backend.app.services.audit_service import audit_service
from backend.app.services.farm_service import farm_service
from backend.app.services.prediction_service import prediction_service
from backend.app.services.user_service import user_service
from backend.app.services.weather import weather_service

TEST_SECRET = "test-jwt-secret-key-32-bytes-long!!"


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Ensure consistent test configuration and reset in-memory state."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "APP_ENV", "testing")
    farm_service.clear()
    user_service.clear()
    audit_service.clear()
    prediction_service.clear()
    weather_repository.clear()
    weather_service.clear_cache()
    feedback_repository.clear()
    alert_repository.clear_local_for_testing()
    jwks_manager.clear()
    yield
    farm_service.clear()
    user_service.clear()
    audit_service.clear()
    prediction_service.clear()
    weather_repository.clear()
    weather_service.clear_cache()
    feedback_repository.clear()
    alert_repository.clear_local_for_testing()
    jwks_manager.clear()


@pytest.fixture
def client() -> TestClient:
    """Provide synchronous FastAPI TestClient."""
    return TestClient(app)


def make_token(
    user_id: str,
    role: str = "farmer",
    email: str = "user@example.com",
    full_name: str = "Test User",
    secret: str = TEST_SECRET,
    expires_in: int = 3600,
) -> str:
    """Helper to mint a signed JWT for testing."""
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "app_metadata": {"role": role},
        "user_metadata": {"full_name": full_name, "role": role},
    }
    return create_jwt_token(payload, secret=secret, expires_in_seconds=expires_in)


@pytest.fixture
def farmer1_token() -> str:
    return make_token(user_id="11111111-1111-1111-1111-111111111111", role="farmer", email="farmer1@example.com", full_name="Ramesh Patel")


@pytest.fixture
def farmer2_token() -> str:
    return make_token(user_id="22222222-2222-2222-2222-222222222222", role="farmer", email="farmer2@example.com", full_name="Suresh Kumar")


@pytest.fixture
def expert_token() -> str:
    return make_token(user_id="33333333-3333-3333-3333-333333333333", role="expert", email="expert1@example.com", full_name="Dr. Swaminathan")


@pytest.fixture
def admin_token() -> str:
    return make_token(user_id="44444444-4444-4444-4444-444444444444", role="admin", email="admin1@example.com", full_name="System Admin")


@pytest.fixture
def expired_token() -> str:
    return make_token(user_id="55555555-5555-5555-5555-555555555555", role="farmer", expires_in=-100)


@pytest.fixture
def invalid_signature_token() -> str:
    return make_token(user_id="66666666-6666-6666-6666-666666666666", role="farmer", secret="wrong-secret-key-different-hash!!")


def auth_headers(token: str) -> Dict[str, str]:
    """Helper to return Authorization header dictionary."""
    return {"Authorization": f"Bearer {token}"}
