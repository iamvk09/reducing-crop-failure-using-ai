"""Test health check endpoints."""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app

client = TestClient(app)


def test_root_health_check():
    """Verify root /health endpoint returns 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "crop-risk-api"
    assert data["version"] == "0.1.0"


def test_versioned_health_check():
    """Verify versioned /api/v1/health endpoint returns 200 and expected payload."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "crop-risk-api"
    assert data["version"] == "0.1.0"


def test_docs_and_redoc_content_security_policy():
    """Verify /docs and /redoc have scoped CSP permitting required CDN assets while API routes remain strict."""
    # 1. Standard API route enforces default-src 'none'
    res_api = client.get("/health")
    assert res_api.status_code == 200
    assert res_api.headers.get("Content-Security-Policy") == "default-src 'none'; frame-ancestors 'none'"
    assert res_api.headers.get("X-Content-Type-Options") == "nosniff"
    assert res_api.headers.get("X-Frame-Options") == "DENY"

    # 2. /docs permits Swagger UI CDNs, inline scripts/styles, and fonts
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    docs_csp = res_docs.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" in docs_csp
    assert "https://fastapi.tiangolo.com" in docs_csp
    assert "'unsafe-inline'" in docs_csp
    assert "frame-ancestors 'none'" in docs_csp
    assert "unsafe-eval" not in docs_csp  # Ensure unsafe-eval is NOT allowed

    # 3. /redoc permits ReDoc CDNs, Google Fonts, and inline styles
    res_redoc = client.get("/redoc")
    assert res_redoc.status_code == 200
    redoc_csp = res_redoc.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" in redoc_csp
    assert "https://fonts.googleapis.com" in redoc_csp
    assert "https://fonts.gstatic.com" in redoc_csp
    assert "frame-ancestors 'none'" in redoc_csp
    assert "unsafe-eval" not in redoc_csp
