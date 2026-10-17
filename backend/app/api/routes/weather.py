"""Direct coordinate-based meteorological query routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.app.api.deps import get_any_authenticated_user, get_weather_svc
from backend.app.core.security import AuthenticatedUser
from backend.app.services.weather import (
    CurrentWeatherResponse,
    WeatherForecastResponse,
    WeatherService,
)

router = APIRouter(prefix="/weather", tags=["Weather Service"])


@router.get("/current", response_model=CurrentWeatherResponse, summary="Get Live Weather by Coordinates")
def get_current_weather_by_coords(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    weather_svc: WeatherService = Depends(get_weather_svc),
) -> CurrentWeatherResponse:
    """Retrieve normalized live weather observations for given coordinate centroid."""
    return weather_svc.get_current_weather(latitude=latitude, longitude=longitude)


@router.get("/forecast", response_model=WeatherForecastResponse, summary="Get Multi-Day Weather Forecast by Coordinates")
def get_weather_forecast_by_coords(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    days: int = Query(7, ge=1, le=16, description="Number of projection days"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    weather_svc: WeatherService = Depends(get_weather_svc),
) -> WeatherForecastResponse:
    """Retrieve multi-day numerical weather forecast projections for given coordinate centroid."""
    return weather_svc.get_forecast(latitude=latitude, longitude=longitude, days=days)


# In-memory LRU cache keyed by (round(lat, 3), round(lon, 3)) to respect provider policies and avoid redundant requests
_GEOCODE_CACHE: dict = {}
_MAX_CACHE_SIZE = 500


@router.get("/reverse-geocode", summary="Reverse geocode coordinates to human-readable place name")
def reverse_geocode_coords(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
) -> dict:
    """Resolve coordinates into human-readable locality, city/town, district, state, and country."""
    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    # Cache key rounded to ~110m resolution (3 decimal places)
    cache_key = (round(latitude, 3), round(longitude, 3))
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    lat_4 = round(latitude, 4)
    lon_4 = round(longitude, 4)

    # 1. Primary Provider: OpenStreetMap Nominatim (rich hierarchy)
    nominatim_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat_4}&lon={lon_4}&format=json&addressdetails=1"
    try:
        req = Request(nominatim_url, headers={"User-Agent": "AI-Crop-Failure-Advisory/2.0 (agri-dashboard)"})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            addr = data.get("address", {})

            # Locality extraction (suburb, neighbourhood, quarter, village, hamlet, town)
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

            # Build deduplicated, clean place name (e.g., 'JP Nagar, Bengaluru, Karnataka, India')
            items = []
            seen = set()
            for part in [locality, city, district, state, country]:
                if not part or not str(part).strip():
                    continue
                p = str(part).strip()
                plower = p.lower()
                if plower in seen:
                    continue
                # If district name contains city name (e.g. 'Bengaluru Urban' when city is 'Bengaluru'), omit district to keep clean
                if city and district and p == district and city.lower() in plower:
                    continue
                items.append(p)
                seen.add(plower)

            place_name = ", ".join(items) if items else f"{lat_4}°N, {lon_4}°E"

            res = {
                "success": True,
                "latitude": lat_4,
                "longitude": lon_4,
                "place_name": place_name,
                "locality": locality or city or district or f"{lat_4}°N, {lon_4}°E",
                "city": city or district or "",
                "district": district or "",
                "state": state or "",
                "country": country,
                "display_name": place_name,
                "provider": "OpenStreetMap Nominatim",
            }

            if len(_GEOCODE_CACHE) >= _MAX_CACHE_SIZE:
                _GEOCODE_CACHE.pop(next(iter(_GEOCODE_CACHE)))
            _GEOCODE_CACHE[cache_key] = res
            return res
    except Exception:
        pass

    # 2. Secondary Fallback Provider: BigDataCloud client API
    bdc_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat_4}&longitude={lon_4}&localityLanguage=en"
    try:
        req = Request(bdc_url, headers={"User-Agent": "AI-Crop-Failure-Advisory/2.0"})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            locality = data.get("locality") or data.get("city")
            city = data.get("city") or locality
            state = data.get("principalSubdivision")
            country = data.get("countryName", "India")

            items = [p for p in [locality, city, state, country] if p]
            # Deduplicate preserving order
            unique_items = []
            seen = set()
            for p in items:
                if p.lower() not in seen:
                    unique_items.append(p)
                    seen.add(p.lower())
            place_name = ", ".join(unique_items) if unique_items else f"{lat_4}°N, {lon_4}°E"

            res = {
                "success": True,
                "latitude": lat_4,
                "longitude": lon_4,
                "place_name": place_name,
                "locality": locality or city or f"{lat_4}°N, {lon_4}°E",
                "city": city or "",
                "district": "",
                "state": state or "",
                "country": country,
                "display_name": place_name,
                "provider": "BigDataCloud",
            }
            if len(_GEOCODE_CACHE) >= _MAX_CACHE_SIZE:
                _GEOCODE_CACHE.pop(next(iter(_GEOCODE_CACHE)))
            _GEOCODE_CACHE[cache_key] = res
            return res
    except Exception:
        pass

    # 3. Graceful Fallback: Clean Coordinate formatting
    fallback_res = {
        "success": False,
        "latitude": lat_4,
        "longitude": lon_4,
        "place_name": f"{lat_4}°N, {lon_4}°E",
        "locality": f"{lat_4}°N, {lon_4}°E",
        "city": "",
        "district": "",
        "state": "",
        "country": "India",
        "display_name": f"{lat_4}°N, {lon_4}°E",
        "provider": "coordinate_fallback",
    }
    return fallback_res


