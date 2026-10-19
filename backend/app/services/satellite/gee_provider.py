"""Google Earth Engine Sentinel-2 Surface Reflectance Provider.

Implements farm-level NDVI extraction using the harmonized Sentinel-2 Level-2A
Surface Reflectance collection ('COPERNICUS/S2_SR_HARMONIZED').

Key Features:
- Cloud/shadow masking via Sentinel-2 SCL / QA bands or Cloud Score+
- Spatial reduction executed on GEE cloud infrastructure (zero raster download to FastAPI)
- Handles unconfigured / offline development state safely without crashes
- Strict protection of private keys, secrets, and credentials (never logged)
"""

import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.satellite.base import SatelliteProvider
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)


class GoogleEarthEngineProvider(SatelliteProvider):
    """Satellite provider querying Sentinel-2 Level-2A via Google Earth Engine API."""

    COLLECTION_ID = "COPERNICUS/S2_SR_HARMONIZED"

    def __init__(
        self,
        project_id: Optional[str] = None,
        service_account: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        self.project_id = project_id if project_id is not None else (getattr(settings, "GEE_PROJECT_ID", None) or os.getenv("GEE_PROJECT_ID"))
        self.service_account = service_account if service_account is not None else (getattr(settings, "GEE_SERVICE_ACCOUNT_EMAIL", None) or os.getenv("GEE_SERVICE_ACCOUNT_EMAIL"))
        self.private_key = private_key if private_key is not None else (getattr(settings, "GEE_PRIVATE_KEY", None) or os.getenv("GEE_PRIVATE_KEY"))

        self._ee = None
        self._is_initialized = False
        self._init_error_type: Optional[str] = None  # "UNCONFIGURED" | "AUTH_FAILED" | "INIT_FAILED"
        self._init_error: Optional[str] = None
        self._last_init_attempt_time: float = 0.0
        self._retry_cooldown_seconds: float = 60.0

    def _initialize_ee_if_needed(self) -> bool:
        """Lazy singleton initialization of Earth Engine client with safe retry throttling."""
        if self._is_initialized and self._ee is not None:
            return True

        project_id = self.project_id if self.project_id is not None else (getattr(settings, "GEE_PROJECT_ID", None) or os.getenv("GEE_PROJECT_ID"))
        service_account = self.service_account if self.service_account is not None else (
            getattr(settings, "GEE_SERVICE_ACCOUNT_EMAIL", None)
            or os.getenv("GEE_SERVICE_ACCOUNT_EMAIL")
            or os.getenv("GEE_SERVICE_ACCOUNT")
        )
        private_key = self.private_key if self.private_key is not None else (getattr(settings, "GEE_PRIVATE_KEY", None) or os.getenv("GEE_PRIVATE_KEY"))

        try:
            import ee
            self._ee = ee
        except ImportError:
            self._is_initialized = False
            self._init_error_type = "UNCONFIGURED"
            self._init_error = "Earth Engine client library is not installed."
            logger.info("GEE Provider: earthengine-api not installed. Running in unconfigured mode.")
            return False

        # If credentials or project are not provided in environment, stay in unconfigured state.
        # Do not throttle or block configuration checks with an auth failure cooldown.
        if not project_id and not service_account and not private_key:
            self._is_initialized = False
            self._init_error_type = "UNCONFIGURED"
            self._init_error = "Earth Engine service is not configured in this environment."
            logger.info("GEE Provider: Credentials not configured. GEE endpoints will return SATELLITE_NOT_CONFIGURED.")
            return False

        now = time.time()
        # If an authentication/initialization attempt failed recently, throttle retries to prevent hammering
        if self._last_init_attempt_time > 0 and (now - self._last_init_attempt_time) < self._retry_cooldown_seconds:
            return False

        self._last_init_attempt_time = now

        # Strip surrounding whitespace and potential quotation marks from Render UI copy-paste
        clean_project_id = project_id.strip().strip("'\"") if project_id else ""
        clean_service_account = service_account.strip().strip("'\"") if service_account else ""
        clean_private_key = private_key.strip().strip("'\"") if private_key else ""

        # If the private key was provided as a full JSON service account string
        if clean_private_key.startswith("{") and clean_private_key.endswith("}"):
            try:
                import json
                sa_data = json.loads(clean_private_key)
                if not clean_service_account and "client_email" in sa_data:
                    clean_service_account = sa_data["client_email"].strip().strip("'\"")
                if not clean_project_id and "project_id" in sa_data:
                    clean_project_id = sa_data["project_id"].strip().strip("'\"")
                clean_private_key = sa_data.get("private_key", clean_private_key).strip().strip("'\"")
            except Exception:
                pass

        # If newlines were escaped as literal \n in dashboard environment variables
        if "\\n" in clean_private_key:
            clean_private_key = clean_private_key.replace("\\n", "\n")

        # Validate PEM envelope safely without exposing key bytes
        pem_has_header = "-----BEGIN " in clean_private_key
        pem_has_footer = "-----END " in clean_private_key

        has_sa = bool(clean_service_account)
        has_pk = bool(clean_private_key)
        has_proj = bool(clean_project_id)

        try:
            # Initialize with service account credentials or project
            if has_sa and has_pk:
                credentials = self._ee.ServiceAccountCredentials(
                    clean_service_account,
                    key_data=clean_private_key,
                )
                self._ee.Initialize(credentials, project=clean_project_id if has_proj else None)
            elif has_proj:
                self._ee.Initialize(project=clean_project_id)
            else:
                self._ee.Initialize()

            self._is_initialized = True
            self._init_error_type = None
            self._init_error = None
            logger.info(
                "GEE Provider: Google Earth Engine initialized successfully (project_configured=%s, service_account_configured=%s).",
                has_proj,
                has_sa,
            )
            return True
        except Exception as e:
            self._is_initialized = False
            err_str = str(e).lower()

            # Diagnostic sub-classification without logging any secrets, tokens, or private keys
            if any(k in err_str for k in ("invalid_grant", "jwt", "signer", "malformed", "pem file", "unable to load")):
                diag_reason = "INVALID_KEY_OR_GRANT"
                is_auth_error = True
            elif any(k in err_str for k in ("permission", "403", "unauthorized", "401", "forbidden", "accessdenied")):
                diag_reason = "PERMISSION_DENIED_OR_UNAUTHORIZED"
                is_auth_error = True
            elif any(k in err_str for k in ("not been used", "disabled", "serviceusage", "enable it")):
                diag_reason = "API_NOT_ENABLED_OR_DISABLED"
                is_auth_error = True
            elif any(k in err_str for k in ("not registered", "unregistered", "project not found", "not found", "404")):
                diag_reason = "PROJECT_NOT_REGISTERED_OR_NOT_FOUND"
                is_auth_error = True
            elif any(kw in err_str for kw in ("credential", "oauth", "token")):
                diag_reason = "AUTH_TOKEN_FAILURE"
                is_auth_error = True
            else:
                diag_reason = "INITIALIZATION_FAILED"
                is_auth_error = False

            self._init_error_type = "AUTH_FAILED" if is_auth_error else "INIT_FAILED"

            # Always return a safe generic error message to API callers; never expose raw exceptions or keys
            if is_auth_error:
                self._init_error = "Earth Engine authentication failed. Please verify provider credentials."
                diag_category = "AUTHENTICATION_FAILED"
            else:
                self._init_error = "Earth Engine initialization failed."
                diag_category = "INITIALIZATION_FAILED"

            # Log strictly the exception class and safe diagnostic category; never log raw exception messages, tokens, or keys
            logger.warning(
                "GEE Provider: Could not initialize Earth Engine (%s: category=%s, reason=%s, project_configured=%s, service_account_configured=%s, private_key_configured=%s, pem_header=%s, pem_footer=%s)",
                type(e).__name__,
                diag_category,
                diag_reason,
                has_proj,
                has_sa,
                has_pk,
                pem_has_header,
                pem_has_footer,
            )
            return False

    def is_configured(self) -> bool:
        """Check if Earth Engine is actively initialized and authenticated."""
        return self._initialize_ee_if_needed()

    def _mask_s2_clouds(self, image: Any) -> Any:
        """Apply SCL (Scene Classification Layer) and QA60 cloud/shadow mask."""
        ee = self._ee

        # SCL Band: 3=cloud shadow, 8=cloud med prob, 9=cloud high prob, 10=cirrus, 11=snow
        scl = image.select("SCL")
        scl_mask = (
            scl.neq(3)
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
            .And(scl.neq(11))
        )

        # QA60 Band: Bit 10 is opaque clouds, Bit 11 is cirrus
        qa = image.select("QA60")
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        qa_mask = (
            qa.bitwiseAnd(cloud_bit_mask).eq(0)
            .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        )

        mask = scl_mask.And(qa_mask)
        return image.updateMask(mask)

    def _compute_ndvi_image(self, image: Any) -> Any:
        """Compute normalized difference vegetation index from NIR (B8) and Red (B4)."""
        # Sentinel-2 SR Harmonized has B8 (NIR, ~842nm) and B4 (Red, ~665nm)
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        return image.addBands(ndvi)

    def get_latest_observation(
        self,
        geometry: FarmGeometry,
        farm_id: Optional[str] = None,
        max_cloud_percent: float = 30.0,
        days_back: int = 45,
    ) -> SatelliteObservationResponse:
        """Query the latest cloud-free Sentinel-2 observation for farm geometry."""
        if not self._initialize_ee_if_needed():
            status = (
                SatelliteObservationStatus.SATELLITE_ERROR
                if self._init_error_type == "AUTH_FAILED"
                else SatelliteObservationStatus.SATELLITE_NOT_CONFIGURED
            )
            quality = "ERROR" if self._init_error_type == "AUTH_FAILED" else "UNCONFIGURED"
            safe_error_msg = self._init_error or "Earth Engine service is unavailable."

            return SatelliteObservationResponse(
                success=False,
                status=status,
                farm_id=farm_id,
                geometry_type=geometry.geometry_type,
                quality_status=quality,
                error=safe_error_msg,
            )

        ee = self._ee
        try:
            ee_geom = geometry.to_ee_geometry(ee)
            end_d = date.today()
            start_d = end_d - timedelta(days=days_back)

            collection = (
                ee.ImageCollection(self.COLLECTION_ID)
                .filterBounds(ee_geom)
                .filterDate(start_d.isoformat(), end_d.isoformat())
                .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_cloud_percent))
                .sort("system:time_start", False)  # Most recent first
            )

            # Check if any images exist in time window
            image_count = collection.size().getInfo()
            if image_count == 0:
                return SatelliteObservationResponse(
                    success=True,
                    status=SatelliteObservationStatus.SATELLITE_NO_VALID_OBSERVATION,
                    farm_id=farm_id,
                    geometry_type=geometry.geometry_type,
                    quality_status="NO_DATA",
                    error=f"No Sentinel-2 observations found with cloud cover <= {max_cloud_percent}% in the last {days_back} days.",
                )

            # Select latest image
            latest_image = ee.Image(collection.first())
            img_time = latest_image.get("system:time_start").getInfo()
            obs_date = datetime.fromtimestamp(img_time / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
            scene_cloud_pct = float(latest_image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo() or 0.0)

            # 1. Total unmasked optical pixel layer across farm geometry at 10m scale
            total_pixels_img = latest_image.select("B4").rename("total_pixels")

            # 2. Mask clouds/shadows and compute NDVI band
            masked_img = self._mask_s2_clouds(latest_image)
            ndvi_img = self._compute_ndvi_image(masked_img).select("NDVI").rename("NDVI")

            # 3. Combine both bands to compute valid NDVI statistics and total pixel counts in 1 server-side reduction
            combined_img = ndvi_img.addBands(total_pixels_img)

            reducer = (
                ee.Reducer.mean()
                .combine(ee.Reducer.median(), "", True)
                .combine(ee.Reducer.minMax(), "", True)
                .combine(ee.Reducer.stdDev(), "", True)
                .combine(ee.Reducer.count(), "", True)
            )

            stats = combined_img.reduceRegion(
                reducer=reducer,
                geometry=ee_geom,
                scale=10,
                maxPixels=1e6,
            ).getInfo()

            valid_pixel_count = int(stats.get("NDVI_count") or 0)
            total_pixel_count = int(stats.get("total_pixels_count") or 0)
            mean_val = stats.get("NDVI_mean")

            ndvi_stats = NDVIStatistics.from_counts_and_stats(
                mean=mean_val,
                median=stats.get("NDVI_median", mean_val),
                min_val=stats.get("NDVI_min", mean_val),
                max_val=stats.get("NDVI_max", mean_val),
                std_val=stats.get("NDVI_stdDev", 0.0),
                valid_count=valid_pixel_count,
                total_count=total_pixel_count,
                scene_cloud_pct=scene_cloud_pct,
            )

            if mean_val is None or valid_pixel_count == 0:
                # All pixels in geometry were masked due to local clouds/shadows
                return SatelliteObservationResponse(
                    success=True,
                    status=SatelliteObservationStatus.SATELLITE_NO_VALID_OBSERVATION,
                    farm_id=farm_id,
                    observation_date=obs_date,
                    ndvi=ndvi_stats,
                    geometry_type=geometry.geometry_type,
                    quality_status="ALL_PIXELS_CLOUD_MASKED",
                    error="All farm pixels were masked due to local cloud/shadow cover.",
                    raw_metadata={
                        "scene_cloud_percent": scene_cloud_pct,
                        "total_pixels": total_pixel_count,
                        "valid_pixels": 0,
                        "buffer_meters": geometry.buffer_meters,
                        "is_geometry_fallback": geometry.is_fallback,
                    },
                )

            # Deterministic quality status rule using both farm-level valid coverage and tile-level scene cloudiness
            valid_pct = ndvi_stats.valid_pixel_percent or 0.0
            if valid_pct >= 80.0 and scene_cloud_pct <= 20.0:
                quality = "GOOD"
            elif valid_pct >= 50.0:
                quality = "FAIR"
            else:
                quality = "LOW_QUALITY"

            return SatelliteObservationResponse(
                success=True,
                status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
                farm_id=farm_id,
                observation_date=obs_date,
                ndvi=ndvi_stats,
                source="Sentinel-2 / GEE",
                provider="GoogleEarthEngine",
                satellite="Sentinel-2",
                product=self.COLLECTION_ID,
                geometry_type=geometry.geometry_type,
                quality_status=quality,
                raw_metadata={
                    "scene_cloud_percent": scene_cloud_pct,
                    "valid_pixel_percent": valid_pct,
                    "total_pixels": total_pixel_count,
                    "valid_pixels": valid_pixel_count,
                    "buffer_meters": geometry.buffer_meters,
                    "is_geometry_fallback": geometry.is_fallback,
                    "geometry_fingerprint": geometry.fingerprint,
                },
            )
        except Exception as e:
            logger.warning("GEE Provider: Query error (%s: category=OBSERVATION_QUERY_FAILED)", type(e).__name__)
            return SatelliteObservationResponse(
                success=False,
                status=SatelliteObservationStatus.SATELLITE_ERROR,
                farm_id=farm_id,
                geometry_type=geometry.geometry_type,
                quality_status="ERROR",
                error="Earth Engine query execution failed. Please retry later.",
            )

    def get_historical_observations(
        self,
        geometry: FarmGeometry,
        start_date: str,
        end_date: str,
        farm_id: Optional[str] = None,
        max_cloud_percent: float = 40.0,
        limit: int = 12,
    ) -> List[SatelliteObservationResponse]:
        """Fetch multiple historical Sentinel-2 observations across a date range."""
        if not self._initialize_ee_if_needed():
            return []

        ee = self._ee
        try:
            ee_geom = geometry.to_ee_geometry(ee)
            collection = (
                ee.ImageCollection(self.COLLECTION_ID)
                .filterBounds(ee_geom)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_cloud_percent))
                .sort("system:time_start", False)
                .limit(limit)
            )

            images = collection.toList(limit)
            count = images.size().getInfo()

            results = []
            for i in range(count):
                img = ee.Image(images.get(i))
                img_time = img.get("system:time_start").getInfo()
                obs_date = datetime.fromtimestamp(img_time / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
                scene_cloud_pct = float(img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo() or 0.0)

                total_pixels_img = img.select("B4").rename("total_pixels")
                masked = self._mask_s2_clouds(img)
                ndvi_img = self._compute_ndvi_image(masked).select("NDVI").rename("NDVI")
                combined_img = ndvi_img.addBands(total_pixels_img)

                reducer = (
                    ee.Reducer.mean()
                    .combine(ee.Reducer.median(), "", True)
                    .combine(ee.Reducer.minMax(), "", True)
                    .combine(ee.Reducer.stdDev(), "", True)
                    .combine(ee.Reducer.count(), "", True)
                )

                stats = combined_img.reduceRegion(
                    reducer=reducer,
                    geometry=ee_geom,
                    scale=10,
                    maxPixels=1e6,
                ).getInfo()

                valid_pixel_count = int(stats.get("NDVI_count") or 0)
                total_pixel_count = int(stats.get("total_pixels_count") or 0)
                mean_val = stats.get("NDVI_mean")

                if mean_val is not None and valid_pixel_count > 0:
                    ndvi_stats = NDVIStatistics.from_counts_and_stats(
                        mean=mean_val,
                        median=stats.get("NDVI_median", mean_val),
                        min_val=stats.get("NDVI_min", mean_val),
                        max_val=stats.get("NDVI_max", mean_val),
                        std_val=stats.get("NDVI_stdDev", 0.0),
                        valid_count=valid_pixel_count,
                        total_count=total_pixel_count,
                        scene_cloud_pct=scene_cloud_pct,
                    )

                    valid_pct = ndvi_stats.valid_pixel_percent or 0.0
                    if valid_pct >= 80.0 and scene_cloud_pct <= 20.0:
                        hist_quality = "GOOD"
                    elif valid_pct >= 50.0:
                        hist_quality = "FAIR"
                    else:
                        hist_quality = "LOW_QUALITY"

                    results.append(
                        SatelliteObservationResponse(
                            success=True,
                            status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
                            farm_id=farm_id,
                            observation_date=obs_date,
                            ndvi=ndvi_stats,
                            source="Sentinel-2 / GEE",
                            provider="GoogleEarthEngine",
                            satellite="Sentinel-2",
                            product=self.COLLECTION_ID,
                            geometry_type=geometry.geometry_type,
                            quality_status=hist_quality,
                            raw_metadata={
                                "scene_cloud_percent": scene_cloud_pct,
                                "valid_pixel_percent": valid_pct,
                                "total_pixels": total_pixel_count,
                                "valid_pixels": valid_pixel_count,
                                "geometry_fingerprint": geometry.fingerprint,
                            },
                        )
                    )

            return results
        except Exception as e:
            logger.warning("GEE Provider: Historical query error (%s: category=HISTORICAL_QUERY_FAILED)", type(e).__name__)
            return []
