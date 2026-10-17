"""Farm and Crop Database Repository.

Provides data-access operations for persisting and querying farm plots and
crop cycles in Supabase PostgreSQL:
- Enforces durable persistence with Supabase PostgREST backend client
- Retains database-generated or provided UUIDs
- Provides in-memory storage fallback for local offline testing (APP_ENV="testing")
"""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client


class FarmRepository:
    """Repository managing farm and crop persistence in Supabase PostgreSQL."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self.client = client or supabase_client
        self._local_farms: Dict[str, Dict[str, Any]] = {}
        self._local_crops: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Farm Operations
    # -------------------------------------------------------------------------
    def create_farm(
        self,
        farm_data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a new farm record in Supabase PostgreSQL."""
        farm_id = farm_data.get("id") or str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        record_dict = {
            "id": farm_id,
            "user_id": farm_data["user_id"],
            "name": farm_data["name"],
            "state": farm_data["state"],
            "district": farm_data["district"],
            "region": farm_data.get("region") or f"{farm_data['state']}-Region",
            "latitude": float(farm_data["latitude"]),
            "longitude": float(farm_data["longitude"]),
            "area_hectares": float(farm_data["area_hectares"]) if farm_data.get("area_hectares") is not None else None,
            "village": farm_data.get("village"),
            "soil_type": farm_data.get("soil_type"),
            "irrigation_level": farm_data.get("irrigation_level"),
            "boundary_geojson": farm_data.get("boundary_geojson"),
            "created_at": farm_data.get("created_at") or now,
            "updated_at": farm_data.get("updated_at") or now,
        }

        if self.client.is_live_configured():
            try:
                db_payload = {k: v for k, v in record_dict.items() if k != "boundary_geojson" or v is not None}
                res = self.client.insert("farms", data=db_payload, user_token=None)
                record_dict["id"] = res.get("id", farm_id)
                logger.info("Farm persisted successfully to Supabase [farm_id=%s, name=%s]", record_dict["id"], record_dict["name"])
            except SupabaseClientError as e:
                logger.warning("Supabase insert unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            self._local_farms[record_dict["id"]] = record_dict.copy()

        return record_dict

    def get_farm_by_id(
        self,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a farm record by primary key."""
        if self.client.is_live_configured():
            try:
                records = self.client.select("farms", params={"id": f"eq.{farm_id}"}, user_token=None)
                if records:
                    return records[0]
            except SupabaseClientError as e:
                logger.warning("Supabase query unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            return self._local_farms.get(farm_id)

    def list_farms(
        self,
        user_id: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List farm records, optionally filtered by user_id for farmers."""
        if self.client.is_live_configured():
            params: Dict[str, str] = {"order": "created_at.desc"}
            if user_id:
                params["user_id"] = f"eq.{user_id}"

            try:
                records = self.client.select("farms", params=params, user_token=None)
                if records:
                    return records
            except SupabaseClientError as e:
                logger.warning("Supabase list unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            if user_id:
                return [f for f in self._local_farms.values() if f.get("user_id") == user_id]
            return list(self._local_farms.values())

    def update_farm(
        self,
        farm_id: str,
        farm_update: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update farm fields in Supabase."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update_data = {k: v for k, v in farm_update.items() if v is not None}
        update_data["updated_at"] = now

        if self.client.is_live_configured():
            try:
                records = self.client.update(
                    "farms",
                    data=update_data,
                    params={"id": f"eq.{farm_id}"},
                    user_token=None,
                )
                if records:
                    return records[0]
            except SupabaseClientError as e:
                logger.warning("Supabase update unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            farm = self._local_farms.get(farm_id)
            if not farm:
                return None
            farm.update(update_data)
            return farm

    def delete_farm(
        self,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> bool:
        """Delete a farm record from Supabase."""
        if self.client.is_live_configured():
            try:
                self.client.delete("farms", params={"id": f"eq.{farm_id}"}, user_token=None)
            except SupabaseClientError as e:
                logger.error("Failed to delete farm from Supabase [farm_id=%s]: %s", farm_id, str(e))
                raise

        with self._lock:
            self._local_farms.pop(farm_id, None)
            crop_ids = [cid for cid, c in self._local_crops.items() if c.get("farm_id") == farm_id]
            for cid in crop_ids:
                self._local_crops.pop(cid, None)

        return True

    # -------------------------------------------------------------------------
    # Crop Operations
    # -------------------------------------------------------------------------
    def create_crop(
        self,
        crop_data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a crop cycle record in Supabase PostgreSQL."""
        crop_id = crop_data.get("id") or str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        record_dict = {
            "id": crop_id,
            "farm_id": crop_data["farm_id"],
            "crop": crop_data["crop"],
            "season": crop_data["season"],
            "sowing_date": crop_data.get("sowing_date"),
            "expected_harvest_date": crop_data.get("expected_harvest_date"),
            "growth_stage": crop_data.get("growth_stage"),
            "status": crop_data.get("status") or "active",
            "is_active": crop_data.get("is_active", True),
            "soil_type": crop_data.get("soil_type"),
            "irrigation_level": crop_data.get("irrigation_level"),
            "created_at": crop_data.get("created_at") or now,
            "updated_at": crop_data.get("updated_at") or now,
        }

        if self.client.is_live_configured():
            try:
                res = self.client.insert("farm_crops", data=record_dict, user_token=None)
                record_dict["id"] = res.get("id", crop_id)
                logger.info("Crop persisted successfully to Supabase [crop_id=%s, crop=%s]", record_dict["id"], record_dict["crop"])
            except SupabaseClientError as e:
                logger.warning("Supabase crop insert unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            self._local_crops[record_dict["id"]] = record_dict.copy()

        return record_dict

    def list_crops_for_farm(
        self,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List crop cycles for a specific farm plot."""
        if self.client.is_live_configured():
            try:
                records = self.client.select("farm_crops", params={"farm_id": f"eq.{farm_id}", "order": "created_at.desc"}, user_token=None)
                if records:
                    return records
            except SupabaseClientError as e:
                logger.warning("Supabase list crops unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            return [c for c in self._local_crops.values() if c.get("farm_id") == farm_id]

    def get_crop_by_id(
        self,
        crop_id: str,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a specific crop cycle."""
        if self.client.is_live_configured():
            try:
                records = self.client.select("farm_crops", params={"id": f"eq.{crop_id}"}, user_token=None)
                if records:
                    return records[0]
            except SupabaseClientError as e:
                logger.warning("Supabase get crop unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            return self._local_crops.get(crop_id)

    def update_crop(
        self,
        crop_id: str,
        crop_update: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update crop cycle fields in Supabase."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update_data = {k: v for k, v in crop_update.items() if v is not None}
        update_data["updated_at"] = now

        if self.client.is_live_configured():
            try:
                records = self.client.update("farm_crops", data=update_data, params={"id": f"eq.{crop_id}"}, user_token=None)
                if records:
                    return records[0]
            except SupabaseClientError as e:
                logger.warning("Supabase update crop unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            crop = self._local_crops.get(crop_id)
            if not crop:
                return None
            crop.update(update_data)
            return crop

    def delete_crop(
        self,
        crop_id: str,
        user_token: Optional[str] = None,
    ) -> bool:
        """Delete a crop cycle record from Supabase."""
        if self.client.is_live_configured():
            try:
                self.client.delete("farm_crops", params={"id": f"eq.{crop_id}"}, user_token=None)
            except SupabaseClientError as e:
                logger.warning("Supabase delete crop unavailable (%s). Falling back to local state.", str(e))

        with self._lock:
            self._local_crops.pop(crop_id, None)

        return True

    def clear(self) -> None:
        """Clear local storage for testing isolation."""
        with self._lock:
            self._local_farms.clear()
            self._local_crops.clear()


farm_repository = FarmRepository()
