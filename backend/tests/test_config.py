"""Test core configuration and settings."""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import Settings


def test_default_settings():
    """Verify default settings instantiate properly with valid defaults."""
    cfg = Settings()
    assert cfg.APP_NAME == "Crop Risk Intelligence API"
    assert cfg.API_VERSION == "v1"
    assert cfg.PORT == 8000
    assert cfg.HOST == "0.0.0.0"
    assert "models/agri_ai_runtime_bundle.pkl" in cfg.RUNTIME_MODEL_BUNDLE_PATH


def test_cors_origins_parsing():
    """Verify CORS origins parser handles both lists and string formats."""
    # List format
    cfg1 = Settings(CORS_ORIGINS=["http://localhost:3000", "http://example.com"])
    assert len(cfg1.CORS_ORIGINS) == 2
    assert "http://localhost:3000" in cfg1.CORS_ORIGINS

    # Comma-separated string format
    cfg2 = Settings(CORS_ORIGINS="http://localhost:3000, http://example.com")
    assert len(cfg2.CORS_ORIGINS) == 2
    assert "http://example.com" in cfg2.CORS_ORIGINS

    # JSON string format
    cfg3 = Settings(CORS_ORIGINS='["http://localhost:3000", "http://example.com"]')
    assert len(cfg3.CORS_ORIGINS) == 2


def test_supabase_new_key_model():
    """Verify loading settings with the new Supabase standard key model."""
    cfg = Settings(
        _env_file=None,
        SUPABASE_URL="https://crop-failure-ai.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_pub_test_key_12345",
        SUPABASE_SECRET_KEY="sb_sec_test_key_67890",
        SUPABASE_JWT_SECRET="test_jwt_secret_abcdef",
    )
    assert cfg.effective_supabase_url == "https://crop-failure-ai.supabase.co"
    assert cfg.effective_supabase_publishable_key == "sb_pub_test_key_12345"
    assert cfg.effective_supabase_secret_key == "sb_sec_test_key_67890"
    assert cfg.effective_supabase_jwt_secret == "test_jwt_secret_abcdef"


def test_supabase_legacy_key_fallback():
    """Verify backwards compatibility fallback to legacy Supabase keys."""
    cfg = Settings(
        _env_file=None,
        SUPABASE_URL="https://legacy-crop.supabase.co",
        SUPABASE_ANON_KEY="legacy_anon_key_111",
        SUPABASE_SERVICE_ROLE_KEY="legacy_service_role_key_222",
    )
    assert cfg.effective_supabase_url == "https://legacy-crop.supabase.co"
    assert cfg.effective_supabase_publishable_key == "legacy_anon_key_111"
    assert cfg.effective_supabase_secret_key == "legacy_service_role_key_222"


def test_supabase_next_public_key_fallback():
    """Verify fallback to NEXT_PUBLIC_SUPABASE_* if backend keys are unset."""
    cfg = Settings(
        _env_file=None,
        NEXT_PUBLIC_SUPABASE_URL="https://frontend-detected.supabase.co",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="next_pub_key_333",
    )
    assert cfg.effective_supabase_url == "https://frontend-detected.supabase.co"
    assert cfg.effective_supabase_publishable_key == "next_pub_key_333"


def test_supabase_priority_new_over_legacy():
    """Verify that new key names take strict priority over legacy names."""
    cfg = Settings(
        _env_file=None,
        SUPABASE_SECRET_KEY="new_secret_key_preferred",
        SUPABASE_SERVICE_ROLE_KEY="old_service_role_key_ignored",
        SUPABASE_PUBLISHABLE_KEY="new_publishable_key_preferred",
        SUPABASE_ANON_KEY="old_anon_key_ignored",
    )
    assert cfg.effective_supabase_secret_key == "new_secret_key_preferred"
    assert cfg.effective_supabase_publishable_key == "new_publishable_key_preferred"


def test_supabase_client_initialization_with_effective_settings():
    """Verify SupabaseClient correctly picks up effective keys and headers."""
    from backend.app.core.supabase import SupabaseClient

    client = SupabaseClient(
        base_url="https://test-project.supabase.co",
        secret_key="custom_secret_key",
        publishable_key="custom_pub_key",
    )
    assert client.base_url == "https://test-project.supabase.co"
    assert client.secret_key == "custom_secret_key"
    assert client.service_role_key == "custom_secret_key"  # Legacy property alias
    assert client.publishable_key == "custom_pub_key"
    assert client.anon_key == "custom_pub_key"  # Legacy property alias

    # Check server-to-server header (service/secret auth)
    headers = client._get_headers()
    assert headers["apikey"] == "custom_secret_key"
    assert headers["Authorization"] == "Bearer custom_secret_key"

    # Check user-delegated header (user JWT + publishable key)
    user_headers = client._get_headers(user_token="user_jwt_token_xyz")
    assert user_headers["apikey"] == "custom_pub_key"
    assert user_headers["Authorization"] == "Bearer user_jwt_token_xyz"


def test_supabase_client_legacy_arguments():
    """Verify SupabaseClient works when called with legacy argument names."""
    from backend.app.core.supabase import SupabaseClient

    client = SupabaseClient(
        base_url="https://test-legacy.supabase.co",
        service_role_key="legacy_arg_service_role",
        anon_key="legacy_arg_anon",
    )
    assert client.secret_key == "legacy_arg_service_role"
    assert client.publishable_key == "legacy_arg_anon"
    assert client.service_role_key == "legacy_arg_service_role"
    assert client.anon_key == "legacy_arg_anon"


# =============================================================================
# Production In-Memory Fallback Guard Tests
# =============================================================================

def test_production_guard_fails_when_url_missing_or_placeholder(monkeypatch):
    """In production mode, missing or placeholder URL must fail startup."""
    from backend.app.core.supabase import SupabaseClient, ProductionConfigurationError
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    # Placeholder URL
    client_placeholder = SupabaseClient(
        base_url="https://placeholder.supabase.co",
        secret_key="actual_secret_key_12345",
        publishable_key="actual_pub_key_12345",
    )
    with pytest.raises(ProductionConfigurationError) as excinfo:
        client_placeholder.validate_production_configuration()
    assert "Supabase URL is missing or set to a placeholder" in str(excinfo.value)
    # Ensure sensitive secrets are not leaked in the error message
    assert "actual_secret_key_12345" not in str(excinfo.value)


def test_production_guard_fails_when_url_malformed(monkeypatch):
    """In production mode, malformed URL must fail startup."""
    from backend.app.core.supabase import SupabaseClient, ProductionConfigurationError
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    client_bad_url = SupabaseClient(
        base_url="not-a-valid-http-url",
        secret_key="actual_secret_key_12345",
        publishable_key="actual_pub_key_12345",
    )
    with pytest.raises(ProductionConfigurationError) as excinfo:
        client_bad_url.validate_production_configuration()
    assert "Supabase URL is malformed" in str(excinfo.value)


def test_production_guard_fails_when_secret_key_missing_or_placeholder(monkeypatch):
    """In production mode, missing or placeholder secret/service-role key must fail startup."""
    from backend.app.core.supabase import SupabaseClient, ProductionConfigurationError
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    client_placeholder_key = SupabaseClient(
        base_url="https://live-cropai-project.supabase.co",
        secret_key="placeholder-service-role-key",
        publishable_key="actual_pub_key_12345",
    )
    with pytest.raises(ProductionConfigurationError) as excinfo:
        client_placeholder_key.validate_production_configuration()
    assert "Supabase secret/service role key is missing or set to a placeholder" in str(excinfo.value)


def test_production_guard_fails_when_publishable_key_missing_or_placeholder(monkeypatch):
    """In production mode, missing or placeholder publishable/anon key must fail startup."""
    from backend.app.core.supabase import SupabaseClient, ProductionConfigurationError
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    client_placeholder_pub = SupabaseClient(
        base_url="https://live-cropai-project.supabase.co",
        secret_key="sb_secret_real_key_xyz",
        publishable_key="placeholder-anon-key",
    )
    with pytest.raises(ProductionConfigurationError) as excinfo:
        client_placeholder_pub.validate_production_configuration()
    assert "Supabase publishable/anon key is missing or set to a placeholder" in str(excinfo.value)


def test_production_guard_passes_with_valid_configuration(monkeypatch):
    """In production mode, valid HTTPS URL and keys must pass without raising."""
    from backend.app.core.supabase import SupabaseClient
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    client_valid = SupabaseClient(
        base_url="https://live-prod-project.supabase.co",
        secret_key="sb_sec_supersecretkey_production_12345",
        publishable_key="sb_pub_superpublishablekey_production_67890",
    )
    # Must not raise
    client_valid.validate_production_configuration()


def test_production_guard_does_not_block_development(monkeypatch):
    """In development mode, placeholder configuration does not trigger an exception."""
    from backend.app.core.supabase import SupabaseClient
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "development")

    client_dev = SupabaseClient(
        base_url="https://placeholder.supabase.co",
        secret_key="placeholder-service-role-key",
        publishable_key="placeholder-anon-key",
    )
    # Development allows local in-memory fallback; must not raise
    client_dev.validate_production_configuration()


def test_production_guard_does_not_block_testing(monkeypatch):
    """In testing mode, placeholder configuration does not trigger an exception."""
    from backend.app.core.supabase import SupabaseClient
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "testing")

    client_test = SupabaseClient(
        base_url="https://placeholder.supabase.co",
        secret_key="placeholder-service-role-key",
        publishable_key="placeholder-anon-key",
    )
    # Testing allows mock/in-memory repositories; must not raise
    client_test.validate_production_configuration()


def test_fastapi_lifespan_enforces_production_guard(monkeypatch):
    """FastAPI startup lifespan executes validate_production_configuration and raises on invalid prod config."""
    from backend.app.core.config import settings
    from backend.app.core.supabase import supabase_client, ProductionConfigurationError
    from backend.app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(supabase_client, "base_url", "https://placeholder.supabase.co")

    with pytest.raises(ProductionConfigurationError):
        with TestClient(app):
            pass


