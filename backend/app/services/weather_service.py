"""Weather service wrapper bridging to src/weather_service.py."""

from typing import Any, Dict
from src.weather_service import get_current_weather


class WeatherService:
    """Service abstraction for live meteorological queries."""

    def get_weather(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Fetch live weather data for given coordinates."""
        return get_current_weather(latitude=latitude, longitude=longitude)


weather_service = WeatherService()
