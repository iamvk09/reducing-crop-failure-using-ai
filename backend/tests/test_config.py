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
