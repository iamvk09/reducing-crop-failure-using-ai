"""Live weather integration service using the free Open-Meteo API.

Provides real-time temperature, relative humidity, precipitation, and
soil moisture retrieval for any latitude and longitude coordinates in India.
No API keys, accounts, or paid services are required.
"""

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import streamlit as st
    _cache_decorator = st.cache_data(ttl=1800, show_spinner=False)
except Exception:
    _cache_decorator = lambda func: func

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "AI-Crop-Failure-Project/2.0 (Open-Meteo-LiveWeather)"


def _validate_coordinates(latitude, longitude):
    """Validate latitude and longitude ranges."""
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


@_cache_decorator
def get_current_weather(latitude: float, longitude: float, timeout: int = 10) -> dict:
    """Fetch current live weather conditions from Open-Meteo.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees.
    longitude : float
        Longitude in decimal degrees.
    timeout : int, optional
        Request timeout in seconds, default is 10.

    Returns
    -------
    dict
        Dictionary containing weather attributes, source provenance, timestamp,
        and success/error status flags.
    """
    valid, err_msg = _validate_coordinates(latitude, longitude)
    if not valid:
        return {
            "success": False,
            "temperature": None,
            "humidity": None,
            "precipitation": None,
            "soil_moisture_m3m3": None,
            "soil_moisture_percentage": None,
            "weather_code": None,
            "timestamp": None,
            "source": "Open-Meteo (Invalid Coordinates)",
            "latitude": latitude,
            "longitude": longitude,
            "precipitation_sum_7d": None,
            "error": err_msg,
        }

    params = {
        "latitude": round(float(latitude), 4),
        "longitude": round(float(longitude), 4),
        "current": (
            "temperature_2m,relative_humidity_2m,precipitation,"
            "weather_code,soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,"
            "soil_moisture_3_to_9cm,soil_moisture_9_to_27cm"
        ),
        "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata",
    }

    url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        current = payload.get("current", {})
        daily = payload.get("daily", {})

        # Extract primary weather variables
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        precip = current.get("precipitation")
        weather_code = current.get("weather_code")
        raw_timestamp = current.get("time", "")

        # Format ISO timestamp into a human-readable display string
        if raw_timestamp:
            try:
                dt = datetime.fromisoformat(raw_timestamp)
                display_time = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                display_time = str(raw_timestamp)
        else:
            display_time = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Root-zone soil moisture calculation across available depths (0-27 cm)
        sm_layers = [
            current.get("soil_moisture_0_to_1cm"),
            current.get("soil_moisture_1_to_3cm"),
            current.get("soil_moisture_3_to_9cm"),
            current.get("soil_moisture_9_to_27cm"),
        ]
        valid_sm = [v for v in sm_layers if v is not None and isinstance(v, (int, float))]
        root_zone_sm = round(sum(valid_sm) / len(valid_sm), 4) if valid_sm else None

        # Convert volumetric fraction (m3/m3, typical saturation ~0.45) to relative moisture %
        if root_zone_sm is not None:
            # Scale 0.0 - 0.45 m3/m3 to approx 0 - 100% relative saturation
            rel_moisture = min(max(round((root_zone_sm / 0.45) * 100.0, 1), 5.0), 95.0)
        else:
            rel_moisture = None

        # 7-day cumulative precipitation sum
        daily_precip_list = daily.get("precipitation_sum", [])
        precip_7d = round(sum(p for p in daily_precip_list if isinstance(p, (int, float))), 1) if daily_precip_list else None

        return {
            "success": True,
            "temperature": round(float(temp), 1) if temp is not None else None,
            "humidity": round(float(humidity), 1) if humidity is not None else None,
            "precipitation": round(float(precip), 1) if precip is not None else 0.0,
            "soil_moisture_m3m3": root_zone_sm,
            "soil_moisture_percentage": rel_moisture,
            "weather_code": weather_code,
            "timestamp": display_time,
            "source": "Open-Meteo (Meteorological Model Estimate)",
            "is_estimate": True,
            "estimate_note": "Numerical weather model estimate; not a physical in-situ farm sensor reading.",
            "latitude": round(float(latitude), 4),
            "longitude": round(float(longitude), 4),
            "precipitation_sum_7d": precip_7d,
            "error": None,
        }

    except (HTTPError, URLError, TimeoutError, Exception) as err:
        return {
            "success": False,
            "temperature": None,
            "humidity": None,
            "precipitation": None,
            "soil_moisture_m3m3": None,
            "soil_moisture_percentage": None,
            "weather_code": None,
            "timestamp": None,
            "source": "Open-Meteo (Unavailable)",
            "latitude": latitude,
            "longitude": longitude,
            "precipitation_sum_7d": None,
            "error": f"Live weather API error: {err}",
        }
