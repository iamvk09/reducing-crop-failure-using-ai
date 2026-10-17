"""Tests for SlidingWindowRateLimiter, proxy trust, and rate-limiting enforcement."""

import time
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from backend.app.api.deps import get_client_ip
from backend.app.core.config import settings
from backend.app.core.rate_limiter import (
    SlidingWindowRateLimiter,
    prediction_limiter,
    diagnostics_limiter,
    check_rate_limit,
)
from backend.app.main import app


def test_sliding_window_rate_limiter_unit():
    """Verify limiter enforces bounds, records timestamps, and reports retry_after accurately."""
    limiter = SlidingWindowRateLimiter(default_limit=3, window_seconds=2)
    key = "test_user_unit"

    # First 3 requests must be allowed
    allowed1, remaining1, _ = limiter.is_allowed(key)
    assert allowed1 is True
    assert remaining1 == 2

    allowed2, remaining2, _ = limiter.is_allowed(key)
    assert allowed2 is True
    assert remaining2 == 1

    allowed3, remaining3, _ = limiter.is_allowed(key)
    assert allowed3 is True
    assert remaining3 == 0

    # 4th request must be rejected with retry_after > 0
    allowed4, remaining4, retry_after = limiter.is_allowed(key)
    assert allowed4 is False
    assert remaining4 == 0
    assert retry_after >= 1

    # Independent keys should not interfere with each other
    allowed_other, _, _ = limiter.is_allowed("other_user")
    assert allowed_other is True


def test_limiter_memory_bounding_and_eviction():
    """Verify rate limiter does not grow unbounded under high key cardinality."""
    limiter = SlidingWindowRateLimiter(default_limit=5, window_seconds=1, max_keys=10)
    for i in range(15):
        limiter.is_allowed(f"user_{i}")
    # History must be pruned to max_keys
    assert len(limiter._history) <= 10


def test_security_headers_and_sanitization():
    """Verify security headers and sanitization of incoming X-Request-ID."""
    client = TestClient(app)

    # 1. Clean valid alphanumeric Request ID
    res = client.get("/health", headers={"X-Request-ID": "req-123_abc.456"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == "req-123_abc.456"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Content-Security-Policy") == "default-src 'none'; frame-ancestors 'none'"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # 2. Malicious / injection X-Request-ID must be sanitized/replaced with UUIDv4
    res_malicious = client.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert res_malicious.status_code == 200
    returned_id = res_malicious.headers.get("X-Request-ID")
    assert returned_id != "<script>alert(1)</script>"
    assert len(returned_id) >= 32


def test_get_client_ip_proxy_trust_and_anti_spoofing():
    """Verify that untrusted direct connections cannot spoof client IP via headers."""
    class MockClient:
        def __init__(self, host):
            self.host = host

    # 1. Direct connection from an UNTRUSTED IP (e.g. public attacker 198.51.100.24)
    # Even if they provide X-Forwarded-For: 203.0.113.195, it MUST be ignored
    req_untrusted = Request({
        "type": "http",
        "client": ("198.51.100.24", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195"), (b"x-real-ip", b"203.0.113.195")],
    })
    assert get_client_ip(req_untrusted) == "198.51.100.24"

    # 2. Direct connection from a TRUSTED IP (e.g. loopback 127.0.0.1)
    # The forwarded client IP MUST be extracted
    req_trusted = Request({
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.50, 10.0.0.1")],
    })
    assert get_client_ip(req_trusted) == "203.0.113.50"

    # 3. Direct connection from a TRUSTED IP with X-Real-IP fallback
    req_trusted_real_ip = Request({
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"x-real-ip", b"198.51.100.99")],
    })
    assert get_client_ip(req_trusted_real_ip) == "198.51.100.99"
