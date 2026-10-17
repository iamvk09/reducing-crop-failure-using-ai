"""Alert Repository — persistent storage for early warning farm alerts.

Implements Supabase PostgREST persistence with in-memory local fallback
for offline development and test isolation.

PostgREST filter params format: {"field": "eq.VALUE"}
"""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client


class AlertRepository:
    """Repository managing farm alert CRUD, deduplication, and diagnostics."""

    TABLE = "farm_alerts"

    def __init__(self, client: Optional[SupabaseClient] = None) -> None:
        self.client = client or supabase_client
        self._local_alerts: Dict[str, Dict[str, Any]] = {}
        self._dedup_count: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_alert(
        self,
        farm_id: str,
        alert_type: str,
        severity: str,
        trigger_reason: str,
        prediction_id: Optional[str] = None,
        crop_id: Optional[str] = None,
        risk_probability: Optional[float] = None,
        previous_risk_probability: Optional[float] = None,
        risk_delta_pp: Optional[float] = None,
        recommended_action: Optional[str] = None,
        shap_context: Optional[List[Dict[str, Any]]] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a new alert record."""
        now = datetime.datetime.now(datetime.timezone.utc)
        alert_id = str(uuid.uuid4())
        record: Dict[str, Any] = {
            "id": alert_id,
            "farm_id": farm_id,
            "crop_id": crop_id,
            "alert_type": alert_type,
            "severity": severity,
            "status": "active",
            "trigger_reason": trigger_reason,
            "prediction_id": prediction_id,
            "risk_probability": risk_probability,
            "previous_risk_probability": previous_risk_probability,
            "risk_delta_pp": risk_delta_pp,
            "recommended_action": recommended_action,
            "shap_context": shap_context or [],
            "acknowledged_at": None,
            "acknowledged_by": None,
            "resolved_at": None,
            "resolved_by": None,
            "resolution_notes": None,
            "created_at": now.isoformat(),
        }

        if self.client.is_live_configured():
            try:
                db_record = record.copy()
                # Supabase doesn't accept list directly for JSONB via PostgREST — wrap correctly
                import json
                db_record["shap_context"] = json.dumps(shap_context or [])
                self.client.insert(self.TABLE, db_record, user_token=user_token)
            except Exception as exc:
                logger.warning("Could not persist alert to Supabase: %s", exc)

        with self._lock:
            self._local_alerts[alert_id] = record.copy()

        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, alert_id: str, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve a single alert by ID."""
        if self.client.is_live_configured():
            try:
                records = self.client.select(self.TABLE, params={"id": f"eq.{alert_id}"}, user_token=user_token)
                if records:
                    return records[0]
            except Exception as exc:
                logger.debug("Supabase alert get_by_id failed: %s", exc)

        with self._lock:
            return self._local_alerts.get(alert_id)

    def list_for_farm(
        self,
        farm_id: str,
        status: Optional[str] = None,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List alerts for a specific farm with optional filters."""
        if self.client.is_live_configured():
            try:
                params: Dict[str, Any] = {
                    "farm_id": f"eq.{farm_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                }
                if status:
                    params["status"] = f"eq.{status}"
                if alert_type:
                    params["alert_type"] = f"eq.{alert_type}"
                if severity:
                    params["severity"] = f"eq.{severity}"
                records = self.client.select(self.TABLE, params=params, user_token=user_token)
                if records:
                    return records
            except Exception as exc:
                logger.debug("Supabase alert list_for_farm failed: %s", exc)

        with self._lock:
            alerts = [a for a in self._local_alerts.values() if a.get("farm_id") == farm_id]
        if status:
            alerts = [a for a in alerts if a.get("status") == status]
        if alert_type:
            alerts = [a for a in alerts if a.get("alert_type") == alert_type]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        alerts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return alerts[:limit]

    def list_all(
        self,
        status: Optional[str] = None,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 200,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all alerts across farms (expert/admin only)."""
        if self.client.is_live_configured():
            try:
                params: Dict[str, Any] = {"order": "created_at.desc", "limit": str(limit)}
                if status:
                    params["status"] = f"eq.{status}"
                if alert_type:
                    params["alert_type"] = f"eq.{alert_type}"
                if severity:
                    params["severity"] = f"eq.{severity}"
                records = self.client.select(self.TABLE, params=params, user_token=user_token)
                if records:
                    return records
            except Exception as exc:
                logger.debug("Supabase alert list_all failed: %s", exc)

        with self._lock:
            alerts = list(self._local_alerts.values())
        if status:
            alerts = [a for a in alerts if a.get("status") == status]
        if alert_type:
            alerts = [a for a in alerts if a.get("alert_type") == alert_type]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        alerts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return alerts[:limit]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_status(
        self,
        alert_id: str,
        new_status: str,
        user_id: Optional[str] = None,
        notes: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update alert status (acknowledge or resolve)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload: Dict[str, Any] = {"status": new_status}

        if new_status == "acknowledged":
            payload["acknowledged_at"] = now
            payload["acknowledged_by"] = user_id
        elif new_status == "resolved":
            payload["resolved_at"] = now
            payload["resolved_by"] = user_id
            if notes:
                payload["resolution_notes"] = notes

        if self.client.is_live_configured():
            try:
                self.client.update(self.TABLE, payload, {"id": f"eq.{alert_id}"}, user_token=user_token)
            except Exception as exc:
                logger.warning("Supabase alert update_status failed: %s", exc)

        with self._lock:
            if alert_id in self._local_alerts:
                self._local_alerts[alert_id].update(payload)
                return self._local_alerts[alert_id].copy()
        return None

    def delete_alert(self, alert_id: str, user_token: Optional[str] = None) -> bool:
        """Delete an alert record (admin only)."""
        deleted = False
        if self.client.is_live_configured():
            try:
                self.client.delete(self.TABLE, params={"id": f"eq.{alert_id}"}, user_token=user_token)
                deleted = True
            except Exception as exc:
                logger.debug("Supabase alert delete failed: %s", exc)

        with self._lock:
            if alert_id in self._local_alerts:
                del self._local_alerts[alert_id]
                deleted = True
        return deleted

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def record_deduplication(self) -> None:
        """Increment deduplication counter (for diagnostics)."""
        with self._lock:
            self._dedup_count += 1

    def get_diagnostics_metrics(self) -> Dict[str, Any]:
        """Return alert diagnostics for monitoring service."""
        with self._lock:
            alerts = list(self._local_alerts.values())
            total = len(alerts)
            active = sum(1 for a in alerts if a.get("status") == "active")
            acknowledged = sum(1 for a in alerts if a.get("status") == "acknowledged")
            resolved = sum(1 for a in alerts if a.get("status") == "resolved")
            by_severity: Dict[str, int] = {}
            by_type: Dict[str, int] = {}
            stale_count = 0
            for a in alerts:
                sev = a.get("severity", "unknown")
                by_severity[sev] = by_severity.get(sev, 0) + 1
                atype = a.get("alert_type", "unknown")
                by_type[atype] = by_type.get(atype, 0) + 1
                if atype in ("WEATHER_STALE", "SATELLITE_STALE", "DATA_QUALITY_DEGRADED"):
                    stale_count += 1
            return {
                "total_alerts": total,
                "active_alerts": active,
                "acknowledged_alerts": acknowledged,
                "resolved_alerts": resolved,
                "alerts_by_severity": by_severity,
                "alerts_by_type": by_type,
                "alert_deduplication_count": self._dedup_count,
                "stale_data_alerts_count": stale_count,
            }

    def clear_local_for_testing(self) -> None:
        """Clear in-memory state for test isolation."""
        with self._lock:
            self._local_alerts.clear()
            self._dedup_count = 0


alert_repository = AlertRepository()

