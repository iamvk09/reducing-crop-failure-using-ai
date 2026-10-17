"""Open-Meteo REST API Provider implementation.

Wraps Open-Meteo endpoints for Indian agricultural coordinates:
- Validates latitude [-90, 90] and longitude [-180, 180]
- Retrieves hourly/daily variables in Asia/Kolkata timezone
- Calculates 4-layer root-zone soil moisture (0-27cm) and relative saturation %
- Extracts multi-day weather forecast projections
- Free API: requires no API keys or paid subscriptions
"""

from datetime import datetime
import json
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.weather.providers.base import WeatherProvider
from backend.app.services.weather.schemas import (
    CurrentWeatherResponse,
    DailyForecastItem,
    WeatherForecastResponse,
)

USER_AGENT = "AI-Crop-Failure-Project/2.0 (Open-Meteo-WeatherProvider)"


def _validate_coordinates(latitude: float, longitude: float) -> tuple[bool, Optional[str]]:
    """Validate numeric coordinate bounds."""
    if latitude is None or longitude is None:
        return False, "Coordinates cannot be None."
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (ValueError, TypeError):
        return False, f"Coordinates must be numeric: lat={latitude}, lon={longitude}"

    if not (-90.0 <= lat <= 90.0):
        return False, f"Latitude {lat} out of range [-90, 90]."
    if not (-180.0 <= lon <= 180.0):
        return False, f"Longitude {lon} out of range [-180, 180]."

    return True, None


class OpenMeteoProvider(WeatherProvider):
    """Provider implementation for Open-Meteo weather service."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.OPENMETEO_BASE_URL).rstrip("/")

    def get_current_weather(
        self, latitude: float, longitude: float, timeout: int = 10
    ) -> CurrentWeatherResponse:
        """Fetch current live weather conditions from Open-Meteo."""
        valid, err_msg = _validate_coordinates(latitude, longitude)
        if not valid:
            return CurrentWeatherResponse(
                success=False,
                latitude=float(latitude) if latitude is not None else 0.0,
                longitude=float(longitude) if longitude is not None else 0.0,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
                source="Open-Meteo (Invalid Coordinates)",
                error=err_msg,
            )

        lat_r = round(float(latitude), 4)
        lon_r = round(float(longitude), 4)

        params = {
            "latitude": lat_r,
            "longitude": lon_r,
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
                "weather_code,soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,"
                "soil_moisture_3_to_9cm,soil_moisture_9_to_27cm"
            ),
            "daily": "precipitation_sum",
            "timezone": "Asia/Kolkata",
        }

        url = f"{self.base_url}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))

            current = payload.get("current", {})
            daily = payload.get("daily", {})

            temp = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m")
            precip = current.get("precipitation")
            wind_speed = current.get("wind_speed_10m")
            weather_code = current.get("weather_code")
            raw_timestamp = current.get("time", "")

            if raw_timestamp:
                try:
                    dt = datetime.fromisoformat(raw_timestamp)
                    display_time = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    display_time = str(raw_timestamp)
            else:
                display_time = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Root-zone soil moisture calculation across 4 depths (0-27 cm)
            sm_layers = [
                current.get("soil_moisture_0_to_1cm"),
                current.get("soil_moisture_1_to_3cm"),
                current.get("soil_moisture_3_to_9cm"),
                current.get("soil_moisture_9_to_27cm"),
            ]
            valid_sm = [v for v in sm_layers if v is not None and isinstance(v, (int, float))]
            root_zone_sm = round(sum(valid_sm) / len(valid_sm), 4) if valid_sm else None

            # Convert volumetric fraction (m3/m3) to relative saturation %
            if root_zone_sm is not None:
                rel_moisture = min(max(round((root_zone_sm / 0.45) * 100.0, 1), 5.0), 95.0)
            else:
                rel_moisture = None

            # 7-day cumulative precipitation sum
            daily_precip_list = daily.get("precipitation_sum", [])
            precip_7d = (
                round(sum(p for p in daily_precip_list if isinstance(p, (int, float))), 1)
                if daily_precip_list
                else None
            )

            return CurrentWeatherResponse(
                success=True,
                latitude=lat_r,
                longitude=lon_r,
                timestamp=display_time,
                timezone="Asia/Kolkata",
                temperature=round(float(temp), 1) if temp is not None else None,
                relative_humidity=round(float(humidity), 1) if humidity is not None else None,
                precipitation=round(float(precip), 1) if precip is not None else 0.0,
                wind_speed_10m=round(float(wind_speed), 1) if wind_speed is not None else None,
                soil_moisture_m3m3=root_zone_sm,
                soil_moisture_percentage=rel_moisture,
                weather_code=weather_code,
                source="Open-Meteo (Meteorological Model Estimate)",
                is_forecast=False,
                is_estimate=True,
                precipitation_sum_7d=precip_7d,
                error=None,
            )

        except (HTTPError, URLError, TimeoutError, Exception) as err:
            logger.warning("Open-Meteo request failed for lat=%.4f, lon=%.4f: %s", lat_r, lon_r, str(err))
            return CurrentWeatherResponse(
                success=False,
                latitude=lat_r,
                longitude=lon_r,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
                source="Open-Meteo (Unavailable)",
                error=f"Live weather API error: {err}",
            )

    def get_forecast(
        self, latitude: float, longitude: float, days: int = 7, timeout: int = 10
    ) -> WeatherForecastResponse:
        """Fetch multi-day daily weather forecast from Open-Meteo."""
        valid, err_msg = _validate_coordinates(latitude, longitude)
        if not valid:
            return WeatherForecastResponse(
                success=False,
                latitude=float(latitude) if latitude is not None else 0.0,
                longitude=float(longitude) if longitude is not None else 0.0,
                source="Open-Meteo (Invalid Coordinates)",
                error=err_msg,
            )

        lat_r = round(float(latitude), 4)
        lon_r = round(float(longitude), 4)
        forecast_days = min(max(int(days), 1), 16)

        params = {
            "latitude": lat_r,
            "longitude": lon_r,
            "daily": (
                "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                "precipitation_probability_max,weather_code"
            ),
            "forecast_days": forecast_days,
            "timezone": "Asia/Kolkata",
        }

        url = f"{self.base_url}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))

            daily = payload.get("daily", {})
            dates = daily.get("time", [])
            t_max = daily.get("temperature_2m_max", [])
            t_min = daily.get("temperature_2m_min", [])
            p_sum = daily.get("precipitation_sum", [])
            p_prob = daily.get("precipitation_probability_max", [])
            w_code = daily.get("weather_code", [])

            items = []
            for i in range(len(dates)):
                items.append(
                    DailyForecastItem(
                        date=dates[i],
                        temperature_max=t_max[i] if i < len(t_max) else None,
                        temperature_min=t_min[i] if i < len(t_min) else None,
                        precipitation_sum=p_sum[i] if i < len(p_sum) else None,
                        precipitation_probability_max=p_prob[i] if i < len(p_prob) else None,
                        weather_code=w_code[i] if i < len(w_code) else None,
                    )
                )

            return WeatherForecastResponse(
                success=True,
                latitude=lat_r,
                longitude=lon_r,
                timezone="Asia/Kolkata",
                source="Open-Meteo Numerical Weather Forecast",
                is_forecast=True,
                forecast_days=len(items),
                daily=items,
            )

        except (HTTPError, URLError, TimeoutError, Exception) as err:
            logger.warning("Open-Meteo forecast failed for lat=%.4f, lon=%.4f: %s", lat_r, lon_r, str(err))
            return WeatherForecastResponse(
                success=False,
                latitude=lat_r,
                longitude=lon_r,
                source="Open-Meteo (Unavailable)",
                error=f"Weather forecast API error: {err}",
            )
