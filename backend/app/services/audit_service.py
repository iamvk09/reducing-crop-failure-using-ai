"""Audit logging service for tracking security-sensitive and operational events."""

import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.core.logging import logger

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "supabase_jwt_secret",
    "service_role_key",
    "supabase_secret_key",
    "anon_key",
    "publishable_key",
    "supabase_publishable_key",
    "api_key",
    "authorization",
}


def sanitize_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Remove passwords, secrets, access tokens, and sensitive keys from log metadata."""
    if not metadata:
        return None

    sanitized = {}
    for key, value in metadata.items():
        lower_key = key.lower()
        if any(sensitive in lower_key for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_metadata(value)
        else:
            sanitized[key] = value
    return sanitized


class AuditRecord(BaseModel):
    """Immutable audit log event entry."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class AuditService:
    """Service to record and query system audit trails."""

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []

    def log_action(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditRecord:
        """Record a security-sensitive event with sanitization."""
        clean_metadata = sanitize_metadata(metadata)
        record = AuditRecord(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=clean_metadata,
            ip_address=ip_address,
        )
        self._records.append(record)
        logger.info(
            f"[AUDIT] action={action} resource={resource_type}:{resource_id} user={user_id}"
        )
        return record

    def list_records(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditRecord]:
        """Retrieve audit log records with optional filtering."""
        filtered = self._records
        if user_id:
            filtered = [r for r in filtered if r.user_id == user_id]
        if resource_type:
            filtered = [r for r in filtered if r.resource_type == resource_type]
        return filtered[-limit:]

    def clear(self) -> None:
        """Clear audit records (primarily for testing)."""
        self._records.clear()


audit_service = AuditService()
