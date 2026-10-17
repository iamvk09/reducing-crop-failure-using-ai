"""Tests for Weather Provider Abstraction, WeatherService, Caching, and Endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.app.services.weather import (
    OpenMeteoProvider,
    WeatherService,
    weather_service,
)
from backend.tests.conftest import auth_headers


def create_test_farm(client: TestClient, token: str) -> str:
    """Helper to create a test farm for a user."""
    farm_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(token),
        json={
            "name": "Baramati Research Plot",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.1517,
            "longitude": 74.5772,
            "area_hectares": 3.0,
            "soil_type": "Black",
            "irrigation_level": "High",
        },
    )
    assert farm_res.status_code == 201
    return farm_res.json()["id"]


def test_open_meteo_provider_current_weather():
    """Ensure OpenMeteoProvider fetches and normalizes live weather."""
    provider = OpenMeteoProvider()
    res = provider.get_current_weather(latitude=18.5204, longitude=73.8567)

    assert res.latitude == 18.5204
    assert res.longitude == 73.8567
    assert res.is_forecast is False
    assert res.timezone == "Asia/Kolkata"
    if res.success:
        assert res.temperature is not None
        assert res.relative_humidity is not None
        assert "Open-Meteo" in res.source


def test_open_meteo_provider_forecast():
    """Ensure OpenMeteoProvider fetches multi-day forecast projections."""
    provider = OpenMeteoProvider()
    res = provider.get_forecast(latitude=18.5204, longitude=73.8567, days=5)

    assert res.is_forecast is True
    assert res.timezone == "Asia/Kolkata"
    if res.success:
        assert len(res.daily) == 5
        for item in res.daily:
            assert item.date != ""


def test_open_meteo_provider_invalid_coordinates():
    """Ensure provider rejects invalid coordinates gracefully."""
    provider = OpenMeteoProvider()
    res = provider.get_current_weather(latitude=195.0, longitude=73.8567)
    assert res.success is False
    assert res.error is not None
    assert "Latitude 195.0 out of range" in res.error


def test_weather_service_in_memory_caching():
    """Ensure WeatherService caches responses with coordinates key."""
    service = WeatherService(cache_ttl_seconds=300)
    service.clear_cache()

    # 1st call
    res1 = service.get_current_weather(latitude=18.5204, longitude=73.8567)
    assert res1.is_cached is False

    # 2nd call (same coordinates) -> cache hit
    if res1.success:
        res2 = service.get_current_weather(latitude=18.5204, longitude=73.8567)
        assert res2.is_cached is True
        assert res2.temperature == res1.temperature


def test_unauthenticated_weather_requests_rejected(client: TestClient):
    """Ensure all weather endpoints require authentication."""
    assert client.get("/api/v1/farms/some-farm-id/weather/current").status_code == 401
    assert client.get("/api/v1/farms/some-farm-id/weather/forecast").status_code == 401
    assert client.get("/api/v1/farms/some-farm-id/weather/history").status_code == 401
    assert client.get("/api/v1/weather/current?latitude=18.5&longitude=73.8").status_code == 401


def test_farm_weather_tenant_isolation(
    client: TestClient, farmer1_token: str, farmer2_token: str
):
    """Ensure Farmer 2 cannot query weather endpoints for Farmer 1's farm."""
    farm1_id = create_test_farm(client, farmer1_token)

    # Current weather
    res_curr = client.get(
        f"/api/v1/farms/{farm1_id}/weather/current",
        headers=auth_headers(farmer2_token),
    )
    assert res_curr.status_code == 404

    # Forecast
    res_fc = client.get(
        f"/api/v1/farms/{farm1_id}/weather/forecast",
        headers=auth_headers(farmer2_token),
    )
    assert res_fc.status_code == 404

    # History
    res_hist = client.get(
        f"/api/v1/farms/{farm1_id}/weather/history",
        headers=auth_headers(farmer2_token),
    )
    assert res_hist.status_code == 404


def test_farmer_can_get_current_weather_for_own_farm(
    client: TestClient, farmer1_token: str
):
    """Ensure Farmer 1 can retrieve live weather for their own registered farm."""
    farm1_id = create_test_farm(client, farmer1_token)

    res = client.get(
        f"/api/v1/farms/{farm1_id}/weather/current",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["farm_id"] == farm1_id
    assert data["latitude"] == 18.1517
    assert data["longitude"] == 74.5772
    assert data["is_forecast"] is False
    assert "Open-Meteo" in data["source"]


def test_farmer_can_get_weather_forecast_for_own_farm(
    client: TestClient, farmer1_token: str
):
    """Ensure Farmer 1 can retrieve multi-day weather forecast for their registered farm."""
    farm1_id = create_test_farm(client, farmer1_token)

    res = client.get(
        f"/api/v1/farms/{farm1_id}/weather/forecast?days=5",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["farm_id"] == farm1_id
    assert data["is_forecast"] is True
    assert "not a crop-failure risk assessment" in data["disclaimer"]
    if data["success"]:
        assert len(data["daily"]) == 5


def test_weather_history_persistence_and_retrieval(
    client: TestClient, farmer1_token: str
):
    """Ensure weather observations are persisted and retrievable via GET /weather/history."""
    farm1_id = create_test_farm(client, farmer1_token)

    # Fetch current weather to trigger observation persistence
    client.get(
        f"/api/v1/farms/{farm1_id}/weather/current",
        headers=auth_headers(farmer1_token),
    )

    # Retrieve history
    hist_res = client.get(
        f"/api/v1/farms/{farm1_id}/weather/history",
        headers=auth_headers(farmer1_token),
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 1
    assert history[0]["farm_id"] == farm1_id
    assert history[0]["is_forecast"] is False


def test_expert_can_view_any_farm_weather(
    client: TestClient, farmer1_token: str, expert_token: str
):
    """Ensure Experts have cross-farm visibility for weather and forecast data."""
    farm1_id = create_test_farm(client, farmer1_token)

    res_curr = client.get(
        f"/api/v1/farms/{farm1_id}/weather/current",
        headers=auth_headers(expert_token),
    )
    assert res_curr.status_code == 200

    res_fc = client.get(
        f"/api/v1/farms/{farm1_id}/weather/forecast",
        headers=auth_headers(expert_token),
    )
    assert res_fc.status_code == 200


def test_reverse_geocode_endpoint(client: TestClient, farmer1_token: str):
    """Verify reverse-geocode resolves coordinates to prominent human-readable place name and address hierarchy."""
    res = client.get(
        "/api/v1/weather/reverse-geocode?latitude=12.9081&longitude=77.5833",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "latitude" in data
    assert "longitude" in data
    assert "place_name" in data
    assert "locality" in data
    assert "Karnataka" in data["state"]
    # Check prominent place name formatting
    assert "Bengaluru" in data["place_name"] or "JP Nagar" in data["place_name"]

    # Verify coordinate-rounded caching (nearby within ~100m hits same cached entry)
    res_cached = client.get(
        "/api/v1/weather/reverse-geocode?latitude=12.9082&longitude=77.5834",
        headers=auth_headers(farmer1_token),
    )
    assert res_cached.status_code == 200
    assert res_cached.json()["place_name"] == data["place_name"]


def test_reverse_geocode_failure_graceful_fallback(client: TestClient, farmer1_token: str, monkeypatch):
    """Verify reverse-geocode gracefully returns formatted coordinates when providers fail."""
    from backend.app.api.routes import weather as weather_routes

    def mock_urlopen_fail(*args, **kwargs):
        raise TimeoutError("Simulated provider outage")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_fail)

    res = client.get(
        "/api/v1/weather/reverse-geocode?latitude=45.1234&longitude=12.5678",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "45.1234°N, 12.5678°E" in data["place_name"]
    assert data["provider"] == "coordinate_fallback"


def test_direct_coords_weather_includes_wind_speed(client: TestClient, farmer1_token: str):
    """Verify coordinate-based live weather returns normalized wind_speed_10m and units."""
    res = client.get(
        "/api/v1/weather/current?latitude=18.5204&longitude=73.8567",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "wind_speed_10m" in data
    assert "temperature" in data
    assert "relative_humidity" in data
    assert "precipitation" in data
    assert "soil_moisture_m3m3" in data


def test_user_location_weather_never_alters_registered_farm_coordinates(
    client: TestClient, farmer1_token: str
):
    """Verify fetching weather for user's travelling location never changes registered farm plot coordinates."""
    # 1. Farmer creates farm in Pune (18.1517, 74.5772)
    farm_id = create_test_farm(client, farmer1_token)
    
    # 2. Farmer travels to Amritsar and queries user location weather (31.6340, 74.8723)
    user_weather_res = client.get(
        "/api/v1/weather/current?latitude=31.6340&longitude=74.8723",
        headers=auth_headers(farmer1_token),
    )
    assert user_weather_res.status_code == 200
    user_weather = user_weather_res.json()
    assert user_weather["latitude"] == 31.6340
    assert user_weather["longitude"] == 74.8723

    # 3. Verify farm coordinates remain completely unchanged in database
    farm_get = client.get(f"/api/v1/farms/{farm_id}", headers=auth_headers(farmer1_token))
    assert farm_get.status_code == 200
    farm_data = farm_get.json()
    assert farm_data["latitude"] == 18.1517
    assert farm_data["longitude"] == 74.5772

    # 4. Verify farm-specific weather still evaluates at farm coordinates (18.1517, 74.5772)
    farm_weather_res = client.get(
        f"/api/v1/farms/{farm_id}/weather/current",
        headers=auth_headers(farmer1_token),
    )
    assert farm_weather_res.status_code == 200
    farm_weather = farm_weather_res.json()
    assert farm_weather["latitude"] == 18.1517
    assert farm_weather["longitude"] == 74.5772

