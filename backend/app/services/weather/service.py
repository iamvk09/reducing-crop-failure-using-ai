"""Weather Service Layer with provider abstraction, caching, and persistence."""

import datetime
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.weather.providers.base import WeatherProvider
from backend.app.services.weather.providers.open_meteo import OpenMeteoProvider
from backend.app.services.weather.schemas import (
    CurrentWeatherResponse,
    WeatherForecastResponse,
    WeatherObservationRecord,
)

if TYPE_CHECKING:
    from backend.app.repositories.weather_repository import WeatherRepository


class WeatherService:
    """Service orchestrating weather retrieval, in-memory caching, and Supabase persistence."""

    def __init__(
        self,
        provider: Optional[WeatherProvider] = None,
        repository: Optional["WeatherRepository"] = None,
        cache_ttl_seconds: Optional[int] = None,
    ):
        self.provider = provider or OpenMeteoProvider()
        self._repository = repository
        self.cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else settings.WEATHER_CACHE_TTL_SECONDS
        )
        self._current_cache: Dict[str, Tuple[float, CurrentWeatherResponse]] = {}
        self._forecast_cache: Dict[str, Tuple[float, WeatherForecastResponse]] = {}
        self._cache_lock = threading.Lock()

    @property
    def repository(self) -> "WeatherRepository":
        if self._repository is None:
            from backend.app.repositories.weather_repository import weather_repository
            self._repository = weather_repository
        return self._repository

    def _get_cache_key(self, lat: float, lon: float, suffix: str = "") -> str:
        return f"{lat:.4f}:{lon:.4f}:{suffix}".rstrip(":")

    def get_current_weather(
        self,
        latitude: float,
        longitude: float,
        farm_id: Optional[str] = None,
        persist: bool = False,
        user_token: Optional[str] = None,
        timeout: int = 10,
    ) -> CurrentWeatherResponse:
        """Fetch current live weather conditions for given coordinates with TTL caching."""
        cache_key = self._get_cache_key(latitude, longitude, "current")
        now = time.time()

        # 1. Check in-memory performance cache
        with self._cache_lock:
            cached_entry = self._current_cache.get(cache_key)
            if cached_entry:
                timestamp, cached_res = cached_entry
                if now - timestamp < self.cache_ttl_seconds:
                    res = cached_res.model_copy()
                    res.is_cached = True
                    if farm_id:
                        res.farm_id = farm_id
                    return res

        # 2. Query external weather provider
        t_start = time.perf_counter()
        weather = self.provider.get_current_weather(latitude=latitude, longitude=longitude, timeout=timeout)
        duration_ms = (time.perf_counter() - t_start) * 1000

        if farm_id:
            weather.farm_id = farm_id

        # 3. If successful, cache and optionally persist
        if weather.success:
            with self._cache_lock:
                self._current_cache[cache_key] = (now, weather.model_copy())

            if persist and farm_id:
                try:
                    self.repository.create(
                        farm_id=farm_id,
                        weather_data=weather.model_dump(),
                        user_token=user_token,
                    )
                except Exception as e:
                    logger.warning("Could not persist weather observation for farm %s: %s", farm_id, str(e))

            logger.info(
                "Fetched live weather from %s for (%.4f, %.4f) in %.1fms",
                weather.source,
                latitude,
                longitude,
                duration_ms,
            )

        return weather

    def get_forecast(
        self,
        latitude: float,
        longitude: float,
        farm_id: Optional[str] = None,
        days: int = 7,
        timeout: int = 10,
    ) -> WeatherForecastResponse:
        """Fetch multi-day weather forecast with TTL caching."""
        cache_key = self._get_cache_key(latitude, longitude, f"forecast:{days}")
        now = time.time()

        # 1. Check cache
        with self._cache_lock:
            cached_entry = self._forecast_cache.get(cache_key)
            if cached_entry:
                timestamp, cached_res = cached_entry
                if now - timestamp < self.cache_ttl_seconds:
                    res = cached_res.model_copy()
                    res.is_cached = True
                    if farm_id:
                        res.farm_id = farm_id
                    return res

        # 2. Query external weather provider
        t_start = time.perf_counter()
        forecast = self.provider.get_forecast(latitude=latitude, longitude=longitude, days=days, timeout=timeout)
        duration_ms = (time.perf_counter() - t_start) * 1000

        if farm_id:
            forecast.farm_id = farm_id

        if forecast.success:
            with self._cache_lock:
                self._forecast_cache[cache_key] = (now, forecast.model_copy())

            logger.info(
                "Fetched %d-day forecast from %s for (%.4f, %.4f) in %.1fms",
                days,
                forecast.source,
                latitude,
                longitude,
                duration_ms,
            )

        return forecast

    def get_history(
        self,
        farm_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[WeatherObservationRecord]:
        """Retrieve historical persisted weather observations for a farm."""
        return self.repository.list_for_farm(
            farm_id=farm_id, limit=limit, offset=offset, user_token=user_token
        )

    def clear_cache(self) -> None:
        """Clear cached weather responses (used for testing)."""
        with self._cache_lock:
            self._current_cache.clear()
            self._forecast_cache.clear()


# Global default weather service instance
weather_service = WeatherService()
