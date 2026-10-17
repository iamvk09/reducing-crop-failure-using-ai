"""Notification Repository — durable audit log of notification dispatches.

Stores dispatch records in Supabase PostgREST.
CRITICAL: Never silently falls back to an in-memory store in production.
An in-memory repository implementation is provided for isolated unit testing.
"""

import datetime
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client


class NotificationRepository:
    """Supabase-backed durable persistence for notification dispatches."""

    TABLE = "notification_dispatches"

    def __init__(self, client: Optional[SupabaseClient] = None) -> None:
        self.client = client or supabase_client

    def create_dispatch(
        self,
        user_id: str,
        phone_number_masked: str,
        message_body: str,
        idempotency_key: str,
        channel: str = "sms",
        farm_id: Optional[str] = None,
        alert_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        provider: str = "twilio",
        max_retries: int = 3,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a queued notification dispatch record into Supabase."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        dispatch_id = str(uuid.uuid4())
        record: Dict[str, Any] = {
            "id": dispatch_id,
            "user_id": user_id,
            "farm_id": farm_id,
            "alert_id": alert_id,
            "prediction_id": prediction_id,
            "channel": channel,
            "phone_number_masked": phone_number_masked,
            "message_body": message_body,
            "idempotency_key": idempotency_key,
            "status": "queued",
            "provider": provider,
            "retry_count": 0,
            "max_retries": max_retries,
            "created_at": now,
        }

        try:
            self.client.post(self.TABLE, record, user_token=user_token)
            return record
        except SupabaseClientError as err:
            logger.error(
                "Failed to insert notification dispatch to Supabase table '%s': %s",
                self.TABLE,
                err,
            )
            raise RuntimeError(f"Database error creating notification dispatch: {err}") from err

    def get_by_idempotency_key(
        self,
        idempotency_key: str,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch existing dispatch record by its unique idempotency key."""
        try:
            params = {"idempotency_key": f"eq.{idempotency_key}", "limit": 1}
            rows = self.client.get(self.TABLE, params=params, user_token=user_token)
            return rows[0] if rows else None
        except SupabaseClientError as err:
            logger.error("Failed to query notification dispatch by idempotency_key: %s", err)
            raise RuntimeError(f"Database query error for idempotency_key: {err}") from err

    def update_status(
        self,
        dispatch_id: str,
        status: str,
        provider_message_id: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message_sanitized: Optional[str] = None,
        increment_retry: bool = False,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update the dispatch status and state transitions in Supabase."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        patch: Dict[str, Any] = {"status": status}

        if provider_message_id:
            patch["provider_message_id"] = provider_message_id
        if error_code:
            patch["error_code"] = error_code
        if error_message_sanitized:
            patch["error_message_sanitized"] = error_message_sanitized

        if status == "submitted":
            patch["submitted_at"] = now
        elif status == "delivered":
            patch["delivered_at"] = now
        elif status in ("failed", "undelivered"):
            patch["failed_at"] = now

        try:
            params = {"id": f"eq.{dispatch_id}"}
            rows = self.client.patch(self.TABLE, patch, params=params, user_token=user_token)
            return rows[0] if rows else patch
        except SupabaseClientError as err:
            logger.error("Failed to update notification dispatch '%s': %s", dispatch_id, err)
            raise RuntimeError(f"Database error updating notification dispatch: {err}") from err

    def list_dispatches_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List recent dispatch audit records for a given user with pagination."""
        try:
            params = {
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": str(limit),
                "offset": str(offset),
            }
            return self.client.get(self.TABLE, params=params, user_token=user_token) or []
        except SupabaseClientError as err:
            logger.error("Failed to list notification dispatches for user '%s': %s", user_id, err)
            raise RuntimeError(f"Database query error listing user dispatches: {err}") from err


class InMemoryNotificationRepository(NotificationRepository):
    """In-memory notification repository strictly for unit testing.
    
    Must never be used as a silent fallback in production.
    """

    def __init__(self) -> None:
        self.dispatches: Dict[str, Dict[str, Any]] = {}

    def create_dispatch(
        self,
        user_id: str,
        phone_number_masked: str,
        message_body: str,
        idempotency_key: str,
        channel: str = "sms",
        farm_id: Optional[str] = None,
        alert_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        provider: str = "twilio",
        max_retries: int = 3,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.get_by_idempotency_key(idempotency_key):
            raise RuntimeError(f"Duplicate idempotency key: {idempotency_key}")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        dispatch_id = str(uuid.uuid4())
        record: Dict[str, Any] = {
            "id": dispatch_id,
            "user_id": user_id,
            "farm_id": farm_id,
            "alert_id": alert_id,
            "prediction_id": prediction_id,
            "channel": channel,
            "phone_number_masked": phone_number_masked,
            "message_body": message_body,
            "idempotency_key": idempotency_key,
            "status": "queued",
            "provider": provider,
            "provider_message_id": None,
            "error_code": None,
            "error_message_sanitized": None,
            "retry_count": 0,
            "max_retries": max_retries,
            "created_at": now,
            "submitted_at": None,
            "delivered_at": None,
            "failed_at": None,
        }
        self.dispatches[dispatch_id] = record
        return record

    def get_by_idempotency_key(
        self,
        idempotency_key: str,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        for d in self.dispatches.values():
            if d.get("idempotency_key") == idempotency_key:
                return dict(d)
        return None

    def update_status(
        self,
        dispatch_id: str,
        status: str,
        provider_message_id: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message_sanitized: Optional[str] = None,
        increment_retry: bool = False,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if dispatch_id not in self.dispatches:
            raise RuntimeError(f"Dispatch {dispatch_id} not found")
        record = self.dispatches[dispatch_id]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record["status"] = status
        if provider_message_id:
            record["provider_message_id"] = provider_message_id
        if error_code:
            record["error_code"] = error_code
        if error_message_sanitized:
            record["error_message_sanitized"] = error_message_sanitized
        if increment_retry:
            record["retry_count"] += 1

        if status == "submitted":
            record["submitted_at"] = now
        elif status == "delivered":
            record["delivered_at"] = now
        elif status in ("failed", "undelivered"):
            record["failed_at"] = now

        return dict(record)

    def list_dispatches_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = [
            dict(d) for d in self.dispatches.values() if d.get("user_id") == user_id
        ]
        records.sort(key=lambda x: x["created_at"], reverse=True)
        return records[offset : offset + limit]


# Global instance
notification_repository = NotificationRepository()
