"""Satellite and Vegetation Observations Database Repository.

Provides data-access operations for persisting and querying farm-level
Sentinel-2 vegetation observations in Supabase PostgreSQL:
- Inserts satellite observation records with NDVI statistics and quality metrics
- Queries historical observations with pagination and tenant isolation
- Fallback in-memory driver for offline testing environments
"""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)


class SatelliteRepository:
    """Repository managing satellite observation persistence in Supabase PostgreSQL."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self.client = client or supabase_client
        self._local_observations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_observation_by_date(
        self,
        farm_id: str,
        observation_date: str,
        user_token: Optional[str] = None,
    ) -> Optional[SatelliteObservationResponse]:
        """Retrieve observation for a specific farm and date."""
        if self.client.is_live_configured():
            params = {
                "farm_id": f"eq.{farm_id}",
                "observation_date": f"eq.{observation_date}",
                "limit": "1",
            }
            try:
                records = self.client.select("satellite_observations", params=params, user_token=None)
                if records:
                    return self._to_response(records[0])
            except SupabaseClientError as e:
                logger.warning("Supabase get observation by date failed: %s", str(e))

        with self._lock:
            for obs in self._local_observations.values():
                if obs.get("farm_id") == farm_id and obs.get("observation_date") == observation_date:
                    return self._to_response(obs)
        return None

    def create(
        self,
        farm_id: str,
        observation: SatelliteObservationResponse,
        user_token: Optional[str] = None,
    ) -> SatelliteObservationResponse:
        """Persist or update a satellite observation record for a farm in Supabase PostgreSQL.

        - If an observation exists for (farm_id, observation_date) with matching geometry fingerprint,
          reuse it idempotently without generating new rows.
        - If an observation exists with a differing geometry (e.g. Polygon A -> Polygon B or Point -> Polygon),
          update the existing single row in-place with newly computed metrics.
        - Guarantees exactly one database row per farm and date under all conditions.
        """
        obs_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)
        obs_date = observation.observation_date or now.strftime("%Y-%m-%d")

        ndvi_data = observation.ndvi or NDVIStatistics()

        # Preserve complete metadata payload including geometry fingerprint
        raw_meta = dict(observation.raw_metadata or {})
        if observation.geometry_fingerprint and "geometry_fingerprint" not in raw_meta:
            raw_meta["geometry_fingerprint"] = observation.geometry_fingerprint
        if ndvi_data.total_pixels is not None and "total_pixels" not in raw_meta:
            raw_meta["total_pixels"] = ndvi_data.total_pixels
        if ndvi_data.valid_pixels is not None and "valid_pixels" not in raw_meta:
            raw_meta["valid_pixels"] = ndvi_data.valid_pixels
        if ndvi_data.scene_cloud_percent is not None and "scene_cloud_percent" not in raw_meta:
            raw_meta["scene_cloud_percent"] = ndvi_data.scene_cloud_percent

        cloud_val = ndvi_data.scene_cloud_percent if ndvi_data.scene_cloud_percent is not None else ndvi_data.cloud_percent

        record_dict = {
            "id": obs_id,
            "farm_id": farm_id,
            "observation_date": obs_date,
            "ndvi_mean": ndvi_data.mean,
            "ndvi_median": ndvi_data.median,
            "ndvi_min": ndvi_data.min,
            "ndvi_max": ndvi_data.max,
            "ndvi_std": ndvi_data.std,
            "valid_pixel_percent": ndvi_data.valid_pixel_percent,
            "cloud_percent": cloud_val,
            "source": observation.source,
            "provider": observation.provider,
            "satellite": observation.satellite,
            "product": observation.product,
            "geometry_type": observation.geometry_type,
            "processing_status": "COMPLETED" if observation.success else "FAILED",
            "quality_status": observation.quality_status,
            "raw_metadata": raw_meta,
            "created_at": now.isoformat(),
        }

        # 1. Check existing observation for same farm and date
        existing = self.get_observation_by_date(farm_id=farm_id, observation_date=obs_date, user_token=user_token)

        if existing:
            existing_fp = (existing.raw_metadata or {}).get("geometry_fingerprint") or getattr(existing, "geometry_fingerprint", None)
            new_fp = raw_meta.get("geometry_fingerprint") or getattr(observation, "geometry_fingerprint", None)

            # Check if geometry identity matches
            if existing_fp and new_fp:
                same_geometry = (existing_fp == new_fp)
            else:
                same_geometry = (existing.geometry_type == observation.geometry_type)

            if same_geometry:
                logger.info(
                    "DIAGNOSTIC_SATELLITE_PERSISTENCE [op=REUSE_EXISTING, farm_id=%s, obs_date=%s, fp=%s]",
                    farm_id,
                    obs_date,
                    existing_fp or existing.geometry_type,
                )
                return existing

            # Case B: Geometry has changed (Polygon A -> Polygon B, Polygon -> Point, etc.) -> Update existing single row
            logger.info(
                "DIAGNOSTIC_SATELLITE_PERSISTENCE [op=UPDATE_GEOMETRY, farm_id=%s, obs_date=%s, old_fp=%s, new_fp=%s]",
                farm_id,
                obs_date,
                existing_fp or existing.geometry_type,
                new_fp or observation.geometry_type,
            )
            update_payload = {k: v for k, v in record_dict.items() if k not in ("id", "created_at")}
            persisted = False
            persistence_error = None

            if self.client.is_live_configured():
                try:
                    updated_records = self.client.update(
                        "satellite_observations",
                        data=update_payload,
                        params={"farm_id": f"eq.{farm_id}", "observation_date": f"eq.{obs_date}"},
                        user_token=None,
                    )
                    if updated_records:
                        record_dict["id"] = updated_records[0].get("id", record_dict["id"])
                    persisted = True
                except SupabaseClientError as e:
                    persistence_error = str(e)
                    logger.error("Failed to update satellite observation for geometry change in Supabase: %s", str(e))
            else:
                persisted = True

            with self._lock:
                for k, v in list(self._local_observations.items()):
                    if v.get("farm_id") == farm_id and v.get("observation_date") == obs_date:
                        record_dict["id"] = k
                        self._local_observations[k] = record_dict.copy()
                        break

            record_dict["raw_metadata"]["persisted"] = persisted
            if persistence_error:
                record_dict["raw_metadata"]["persistence_error"] = "Database update failed"

            return self._to_response(record_dict)

        # 2. No existing record: INSERT new row
        persisted = False
        persistence_error = None

        if self.client.is_live_configured():
            try:
                logger.info(
                    "DIAGNOSTIC_SATELLITE_PERSISTENCE [op=INSERT, farm_id=%s, obs_date=%s, auth_mode=server, target_table=satellite_observations]",
                    farm_id,
                    obs_date,
                )
                res = self.client.insert("satellite_observations", data=record_dict, user_token=None)
                obs_id = res.get("id", obs_id)
                persisted = True
                logger.info(
                    "DIAGNOSTIC_SATELLITE_PERSISTENCE [op=INSERT_SUCCESS, farm_id=%s, obs_id=%s, persisted=True]",
                    farm_id,
                    obs_id,
                )
            except SupabaseClientError as e:
                # Handle unique constraint race condition gracefully
                err_str = str(e).lower()
                if "23505" in str(e) or "duplicate" in err_str or "conflict" in err_str or "uq_satellite_obs_farm_date" in err_str:
                    logger.warning(
                        "Satellite persistence conflict [farm_id=%s, obs_date=%s]. Handling race condition...",
                        farm_id,
                        obs_date,
                    )
                    race_existing = self.get_observation_by_date(farm_id=farm_id, observation_date=obs_date, user_token=user_token)
                    if race_existing:
                        race_fp = (race_existing.raw_metadata or {}).get("geometry_fingerprint") or getattr(race_existing, "geometry_fingerprint", None)
                        new_fp = raw_meta.get("geometry_fingerprint") or getattr(observation, "geometry_fingerprint", None)
                        same_geo = (race_fp == new_fp) if (race_fp and new_fp) else (race_existing.geometry_type == observation.geometry_type)
                        if same_geo:
                            return race_existing
                        else:
                            update_payload = {k: v for k, v in record_dict.items() if k not in ("id", "created_at")}
                            self.client.update(
                                "satellite_observations",
                                data=update_payload,
                                params={"farm_id": f"eq.{farm_id}", "observation_date": f"eq.{obs_date}"},
                                user_token=None,
                            )
                            return self._to_response(record_dict)

                persistence_error = str(e)
                logger.error(
                    "DIAGNOSTIC_SATELLITE_PERSISTENCE [op=INSERT_FAILED, farm_id=%s, status_code=%s, error=%s, persisted=False]",
                    farm_id,
                    getattr(e, "status_code", None),
                    str(e),
                )
        else:
            # Local offline/testing environment (APP_ENV="testing")
            with self._lock:
                self._local_observations[obs_id] = record_dict.copy()
            persisted = True

        if self.client.is_live_configured() and persisted:
            with self._lock:
                self._local_observations[obs_id] = record_dict.copy()

        record_dict["raw_metadata"]["persisted"] = persisted
        if persistence_error:
            record_dict["raw_metadata"]["persistence_error"] = "Database write failed"

        return self._to_response(record_dict)

    def list_for_farm(
        self,
        farm_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[SatelliteObservationResponse]:
        """Retrieve historical satellite observations for a farm plot."""
        # 1. Supabase query if configured
        if self.client.is_live_configured():
            params = {
                "farm_id": f"eq.{farm_id}",
                "order": "observation_date.desc",
                "limit": str(limit),
                "offset": str(offset),
            }
            try:
                # Deterministic server-side query with service client
                records = self.client.select("satellite_observations", params=params, user_token=None)
                if records:
                    return [self._to_response(r) for r in records]
            except SupabaseClientError as e:
                logger.warning("Supabase select satellite observations failed (%s): %s", type(e).__name__, str(e))

        # 2. Local fallback memory store
        with self._lock:
            items = [o for o in self._local_observations.values() if o.get("farm_id") == farm_id]

        items.sort(key=lambda x: x.get("observation_date", ""), reverse=True)
        paginated = items[offset : offset + limit]

        return [self._to_response(r) for r in paginated]

    def get_latest_for_farm(
        self,
        farm_id: str,
        user_token: Optional[str] = None,
    ) -> Optional[SatelliteObservationResponse]:
        """Retrieve the most recent satellite observation for a farm."""
        records = self.list_for_farm(farm_id=farm_id, limit=1, offset=0, user_token=user_token)
        return records[0] if records else None

    def _to_response(self, r: Dict[str, Any]) -> SatelliteObservationResponse:
        """Convert database record to normalized response model."""
        ndvi_stats = None
        if r.get("ndvi_mean") is not None:
            raw_meta = r.get("raw_metadata") or {}
            c_pct = float(r["cloud_percent"]) if r.get("cloud_percent") is not None else None
            ndvi_stats = NDVIStatistics(
                mean=float(r["ndvi_mean"]) if r.get("ndvi_mean") is not None else None,
                median=float(r["ndvi_median"]) if r.get("ndvi_median") is not None else None,
                min=float(r["ndvi_min"]) if r.get("ndvi_min") is not None else None,
                max=float(r["ndvi_max"]) if r.get("ndvi_max") is not None else None,
                std=float(r["ndvi_std"]) if r.get("ndvi_std") is not None else None,
                valid_pixel_percent=float(r["valid_pixel_percent"]) if r.get("valid_pixel_percent") is not None else None,
                scene_cloud_percent=float(raw_meta.get("scene_cloud_percent", c_pct)) if (raw_meta.get("scene_cloud_percent") is not None or c_pct is not None) else None,
                cloud_percent=c_pct,
                total_pixels=raw_meta.get("total_pixels"),
                valid_pixels=raw_meta.get("valid_pixels"),
            )

        status = SatelliteObservationStatus.REAL_SATELLITE_DATA
        if r.get("source") == "mock":
            status = SatelliteObservationStatus.MOCK_DEVELOPMENT

        return SatelliteObservationResponse(
            success=True,
            status=status,
            farm_id=r.get("farm_id"),
            observation_date=r.get("observation_date"),
            ndvi=ndvi_stats,
            source=r.get("source", "Sentinel-2 / GEE"),
            provider=r.get("provider", "GoogleEarthEngine"),
            satellite=r.get("satellite", "Sentinel-2"),
            product=r.get("product", "COPERNICUS/S2_SR_HARMONIZED"),
            geometry_type=r.get("geometry_type", "buffered_point"),
            geometry_fingerprint=raw_meta.get("geometry_fingerprint"),
            quality_status=r.get("quality_status", "GOOD"),
            raw_metadata=raw_meta,
            created_at=r.get("created_at", ""),
        )

    def clear(self) -> None:
        """Clear local storage for test fixtures."""
        with self._lock:
            self._local_observations.clear()


satellite_repository = SatelliteRepository()
