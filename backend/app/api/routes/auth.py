"""Authentication and user session routes."""

from fastapi import APIRouter, Depends, Request, status
from backend.app.api.deps import get_client_ip, get_current_user, get_user_svc
from backend.app.core.config import settings
from backend.app.core.rate_limiter import check_rate_limit, general_limiter
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.auth import UserProfileResponse, UserProfileUpdateRequest
from backend.app.services.user_service import UserService

router = APIRouter(tags=["Authentication & Profiles"])


@router.get(
    "/auth/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile (Auth route)",
    description="Retrieve profile and role information for currently authenticated user.",
)
def get_user_profile_auth(
    user: AuthenticatedUser = Depends(get_current_user),
    user_svc: UserService = Depends(get_user_svc),
) -> UserProfileResponse:
    """Retrieve profile of authenticated user."""
    return user_svc.get_or_create_profile(user)


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile",
    description="Retrieve profile and role information for currently authenticated user.",
)
def get_user_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    user_svc: UserService = Depends(get_user_svc),
) -> UserProfileResponse:
    """Retrieve profile of authenticated user."""
    return user_svc.get_or_create_profile(user)


@router.patch(
    "/me",
    response_model=UserProfileResponse,
    summary="Update Current User Profile",
    description="Update mutable profile fields (full name, phone number, language). Privilege escalation is strictly prevented.",
)
def update_user_profile(
    profile_in: UserProfileUpdateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    user_svc: UserService = Depends(get_user_svc),
) -> UserProfileResponse:
    """Update profile fields for the authenticated user without allowing role elevation."""
    rate_key = f"auth_user_{user.id}" if user and user.id else "auth_anon"
    check_rate_limit(
        rate_key,
        general_limiter,
        limit=settings.RATE_LIMIT_GENERAL_PER_MIN,
        error_message="Profile update rate limit exceeded. Please wait before updating your profile again.",
    )
    ip_address = get_client_ip(request)
    return user_svc.update_profile(user=user, update_in=profile_in, ip_address=ip_address)
