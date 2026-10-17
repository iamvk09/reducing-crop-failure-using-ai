"""Farm and crop domain service with multi-tenant isolation and ownership checks."""

import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel

from backend.app.core.logging import logger
from backend.app.core.security import AuthenticatedUser
from backend.app.core.supabase import SupabaseClientError
from backend.app.repositories.farm_repository import FarmRepository, farm_repository
from backend.app.schemas.farm import (
    CropCreateRequest,
    CropResponse,
    CropUpdateRequest,
    FarmCreateRequest,
    FarmResponse,
    FarmUpdateRequest,
)
from backend.app.services.audit_service import audit_service


class FarmService:
    """Service managing farms and crops with strict tenant isolation and durable persistence."""

    def __init__(self, repository: Optional[FarmRepository] = None) -> None:
        self.repository = repository or farm_repository

    # -------------------------------------------------------------------------
    # Farm Management
    # -------------------------------------------------------------------------
    def create_farm(
        self,
        farm_in: FarmCreateRequest,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> FarmResponse:
        """Register a new farm plot owned by the authenticated user in durable storage."""
        farm_id = str(uuid.uuid4())
        region = farm_in.region or f"{farm_in.state}-Region"

        farm_data = {
            "id": farm_id,
            "user_id": user.id,
            "name": farm_in.name,
            "state": farm_in.state,
            "district": farm_in.district,
            "region": region,
            "latitude": farm_in.latitude,
            "longitude": farm_in.longitude,
            "area_hectares": farm_in.area_hectares,
            "village": farm_in.village,
            "soil_type": farm_in.soil_type,
            "irrigation_level": farm_in.irrigation_level,
            "boundary_geojson": farm_in.boundary_geojson,
        }

        try:
            persisted_farm = self.repository.create_farm(farm_data=farm_data, user_token=user_token)
        except SupabaseClientError as e:
            logger.error("Failed to persist farm [name=%s, user_id=%s]: %s", farm_in.name, user.id, str(e))
            raise

        audit_service.log_action(
            action="farm:create",
            resource_type="farm",
            resource_id=persisted_farm["id"],
            user_id=user.id,
            metadata={"name": persisted_farm["name"], "state": persisted_farm["state"], "district": persisted_farm["district"]},
            ip_address=ip_address,
        )

        return self._to_farm_response(persisted_farm)

    def list_farms(
        self,
        user: AuthenticatedUser,
        user_token: Optional[str] = None,
    ) -> List[FarmResponse]:
        """List farms accessible to the user from durable storage.

        - Farmers see only their own farms.
        - Experts and Admins can see all registered farms.
        """
        user_id_filter = None if user.role in ["expert", "admin"] else user.id
        farms = self.repository.list_farms(user_id=user_id_filter, user_token=user_token)
        return [self._to_farm_response(f) for f in farms]

    def get_farm(
        self,
        farm_id: str,
        user: AuthenticatedUser,
        user_token: Optional[str] = None,
    ) -> Optional[FarmResponse]:
        """Retrieve a specific farm if user has access."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return None

        # Isolation check: Farmer can access only own farm
        if user.role not in ["expert", "admin"] and farm.get("user_id") != user.id:
            return None

        return self._to_farm_response(farm)

    def update_farm(
        self,
        farm_id: str,
        farm_update: FarmUpdateRequest,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[FarmResponse]:
        """Update farm details if user is the owner or an admin."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return None

        # Ownership check
        if user.role != "admin" and farm.get("user_id") != user.id:
            return None

        update_data = farm_update.model_dump(exclude_unset=True)
        updated_farm = self.repository.update_farm(farm_id=farm_id, farm_update=update_data, user_token=user_token)
        if not updated_farm:
            return None

        # Invalidate any in-memory satellite cache for this farm
        try:
            from backend.app.services.satellite.service import satellite_service
            satellite_service.invalidate_cache_for_farm(farm_id)
        except Exception:
            pass

        audit_service.log_action(
            action="farm:update",
            resource_type="farm",
            resource_id=farm_id,
            user_id=user.id,
            metadata=update_data,
            ip_address=ip_address,
        )

        return self._to_farm_response(updated_farm)

    def delete_farm(
        self,
        farm_id: str,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> bool:
        """Delete a farm and its associated crops if user is the owner or an admin."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return False

        # Ownership check
        if user.role != "admin" and farm.get("user_id") != user.id:
            return False

        self.repository.delete_farm(farm_id=farm_id, user_token=user_token)

        # Invalidate any in-memory satellite cache for this farm
        try:
            from backend.app.services.satellite.service import satellite_service
            satellite_service.invalidate_cache_for_farm(farm_id)
        except Exception:
            pass

        audit_service.log_action(
            action="farm:delete",
            resource_type="farm",
            resource_id=farm_id,
            user_id=user.id,
            ip_address=ip_address,
        )

        return True

    # -------------------------------------------------------------------------
    # Crop Cycle Management
    # -------------------------------------------------------------------------
    def register_crop(
        self,
        farm_id: str,
        crop_in: CropCreateRequest,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[CropResponse]:
        """Register a crop cycle for a farm owned by the user."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return None

        # Ownership check: Only farm owner or admin can register crops
        if user.role != "admin" and farm.get("user_id") != user.id:
            return None

        crop_id = str(uuid.uuid4())
        crop_data = {
            "id": crop_id,
            "farm_id": farm_id,
            "crop": crop_in.crop,
            "season": crop_in.season,
            "soil_type": crop_in.soil_type or farm.get("soil_type"),
            "irrigation_level": crop_in.irrigation_level or farm.get("irrigation_level"),
            "sowing_date": crop_in.sowing_date.isoformat() if crop_in.sowing_date else None,
            "expected_harvest_date": crop_in.expected_harvest_date.isoformat() if crop_in.expected_harvest_date else None,
            "growth_stage": crop_in.growth_stage,
            "status": crop_in.status or "active",
            "is_active": True,
        }

        persisted_crop = self.repository.create_crop(crop_data=crop_data, user_token=user_token)

        audit_service.log_action(
            action="crop:create",
            resource_type="crop",
            resource_id=crop_id,
            user_id=user.id,
            metadata={"farm_id": farm_id, "crop": crop_in.crop, "season": crop_in.season},
            ip_address=ip_address,
        )

        return self._to_crop_response(persisted_crop)

    def list_crops_for_farm(
        self,
        farm_id: str,
        user: AuthenticatedUser,
        user_token: Optional[str] = None,
    ) -> Optional[List[CropResponse]]:
        """List all crops for a given farm if user has access to that farm."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return None

        if user.role not in ["expert", "admin"] and farm.get("user_id") != user.id:
            return None

        crops = self.repository.list_crops_for_farm(farm_id=farm_id, user_token=user_token)
        return [self._to_crop_response(c) for c in crops]

    def update_crop(
        self,
        farm_id: str,
        crop_id: str,
        crop_update: CropUpdateRequest,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[CropResponse]:
        """Update a crop cycle if user owns the farm."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return None

        if user.role != "admin" and farm.get("user_id") != user.id:
            return None

        crop = self.repository.get_crop_by_id(crop_id=crop_id, user_token=user_token)
        if not crop or crop.get("farm_id") != farm_id:
            return None

        update_data = crop_update.model_dump(exclude_unset=True)
        if "sowing_date" in update_data and update_data["sowing_date"] is not None:
            update_data["sowing_date"] = update_data["sowing_date"].isoformat()
        if "expected_harvest_date" in update_data and update_data["expected_harvest_date"] is not None:
            update_data["expected_harvest_date"] = update_data["expected_harvest_date"].isoformat()

        updated_crop = self.repository.update_crop(crop_id=crop_id, crop_update=update_data, user_token=user_token)
        if not updated_crop:
            return None

        audit_service.log_action(
            action="crop:update",
            resource_type="crop",
            resource_id=crop_id,
            user_id=user.id,
            metadata={"farm_id": farm_id, **crop_update.model_dump(exclude_unset=True)},
            ip_address=ip_address,
        )

        return self._to_crop_response(updated_crop)

    def delete_crop(
        self,
        farm_id: str,
        crop_id: str,
        user: AuthenticatedUser,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> bool:
        """Delete a crop cycle if user owns the farm."""
        farm = self.repository.get_farm_by_id(farm_id=farm_id, user_token=user_token)
        if not farm:
            return False

        if user.role != "admin" and farm.get("user_id") != user.id:
            return False

        crop = self.repository.get_crop_by_id(crop_id=crop_id, user_token=user_token)
        if not crop or crop.get("farm_id") != farm_id:
            return False

        self.repository.delete_crop(crop_id=crop_id, user_token=user_token)

        audit_service.log_action(
            action="crop:delete",
            resource_type="crop",
            resource_id=crop_id,
            user_id=user.id,
            metadata={"farm_id": farm_id},
            ip_address=ip_address,
        )

        return True

    def clear(self) -> None:
        """Clear all in-memory farm and crop data (used for tests)."""
        self.repository.clear()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def _to_farm_response(farm: Dict[str, Any]) -> FarmResponse:
        created_at = farm.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.datetime.fromisoformat(created_at)
            except Exception:
                created_at = datetime.datetime.now(datetime.timezone.utc)
        elif created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc)

        updated_at = farm.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = datetime.datetime.now(datetime.timezone.utc)
        elif updated_at is None:
            updated_at = datetime.datetime.now(datetime.timezone.utc)

        return FarmResponse(
            id=str(farm["id"]),
            user_id=str(farm["user_id"]),
            name=farm["name"],
            state=farm["state"],
            district=farm["district"],
            region=farm.get("region"),
            latitude=float(farm["latitude"]),
            longitude=float(farm["longitude"]),
            area_hectares=float(farm["area_hectares"]) if farm.get("area_hectares") is not None else None,
            village=farm.get("village"),
            soil_type=farm.get("soil_type"),
            irrigation_level=farm.get("irrigation_level"),
            boundary_geojson=farm.get("boundary_geojson"),
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _to_crop_response(crop: Dict[str, Any]) -> CropResponse:
        created_at = crop.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.datetime.fromisoformat(created_at)
            except Exception:
                created_at = datetime.datetime.now(datetime.timezone.utc)
        elif created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc)

        updated_at = crop.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = datetime.datetime.now(datetime.timezone.utc)
        elif updated_at is None:
            updated_at = datetime.datetime.now(datetime.timezone.utc)

        sowing_date = crop.get("sowing_date")
        if isinstance(sowing_date, str):
            try:
                sowing_date = datetime.date.fromisoformat(sowing_date)
            except Exception:
                sowing_date = None

        expected_harvest_date = crop.get("expected_harvest_date")
        if isinstance(expected_harvest_date, str):
            try:
                expected_harvest_date = datetime.date.fromisoformat(expected_harvest_date)
            except Exception:
                expected_harvest_date = None

        return CropResponse(
            id=str(crop["id"]),
            farm_id=str(crop["farm_id"]),
            crop=crop["crop"],
            season=crop["season"],
            soil_type=crop.get("soil_type"),
            irrigation_level=crop.get("irrigation_level"),
            sowing_date=sowing_date,
            expected_harvest_date=expected_harvest_date,
            growth_stage=crop.get("growth_stage"),
            status=crop.get("status", "active"),
            is_active=bool(crop.get("is_active", True)),
            created_at=created_at,
            updated_at=updated_at,
        )


farm_service = FarmService()
