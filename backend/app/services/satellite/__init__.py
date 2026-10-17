"""Satellite and Earth Observation Service Package."""

from backend.app.services.satellite.base import SatelliteProvider
from backend.app.services.satellite.gee_provider import GoogleEarthEngineProvider
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.mock_provider import MockSatelliteProvider
from backend.app.services.satellite.schemas import (
    FarmVegetationSummary,
    NDVIStatistics,
    SatelliteHistoryResponse,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)
from backend.app.services.satellite.service import SatelliteService, satellite_service

__all__ = [
    "SatelliteProvider",
    "GoogleEarthEngineProvider",
    "MockSatelliteProvider",
    "FarmGeometry",
    "SatelliteObservationStatus",
    "NDVIStatistics",
    "SatelliteObservationResponse",
    "SatelliteHistoryResponse",
    "FarmVegetationSummary",
    "SatelliteService",
    "satellite_service",
]
