"""Pydantic schemas and domain models for Satellite and Vegetation Data."""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class SatelliteObservationStatus(str, Enum):
    """Explicit lifecycle and availability status for satellite observations."""
    REAL_SATELLITE_DATA = "REAL_SATELLITE_DATA"
    SATELLITE_PENDING = "SATELLITE_PENDING"
    SATELLITE_NOT_CONFIGURED = "SATELLITE_NOT_CONFIGURED"
    SATELLITE_NO_VALID_OBSERVATION = "SATELLITE_NO_VALID_OBSERVATION"
    SATELLITE_ERROR = "SATELLITE_ERROR"
    MOCK_DEVELOPMENT = "MOCK_DEVELOPMENT"


class NDVIStatistics(BaseModel):
    """Vegetation index spatial statistics computed over the farm region."""
    mean: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Mean NDVI across valid farm pixels")
    median: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Median NDVI across valid farm pixels")
    min: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Minimum NDVI valid pixel value")
    max: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Maximum NDVI valid pixel value")
    std: Optional[float] = Field(None, ge=0.0, description="Standard deviation of NDVI values")
    valid_pixel_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Percentage of valid cloud/shadow-free pixels in farm geometry")
    scene_cloud_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Sentinel-2 scene-level cloud percentage from metadata")
    cloud_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Scene-level cloud percentage (alias of scene_cloud_percent for backward compatibility)")
    total_pixels: Optional[int] = Field(None, ge=0, description="Total 10m grid pixels within farm geometry")
    valid_pixels: Optional[int] = Field(None, ge=0, description="Count of cloud-free valid pixels within farm geometry")

    @classmethod
    def from_counts_and_stats(
        cls,
        mean: Optional[float],
        median: Optional[float],
        min_val: Optional[float],
        max_val: Optional[float],
        std_val: Optional[float],
        valid_count: int,
        total_count: int,
        scene_cloud_pct: Optional[float],
    ) -> "NDVIStatistics":
        """Factory helper calculating bounded valid pixel percentage from pixel counts."""
        if total_count > 0:
            valid_pct = round(min(max((valid_count / float(total_count)) * 100.0, 0.0), 100.0), 2)
        else:
            valid_pct = 0.0

        cloud_val = round(scene_cloud_pct, 1) if scene_cloud_pct is not None else None

        return cls(
            mean=round(float(mean), 4) if mean is not None else None,
            median=round(float(median), 4) if median is not None else None,
            min=round(float(min_val), 4) if min_val is not None else None,
            max=round(float(max_val), 4) if max_val is not None else None,
            std=round(float(std_val), 4) if std_val is not None else None,
            valid_pixel_percent=valid_pct,
            scene_cloud_percent=cloud_val,
            cloud_percent=cloud_val,
            total_pixels=max(0, total_count),
            valid_pixels=max(0, valid_count),
        )

    @model_validator(mode="after")
    def sync_cloud_percentage_fields(self) -> "NDVIStatistics":
        if self.scene_cloud_percent is None and self.cloud_percent is not None:
            self.scene_cloud_percent = self.cloud_percent
        elif self.cloud_percent is None and self.scene_cloud_percent is not None:
            self.cloud_percent = self.scene_cloud_percent
        return self


class SatelliteObservationResponse(BaseModel):
    """Normalized satellite observation record for APIs and persistence."""
    success: bool = True
    status: SatelliteObservationStatus = SatelliteObservationStatus.REAL_SATELLITE_DATA
    farm_id: Optional[str] = None
    observation_date: Optional[str] = None  # YYYY-MM-DD
    ndvi: Optional[NDVIStatistics] = None
    source: str = "Sentinel-2 / GEE"
    provider: str = "GoogleEarthEngine"
    satellite: str = "Sentinel-2"
    product: str = "COPERNICUS/S2_SR_HARMONIZED"
    geometry_type: str = "buffered_point"  # 'polygon' or 'buffered_point'
    geometry_fingerprint: Optional[str] = None
    quality_status: str = "GOOD"  # 'GOOD', 'FAIR', 'LOW_QUALITY', 'UNCONFIGURED'
    disclaimer: str = (
        "Vegetation indices (NDVI) provide surface reflectance metrics for crop health "
        "monitoring and do not constitute direct crop failure probability."
    )
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)
    is_cached: bool = False
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def sync_geometry_fingerprint(self) -> "SatelliteObservationResponse":
        if self.geometry_fingerprint is None and "geometry_fingerprint" in self.raw_metadata:
            self.geometry_fingerprint = str(self.raw_metadata["geometry_fingerprint"])
        elif self.geometry_fingerprint is not None and "geometry_fingerprint" not in self.raw_metadata:
            self.raw_metadata["geometry_fingerprint"] = self.geometry_fingerprint
        return self


class SatelliteHistoryResponse(BaseModel):
    """Multi-observation historical vegetation time-series for a farm."""
    farm_id: str
    total_count: int
    observations: List[SatelliteObservationResponse] = Field(default_factory=list)


class FarmVegetationSummary(BaseModel):
    """Farmer-friendly simplified vegetation health summary."""
    farm_id: str
    has_observation: bool
    status: SatelliteObservationStatus
    vegetation_health: str  # 'Healthy', 'Moderate', 'Stressed', 'Pending Observation', 'Unconfigured'
    latest_ndvi: Optional[float] = None
    observation_date: Optional[str] = None
    valid_pixel_percent: Optional[float] = None
    scene_cloud_percent: Optional[float] = None
    data_source: str = "Sentinel-2 (Google Earth Engine)"
    quality_label: str = "Good"
    message: str = ""
    disclaimer: str = (
        "Vegetation health is based on satellite-observed surface greenness (NDVI)."
    )
