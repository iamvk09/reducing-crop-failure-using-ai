"""FastAPI dependency injection providers."""

from typing import Generator, Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import settings
from backend.app.core.security import AuthenticatedUser, decode_jwt_token, verify_user_role
from backend.app.services.prediction_service import PredictionService, prediction_service
from backend.app.services.weather_service import WeatherService, weather_service

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """Extract and verify authenticated user from Authorization Bearer token.

    In development mode without credentials, provides a default development user.
    """
    if credentials:
        payload = decode_jwt_token(credentials.credentials)
        if payload:
            return AuthenticatedUser(
                id=payload.get("sub", "00000000-0000-0000-0000-000000000001"),
                email=payload.get("email"),
                role=payload.get("role", "farmer"),
                full_name=payload.get("user_metadata", {}).get("full_name"),
            )

    # In local development fallback
    if settings.APP_ENV == "development":
        return AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="developer@example.com",
            role="admin",
            full_name="Local Developer",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(allowed_roles: list):
    """Dependency factory enforcing RBAC roles."""

    def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not verify_user_role(user, allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user.role}' not permitted to access this resource.",
            )
        return user

    return role_checker


get_farmer_user = require_role(["farmer", "admin"])
get_expert_user = require_role(["expert", "admin"])
get_admin_user = require_role(["admin"])


def get_prediction_svc() -> PredictionService:
    """Provide prediction service singleton instance."""
    return prediction_service


def get_weather_svc() -> WeatherService:
    """Provide weather service singleton instance."""
    return weather_service
