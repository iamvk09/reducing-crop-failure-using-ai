"""High-level Satellite & Vegetation Service.

Orchestrates Sentinel-2 vegetation index queries, caching, persistence, and
agronomic vegetation summarization for farmers and experts.
"""

import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.schemas.farm import FarmResponse
from backend.app.services.satellite.base import SatelliteProvider
from backend.app.services.satellite.gee_provider import GoogleEarthEngineProvider
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.schemas import (
    FarmVegetationSummary,
    SatelliteHistoryResponse,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)

if TYPE_CHECKING:
    from backend.app.repositories.satellite_repository import SatelliteRepository


class SatelliteService:
    """Service boundary for satellite observations with caching and persistence."""

    def __init__(
        self,
        provider: Optional[SatelliteProvider] = None,
        repository: Optional["SatelliteRepository"] = None,
        cache_ttl_seconds: Optional[int] = None,
    ):
        self.provider = provider or GoogleEarthEngineProvider()
        self._repository = repository
        self.cache_ttl = cache_ttl_seconds or getattr(settings, "SATELLITE_CACHE_TTL_SECONDS", 86400)

        # In-memory cache: {cache_key: (timestamp, SatelliteObservationResponse)}
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def repository(self) -> "SatelliteRepository":
        if self._repository is None:
            from backend.app.repositories.satellite_repository import satellite_repository
            self._repository = satellite_repository
        return self._repository

    def _get_cache_key(self, farm_id: str, fingerprint: str = "default", suffix: str = "latest") -> str:
        return f"{farm_id}:satellite:{fingerprint}:{suffix}"

    def invalidate_cache_for_farm(self, farm_id: str) -> None:
        """Invalidate all cached satellite observation entries for a specific farm."""
        prefix = f"{farm_id}:"
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]

    def get_latest_observation(
        self,
        farm: Any,
        max_cloud_percent: float = 30.0,
        days_back: int = 45,
        persist: bool = True,
        user_token: Optional[str] = None,
    ) -> SatelliteObservationResponse:
        """Retrieve the latest vegetation observation for a farm."""
        # 1. Create geometry representation prioritizing cadastral boundary over fallback
        geometry = FarmGeometry.from_farm(farm)
        cache_key = self._get_cache_key(farm.id, geometry.fingerprint, "latest")
        now = time.time()

        # 2. Check in-memory cache
        with self._lock:
            if cache_key in self._cache:
                ts, cached_res = self._cache[cache_key]
                if now - ts < self.cache_ttl:
                    cached_copy = cached_res.model_copy(deep=True)
                    cached_copy.is_cached = True
                    return cached_copy

        # 3. Check repository persistence for recent observation (within 3 days)
        # CRITICAL: Verify the persisted record matches the exact geometry fingerprint
        recent_db = self.repository.get_latest_for_farm(farm_id=farm.id, user_token=user_token)
        if recent_db and recent_db.observation_date:
            try:
                obs_d = date.fromisoformat(recent_db.observation_date)
                if (date.today() - obs_d).days <= 3:
                    recent_fp = (recent_db.raw_metadata or {}).get("geometry_fingerprint") or getattr(recent_db, "geometry_fingerprint", None)
                    if recent_fp and recent_fp == geometry.fingerprint:
                        with self._lock:
                            self._cache[cache_key] = (now, recent_db)
                        recent_db_copy = recent_db.model_copy(deep=True)
                        recent_db_copy.is_cached = True
                        return recent_db_copy
                    elif not recent_fp and recent_db.geometry_type == geometry.geometry_type:
                        with self._lock:
                            self._cache[cache_key] = (now, recent_db)
                        recent_db_copy = recent_db.model_copy(deep=True)
                        recent_db_copy.is_cached = True
                        return recent_db_copy
            except Exception:
                pass

        # 4. Query provider
        obs_res = self.provider.get_latest_observation(
            geometry=geometry,
            farm_id=farm.id,
            max_cloud_percent=max_cloud_percent,
            days_back=days_back,
        )

        # 5. Persist if successful observation returned
        if obs_res.success and obs_res.status in (
            SatelliteObservationStatus.REAL_SATELLITE_DATA,
            SatelliteObservationStatus.MOCK_DEVELOPMENT,
        ) and obs_res.ndvi is not None:
            if persist:
                try:
                    self.repository.create(
                        farm_id=farm.id,
                        observation=obs_res,
                        user_token=user_token,
                    )
                except Exception as e:
                    logger.warning("Could not persist satellite observation: %s", str(e))

            with self._lock:
                self._cache[cache_key] = (now, obs_res)

        return obs_res

    def get_historical_observations(
        self,
        farm: Any,
        days_back: int = 90,
        max_cloud_percent: float = 40.0,
        limit: int = 12,
        user_token: Optional[str] = None,
    ) -> SatelliteHistoryResponse:
        """Retrieve historical vegetation observations for a farm plot."""
        # 1. Retrieve from database first
        db_records = self.repository.list_for_farm(
            farm_id=farm.id,
            limit=limit,
            offset=0,
            user_token=user_token,
        )

        if db_records:
            return SatelliteHistoryResponse(
                farm_id=farm.id,
                total_count=len(db_records),
                observations=db_records,
            )

        # 2. Query provider across date window if no stored records
        end_d = date.today().isoformat()
        start_d = (date.today() - timedelta(days=days_back)).isoformat()

        geometry = FarmGeometry.from_farm(farm)

        provider_records = self.provider.get_historical_observations(
            geometry=geometry,
            start_date=start_d,
            end_date=end_d,
            farm_id=farm.id,
            max_cloud_percent=max_cloud_percent,
            limit=limit,
        )

        # Persist newly fetched historical records
        for rec in provider_records:
            if rec.success and rec.ndvi is not None:
                try:
                    self.repository.create(farm_id=farm.id, observation=rec, user_token=user_token)
                except Exception:
                    pass

        return SatelliteHistoryResponse(
            farm_id=farm.id,
            total_count=len(provider_records),
            observations=provider_records,
        )

    def get_vegetation_summary(
        self,
        farm: Any,
        user_token: Optional[str] = None,
    ) -> FarmVegetationSummary:
        """Generate a simplified, farmer-friendly vegetation health summary."""
        obs = self.get_latest_observation(farm=farm, user_token=user_token)

        if not obs.success or obs.ndvi is None or obs.ndvi.mean is None:
            if obs.status == SatelliteObservationStatus.SATELLITE_NOT_CONFIGURED:
                return FarmVegetationSummary(
                    farm_id=farm.id,
                    has_observation=False,
                    status=obs.status,
                    vegetation_health="Unconfigured",
                    message="Satellite connection is currently pending system configuration.",
                )
            return FarmVegetationSummary(
                farm_id=farm.id,
                has_observation=False,
                status=obs.status,
                vegetation_health="Pending Observation",
                message="No recent cloud-free satellite imagery available for this location.",
            )

        mean_ndvi = obs.ndvi.mean

        # Farmer friendly categorization based on vegetative canopy density
        if mean_ndvi >= 0.60:
            health_label = "Healthy"
            msg = "Crop canopy is dense and actively photosynthesizing."
        elif mean_ndvi >= 0.40:
            health_label = "Moderate"
            msg = "Moderate vegetation coverage. Maintain regular irrigation and crop scouting."
        elif mean_ndvi >= 0.20:
            health_label = "Low Greenness"
            msg = "Sparse vegetation coverage detected. Check for emergence delay, water stress, or gaps."
        else:
            health_label = "Very Low / Bare Soil"
            msg = "Very low surface greenness observed. Typical of early sowing or fallow ground."

        return FarmVegetationSummary(
            farm_id=farm.id,
            has_observation=True,
            status=obs.status,
            vegetation_health=health_label,
            latest_ndvi=mean_ndvi,
            observation_date=obs.observation_date,
            valid_pixel_percent=obs.ndvi.valid_pixel_percent if obs.ndvi else None,
            scene_cloud_percent=obs.ndvi.scene_cloud_percent if obs.ndvi else None,
            data_source=f"{obs.satellite} ({obs.provider})",
            quality_label=obs.quality_status,
            message=msg,
        )

    def clear_cache(self) -> None:
        """Clear memory cache for test isolation."""
        with self._lock:
            self._cache.clear()


satellite_service = SatelliteService()
