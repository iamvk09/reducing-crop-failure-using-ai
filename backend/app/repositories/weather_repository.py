"""Weather Observations Database Repository.

Provides data-access operations for persisting and querying farm-level
weather observations in Supabase PostgreSQL:
- Inserts current observations or forecast snapshots
- Queries historical observations with pagination and tenant isolation
- Fallback in-memory driver for offline testing environments
"""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client
from backend.app.services.weather.schemas import WeatherObservationRecord


class WeatherRepository:
    """Repository managing weather observation persistence in Supabase PostgreSQL."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self.client = client or supabase_client
        self._local_observations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(
        self,
        farm_id: str,
        weather_data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> WeatherObservationRecord:
        """Persist a weather observation for a specific farm plot."""
        obs_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)

        raw_time = weather_data.get("timestamp")
        if isinstance(raw_time, datetime.datetime):
            obs_time_str = raw_time.isoformat()
        elif isinstance(raw_time, str) and raw_time:
            obs_time_str = raw_time
        else:
            obs_time_str = now.isoformat()

        record_dict = {
            "id": obs_id,
            "farm_id": farm_id,
            "latitude": weather_data.get("latitude"),
            "longitude": weather_data.get("longitude"),
            "observation_time": obs_time_str,
            "temperature_c": weather_data.get("temperature"),
            "humidity_pct": weather_data.get("relative_humidity") or weather_data.get("humidity"),
            "precipitation_mm": weather_data.get("precipitation"),
            "soil_moisture_pct": weather_data.get("soil_moisture_percentage") or weather_data.get("soil_moisture"),
            "soil_moisture_m3m3": weather_data.get("soil_moisture_m3m3"),
            "weather_code": weather_data.get("weather_code"),
            "source": weather_data.get("source", "Open-Meteo"),
            "is_forecast": bool(weather_data.get("is_forecast", False)),
            "created_at": now.isoformat(),
        }

        # 1. Supabase persistence if configured
        if self.client.is_live_configured():
            try:
                res = self.client.insert("weather_observations", data=record_dict, user_token=user_token)
                obs_id = res.get("id", obs_id)
            except SupabaseClientError as e:
                logger.warning("Failed to persist weather observation to Supabase: %s", str(e))

        # 2. Local store
        with self._lock:
            self._local_observations[obs_id] = record_dict.copy()

        return WeatherObservationRecord(
            id=obs_id,
            farm_id=farm_id,
            latitude=record_dict.get("latitude"),
            longitude=record_dict.get("longitude"),
            observation_time=record_dict.get("observation_time", obs_time_str),
            temperature_c=record_dict.get("temperature_c"),
            humidity_pct=record_dict.get("humidity_pct"),
            precipitation_mm=record_dict.get("precipitation_mm"),
            soil_moisture_pct=record_dict.get("soil_moisture_pct"),
            soil_moisture_m3m3=record_dict.get("soil_moisture_m3m3"),
            weather_code=record_dict.get("weather_code"),
            source=record_dict.get("source", "Open-Meteo"),
            is_forecast=record_dict.get("is_forecast", False),
            created_at=record_dict.get("created_at", now.isoformat()),
        )

    def list_for_farm(
        self,
        farm_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[WeatherObservationRecord]:
        """Retrieve historical weather observations recorded for a farm."""
        # 1. Supabase query if configured
        if self.client.is_live_configured():
            try:
                params = {
                    "farm_id": f"eq.{farm_id}",
                    "order": "observation_time.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                }
                records = self.client.select("weather_observations", params=params, user_token=user_token)
                return [
                    WeatherObservationRecord(
                        id=r["id"],
                        farm_id=r["farm_id"],
                        latitude=r.get("latitude"),
                        longitude=r.get("longitude"),
                        observation_time=r.get("observation_time", ""),
                        temperature_c=r.get("temperature_c"),
                        humidity_pct=r.get("humidity_pct"),
                        precipitation_mm=r.get("precipitation_mm"),
                        soil_moisture_pct=r.get("soil_moisture_pct"),
                        soil_moisture_m3m3=r.get("soil_moisture_m3m3"),
                        weather_code=r.get("weather_code"),
                        source=r.get("source", "Open-Meteo"),
                        is_forecast=r.get("is_forecast", False),
                        created_at=r.get("created_at", ""),
                    )
                    for r in records
                ]
            except SupabaseClientError as e:
                logger.warning("Supabase select weather observations failed: %s", str(e))

        # 2. Local fallback
        with self._lock:
            items = [o for o in self._local_observations.values() if o.get("farm_id") == farm_id]

        items.sort(key=lambda x: x.get("observation_time", ""), reverse=True)
        paginated = items[offset : offset + limit]

        return [
            WeatherObservationRecord(
                id=r["id"],
                farm_id=r["farm_id"],
                latitude=r.get("latitude"),
                longitude=r.get("longitude"),
                observation_time=r.get("observation_time", ""),
                temperature_c=r.get("temperature_c"),
                humidity_pct=r.get("humidity_pct"),
                precipitation_mm=r.get("precipitation_mm"),
                soil_moisture_pct=r.get("soil_moisture_pct"),
                soil_moisture_m3m3=r.get("soil_moisture_m3m3"),
                weather_code=r.get("weather_code"),
                source=r.get("source", "Open-Meteo"),
                is_forecast=r.get("is_forecast", False),
                created_at=r.get("created_at", ""),
            )
            for r in paginated
        ]

    def clear(self) -> None:
        """Clear local observations for test resets."""
        with self._lock:
            self._local_observations.clear()


weather_repository = WeatherRepository()
