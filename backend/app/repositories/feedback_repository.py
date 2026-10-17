"""Feedback and Outcome Database Repository with Local In-Memory Fallback."""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client


class FeedbackRepository:
    """Repository managing farmer feedback, management actions, and ground-truth crop outcomes."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self.client = client or supabase_client
        self._local_feedback: Dict[str, Dict[str, Any]] = {}
        self._local_outcomes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_feedback(
        self,
        farm_id: str,
        user_id: str,
        action_type: str,
        prediction_id: Optional[str] = None,
        notes: Optional[str] = "",
        action_date: Optional[datetime.datetime] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record farmer management action, advisory acknowledgment, or observation note."""
        feedback_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)
        act_date = action_date or now

        record = {
            "id": feedback_id,
            "farm_id": farm_id,
            "user_id": user_id,
            "prediction_id": prediction_id,
            "action_type": action_type,
            "notes": notes or "",
            "action_date": act_date.isoformat(),
            "created_at": now.isoformat(),
        }

        # 1. Attempt live Supabase persistence if table exists
        if self.client.is_live_configured():
            try:
                inserted = self.client.insert("farm_feedback", record, user_token=user_token)
                if inserted and isinstance(inserted, dict):
                    record["id"] = inserted.get("id", feedback_id)
            except SupabaseClientError as e:
                logger.warning("Could not persist feedback to Supabase (using memory): %s", str(e))

        # 2. Store in local state for test isolation
        with self._lock:
            self._local_feedback[record["id"]] = record.copy()

        return record

    def list_feedback(
        self,
        farm_id: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve feedback and action log for a given farm, enforcing tenant isolation."""
        if self.client.is_live_configured():
            try:
                params = {
                    "farm_id": f"eq.{farm_id}",
                    "order": "action_date.desc",
                    "limit": limit,
                    "offset": offset,
                }
                records = self.client.select("farm_feedback", params=params, user_token=user_token)
                if records:
                    return records
            except SupabaseClientError as e:
                logger.debug("Supabase feedback select failed: %s", str(e))

        with self._lock:
            filtered = [
                f for f in self._local_feedback.values()
                if f.get("farm_id") == farm_id
            ]
            # Isolation check: farmers can only see their own feedback unless expert/admin
            if role not in ("expert", "admin") and user_id:
                filtered = [f for f in filtered if f.get("user_id") == user_id]

            filtered.sort(key=lambda x: x.get("action_date", ""), reverse=True)
            return filtered[offset: offset + limit]

    def record_crop_outcome(
        self,
        crop_id: str,
        farm_id: str,
        status: str,
        actual_harvest_date: Optional[datetime.date] = None,
        reported_yield_kg_per_ha: Optional[float] = None,
        outcome_notes: Optional[str] = None,
        is_verified_ground_truth: bool = False,
        is_synthetic: bool = False,
        verification_status: Optional[str] = None,
        verified_by: Optional[str] = None,
        verified_at: Optional[datetime.datetime] = None,
        verification_notes: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record ground-truth outcome on a crop cycle (harvested, failed)."""
        now = datetime.datetime.now(datetime.timezone.utc)

        if verification_status is None:
            if is_synthetic:
                verification_status = "synthetic"
            elif is_verified_ground_truth:
                verification_status = "verified"
            else:
                verification_status = "pending"

        payload = {
            "status": status,
            "actual_harvest_date": actual_harvest_date.isoformat() if actual_harvest_date else None,
            "reported_yield_kg_per_ha": reported_yield_kg_per_ha,
            "outcome_notes": outcome_notes,
            "updated_at": now.isoformat(),
        }

        # If harvested or failed, set is_active to False
        if status in ("harvested", "failed"):
            payload["is_active"] = False

        # 1. Update in Supabase farm_crops table
        if self.client.is_live_configured():
            try:
                self.client.update("farm_crops", payload, {"id": f"eq.{crop_id}"}, user_token=user_token)
            except SupabaseClientError as e:
                logger.warning("Could not update crop outcome in Supabase: %s", str(e))

        outcome_record = {
            "crop_id": crop_id,
            "farm_id": farm_id,
            "status": status,
            "actual_harvest_date": actual_harvest_date.isoformat() if actual_harvest_date else None,
            "reported_yield_kg_per_ha": reported_yield_kg_per_ha,
            "outcome_notes": outcome_notes,
            "verification_status": verification_status,
            "is_verified_ground_truth": is_verified_ground_truth,
            "is_synthetic": is_synthetic,
            "verified_by": verified_by,
            "verified_at": verified_at.isoformat() if verified_at else None,
            "verification_notes": verification_notes,
            "recorded_at": now.isoformat(),
        }

        with self._lock:
            self._local_outcomes[crop_id] = outcome_record.copy()

        from backend.app.repositories.farm_repository import farm_repository
        with farm_repository._lock:
            if crop_id in farm_repository._local_crops:
                farm_repository._local_crops[crop_id]["status"] = status
                farm_repository._local_crops[crop_id]["actual_harvest_date"] = actual_harvest_date.isoformat() if actual_harvest_date else None
                farm_repository._local_crops[crop_id]["reported_yield_kg_per_ha"] = reported_yield_kg_per_ha
                farm_repository._local_crops[crop_id]["outcome_notes"] = outcome_notes
                if status in ("harvested", "failed"):
                    farm_repository._local_crops[crop_id]["is_active"] = False

        return outcome_record

    def verify_crop_outcome(
        self,
        crop_id: str,
        farm_id: str,
        action: str,  # "verify" | "reject"
        verified_by: str,
        verification_notes: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Verify or reject a recorded crop outcome (expert/admin only)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        with self._lock:
            existing = self._local_outcomes.get(crop_id)
            if not existing:
                # Try to load from farm repository if exists
                from backend.app.repositories.farm_repository import farm_repository
                with farm_repository._lock:
                    crop = farm_repository._local_crops.get(crop_id)
                if crop and crop.get("status") in ("harvested", "failed"):
                    existing = {
                        "crop_id": crop_id,
                        "farm_id": farm_id,
                        "status": crop.get("status"),
                        "actual_harvest_date": crop.get("actual_harvest_date"),
                        "reported_yield_kg_per_ha": crop.get("reported_yield_kg_per_ha"),
                        "outcome_notes": crop.get("outcome_notes"),
                        "recorded_at": crop.get("updated_at") or now.isoformat(),
                    }

            if not existing:
                return None

            is_verified = (action == "verify")
            ver_status = "verified" if action == "verify" else "invalid"

            existing.update({
                "is_verified_ground_truth": is_verified,
                "is_synthetic": False,
                "verification_status": ver_status,
                "verified_by": verified_by,
                "verified_at": now.isoformat(),
                "verification_notes": verification_notes,
            })
            self._local_outcomes[crop_id] = existing.copy()
            return existing.copy()

    def get_crop_outcome(self, crop_id: str, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve outcome record for a specific crop cycle."""
        with self._lock:
            if crop_id in self._local_outcomes:
                return self._local_outcomes[crop_id]

        if self.client.is_live_configured():
            try:
                records = self.client.select("farm_crops", {"id": f"eq.{crop_id}"}, user_token=user_token)
                if records and records[0].get("status") in ("harvested", "failed"):
                    r = records[0]
                    return {
                        "crop_id": r.get("id"),
                        "farm_id": r.get("farm_id"),
                        "crop": r.get("crop"),
                        "season": r.get("season"),
                        "status": r.get("status"),
                        "actual_harvest_date": r.get("actual_harvest_date"),
                        "reported_yield_kg_per_ha": r.get("reported_yield_kg_per_ha"),
                        "outcome_notes": r.get("outcome_notes"),
                        "verification_status": "pending",
                        "is_verified_ground_truth": False,
                        "is_synthetic": False,
                        "recorded_at": r.get("updated_at"),
                    }
            except Exception as e:
                logger.debug("Could not select crop outcome from Supabase: %s", str(e))

        return None

    def delete_feedback(
        self,
        feedback_id: str,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> bool:
        """Safely remove a feedback record by ID."""
        deleted = False
        if self.client.is_live_configured():
            try:
                # Attempt to delete from Supabase if table exists
                self.client.update("farm_feedback", {"deleted_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, {"id": f"eq.{feedback_id}"}, user_token=user_token)
                deleted = True
            except Exception as e:
                logger.debug("Supabase feedback delete notice: %s", str(e))

        with self._lock:
            if feedback_id in self._local_feedback:
                del self._local_feedback[feedback_id]
                deleted = True

        return deleted

    def clear_crop_outcome(
        self,
        crop_id: str,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> bool:
        """Safely clear outcome and restore crop to active status."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload = {
            "status": "active",
            "is_active": True,
            "growth_stage": "Vegetative",
            "actual_harvest_date": None,
            "reported_yield_kg_per_ha": None,
            "outcome_notes": None,
            "updated_at": now,
        }

        if self.client.is_live_configured():
            try:
                self.client.update("farm_crops", payload, {"id": f"eq.{crop_id}"}, user_token=user_token)
            except SupabaseClientError as e:
                logger.warning("Could not clear crop outcome in Supabase: %s", str(e))

        with self._lock:
            if crop_id in self._local_outcomes:
                del self._local_outcomes[crop_id]

        from backend.app.repositories.farm_repository import farm_repository
        with farm_repository._lock:
            if crop_id in farm_repository._local_crops:
                farm_repository._local_crops[crop_id]["status"] = "active"
                farm_repository._local_crops[crop_id]["is_active"] = True
                farm_repository._local_crops[crop_id]["actual_harvest_date"] = None
                farm_repository._local_crops[crop_id]["reported_yield_kg_per_ha"] = None
                farm_repository._local_crops[crop_id]["outcome_notes"] = None

        return True

    def count_all_feedback(self) -> int:
        """Count total recorded feedbacks for operational diagnostics."""
        with self._lock:
            return len(self._local_feedback)

    def count_all_outcomes(self) -> int:
        """Count total recorded ground-truth outcomes for diagnostics."""
        with self._lock:
            return len(self._local_outcomes)

    def clear(self) -> None:
        """Clear local stores for test teardown."""
        with self._lock:
            self._local_feedback.clear()
            self._local_outcomes.clear()


feedback_repository = FeedbackRepository()

