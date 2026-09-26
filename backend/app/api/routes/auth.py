"""Authentication and user session routes."""

from fastapi import APIRouter, Depends
from backend.app.api.deps import get_current_user
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.auth import UserProfileResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=UserProfileResponse, summary="Get Current User Profile")
def get_user_profile(user: AuthenticatedUser = Depends(get_current_user)) -> UserProfileResponse:
    """Retrieve profile and role information for currently authenticated user."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        preferred_language="en",
    )
