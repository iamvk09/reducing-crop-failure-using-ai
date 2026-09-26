"""Security, authorization, and Supabase JWT verification primitives."""

from typing import Dict, List, Optional
from pydantic import BaseModel
from backend.app.core.config import settings
from backend.app.core.logging import logger


class AuthenticatedUser(BaseModel):
    """Authenticated user context extracted from verified JWT payload."""

    id: str
    email: Optional[str] = None
    role: str = "farmer"  # 'farmer', 'expert', 'admin'
    full_name: Optional[str] = None


def decode_jwt_token(token: str) -> Optional[Dict]:
    """Placeholder for Supabase JWT decoding and signature verification.

    In production, this verifies the JWT signature against SUPABASE_JWT_SECRET
    or the Supabase JWKS public endpoint.
    """
    if not token or token == "invalid-token":
        return None

    # Development fallback for unconfigured environments
    if settings.APP_ENV == "development" and token.startswith("mock-dev-token-"):
        parts = token.split("-")
        role = parts[-1] if parts[-1] in ["farmer", "expert", "admin"] else "farmer"
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": f"dev_{role}@example.com",
            "role": role,
            "user_metadata": {"full_name": f"Dev {role.title()}"},
        }

    logger.warning("JWT verification requested without configured Supabase credentials.")
    return None


def verify_user_role(user: AuthenticatedUser, required_roles: List[str]) -> bool:
    """Verify whether the user has one of the required authorization roles."""
    if "admin" == user.role:
        return True
    return user.role in required_roles
