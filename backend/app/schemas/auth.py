"""Authentication and user session schemas."""

import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """Authenticated user profile representation."""

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
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


class UserProfileUpdateRequest(BaseModel):
    """User profile update request.

    Note: Privilege escalation is strictly prevented - 'role' and 'id' cannot be modified here.
    """

    full_name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone_number: Optional[str] = Field(None, min_length=5, max_length=20)
    preferred_language: Optional[str] = Field(None, min_length=2, max_length=10)
    sms_notifications_enabled: Optional[bool] = None
    whatsapp_notifications_enabled: Optional[bool] = None
