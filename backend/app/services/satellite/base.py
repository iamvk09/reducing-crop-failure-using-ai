"""Abstract Base Class for Satellite and Earth Observation Data Providers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.schemas import SatelliteObservationResponse


class SatelliteProvider(ABC):
    """Abstract interface defining operations for satellite vegetation observations.

    Decouples Google Earth Engine from upstream services and APIs so alternative
    providers (e.g., Planetary Computer, Copernicus Data Space, Sentinel Hub) can be
    integrated seamlessly in the future.
    """

    @abstractmethod
    def get_latest_observation(
        self,
        geometry: FarmGeometry,
        farm_id: Optional[str] = None,
        max_cloud_percent: float = 30.0,
        days_back: int = 45,
    ) -> SatelliteObservationResponse:
        """Fetch the latest high-quality cloud-masked vegetation observation for a farm."""
        pass

    @abstractmethod
    def get_historical_observations(
        self,
        geometry: FarmGeometry,
        start_date: str,
        end_date: str,
        farm_id: Optional[str] = None,
        max_cloud_percent: float = 40.0,
        limit: int = 12,
    ) -> List[SatelliteObservationResponse]:
        """Fetch historical vegetation observations across a date window."""
        pass
