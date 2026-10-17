"""Pydantic schemas for SMS notifications, user consent, and dispatch logs."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DispatchStatus(str, Enum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNDELIVERED = "undelivered"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class NotificationChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class SmsConsentUpdate(BaseModel):
    """Payload to opt in or opt out of SMS alerts."""
    sms_notifications_enabled: bool = Field(..., description="Explicit opt-in/opt-out status for SMS.")
    phone_number: Optional[str] = Field(None, min_length=7, max_length=20, description="E.164 phone number.")


class WhatsAppConsentUpdate(BaseModel):
    """Payload to opt in or opt out of WhatsApp alerts."""
    whatsapp_notifications_enabled: bool = Field(..., description="Explicit opt-in/opt-out status for WhatsApp.")
    phone_number: Optional[str] = Field(None, min_length=7, max_length=20, description="E.164 phone number.")


class ChannelPreferencesResponse(BaseModel):
    """Combined notification preferences across channels."""
    user_id: str
    phone_number_masked: Optional[str] = None
    sms_notifications_enabled: bool = False
    sms_consent_timestamp: Optional[datetime] = None
    whatsapp_notifications_enabled: bool = False
    whatsapp_consent_timestamp: Optional[datetime] = None


class NotificationDispatchResponse(BaseModel):
    """Safe representation of an SMS notification delivery attempt."""
    id: str
    user_id: Optional[str] = None
    farm_id: Optional[str] = None
    alert_id: Optional[str] = None
    prediction_id: Optional[str] = None
    channel: str = "sms"
    phone_number_masked: str
    message_body: str
    idempotency_key: str
    status: DispatchStatus
    provider: str
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    submitted_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None


class NotificationDispatchListResponse(BaseModel):
    dispatches: List[NotificationDispatchResponse]
    total_count: int
