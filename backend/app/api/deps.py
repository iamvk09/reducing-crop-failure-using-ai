"""FastAPI dependency injection providers for authentication, RBAC, and services."""

from typing import List, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import settings
from backend.app.core.security import (
    AuthenticatedUser,
    InvalidTokenSignatureError,
    JWTVerificationError,
    MalformedTokenError,
    TokenExpiredError,
    decode_and_verify_jwt,
    extract_authenticated_user_from_claims,
    verify_user_role,
)
from backend.app.services.audit_service import AuditService, audit_service
from backend.app.services.farm_service import FarmService, farm_service
from backend.app.services.prediction_service import PredictionService, prediction_service
from backend.app.services.satellite import SatelliteService, satellite_service
from backend.app.services.user_service import UserService, user_service
from backend.app.services.weather_service import WeatherService, weather_service

security_scheme = HTTPBearer(auto_error=False)


def get_raw_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Optional[str]:
    """Extract raw bearer token string if present in request."""
    return credentials.credentials if credentials else None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """Extract, verify, and authenticate user identity from Bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        claims = decode_and_verify_jwt(token)
        return extract_authenticated_user_from_claims(claims)

    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except (InvalidTokenSignatureError, MalformedTokenError, JWTVerificationError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_role(allowed_roles: List[str]):
    """Dependency factory enforcing server-side Role-Based Access Control (RBAC)."""

    def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not verify_user_role(user, allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user.role}' not permitted to access this resource.",
            )
        return user

    return role_checker


get_any_authenticated_user = require_role(["farmer", "expert", "admin"])
get_farmer_user = require_role(["farmer", "admin"])
get_expert_user = require_role(["expert", "admin"])
get_admin_user = require_role(["admin"])


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP address safely, checking proxy headers only from explicitly trusted proxies."""
    direct_ip = request.client.host if request.client else None
    trusted = set(getattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "::1"]))

    # Only inspect forwarding headers if the immediate upstream connection is a known, trusted proxy
    if direct_ip in trusted:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First element in comma-separated list is the client originating IP
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                return client_ip
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and real_ip.strip():
            return real_ip.strip()

    return direct_ip


# Service injection providers
def get_farm_svc() -> FarmService:
    """Provide FarmService instance."""
    return farm_service


def get_user_svc() -> UserService:
    """Provide UserService instance."""
    return user_service


def get_audit_svc() -> AuditService:
    """Provide AuditService instance."""
    return audit_service


def get_prediction_svc() -> PredictionService:
    """Provide PredictionService instance."""
    return prediction_service


def get_weather_svc() -> WeatherService:
    """Provide WeatherService instance."""
    return weather_service


def get_satellite_svc() -> SatelliteService:
    """Provide SatelliteService instance."""
    return satellite_service


def get_monitoring_svc():
    """Provide MonitoringService instance."""
    from backend.app.services.monitoring_service import monitoring_service
    return monitoring_service


def get_alert_svc():
    """Provide AlertService instance."""
    from backend.app.services.alert_service import alert_service
    return alert_service


def get_evaluation_svc():
    """Provide EvaluationService instance."""
    from backend.app.services.evaluation_service import evaluation_service
    return evaluation_service
