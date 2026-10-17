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
            "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
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
        wind_speed = current.get("wind_speed_10m")
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
            "wind_speed_10m": round(float(wind_speed), 1) if wind_speed is not None else None,
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


@_cache_decorator
def get_weather_forecast(latitude: float, longitude: float, days: int = 7, timeout: int = 10) -> dict:
    """Fetch multi-day weather forecast (7 or 14-day) from Open-Meteo.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees.
    longitude : float
        Longitude in decimal degrees.
    days : int, optional
        Requested projection horizon (1 to 16, typically 7 or 14). Default is 7.
    timeout : int, optional
        Request timeout in seconds, default is 10.

    Returns
    -------
    dict
        Dictionary containing daily projections, actual available horizon,
        data source, and error status. Never fabricates or extrapolates missing days.
    """
    valid, err_msg = _validate_coordinates(latitude, longitude)
    if not valid:
        return {
            "success": False,
            "latitude": latitude,
            "longitude": longitude,
            "requested_days": days,
            "available_days": 0,
            "daily": [],
            "source": "Open-Meteo (Invalid Coordinates)",
            "is_forecast": True,
            "error": err_msg,
        }

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

    url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"
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
            items.append({
                "date": dates[i],
                "temperature_max": round(float(t_max[i]), 1) if i < len(t_max) and t_max[i] is not None else None,
                "temperature_min": round(float(t_min[i]), 1) if i < len(t_min) and t_min[i] is not None else None,
                "precipitation_sum": round(float(p_sum[i]), 1) if i < len(p_sum) and p_sum[i] is not None else None,
                "precipitation_probability_max": int(p_prob[i]) if i < len(p_prob) and p_prob[i] is not None else None,
                "weather_code": int(w_code[i]) if i < len(w_code) and w_code[i] is not None else None,
            })

        return {
            "success": True,
            "latitude": lat_r,
            "longitude": lon_r,
            "timezone": "Asia/Kolkata",
            "source": "Open-Meteo Numerical Weather Forecast",
            "is_forecast": True,
            "requested_days": forecast_days,
            "available_days": len(items),
            "daily": items,
            "disclaimer": (
                "Numerical meteorological forecast data for agronomic planning. "
                "Distinct from crop failure risk predictions and simulation models."
            ),
            "error": None,
        }

    except (HTTPError, URLError, TimeoutError, Exception) as err:
        return {
            "success": False,
            "latitude": lat_r,
            "longitude": lon_r,
            "requested_days": forecast_days,
            "available_days": 0,
            "daily": [],
            "source": "Open-Meteo (Unavailable)",
            "is_forecast": True,
            "error": f"Live weather forecast API error: {err}",
        }


@_cache_decorator
def reverse_geocode_place(latitude: float, longitude: float, timeout: int = 5) -> dict:
    """Reverse-geocode latitude and longitude into a structured human-readable place name."""
    is_valid, error_msg = _validate_coordinates(latitude, longitude)
    if not is_valid:
        return {"success": False, "place_name": f"{latitude}, {longitude}", "error": error_msg}

    lat_4 = round(float(latitude), 4)
    lon_4 = round(float(longitude), 4)

    # 1. Primary: Nominatim OpenStreetMap
    nominatim_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat_4}&lon={lon_4}&format=json&addressdetails=1"
    try:
        req = Request(nominatim_url, headers={"User-Agent": "AI-Crop-Failure-Advisory/2.0 (agri-dashboard)"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            addr = data.get("address", {})

            locality = (
                addr.get("quarter")
                or addr.get("suburb")
                or addr.get("neighbourhood")
                or addr.get("residential")
                or addr.get("village")
                or addr.get("town")
                or addr.get("hamlet")
            )
            city = addr.get("city") or addr.get("town") or addr.get("municipality")
            district = addr.get("state_district") or addr.get("county") or addr.get("district")
            state = addr.get("state")
            country = addr.get("country", "India")

            items = []
            seen = set()
            for part in [locality, city, district, state, country]:
                if not part or not str(part).strip():
                    continue
                p = str(part).strip()
                plower = p.lower()
                if plower in seen:
                    continue
                if city and district and p == district and city.lower() in plower:
                    continue
                items.append(p)
                seen.add(plower)

            place_name = ", ".join(items) if items else f"{lat_4}°N, {lon_4}°E"
            return {
                "success": True,
                "place_name": place_name,
                "locality": locality or city or f"{lat_4}°N, {lon_4}°E",
                "city": city or "",
                "state": state or "",
                "country": country,
                "provider": "OpenStreetMap Nominatim",
            }
    except Exception:
        pass

    # 2. Secondary fallback: BigDataCloud
    bdc_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat_4}&longitude={lon_4}&localityLanguage=en"
    try:
        req = Request(bdc_url, headers={"User-Agent": "AI-Crop-Failure-Advisory/2.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            locality = data.get("locality") or data.get("city")
            city = data.get("city") or locality
            state = data.get("principalSubdivision")
            country = data.get("countryName", "India")
            items = [p for p in [locality, city, state, country] if p]
            unique_items = []
            seen = set()
            for p in items:
                if p.lower() not in seen:
                    unique_items.append(p)
                    seen.add(p.lower())
            place_name = ", ".join(unique_items) if unique_items else f"{lat_4}°N, {lon_4}°E"
            return {
                "success": True,
                "place_name": place_name,
                "locality": locality or f"{lat_4}°N, {lon_4}°E",
                "city": city or "",
                "state": state or "",
                "country": country,
                "provider": "BigDataCloud",
            }
    except Exception:
        pass

    # 3. Fallback to coordinates
    return {
        "success": False,
        "place_name": f"{lat_4}°N, {lon_4}°E",
        "locality": f"{lat_4}°N, {lon_4}°E",
        "city": "",
        "state": "",
        "country": "India",
        "provider": "coordinate_fallback",
    }


