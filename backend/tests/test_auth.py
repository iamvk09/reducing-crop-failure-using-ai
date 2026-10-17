"""Tests for Supabase JWT verification and authentication endpoints."""

from fastapi.testclient import TestClient
from backend.tests.conftest import auth_headers


def test_auth_missing_token(client: TestClient):
    """Ensure accessing protected route without token returns 401."""
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_auth_malformed_token(client: TestClient):
    """Ensure malformed or garbage token returns 401."""
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer this-is-not-a-valid-jwt"})
    assert response.status_code == 401
    assert "detail" in response.json()


def test_auth_missing_bearer_prefix(client: TestClient, farmer1_token: str):
    """Ensure header without 'Bearer ' prefix is rejected."""
    response = client.get("/api/v1/me", headers={"Authorization": farmer1_token})
    assert response.status_code == 401


def test_auth_expired_token(client: TestClient, expired_token: str):
    """Ensure expired JWT returns 401 with descriptive error."""
    response = client.get("/api/v1/me", headers=auth_headers(expired_token))
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_auth_invalid_signature(client: TestClient, invalid_signature_token: str):
    """Ensure JWT signed with invalid/different secret is rejected with 401."""
    response = client.get("/api/v1/me", headers=auth_headers(invalid_signature_token))
    assert response.status_code == 401


def test_auth_valid_token_me_endpoint(client: TestClient, farmer1_token: str):
    """Ensure valid authenticated user can access their profile."""
    response = client.get("/api/v1/me", headers=auth_headers(farmer1_token))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "11111111-1111-1111-1111-111111111111"
    assert data["email"] == "farmer1@example.com"
    assert data["full_name"] == "Ramesh Patel"
    assert data["role"] == "farmer"


def test_auth_update_profile(client: TestClient, farmer1_token: str):
    """Ensure user can update permitted profile fields."""
    response = client.patch(
        "/api/v1/me",
        headers=auth_headers(farmer1_token),
        json={"full_name": "Ramesh K. Patel", "phone_number": "+919876543210", "preferred_language": "hi"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Ramesh K. Patel"
    assert data["phone_number"] == "+919876543210"
    assert data["preferred_language"] == "hi"


def test_auth_asymmetric_rs256_jwks_verification():
    """Verify asymmetric RS256 token verification using a mock JWKS key client."""
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from unittest.mock import MagicMock
    from backend.app.core.security import decode_and_verify_jwt, extract_authenticated_user_from_claims

    # Generate RSA keypair for testing
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    token = jwt.encode(
        {
            "sub": "99999999-9999-9999-9999-999999999999",
            "email": "asymmetric_farmer@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
            "user_metadata": {"full_name": "Asymmetric Farmer", "role": "farmer"},
        },
        pem_private,
        algorithm="RS256",
        headers={"kid": "supabase-test-key-1"},
    )

    # Mock PyJWKClient returning public key for the kid
    mock_jwk_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    # Decode using custom JWK client
    claims = decode_and_verify_jwt(token, custom_jwk_client=mock_jwk_client)
    assert claims["sub"] == "99999999-9999-9999-9999-999999999999"
    assert claims["email"] == "asymmetric_farmer@example.com"

    user = extract_authenticated_user_from_claims(claims)
    assert user.id == "99999999-9999-9999-9999-999999999999"
    assert user.role == "farmer"
    assert user.full_name == "Asymmetric Farmer"


def test_auth_asymmetric_rs256_expired_token():
    """Verify expired asymmetric RS256 token raises TokenExpiredError."""
    import time
    import jwt
    import pytest
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from unittest.mock import MagicMock
    from backend.app.core.security import decode_and_verify_jwt, TokenExpiredError

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    expired_token = jwt.encode(
        {"sub": "expired-user", "aud": "authenticated", "exp": int(time.time()) - 100},
        pem_private,
        algorithm="RS256",
        headers={"kid": "supabase-test-key-1"},
    )

    mock_jwk_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with pytest.raises(TokenExpiredError):
        decode_and_verify_jwt(expired_token, custom_jwk_client=mock_jwk_client)


def test_auth_asymmetric_rs256_invalid_signature():
    """Verify asymmetric RS256 token signed by unknown key is rejected."""
    import time
    import jwt
    import pytest
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from unittest.mock import MagicMock
    from backend.app.core.security import decode_and_verify_jwt, InvalidTokenSignatureError

    key1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem1 = key1.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    token = jwt.encode(
        {"sub": "wrong-key-user", "aud": "authenticated", "exp": int(time.time()) + 3600},
        pem1,
        algorithm="RS256",
        headers={"kid": "supabase-test-key-1"},
    )

    # Provider returns public key of key2 (mismatched)
    mock_jwk_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = key2.public_key()
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with pytest.raises(InvalidTokenSignatureError):
        decode_and_verify_jwt(token, custom_jwk_client=mock_jwk_client)


def test_auth_supabase_rest_fallback_success(monkeypatch):
    """Verify fallback to Supabase Auth REST /auth/v1/user endpoint when invoked."""
    from unittest.mock import patch, MagicMock
    from backend.app.core.security import decode_and_verify_jwt, extract_authenticated_user_from_claims

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "77777777-7777-7777-7777-777777777777",
        "email": "rest_farmer@example.com",
        "aud": "authenticated",
        "role": "authenticated",
        "user_metadata": {"full_name": "REST Verified Farmer", "role": "farmer"},
        "app_metadata": {"provider": "email"},
    }

    with patch("httpx.Client.get", return_value=mock_response):
        claims = decode_and_verify_jwt(
            "mock.supabase.token",
            supabase_url="https://live-project.supabase.co",
        )
        assert claims["sub"] == "77777777-7777-7777-7777-777777777777"
        assert claims["email"] == "rest_farmer@example.com"
        user = extract_authenticated_user_from_claims(claims)
        assert user.id == "77777777-7777-7777-7777-777777777777"
        assert user.role == "farmer"
        assert user.full_name == "REST Verified Farmer"

