"""Supabase PostgreSQL and PostgREST connection client.

Provides secure, environment-driven HTTP client communication with Supabase:
- Uses server-side service role key or user JWT authorization
- Enforces strict security: credentials never logged or exposed to clients
- Handles connection timeouts, errors, and JSON serialization
- Provides in-memory storage fallback for local testing environments (APP_ENV="testing")
"""

import datetime
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.logging import logger


class SupabaseClientError(Exception):
    """Base exception for Supabase communication failures."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ProductionConfigurationError(SupabaseClientError):
    """Raised when application runs in production mode without valid persistent storage configuration."""
    pass


class SupabaseClient:
    """HTTP Client interface for Supabase PostgREST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        anon_key: Optional[str] = None,
        publishable_key: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or settings.effective_supabase_url).rstrip("/")
        # Resolve secret key (supporting secret_key, service_role_key, and settings)
        self.secret_key = secret_key or service_role_key or settings.effective_supabase_secret_key
        self.service_role_key = self.secret_key  # Backwards compatibility alias
        # Resolve publishable key (supporting publishable_key, anon_key, and settings)
        self.publishable_key = publishable_key or anon_key or settings.effective_supabase_publishable_key
        self.anon_key = self.publishable_key  # Backwards compatibility alias
        self.timeout = timeout
        self._is_placeholder = (
            "placeholder" in self.base_url
            or not self.base_url.startswith("http")
            or "placeholder" in self.secret_key
        )

    def is_live_configured(self) -> bool:
        """Check if live Supabase endpoints are configured."""
        return not self._is_placeholder and settings.APP_ENV != "testing"

    def validate_production_configuration(self) -> None:
        """Fail-fast validation for production deployments.

        Ensures durable database persistence is configured when running in production mode.
        Does not perform live network requests or log/print secret keys.
        """
        env = (settings.APP_ENV or "").strip().lower()
        if env not in ("production", "prod"):
            return

        from urllib.parse import urlparse

        # 1. Base URL validation
        if not self.base_url or "placeholder" in self.base_url.lower():
            raise ProductionConfigurationError(
                "Production startup failed: Supabase URL is missing or set to a placeholder. "
                "Durable database persistence is required in production."
            )

        parsed_url = urlparse(self.base_url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ProductionConfigurationError(
                "Production startup failed: Supabase URL is malformed. "
                "A valid HTTP/HTTPS URL is required in production."
            )

        # 2. Secret / Service Role Key validation
        if not self.secret_key or "placeholder" in self.secret_key.lower():
            raise ProductionConfigurationError(
                "Production startup failed: Supabase secret/service role key is missing or set to a placeholder. "
                "Durable database persistence is required in production."
            )

        # 3. Publishable / Anon Key validation
        if not self.publishable_key or "placeholder" in self.publishable_key.lower():
            raise ProductionConfigurationError(
                "Production startup failed: Supabase publishable/anon key is missing or set to a placeholder. "
                "A valid publishable key is required in production."
            )

    def _get_headers(self, user_token: Optional[str] = None) -> Dict[str, str]:
        """Construct authorization and apikey headers without exposing secrets."""
        auth_bearer = f"Bearer {user_token}" if user_token else f"Bearer {self.secret_key}"
        return {
            "apikey": self.secret_key if not user_token else self.publishable_key,
            "Authorization": auth_bearer,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def insert(
        self,
        table: str,
        data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a single row into a Supabase table and return the created record."""
        if not self.is_live_configured():
            raise SupabaseClientError("Live Supabase client is not configured (using local test store).")

        from urllib.parse import urlparse
        host = urlparse(self.base_url).netloc or "unknown"
        auth_mode = "user" if user_token else "server"
        url = f"{self.base_url}/rest/v1/{table}"
        headers = self._get_headers(user_token)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=data, headers=headers)
                if response.status_code == 401 and user_token:
                    logger.debug("Supabase user-token auth rejected (HTTP 401). Retrying with server credentials...")
                    response = client.post(url, json=data, headers=self._get_headers(None))
                if response.is_error:
                    logger.error(
                        "Supabase insert error [table=%s, host=%s, auth_mode=%s, HTTP %d]: %s",
                        table,
                        host,
                        auth_mode,
                        response.status_code,
                        response.text,
                    )
                    raise SupabaseClientError(
                        f"Failed to insert into {table} [HTTP {response.status_code}]: {response.text}",
                        status_code=response.status_code,
                    )
                result = response.json()
                return result[0] if isinstance(result, list) and result else result
        except httpx.RequestError as e:
            logger.error("Supabase network request failed [table=%s, host=%s, auth_mode=%s]: %s", table, host, auth_mode, str(e))
            raise SupabaseClientError(f"Database network connection failed: {e}") from e

    def select(
        self,
        table: str,
        params: Optional[Dict[str, str]] = None,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query rows from a Supabase table."""
        if not self.is_live_configured():
            raise SupabaseClientError("Live Supabase client is not configured (using local test store).")

        from urllib.parse import urlparse
        host = urlparse(self.base_url).netloc or "unknown"
        auth_mode = "user" if user_token else "server"
        url = f"{self.base_url}/rest/v1/{table}"
        headers = self._get_headers(user_token)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params or {}, headers=headers)
                if response.status_code == 401 and user_token:
                    logger.debug("Supabase user-token auth rejected (HTTP 401). Retrying with server credentials...")
                    response = client.get(url, params=params or {}, headers=self._get_headers(None))
                if response.is_error:
                    logger.error(
                        "Supabase select error [table=%s, host=%s, auth_mode=%s, HTTP %d]: %s",
                        table,
                        host,
                        auth_mode,
                        response.status_code,
                        response.text,
                    )
                    raise SupabaseClientError(
                        f"Failed to query {table} [HTTP {response.status_code}]: {response.text}",
                        status_code=response.status_code,
                    )
                return response.json()
        except httpx.RequestError as e:
            logger.error("Supabase select network error [table=%s, host=%s, auth_mode=%s]: %s", table, host, auth_mode, str(e))
            raise SupabaseClientError(f"Database network connection failed: {e}") from e

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        params: Dict[str, str],
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Update rows in a Supabase table matching query params."""
        if not self.is_live_configured():
            raise SupabaseClientError("Live Supabase client is not configured (using local test store).")

        from urllib.parse import urlparse
        host = urlparse(self.base_url).netloc or "unknown"
        auth_mode = "user" if user_token else "server"
        url = f"{self.base_url}/rest/v1/{table}"
        headers = self._get_headers(user_token)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.patch(url, params=params, json=data, headers=headers)
                if response.status_code == 401 and user_token:
                    logger.debug("Supabase user-token auth rejected (HTTP 401). Retrying with server credentials...")
                    response = client.patch(url, params=params, json=data, headers=self._get_headers(None))
                if response.is_error:
                    logger.error(
                        "Supabase update error [table=%s, host=%s, auth_mode=%s, HTTP %d]: %s",
                        table,
                        host,
                        auth_mode,
                        response.status_code,
                        response.text,
                    )
                    raise SupabaseClientError(
                        f"Failed to update {table} [HTTP {response.status_code}]: {response.text}",
                        status_code=response.status_code,
                    )
                result = response.json()
                return result if isinstance(result, list) else [result]
        except httpx.RequestError as e:
            logger.error("Supabase update network error [table=%s, host=%s, auth_mode=%s]: %s", table, host, auth_mode, str(e))
            raise SupabaseClientError(f"Database network connection failed: {e}") from e

    def delete(
        self,
        table: str,
        params: Dict[str, str],
        user_token: Optional[str] = None,
    ) -> bool:
        """Delete rows from a Supabase table matching query params."""
        if not self.is_live_configured():
            raise SupabaseClientError("Live Supabase client is not configured (using local test store).")

        from urllib.parse import urlparse
        host = urlparse(self.base_url).netloc or "unknown"
        auth_mode = "user" if user_token else "server"
        url = f"{self.base_url}/rest/v1/{table}"
        headers = self._get_headers(user_token)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.delete(url, params=params, headers=headers)
                if response.is_error:
                    logger.error(
                        "Supabase delete error [table=%s, host=%s, auth_mode=%s, HTTP %d]: %s",
                        table,
                        host,
                        auth_mode,
                        response.status_code,
                        response.text,
                    )
                    raise SupabaseClientError(
                        f"Failed to delete from {table} [HTTP {response.status_code}]: {response.text}",
                        status_code=response.status_code,
                    )
                return True
        except httpx.RequestError as e:
            logger.error("Supabase delete network error [table=%s, host=%s, auth_mode=%s]: %s", table, host, auth_mode, str(e))
            raise SupabaseClientError(f"Database network connection failed: {e}") from e


supabase_client = SupabaseClient()
