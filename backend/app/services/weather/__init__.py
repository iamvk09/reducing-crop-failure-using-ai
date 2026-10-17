"""Weather service package initialization."""

from backend.app.services.weather.providers.base import WeatherProvider
from backend.app.services.weather.providers.open_meteo import OpenMeteoProvider
from backend.app.services.weather.schemas import (
    CurrentWeatherResponse,
    DailyForecastItem,
    WeatherForecastResponse,
    WeatherObservationRecord,
)
from backend.app.services.weather.service import WeatherService, weather_service

__all__ = [
    "WeatherService",
    "weather_service",
    "WeatherProvider",
    "OpenMeteoProvider",
    "CurrentWeatherResponse",
    "DailyForecastItem",
    "WeatherForecastResponse",
    "WeatherObservationRecord",
]
