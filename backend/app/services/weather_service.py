"""Weather service wrapper providing backwards-compatible imports."""

from backend.app.services.weather import (
    CurrentWeatherResponse,
    DailyForecastItem,
    OpenMeteoProvider,
    WeatherForecastResponse,
    WeatherObservationRecord,
    WeatherProvider,
    WeatherService,
    weather_service,
)

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
