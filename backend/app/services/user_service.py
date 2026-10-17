"""User profile domain service with role-protection and audit logging."""

import datetime
import threading
from typing import Dict, Optional
from pydantic import BaseModel

from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.auth import UserProfileResponse, UserProfileUpdateRequest
from backend.app.services.audit_service import audit_service


class UserProfileEntity(BaseModel):
    """Internal user profile representation."""

    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "farmer"
    phone_number: Optional[str] = None
    preferred_language: str = "en"
    sms_notifications_enabled: bool = False
    sms_consent_timestamp: Optional[datetime.datetime] = None
    whatsapp_notifications_enabled: bool = False
    whatsapp_consent_timestamp: Optional[datetime.datetime] = None
    is_active: bool = True
    created_at: datetime.datetime
    updated_at: datetime.datetime


class UserService:
    """Service managing application user profiles."""

    def __init__(self) -> None:
        self._users: Dict[str, UserProfileEntity] = {}
        self._lock = threading.Lock()

    def get_or_create_profile(self, user: AuthenticatedUser) -> UserProfileResponse:
        """Retrieve profile for authenticated user or initialize if first visit."""
        with self._lock:
            profile = self._users.get(user.id)
            if not profile:
                now = datetime.datetime.now(datetime.timezone.utc)
                profile = UserProfileEntity(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=user.role,
                    phone_number=user.phone_number,
                    preferred_language=user.preferred_language or "en",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                self._users[user.id] = profile

        return self._to_response(profile)

    def update_profile(
        self,
        user: AuthenticatedUser,
        update_in: UserProfileUpdateRequest,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> UserProfileResponse:
        """Update authenticated user profile fields.

        Privilege escalation check: role, id, is_active, and email are strictly immutable via this endpoint.
        Persists to Supabase if live client is configured.
        """
        update_dict = update_in.model_dump(exclude_unset=True)
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Supabase durable persistence when live client is available
        from backend.app.core.supabase import supabase_client
        if supabase_client.is_live_configured():
            try:
                db_patch: Dict[str, Any] = {"updated_at": now.isoformat()}
                if "phone_number" in update_dict:
                    db_patch["phone_number"] = update_dict["phone_number"]
                if "preferred_language" in update_dict:
                    db_patch["preferred_language"] = update_dict["preferred_language"]
                if "full_name" in update_dict:
                    db_patch["full_name"] = update_dict["full_name"]
                if "sms_notifications_enabled" in update_dict:
                    is_enabled = bool(update_dict["sms_notifications_enabled"])
                    db_patch["sms_notifications_enabled"] = is_enabled
                    db_patch["sms_consent_timestamp"] = now.isoformat() if is_enabled else None
                if "whatsapp_notifications_enabled" in update_dict:
                    is_enabled = bool(update_dict["whatsapp_notifications_enabled"])
                    db_patch["whatsapp_notifications_enabled"] = is_enabled
                    db_patch["whatsapp_consent_timestamp"] = now.isoformat() if is_enabled else None

                supabase_client.update("users", db_patch, params={"id": f"eq.{user.id}"}, user_token=user_token)
            except Exception as db_err:
                from backend.app.core.logging import logger
                logger.error("Failed to persist user profile update to Supabase: %s", db_err)
                raise RuntimeError(f"Database error updating user profile: {db_err}") from db_err

        # 2. Update in-memory profile state only after durable persistence succeeds
        with self._lock:
            profile = self._users.get(user.id)
            if not profile:
                profile = UserProfileEntity(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=user.role,
                    phone_number=user.phone_number,
                    preferred_language=user.preferred_language or "en",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                self._users[user.id] = profile

            for field, val in update_dict.items():
                if hasattr(profile, field) and val is not None:
                    setattr(profile, field, val)

            # Handle consent timestamp changes in memory
            if "sms_notifications_enabled" in update_dict:
                profile.sms_consent_timestamp = now if update_dict["sms_notifications_enabled"] else None
            if "whatsapp_notifications_enabled" in update_dict:
                profile.whatsapp_consent_timestamp = now if update_dict["whatsapp_notifications_enabled"] else None

            profile.updated_at = now
            self._users[user.id] = profile

        audit_service.log_action(
            action="user:profile_update",
            resource_type="user",
            resource_id=user.id,
            user_id=user.id,
            metadata=update_dict,
            ip_address=ip_address,
        )

        return self._to_response(profile)

    def get_user_profile(self, user_id: str) -> Optional[UserProfileResponse]:
        """Fetch profile for user by ID if it exists."""
        with self._lock:
            profile = self._users.get(user_id)
            return self._to_response(profile) if profile else None

    def clear(self) -> None:
        """Clear user profiles (used for tests)."""
        with self._lock:
            self._users.clear()

    @staticmethod
    def _to_response(entity: UserProfileEntity) -> UserProfileResponse:
        return UserProfileResponse(
            id=entity.id,
            email=entity.email,
            full_name=entity.full_name,
            role=entity.role,
            phone_number=entity.phone_number,
            preferred_language=entity.preferred_language,
            sms_notifications_enabled=entity.sms_notifications_enabled,
            sms_consent_timestamp=entity.sms_consent_timestamp,
            whatsapp_notifications_enabled=entity.whatsapp_notifications_enabled,
            whatsapp_consent_timestamp=entity.whatsapp_consent_timestamp,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


user_service = UserService()
