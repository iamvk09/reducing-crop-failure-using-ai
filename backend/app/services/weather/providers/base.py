"""Abstract base class for weather data providers."""

from abc import ABC, abstractmethod
from backend.app.services.weather.schemas import CurrentWeatherResponse, WeatherForecastResponse


class WeatherProvider(ABC):
    """Abstract interface for external meteorological data providers."""

    @abstractmethod
    def get_current_weather(
        self, latitude: float, longitude: float, timeout: int = 10
    ) -> CurrentWeatherResponse:
        """Fetch current live weather conditions for given coordinates."""
        pass

    @abstractmethod
    def get_forecast(
        self, latitude: float, longitude: float, days: int = 7, timeout: int = 10
    ) -> WeatherForecastResponse:
        """Fetch multi-day weather forecast projections for given coordinates."""
        pass
