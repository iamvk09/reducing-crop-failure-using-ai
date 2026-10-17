"""Mock Satellite Provider for Offline Development and Automated Unit Testing.

Provides deterministic test responses with explicit 'MOCK_DEVELOPMENT' status
and 'mock' source labeling. Real satellite data is never simulated as genuine.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from backend.app.services.satellite.base import SatelliteProvider
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)


class MockSatelliteProvider(SatelliteProvider):
    """Deterministic mock provider used strictly for automated testing."""

    def __init__(self, default_ndvi: float = 0.62, mock_cloud_pct: float = 8.5):
        self.default_ndvi = default_ndvi
        self.mock_cloud_pct = mock_cloud_pct

    def get_latest_observation(
        self,
        geometry: FarmGeometry,
        farm_id: Optional[str] = None,
        max_cloud_percent: float = 30.0,
        days_back: int = 45,
    ) -> SatelliteObservationResponse:
        obs_date = (date.today() - timedelta(days=3)).isoformat()

        ndvi_stats = NDVIStatistics.from_counts_and_stats(
            mean=self.default_ndvi,
            median=self.default_ndvi + 0.01,
            min_val=self.default_ndvi - 0.12,
            max_val=min(1.0, self.default_ndvi + 0.15),
            std_val=0.045,
            valid_count=94,
            total_count=100,
            scene_cloud_pct=self.mock_cloud_pct,
        )

        return SatelliteObservationResponse(
            success=True,
            status=SatelliteObservationStatus.MOCK_DEVELOPMENT,
            farm_id=farm_id,
            observation_date=obs_date,
            ndvi=ndvi_stats,
            source="mock",
            provider="MockSatelliteProvider",
            satellite="Sentinel-2-Simulated",
            product="COPERNICUS/S2_SR_HARMONIZED (Mock)",
            geometry_type=geometry.geometry_type,
            quality_status="GOOD",
            disclaimer="[MOCK DATA] This is synthetic data generated strictly for automated test suites.",
            raw_metadata={
                "is_mock": True,
                "scene_cloud_percent": self.mock_cloud_pct,
                "valid_pixel_percent": ndvi_stats.valid_pixel_percent,
                "total_pixels": 100,
                "valid_pixels": 94,
                "buffer_meters": geometry.buffer_meters,
            },
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
        results = []
        base_date = date.today() - timedelta(days=10)

        for i in range(min(limit, 4)):
            obs_d = (base_date - timedelta(days=i * 12)).isoformat()
            ndvi_val = max(0.2, min(0.85, self.default_ndvi - (i * 0.05)))

            ndvi_stats = NDVIStatistics.from_counts_and_stats(
                mean=ndvi_val,
                median=ndvi_val + 0.01,
                min_val=ndvi_val - 0.10,
                max_val=min(1.0, ndvi_val + 0.12),
                std_val=0.038,
                valid_count=92,
                total_count=100,
                scene_cloud_pct=self.mock_cloud_pct,
            )

            results.append(
                SatelliteObservationResponse(
                    success=True,
                    status=SatelliteObservationStatus.MOCK_DEVELOPMENT,
                    farm_id=farm_id,
                    observation_date=obs_d,
                    ndvi=ndvi_stats,
                    source="mock",
                    provider="MockSatelliteProvider",
                    satellite="Sentinel-2-Simulated",
                    product="COPERNICUS/S2_SR_HARMONIZED (Mock)",
                    geometry_type=geometry.geometry_type,
                    quality_status="GOOD",
                    disclaimer="[MOCK DATA] This is synthetic data generated strictly for automated test suites.",
                    raw_metadata={"is_mock": True, "index": i},
                )
            )

        return results
