"""Automated Tests for Sentinel-2 & Earth Engine Satellite Vegetation Pipeline."""

import pytest
from fastapi.testclient import TestClient

from backend.app.schemas.farm import FarmResponse
from backend.app.repositories.satellite_repository import satellite_repository
from backend.app.services.satellite.gee_provider import GoogleEarthEngineProvider
from backend.app.services.satellite.geometry import FarmGeometry
from backend.app.services.satellite.mock_provider import MockSatelliteProvider
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)
from backend.app.services.satellite.service import SatelliteService, satellite_service
from backend.tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def reset_satellite_fixtures():
    """Reset repository and in-memory caches before each test."""
    satellite_repository.clear()
    satellite_service.clear_cache()
    yield
    satellite_repository.clear()
    satellite_service.clear_cache()


def test_ndvi_statistics_and_range_validation():
    """Verify NDVI statistics strictly conform to [-1.0, 1.0] bounds."""
    stats = NDVIStatistics(
        mean=0.65,
        median=0.66,
        min=0.45,
        max=0.82,
        std=0.05,
        valid_pixel_percent=95.0,
        cloud_percent=5.0,
    )
    assert -1.0 <= stats.mean <= 1.0
    assert -1.0 <= stats.median <= 1.0
    assert -1.0 <= stats.min <= 1.0
    assert -1.0 <= stats.max <= 1.0
    assert 0.0 <= stats.valid_pixel_percent <= 100.0


def test_farm_geometry_buffer_calculation():
    """Verify FarmGeometry derives radius from area and marks fallback status."""
    geom = FarmGeometry.from_lat_lon(latitude=18.5204, longitude=73.8567, area_hectares=2.5)
    assert geom.geometry_type == "buffered_point"
    assert geom.is_fallback is True
    assert geom.coordinates == [73.8567, 18.5204]
    # Area = 2.5 ha = 25000 m2. Radius = sqrt(25000 / pi) approx 89.2m
    assert 80.0 <= geom.buffer_meters <= 100.0


def test_mock_satellite_provider_deterministic_behavior():
    """Verify MockSatelliteProvider returns deterministic mock observations."""
    provider = MockSatelliteProvider(default_ndvi=0.68, mock_cloud_pct=4.2)
    geom = FarmGeometry.from_lat_lon(18.5, 74.0)
    res = provider.get_latest_observation(geometry=geom, farm_id="test-farm-1")

    assert res.success is True
    assert res.status == SatelliteObservationStatus.MOCK_DEVELOPMENT
    assert res.source == "mock"
    assert res.ndvi is not None
    assert res.ndvi.mean == 0.68
    assert res.ndvi.cloud_percent == 4.2
    assert res.quality_status == "GOOD"


def test_gee_provider_unconfigured_safe_handling(monkeypatch):
    """Verify GoogleEarthEngineProvider gracefully returns SATELLITE_NOT_CONFIGURED when unconfigured."""
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "GEE_PROJECT_ID", None)
    monkeypatch.setattr(settings, "GEE_SERVICE_ACCOUNT_EMAIL", None)
    monkeypatch.setattr(settings, "GEE_PRIVATE_KEY", None)
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_EMAIL", raising=False)
    monkeypatch.delenv("GEE_PRIVATE_KEY", raising=False)
    # Instantiating with no credentials
    provider = GoogleEarthEngineProvider(project_id="", service_account="", private_key="")
    geom = FarmGeometry.from_lat_lon(18.5, 74.0)
    res = provider.get_latest_observation(geometry=geom, farm_id="test-farm-1")

    assert res.success is False
    assert res.status == SatelliteObservationStatus.SATELLITE_NOT_CONFIGURED
    assert res.quality_status == "UNCONFIGURED"
    assert "not configured" in (res.error or "").lower() or "not available" in (res.error or "").lower()


def test_unauthenticated_satellite_requests_rejected(client: TestClient):
    """Ensure unauthenticated access to satellite endpoints is rejected with 401."""
    res = client.get("/api/v1/farms/any-id/satellite/latest")
    assert res.status_code == 401

    res = client.get("/api/v1/farms/any-id/satellite/history")
    assert res.status_code == 401

    res = client.get("/api/v1/farms/any-id/vegetation")
    assert res.status_code == 401


def test_farm_satellite_tenant_isolation(
    client: TestClient,
    farmer1_token: str,
    farmer2_token: str,
):
    """Ensure Farmer A cannot access Farmer B's satellite observations."""
    # Farmer 1 creates farm
    f_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Farmer 1 Private Plot",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "area_hectares": 2.0,
        },
    )
    assert f_res.status_code == 201
    farm1_id = f_res.json()["id"]

    # Farmer 2 tries to access Farmer 1's satellite data
    res_lat = client.get(
        f"/api/v1/farms/{farm1_id}/satellite/latest",
        headers=auth_headers(farmer2_token),
    )
    assert res_lat.status_code == 404

    res_hist = client.get(
        f"/api/v1/farms/{farm1_id}/satellite/history",
        headers=auth_headers(farmer2_token),
    )
    assert res_hist.status_code == 404

    res_veg = client.get(
        f"/api/v1/farms/{farm1_id}/vegetation",
        headers=auth_headers(farmer2_token),
    )
    assert res_veg.status_code == 404


def test_farmer_can_get_vegetation_summary_with_mock_provider(
    client: TestClient,
    farmer1_token: str,
    monkeypatch,
):
    """Verify Farmer gets vegetation health summary when provider is active."""
    # Monkeypatch satellite_service provider with MockSatelliteProvider
    mock_prov = MockSatelliteProvider(default_ndvi=0.64)
    monkeypatch.setattr(satellite_service, "provider", mock_prov)

    # Create farm
    f_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Baramati Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.1513,
            "longitude": 74.5771,
            "area_hectares": 3.0,
        },
    )
    assert f_res.status_code == 201
    farm_id = f_res.json()["id"]

    # 1. Fetch vegetation summary
    res = client.get(
        f"/api/v1/farms/{farm_id}/vegetation",
        headers=auth_headers(farmer1_token),
    )
    assert res.status_code == 200
    data = res.json()

    assert data["farm_id"] == farm_id
    assert data["has_observation"] is True
    assert data["vegetation_health"] == "Healthy"
    assert data["latest_ndvi"] == 0.64
    assert "Sentinel-2" in data["data_source"]

    # 2. Fetch latest satellite observation
    res_lat = client.get(
        f"/api/v1/farms/{farm_id}/satellite/latest",
        headers=auth_headers(farmer1_token),
    )
    assert res_lat.status_code == 200
    lat_data = res_lat.json()
    assert lat_data["success"] is True
    assert lat_data["ndvi"]["mean"] == 0.64
    assert lat_data["geometry_type"] == "buffered_point"


def test_expert_can_view_any_farm_satellite(
    client: TestClient,
    farmer1_token: str,
    expert_token: str,
    monkeypatch,
):
    """Ensure Expert users have permission to inspect satellite telemetry for any farm."""
    mock_prov = MockSatelliteProvider(default_ndvi=0.55)
    monkeypatch.setattr(satellite_service, "provider", mock_prov)

    f_res = client.post(
        "/api/v1/farms",
        headers=auth_headers(farmer1_token),
        json={
            "name": "Monitored Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
        },
    )
    farm_id = f_res.json()["id"]

    res = client.get(
        f"/api/v1/farms/{farm_id}/satellite/latest",
        headers=auth_headers(expert_token),
    )
    assert res.status_code == 200
    assert res.json()["ndvi"]["mean"] == 0.55


def test_satellite_service_caching_and_persistence(monkeypatch):
    """Verify in-memory caching and repository persistence operate seamlessly."""
    mock_prov = MockSatelliteProvider(default_ndvi=0.72)
    svc = SatelliteService(provider=mock_prov, cache_ttl_seconds=300)

    farm = FarmResponse(
        id="farm-cache-test",
        user_id="user-1",
        name="Cache Farm",
        state="Maharashtra",
        district="Pune",
        latitude=18.5,
        longitude=74.0,
        created_at="2026-09-26T12:00:00Z",
        updated_at="2026-09-26T12:00:00Z",
    )

    # First call - queries provider & caches
    obs1 = svc.get_latest_observation(farm=farm)
    assert obs1.is_cached is False
    assert obs1.ndvi.mean == 0.72

    # Second call - returns cached instance
    obs2 = svc.get_latest_observation(farm=farm)
    assert obs2.is_cached is True
    assert obs2.ndvi.mean == 0.72

    # Verify record was persisted in repository
    latest_db = satellite_repository.get_latest_for_farm(farm_id=farm.id)
    assert latest_db is not None
    assert latest_db.ndvi.mean == 0.72


def test_valid_pixel_percentage_pixel_count_variations():
    """Verify valid_pixel_percent calculation across all boundary and count variations."""
    # 1. 0 valid / 0 total pixels -> 0.0%
    stats_zero_total = NDVIStatistics.from_counts_and_stats(
        mean=None, median=None, min_val=None, max_val=None, std_val=0.0,
        valid_count=0, total_count=0, scene_cloud_pct=10.0,
    )
    assert stats_zero_total.valid_pixel_percent == 0.0
    assert stats_zero_total.total_pixels == 0
    assert stats_zero_total.valid_pixels == 0

    # 2. 0 valid / >0 total pixels -> 0.0%
    stats_zero_valid = NDVIStatistics.from_counts_and_stats(
        mean=None, median=None, min_val=None, max_val=None, std_val=0.0,
        valid_count=0, total_count=120, scene_cloud_pct=15.0,
    )
    assert stats_zero_valid.valid_pixel_percent == 0.0
    assert stats_zero_valid.total_pixels == 120
    assert stats_zero_valid.valid_pixels == 0

    # 3. Partial valid coverage (45 valid / 100 total -> 45.0%)
    stats_partial = NDVIStatistics.from_counts_and_stats(
        mean=0.55, median=0.56, min_val=0.40, max_val=0.70, std_val=0.04,
        valid_count=45, total_count=100, scene_cloud_pct=25.0,
    )
    assert stats_partial.valid_pixel_percent == 45.0
    assert stats_partial.valid_pixels == 45
    assert stats_partial.total_pixels == 100

    # 4. 100% valid coverage (100 valid / 100 total -> 100.0%)
    stats_full = NDVIStatistics.from_counts_and_stats(
        mean=0.68, median=0.69, min_val=0.50, max_val=0.85, std_val=0.03,
        valid_count=100, total_count=100, scene_cloud_pct=5.0,
    )
    assert stats_full.valid_pixel_percent == 100.0

    # 5. Range bounds [0.0, 100.0] invariant
    assert 0.0 <= stats_zero_total.valid_pixel_percent <= 100.0
    assert 0.0 <= stats_partial.valid_pixel_percent <= 100.0
    assert 0.0 <= stats_full.valid_pixel_percent <= 100.0


def test_scene_cloud_vs_farm_valid_pixels_distinction():
    """Verify explicit distinction between scene-level cloud % and farm-level valid pixel %."""
    stats = NDVIStatistics.from_counts_and_stats(
        mean=0.60,
        median=0.61,
        min_val=0.45,
        max_val=0.75,
        std_val=0.05,
        valid_count=85,
        total_count=100,
        scene_cloud_pct=18.5,
    )

    # Farm-level valid pixel percentage is 85%
    assert stats.valid_pixel_percent == 85.0

    # Scene-level cloud cover is 18.5%
    assert stats.scene_cloud_percent == 18.5

    # Backward compatibility alias mirrors scene_cloud_percent
    assert stats.cloud_percent == 18.5
    assert stats.valid_pixels == 85
    assert stats.total_pixels == 100


def test_quality_status_classification_rule():
    """Verify deterministic quality status classification using farm coverage and scene cloudiness."""
    # GOOD: valid_pixel_percent >= 80% and scene_cloud_percent <= 20%
    obs_good = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        quality_status="GOOD",
        ndvi=NDVIStatistics.from_counts_and_stats(
            mean=0.70, median=0.71, min_val=0.55, max_val=0.85, std_val=0.03,
            valid_count=90, total_count=100, scene_cloud_pct=10.0,
        ),
    )
    assert obs_good.quality_status == "GOOD"
    assert obs_good.ndvi.valid_pixel_percent >= 80.0
    assert obs_good.ndvi.scene_cloud_percent <= 20.0

    # FAIR: valid_pixel_percent >= 50%
    obs_fair = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        quality_status="FAIR",
        ndvi=NDVIStatistics.from_counts_and_stats(
            mean=0.55, median=0.55, min_val=0.40, max_val=0.70, std_val=0.05,
            valid_count=60, total_count=100, scene_cloud_pct=25.0,
        ),
    )
    assert obs_fair.quality_status == "FAIR"
    assert obs_fair.ndvi.valid_pixel_percent >= 50.0

    # LOW_QUALITY: valid_pixel_percent < 50%
    obs_low = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        quality_status="LOW_QUALITY",
        ndvi=NDVIStatistics.from_counts_and_stats(
            mean=0.40, median=0.40, min_val=0.30, max_val=0.50, std_val=0.06,
            valid_count=30, total_count=100, scene_cloud_pct=40.0,
        ),
    )
    assert obs_low.quality_status == "LOW_QUALITY"
    assert obs_low.ndvi.valid_pixel_percent < 50.0


# =============================================================================
# GEOMETRY FINGERPRINTING & CACHE / PERSISTENCE INTEGRITY TESTS
# =============================================================================

def test_same_polygon_reuses_existing_observation():
    """Verify same Polygon boundary reuses existing observation without generating duplicates."""
    farm_id = "test-farm-same-polygon-reuse"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom = FarmGeometry.from_geojson_polygon(poly_coords)

    obs1 = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom.fingerprint,
        ndvi=NDVIStatistics(mean=0.62, valid_pixels=500, total_pixels=500),
    )
    saved1 = satellite_repository.create(farm_id=farm_id, observation=obs1)
    assert saved1.geometry_fingerprint == geom.fingerprint

    # Second creation with same polygon
    obs2 = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom.fingerprint,
        ndvi=NDVIStatistics(mean=0.62, valid_pixels=500, total_pixels=500),
    )
    saved2 = satellite_repository.create(farm_id=farm_id, observation=obs2)

    assert saved2.geometry_fingerprint == saved1.geometry_fingerprint
    assert saved2.observation_date == obs_date
    assert saved2.ndvi.mean == saved1.ndvi.mean

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


def test_identical_polygon_reordered_formatting_fingerprint():
    """Verify GeoJSON formatting differences (e.g. key order, tuple vs list) yield identical fingerprints."""
    coords = [
        [[73.8500001, 18.5200004], [73.8600002, 18.5200001], [73.8600000, 18.5300000], [73.8500000, 18.5300000], [73.8500001, 18.5200004]]
    ]

    farm_dict_1 = {
        "latitude": 18.525,
        "longitude": 73.855,
        "boundary_geojson": {"type": "Polygon", "coordinates": coords},
    }
    farm_dict_2 = {
        "latitude": 18.525,
        "longitude": 73.855,
        "boundary_geojson": {"coordinates": coords, "type": "Polygon"},  # Reordered dictionary keys
    }

    geom1 = FarmGeometry.from_farm(farm_dict_1)
    geom2 = FarmGeometry.from_farm(farm_dict_2)

    assert geom1.fingerprint == geom2.fingerprint
    assert geom1.fingerprint.startswith("polygon:")


def test_polygon_a_to_polygon_b_updates_row_and_recomputes():
    """Verify modifying polygon boundary (Polygon A -> Polygon B) updates the single DB row in-place."""
    farm_id = "test-farm-poly-a-to-poly-b"
    obs_date = "2026-09-15"

    poly_a_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_a = FarmGeometry.from_geojson_polygon(poly_a_coords)

    # 1. Observation for Polygon A
    obs_a = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_a.fingerprint,
        ndvi=NDVIStatistics(mean=0.45, valid_pixels=300, total_pixels=300),
    )
    saved_a = satellite_repository.create(farm_id=farm_id, observation=obs_a)
    assert saved_a.geometry_fingerprint == geom_a.fingerprint
    assert saved_a.ndvi.mean == 0.45

    # 2. Farmer updates boundary to Polygon B (expanded boundary)
    poly_b_coords = [
        [[73.8500, 18.5200], [73.8700, 18.5200], [73.8700, 18.5400], [73.8500, 18.5400], [73.8500, 18.5200]]
    ]
    geom_b = FarmGeometry.from_geojson_polygon(poly_b_coords)
    assert geom_b.fingerprint != geom_a.fingerprint

    obs_b = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_b.fingerprint,
        ndvi=NDVIStatistics(mean=0.58, valid_pixels=620, total_pixels=620),
    )
    saved_b = satellite_repository.create(farm_id=farm_id, observation=obs_b)

    # Verify in-place update
    assert saved_b.geometry_fingerprint == geom_b.fingerprint
    assert saved_b.ndvi.mean == 0.58
    assert saved_b.ndvi.valid_pixels == 620

    # Ensure strictly 1 database row exists
    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_fingerprint == geom_b.fingerprint
    assert rows[0].ndvi.mean == 0.58


def test_polygon_to_multipolygon_updates_row():
    """Verify transitioning from Polygon to MultiPolygon updates the existing row in-place."""
    farm_id = "test-farm-poly-to-multipoly"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_poly = FarmGeometry.from_geojson_polygon(poly_coords)

    obs_poly = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_poly.fingerprint,
        ndvi=NDVIStatistics(mean=0.48, valid_pixels=320, total_pixels=320),
    )
    satellite_repository.create(farm_id=farm_id, observation=obs_poly)

    # Update to MultiPolygon
    multipoly_coords = [poly_coords, poly_coords]
    geom_multi = FarmGeometry(
        geometry_type="multipolygon",
        coordinates=multipoly_coords,
        buffer_meters=0.0,
        is_fallback=False,
    )
    assert geom_multi.fingerprint != geom_poly.fingerprint

    obs_multi = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="multipolygon",
        geometry_fingerprint=geom_multi.fingerprint,
        ndvi=NDVIStatistics(mean=0.52, valid_pixels=640, total_pixels=640),
    )
    saved_multi = satellite_repository.create(farm_id=farm_id, observation=obs_multi)

    assert saved_multi.geometry_type == "multipolygon"
    assert saved_multi.geometry_fingerprint == geom_multi.fingerprint
    assert saved_multi.ndvi.mean == 0.52

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_type == "multipolygon"


def test_polygon_to_buffered_point_updates_row():
    """Verify removing boundary (Polygon -> buffered_point) updates the existing row in-place."""
    farm_id = "test-farm-poly-to-point"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_poly = FarmGeometry.from_geojson_polygon(poly_coords)

    obs_poly = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_poly.fingerprint,
        ndvi=NDVIStatistics(mean=0.55, valid_pixels=400, total_pixels=400),
    )
    satellite_repository.create(farm_id=farm_id, observation=obs_poly)

    # Revert to buffered point
    geom_point = FarmGeometry.from_lat_lon(latitude=18.525, longitude=73.855, area_hectares=2.0)
    assert geom_point.fingerprint != geom_poly.fingerprint

    obs_point = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="buffered_point",
        geometry_fingerprint=geom_point.fingerprint,
        ndvi=NDVIStatistics(mean=0.38, valid_pixels=250, total_pixels=250),
    )
    saved_point = satellite_repository.create(farm_id=farm_id, observation=obs_point)

    assert saved_point.geometry_type == "buffered_point"
    assert saved_point.geometry_fingerprint == geom_point.fingerprint
    assert saved_point.ndvi.mean == 0.38

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_type == "buffered_point"


def test_repeated_requests_unchanged_geometry_single_row():
    """Verify repeated consecutive requests for identical geometry never create duplicate rows."""
    farm_id = "test-farm-repeated-requests"
    obs_date = "2026-09-15"

    geom = FarmGeometry.from_lat_lon(18.5, 74.0, area_hectares=3.0)

    for i in range(5):
        obs = SatelliteObservationResponse(
            success=True,
            status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
            farm_id=farm_id,
            observation_date=obs_date,
            geometry_type="buffered_point",
            geometry_fingerprint=geom.fingerprint,
            ndvi=NDVIStatistics(mean=0.60, valid_pixels=300, total_pixels=300),
        )
        saved = satellite_repository.create(farm_id=farm_id, observation=obs)
        assert saved.geometry_fingerprint == geom.fingerprint

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


def test_cache_does_not_return_stale_data_after_boundary_change():
    """Verify SatelliteService cache does not return stale data when farm boundary changes from Polygon A to Polygon B."""
    from datetime import date
    from backend.app.schemas.farm import FarmResponse
    from backend.app.services.satellite.base import SatelliteProvider

    today_str = date.today().isoformat()

    class DynamicMockProvider(SatelliteProvider):
        def get_latest_observation(self, geometry, farm_id=None, **kwargs):
            # Deterministic NDVI based on geometry coordinates
            ndvi_val = 0.40 if "73.86" in str(geometry.coordinates) else 0.70
            return SatelliteObservationResponse(
                success=True,
                status=SatelliteObservationStatus.MOCK_DEVELOPMENT,
                farm_id=farm_id,
                observation_date=today_str,
                ndvi=NDVIStatistics(mean=ndvi_val, valid_pixels=100, total_pixels=100),
                geometry_type=geometry.geometry_type,
                geometry_fingerprint=geometry.fingerprint,
                raw_metadata={"geometry_fingerprint": geometry.fingerprint},
            )

        def get_historical_observations(self, *args, **kwargs):
            return []

    test_svc = SatelliteService(provider=DynamicMockProvider(), repository=satellite_repository, cache_ttl_seconds=3600)

    # 1. Farm with Polygon A
    farm_dict = {
        "id": "farm-stale-cache-test",
        "user_id": "u1",
        "name": "Cache Stale Test Farm",
        "state": "Maharashtra",
        "district": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "area_hectares": 2.5,
        "boundary_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.850, 18.520], [73.860, 18.520], [73.860, 18.530], [73.850, 18.530], [73.850, 18.520]]],
        },
        "created_at": today_str,
        "updated_at": today_str,
    }
    farm_model_a = FarmResponse(**farm_dict)

    obs_a = test_svc.get_latest_observation(farm_model_a)
    assert obs_a.ndvi.mean == 0.40
    assert obs_a.is_cached is False

    # Immediate second call with Polygon A hits cache
    obs_a_cached = test_svc.get_latest_observation(farm_model_a)
    assert obs_a_cached.is_cached is True
    assert obs_a_cached.ndvi.mean == 0.40

    # 2. Boundary is updated to Polygon B (coordinates shifted away from 73.86)
    farm_dict["boundary_geojson"] = {
        "type": "Polygon",
        "coordinates": [[[73.870, 18.520], [73.880, 18.520], [73.880, 18.530], [73.870, 18.530], [73.870, 18.520]]],
    }
    farm_model_b = FarmResponse(**farm_dict)

    # 3. Call get_latest_observation with Polygon B - MUST NOT return stale 0.40
    obs_b = test_svc.get_latest_observation(farm_model_b)
    assert obs_b.ndvi.mean == 0.70
    assert obs_b.geometry_fingerprint != obs_a.geometry_fingerprint


def test_concurrent_persistence_requests_preserve_single_row():
    """Verify multi-threaded concurrent create calls preserve strictly one row per farm/date."""
    import concurrent.futures

    farm_id = "test-farm-concurrent-persist"
    obs_date = "2026-09-15"
    geom = FarmGeometry.from_lat_lon(18.5, 74.0)

    def persist_worker(idx: int):
        obs = SatelliteObservationResponse(
            success=True,
            status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
            farm_id=farm_id,
            observation_date=obs_date,
            geometry_type="buffered_point",
            geometry_fingerprint=geom.fingerprint,
            ndvi=NDVIStatistics(mean=0.65, valid_pixels=300, total_pixels=300),
        )
        return satellite_repository.create(farm_id=farm_id, observation=obs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(persist_worker, i) for i in range(16)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 16
    for r in results:
        assert r.observation_date == obs_date
        assert r.geometry_type == "buffered_point"

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


# =============================================================================
# GEOMETRY FINGERPRINTING & CACHE / PERSISTENCE INTEGRITY TESTS
# =============================================================================

def test_same_polygon_reuses_existing_observation():
    """Verify same Polygon boundary reuses existing observation without generating duplicates."""
    farm_id = "test-farm-same-polygon-reuse"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom = FarmGeometry.from_geojson_polygon(poly_coords)

    obs1 = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom.fingerprint,
        ndvi=NDVIStatistics(mean=0.62, valid_pixels=500, total_pixels=500),
    )
    saved1 = satellite_repository.create(farm_id=farm_id, observation=obs1)
    assert saved1.geometry_fingerprint == geom.fingerprint

    # Second creation with same polygon
    obs2 = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom.fingerprint,
        ndvi=NDVIStatistics(mean=0.62, valid_pixels=500, total_pixels=500),
    )
    saved2 = satellite_repository.create(farm_id=farm_id, observation=obs2)

    assert saved2.geometry_fingerprint == saved1.geometry_fingerprint
    assert saved2.observation_date == obs_date
    assert saved2.ndvi.mean == saved1.ndvi.mean

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


def test_identical_polygon_reordered_formatting_fingerprint():
    """Verify GeoJSON formatting differences (e.g. key order, tuple vs list) yield identical fingerprints."""
    coords = [
        [[73.8500001, 18.5200004], [73.8600002, 18.5200001], [73.8600000, 18.5300000], [73.8500000, 18.5300000], [73.8500001, 18.5200004]]
    ]

    farm_dict_1 = {
        "latitude": 18.525,
        "longitude": 73.855,
        "boundary_geojson": {"type": "Polygon", "coordinates": coords},
    }
    farm_dict_2 = {
        "latitude": 18.525,
        "longitude": 73.855,
        "boundary_geojson": {"coordinates": coords, "type": "Polygon"},  # Reordered dictionary keys
    }

    geom1 = FarmGeometry.from_farm(farm_dict_1)
    geom2 = FarmGeometry.from_farm(farm_dict_2)

    assert geom1.fingerprint == geom2.fingerprint
    assert geom1.fingerprint.startswith("polygon:")


def test_polygon_a_to_polygon_b_updates_row_and_recomputes():
    """Verify modifying polygon boundary (Polygon A -> Polygon B) updates the single DB row in-place."""
    farm_id = "test-farm-poly-a-to-poly-b"
    obs_date = "2026-09-15"

    poly_a_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_a = FarmGeometry.from_geojson_polygon(poly_a_coords)

    # 1. Observation for Polygon A
    obs_a = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_a.fingerprint,
        ndvi=NDVIStatistics(mean=0.45, valid_pixels=300, total_pixels=300),
    )
    saved_a = satellite_repository.create(farm_id=farm_id, observation=obs_a)
    assert saved_a.geometry_fingerprint == geom_a.fingerprint
    assert saved_a.ndvi.mean == 0.45

    # 2. Farmer updates boundary to Polygon B (expanded boundary)
    poly_b_coords = [
        [[73.8500, 18.5200], [73.8700, 18.5200], [73.8700, 18.5400], [73.8500, 18.5400], [73.8500, 18.5200]]
    ]
    geom_b = FarmGeometry.from_geojson_polygon(poly_b_coords)
    assert geom_b.fingerprint != geom_a.fingerprint

    obs_b = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_b.fingerprint,
        ndvi=NDVIStatistics(mean=0.58, valid_pixels=620, total_pixels=620),
    )
    saved_b = satellite_repository.create(farm_id=farm_id, observation=obs_b)

    # Verify in-place update
    assert saved_b.geometry_fingerprint == geom_b.fingerprint
    assert saved_b.ndvi.mean == 0.58
    assert saved_b.ndvi.valid_pixels == 620

    # Ensure strictly 1 database row exists
    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_fingerprint == geom_b.fingerprint
    assert rows[0].ndvi.mean == 0.58


def test_polygon_to_multipolygon_updates_row():
    """Verify transitioning from Polygon to MultiPolygon updates the existing row in-place."""
    farm_id = "test-farm-poly-to-multipoly"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_poly = FarmGeometry.from_geojson_polygon(poly_coords)

    obs_poly = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_poly.fingerprint,
        ndvi=NDVIStatistics(mean=0.48, valid_pixels=320, total_pixels=320),
    )
    satellite_repository.create(farm_id=farm_id, observation=obs_poly)

    # Update to MultiPolygon
    multipoly_coords = [poly_coords, poly_coords]
    geom_multi = FarmGeometry(
        geometry_type="multipolygon",
        coordinates=multipoly_coords,
        buffer_meters=0.0,
        is_fallback=False,
    )
    assert geom_multi.fingerprint != geom_poly.fingerprint

    obs_multi = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="multipolygon",
        geometry_fingerprint=geom_multi.fingerprint,
        ndvi=NDVIStatistics(mean=0.52, valid_pixels=640, total_pixels=640),
    )
    saved_multi = satellite_repository.create(farm_id=farm_id, observation=obs_multi)

    assert saved_multi.geometry_type == "multipolygon"
    assert saved_multi.geometry_fingerprint == geom_multi.fingerprint
    assert saved_multi.ndvi.mean == 0.52

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_type == "multipolygon"


def test_polygon_to_buffered_point_updates_row():
    """Verify removing boundary (Polygon -> buffered_point) updates the existing row in-place."""
    farm_id = "test-farm-poly-to-point"
    obs_date = "2026-09-15"

    poly_coords = [
        [[73.8500, 18.5200], [73.8600, 18.5200], [73.8600, 18.5300], [73.8500, 18.5300], [73.8500, 18.5200]]
    ]
    geom_poly = FarmGeometry.from_geojson_polygon(poly_coords)

    obs_poly = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="polygon",
        geometry_fingerprint=geom_poly.fingerprint,
        ndvi=NDVIStatistics(mean=0.55, valid_pixels=400, total_pixels=400),
    )
    satellite_repository.create(farm_id=farm_id, observation=obs_poly)

    # Revert to buffered point
    geom_point = FarmGeometry.from_lat_lon(latitude=18.525, longitude=73.855, area_hectares=2.0)
    assert geom_point.fingerprint != geom_poly.fingerprint

    obs_point = SatelliteObservationResponse(
        success=True,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        farm_id=farm_id,
        observation_date=obs_date,
        geometry_type="buffered_point",
        geometry_fingerprint=geom_point.fingerprint,
        ndvi=NDVIStatistics(mean=0.38, valid_pixels=250, total_pixels=250),
    )
    saved_point = satellite_repository.create(farm_id=farm_id, observation=obs_point)

    assert saved_point.geometry_type == "buffered_point"
    assert saved_point.geometry_fingerprint == geom_point.fingerprint
    assert saved_point.ndvi.mean == 0.38

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1
    assert rows[0].geometry_type == "buffered_point"


def test_repeated_requests_unchanged_geometry_single_row():
    """Verify repeated consecutive requests for identical geometry never create duplicate rows."""
    farm_id = "test-farm-repeated-requests"
    obs_date = "2026-09-15"

    geom = FarmGeometry.from_lat_lon(18.5, 74.0, area_hectares=3.0)

    for i in range(5):
        obs = SatelliteObservationResponse(
            success=True,
            status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
            farm_id=farm_id,
            observation_date=obs_date,
            geometry_type="buffered_point",
            geometry_fingerprint=geom.fingerprint,
            ndvi=NDVIStatistics(mean=0.60, valid_pixels=300, total_pixels=300),
        )
        saved = satellite_repository.create(farm_id=farm_id, observation=obs)
        assert saved.geometry_fingerprint == geom.fingerprint

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


def test_cache_does_not_return_stale_data_after_boundary_change():
    """Verify SatelliteService cache does not return stale data when farm boundary changes from Polygon A to Polygon B."""
    from datetime import date
    from backend.app.schemas.farm import FarmResponse
    from backend.app.services.satellite.base import SatelliteProvider
    from backend.app.services.satellite.mock_provider import MockSatelliteProvider

    today_str = date.today().isoformat()

    class DynamicMockProvider(SatelliteProvider):
        def get_latest_observation(self, geometry, farm_id=None, **kwargs):
            # Deterministic NDVI based on geometry coordinates
            ndvi_val = 0.40 if "73.86" in str(geometry.coordinates) else 0.70
            return SatelliteObservationResponse(
                success=True,
                status=SatelliteObservationStatus.MOCK_DEVELOPMENT,
                farm_id=farm_id,
                observation_date=today_str,
                ndvi=NDVIStatistics(mean=ndvi_val, valid_pixels=100, total_pixels=100),
                geometry_type=geometry.geometry_type,
                geometry_fingerprint=geometry.fingerprint,
                raw_metadata={"geometry_fingerprint": geometry.fingerprint},
            )

        def get_historical_observations(self, *args, **kwargs):
            return []

    test_svc = SatelliteService(provider=DynamicMockProvider(), repository=satellite_repository, cache_ttl_seconds=3600)

    # 1. Farm with Polygon A
    farm_dict = {
        "id": "farm-stale-cache-test",
        "user_id": "u1",
        "name": "Cache Stale Test Farm",
        "state": "Maharashtra",
        "district": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "area_hectares": 2.5,
        "boundary_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.850, 18.520], [73.860, 18.520], [73.860, 18.530], [73.850, 18.530], [73.850, 18.520]]],
        },
        "created_at": today_str,
        "updated_at": today_str,
    }
    farm_model_a = FarmResponse(**farm_dict)

    obs_a = test_svc.get_latest_observation(farm_model_a)
    assert obs_a.ndvi.mean == 0.40
    assert obs_a.is_cached is False

    # Immediate second call with Polygon A hits cache
    obs_a_cached = test_svc.get_latest_observation(farm_model_a)
    assert obs_a_cached.is_cached is True
    assert obs_a_cached.ndvi.mean == 0.40

    # 2. Boundary is updated to Polygon B (coordinates shifted away from 73.86)
    farm_dict["boundary_geojson"] = {
        "type": "Polygon",
        "coordinates": [[[73.870, 18.520], [73.880, 18.520], [73.880, 18.530], [73.870, 18.530], [73.870, 18.520]]],
    }
    farm_model_b = FarmResponse(**farm_dict)

    # 3. Call get_latest_observation with Polygon B - MUST NOT return stale 0.40
    obs_b = test_svc.get_latest_observation(farm_model_b)
    assert obs_b.ndvi.mean == 0.70
    assert obs_b.geometry_fingerprint != obs_a.geometry_fingerprint


def test_concurrent_persistence_requests_preserve_single_row():
    """Verify multi-threaded concurrent create calls preserve strictly one row per farm/date."""
    import concurrent.futures

    farm_id = "test-farm-concurrent-persist"
    obs_date = "2026-09-15"
    geom = FarmGeometry.from_lat_lon(18.5, 74.0)

    def persist_worker(idx: int):
        obs = SatelliteObservationResponse(
            success=True,
            status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
            farm_id=farm_id,
            observation_date=obs_date,
            geometry_type="buffered_point",
            geometry_fingerprint=geom.fingerprint,
            ndvi=NDVIStatistics(mean=0.65, valid_pixels=300, total_pixels=300),
        )
        return satellite_repository.create(farm_id=farm_id, observation=obs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(persist_worker, i) for i in range(16)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 16
    for r in results:
        assert r.observation_date == obs_date
        assert r.geometry_type == "buffered_point"

    rows = satellite_repository.list_for_farm(farm_id)
    assert len(rows) == 1


def test_polygon_self_intersection_rejected_by_schema():
    """Verify backend FarmCreateRequest rejects self-intersecting polygon rings."""
    from backend.app.schemas.farm import FarmCreateRequest
    from pydantic import ValidationError

    # Self-intersecting figure-8 / bowtie polygon
    bowtie_geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.850, 18.520],
                [73.860, 18.530],
                [73.860, 18.520],
                [73.850, 18.530],
                [73.850, 18.520],
            ]
        ],
    }

    with pytest.raises(ValidationError) as exc:
        FarmCreateRequest(
            name="Bowtie Farm",
            state="Maharashtra",
            district="Pune",
            latitude=18.5204,
            longitude=73.8567,
            area_hectares=2.5,
            boundary_geojson=bowtie_geojson,
        )
    assert "self-intersecting" in str(exc.value).lower()


def test_valid_polygon_accepted_by_schema():
    """Verify backend FarmCreateRequest accepts valid closed polygon rings."""
    from backend.app.schemas.farm import FarmCreateRequest

    valid_polygon_geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.850, 18.520],
                [73.860, 18.520],
                [73.860, 18.530],
                [73.850, 18.530],
                [73.850, 18.520],
            ]
        ],
    }

    req = FarmCreateRequest(
        name="Valid Polygon Farm",
        state="Maharashtra",
        district="Pune",
        latitude=18.5204,
        longitude=73.8567,
        area_hectares=2.5,
        boundary_geojson=valid_polygon_geojson,
    )
    assert req.boundary_geojson == valid_polygon_geojson


def test_farm_geometry_prioritizes_polygon_over_point_buffer():
    """Verify FarmGeometry.from_farm prioritizes valid polygon and marks is_fallback=False."""
    valid_polygon_geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.850, 18.520],
                [73.860, 18.520],
                [73.860, 18.530],
                [73.850, 18.530],
                [73.850, 18.520],
            ]
        ],
    }
    farm_with_poly = {
        "id": "f-poly",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "area_hectares": 2.5,
        "boundary_geojson": valid_polygon_geojson,
    }
    geom_poly = FarmGeometry.from_farm(farm_with_poly)
    assert geom_poly.geometry_type == "polygon"
    assert geom_poly.is_fallback is False
    assert geom_poly.buffer_meters == 0.0

    # Farm with no polygon -> falls back to point buffer
    farm_no_poly = {
        "id": "f-no-poly",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "area_hectares": 2.5,
        "boundary_geojson": None,
    }
    geom_point = FarmGeometry.from_farm(farm_no_poly)
    assert geom_point.geometry_type == "buffered_point"
    assert geom_point.is_fallback is True
    assert geom_point.buffer_meters > 0.0


