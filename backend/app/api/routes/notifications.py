"""FastAPI routes for user notification preferences and dispatch history."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.deps import get_current_user
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.auth import UserProfileUpdateRequest
from backend.app.schemas.notification import (
    ChannelPreferencesResponse,
    NotificationDispatchListResponse,
    NotificationDispatchResponse,
    SmsConsentUpdate,
    WhatsAppConsentUpdate,
)
from backend.app.services.notification_service import mask_phone_number, notification_service
from backend.app.services.user_service import user_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/preferences", response_model=ChannelPreferencesResponse)
def get_notification_preferences(
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChannelPreferencesResponse:
    """Retrieve explicit notification opt-in states across SMS and WhatsApp."""
    profile = user_service.get_user_profile(user.id)
    return ChannelPreferencesResponse(
        user_id=user.id,
        phone_number_masked=mask_phone_number(profile.phone_number) if profile and profile.phone_number else None,
        sms_notifications_enabled=getattr(profile, "sms_notifications_enabled", False) if profile else False,
        sms_consent_timestamp=getattr(profile, "sms_consent_timestamp", None) if profile else None,
        whatsapp_notifications_enabled=getattr(profile, "whatsapp_notifications_enabled", False) if profile else False,
        whatsapp_consent_timestamp=getattr(profile, "whatsapp_consent_timestamp", None) if profile else None,
    )


@router.get("/dispatches", response_model=NotificationDispatchListResponse)
def get_user_dispatches(
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> NotificationDispatchListResponse:
    """Fetch recent notification dispatch logs for the authenticated farmer with bounded pagination."""
    records = notification_service.repository.list_dispatches_for_user(
        user_id=user.id,
        limit=limit,
        offset=offset,
    )
    items = []
    for r in records:
        try:
            items.append(NotificationDispatchResponse(**r))
        except Exception as val_err:
            from backend.app.core.logging import logger
            logger.warning(
                "Skipping dispatch record due to schema validation mismatch [dispatch_id=%s]: %s",
                r.get("id"),
                val_err,
            )
    return NotificationDispatchListResponse(dispatches=items, total_count=len(items))


@router.put("/preferences/sms", status_code=status.HTTP_200_OK)
def update_sms_preferences(
    payload: SmsConsentUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update explicit SMS notification opt-in/opt-out status and phone number."""
    update_in = UserProfileUpdateRequest(
        sms_notifications_enabled=payload.sms_notifications_enabled,
        phone_number=payload.phone_number if payload.phone_number is not None else None,
    )
    updated_profile = user_service.update_profile(
        user=user,
        update_in=update_in,
    )

    return {
        "user_id": user.id,
        "sms_notifications_enabled": updated_profile.sms_notifications_enabled,
        "phone_number_masked": mask_phone_number(updated_profile.phone_number) if updated_profile.phone_number else None,
        "status": "updated",
    }


@router.put("/preferences/whatsapp", status_code=status.HTTP_200_OK)
def update_whatsapp_preferences(
    payload: WhatsAppConsentUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update explicit WhatsApp notification opt-in/opt-out status and phone number."""
    update_in = UserProfileUpdateRequest(
        whatsapp_notifications_enabled=payload.whatsapp_notifications_enabled,
        phone_number=payload.phone_number if payload.phone_number is not None else None,
    )
    updated_profile = user_service.update_profile(
        user=user,
        update_in=update_in,
    )

    return {
        "user_id": user.id,
        "whatsapp_notifications_enabled": updated_profile.whatsapp_notifications_enabled,
        "phone_number_masked": mask_phone_number(updated_profile.phone_number) if updated_profile.phone_number else None,
        "status": "updated",
    }

