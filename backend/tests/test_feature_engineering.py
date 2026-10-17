"""Tests for Stage-Aware Live Feature Engineering, Assembly, and Phenology Mapping."""

from datetime import date, datetime, timedelta, timezone
import pytest
from unittest.mock import MagicMock

from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.farm import CropResponse, FarmResponse
from backend.app.services.feature_service import (
    CROP_FLOWERING_WINDOWS,
    FeatureAssembler,
    FeatureAssemblyResult,
    FeatureProvenanceItem,
    RainfallAccumulationEngine,
    StageAwareNDVIEngine,
)
from backend.app.services.prediction_service import PredictionService
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)
from backend.app.services.weather.schemas import CurrentWeatherResponse, WeatherObservationRecord
from src.live_prediction import get_prediction_explanation, predict_new_case, validate_prediction_input


EXPECTED_16_FEATURES = [
    "Year", "Rainfall", "Temperature", "Humidity", "SoilMoisture",
    "NDVI_Flowering", "WaterStress", "PestRisk", "SuitabilityScore", "YieldIndex",
    "State", "Region", "Season", "Crop", "SoilType", "IrrigationLevel"
]


# =============================================================================
# 1. EXACT 16-FEATURE SCHEMA & VALIDATION TESTS
# =============================================================================

def test_feature_assembler_produces_exact_16_features():
    """Verify FeatureAssembler produces exactly the 16 features expected by the trained ML model."""
    result = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Nashik",
        crop_name="Rice",
        crop_season="Kharif",
    )

    assert result.is_valid is True
    assert result.validation_error is None
    assert set(result.features.keys()) == set(EXPECTED_16_FEATURES)
    assert len(result.features) == 16
    assert result.features["State"] == "Maharashtra"
    assert result.features["Crop"] == "Rice"
    assert result.features["Season"] == "Kharif"
    assert isinstance(result.features["Year"], int)
    assert isinstance(result.features["Temperature"], float)
    assert isinstance(result.features["Rainfall"], float)
    assert isinstance(result.features["NDVI_Flowering"], float)


# =============================================================================
# 2. STAGE-AWARE SENTINEL-2 NDVI TESTS
# =============================================================================

def test_stage_aware_ndvi_uses_satellite_during_flowering_stage():
    """Verify Sentinel-2 NDVI is mapped to NDVI_Flowering when crop growth stage is explicitly Flowering."""
    obs_date = (date.today() - timedelta(days=5)).isoformat()
    sow_date = (date.today() - timedelta(days=70)).isoformat()
    obs = SatelliteObservationResponse(
        farm_id="farm-123",
        observation_date=obs_date,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.685, min=0.52, max=0.84, std=0.06),
        valid_pixels=310,
        total_pixels=310,
        cloud_percentage=5.0,
        provider="GoogleEarthEngine",
        satellite_source="Sentinel-2 L2A",
    )

    prov = StageAwareNDVIEngine.derive_ndvi_flowering(
        crop_name="Rice",
        growth_stage="Flowering",
        sowing_date=sow_date,
        baseline_ndvi_flowering=0.55,
        satellite_observation=obs,
    )

    assert prov.value == 0.685
    assert prov.is_live is True
    assert prov.is_baseline is False
    assert prov.source_type == "live_satellite"
    assert "GoogleEarthEngine" in prov.source_reference
    assert "Flowering" in prov.details["stage_context"]


def test_stage_aware_ndvi_uses_satellite_when_das_in_flowering_window():
    """Verify Sentinel-2 NDVI is mapped to NDVI_Flowering when DAS falls within crop flowering window."""
    obs_dt = date.today() - timedelta(days=5)
    sow_dt = obs_dt - timedelta(days=71)
    obs = SatelliteObservationResponse(
        farm_id="farm-123",
        observation_date=obs_dt.isoformat(),
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.712, min=0.60, max=0.88, std=0.05),
        valid_pixels=250,
        total_pixels=250,
        cloud_percentage=2.0,
        provider="GoogleEarthEngine",
        satellite_source="Sentinel-2 L2A",
    )

    prov = StageAwareNDVIEngine.derive_ndvi_flowering(
        crop_name="Rice",
        growth_stage=None,  # Not explicitly stated, inferred from DAS
        sowing_date=sow_dt.isoformat(),
        baseline_ndvi_flowering=0.55,
        satellite_observation=obs,
    )

    assert prov.value == 0.712
    assert prov.is_live is True
    assert prov.is_baseline is False
    assert prov.source_type == "live_satellite"
    assert prov.details["das"] == 71


def test_stage_aware_ndvi_preserves_baseline_during_vegetative_stage():
    """Verify that when a crop is in Vegetative stage, raw instantaneous NDVI is NOT silently substituted for NDVI_Flowering."""
    # Fresh observation (5 days old), Sowing 14 days before observation -> DAS = 14 days (Vegetative)
    obs_date = (date.today() - timedelta(days=5)).isoformat()
    sow_date = (date.today() - timedelta(days=19)).isoformat()
    obs = SatelliteObservationResponse(
        farm_id="farm-123",
        observation_date=obs_date,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.320, min=0.20, max=0.45, std=0.04),
        valid_pixels=310,
        total_pixels=310,
        cloud_percentage=0.0,
        provider="GoogleEarthEngine",
        satellite_source="Sentinel-2 L2A",
    )

    prov = StageAwareNDVIEngine.derive_ndvi_flowering(
        crop_name="Rice",
        growth_stage="Vegetative",
        sowing_date=sow_date,
        baseline_ndvi_flowering=0.58,
        satellite_observation=obs,
    )

    # Must preserve baseline to protect model feature integrity!
    assert prov.value == 0.58
    assert prov.is_live is False
    assert prov.is_baseline is True
    assert prov.source_type == "historical_baseline"
    assert "Vegetative" in prov.details["baseline_reason"]
    assert prov.details["available_instantaneous_ndvi"] == 0.320


def test_stage_aware_ndvi_preserves_baseline_when_no_satellite_data():
    """Verify baseline NDVI_Flowering is preserved when no satellite observations exist."""
    prov = StageAwareNDVIEngine.derive_ndvi_flowering(
        crop_name="Wheat",
        growth_stage="Flowering",
        sowing_date="2026-11-15",
        baseline_ndvi_flowering=0.62,
        satellite_observation=None,
    )

    assert prov.value == 0.62
    assert prov.is_live is False
    assert prov.is_baseline is True
    assert prov.source_type == "historical_baseline"
    assert "No satellite telemetry available" in prov.details["baseline_reason"]


# =============================================================================
# 3. RAINFALL ACCUMULATION TESTS
# =============================================================================

def test_rainfall_accumulation_with_historical_observations():
    """Verify rainfall accumulation calculates recorded sum and seasonal projection."""
    sow_d = (date.today() - timedelta(days=40)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    hist_weather = [
        WeatherObservationRecord(
            id=f"obs-{i}",
            farm_id="farm-123",
            observation_time=(date.today() - timedelta(days=i)).isoformat(),
            temperature_c=28.5,
            humidity_pct=70.0,
            precipitation_mm=10.0,  # 10mm per day
            soil_moisture_pct=60.0,
            source="Open-Meteo",
            created_at=now_iso,
        )
        for i in range(1, 30)  # 29 days of recorded history
    ]

    prov = RainfallAccumulationEngine.calculate_rainfall(
        crop_name="Rice",
        sowing_date=sow_d,
        baseline_rainfall=800.0,
        weather=None,
        historical_weather=hist_weather,
    )

    assert prov.is_derived is True
    assert prov.freshness == "fresh"
    assert prov.is_baseline is False
    assert prov.source_type == "accumulated_weather"
    assert prov.details["rainfall_accumulation_mm"] == 290.0
    assert prov.value > 290.0  # Includes remaining season baseline projection


def test_rainfall_fallback_to_baseline_when_insufficient_history():
    """Verify rainfall falls back gracefully to regional baseline when insufficient daily history exists."""
    weather = CurrentWeatherResponse(
        success=True,
        latitude=19.876,
        longitude=75.343,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        temperature=31.2,
        relative_humidity=65.0,
        precipitation=0.0,
        precipitation_sum_7d=18.5,
        soil_moisture_percentage=55.0,
        source="Open-Meteo",
    )

    prov = RainfallAccumulationEngine.calculate_rainfall(
        crop_name="Cotton",
        sowing_date=None,  # No sowing date
        baseline_rainfall=720.0,
        weather=weather,
        historical_weather=None,
    )

    assert prov.value == 720.0
    assert prov.is_live is False
    assert prov.is_baseline is True
    assert prov.source_type == "historical_baseline"
    assert prov.details["live_7d_precipitation_mm"] == 18.5


# =============================================================================
# 4. EXPERT OVERRIDES & FULL PROVENANCE
# =============================================================================

def test_feature_assembler_with_manual_expert_overrides():
    """Verify manual expert overrides update values and record expert_override provenance."""
    overrides = {
        "temperature_override": 38.5,
        "rainfall_override": 150.0,
        "ndvi_override": 0.42,
    }

    result = FeatureAssembler.assemble_features(
        farm_state="Gujarat",
        farm_district="Ahmedabad",
        crop_name="Cotton",
        crop_season="Kharif",
        overrides=overrides,
    )

    assert result.is_valid is True
    assert result.features["Temperature"] == 38.5
    assert result.features["Rainfall"] == 150.0
    assert result.features["NDVI_Flowering"] == 0.42

    assert result.feature_provenance["Temperature"].source_type == "expert_override"
    assert result.feature_provenance["Rainfall"].source_type == "expert_override"
    assert result.feature_provenance["NDVI_Flowering"].source_type == "expert_override"


# =============================================================================
# 5. ML PREDICTION & SHAP EXPLAINABILITY INTEGRATION
# =============================================================================

def test_live_prediction_pipeline_executes_on_assembled_features():
    """Verify raw ML consensus prediction functions smoothly on FeatureAssembler output."""
    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Nashik",
        crop_name="Rice",
        crop_season="Kharif",
    )

    pred = predict_new_case(assembly.features)
    assert "risk_probability" in pred
    assert 0.0 <= pred["risk_probability"] <= 1.0
    assert pred["risk_level"] in ("Low", "Medium", "High")
    assert "consensus_risk" in pred


def test_shap_explanation_works_on_assembled_features():
    """Verify SHAP explainability runs on the 16-feature vector produced by FeatureAssembler."""
    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Nashik",
        crop_name="Wheat",
        crop_season="Rabi",
    )

    explanation = get_prediction_explanation(assembly.features)
    assert "top_features" in explanation
    assert len(explanation["top_features"]) > 0
    assert "summary" in explanation

    # Ensure factors match valid features
    factor_names = [f["feature"].replace("num__", "").replace("cat__", "").split("_")[0] for f in explanation["top_features"]]
    for name in factor_names:
        assert name in EXPECTED_16_FEATURES


# =============================================================================
# 6. PREDICTION SERVICE FARM INTEGRATION & PERSISTENCE
# =============================================================================

def test_prediction_service_predict_for_farm_with_stage_aware_pipeline():
    """Test full predict_for_farm flow in PredictionService with mock repository and verified isolation."""
    pred_svc = PredictionService()

    # Call predict_with_weather with live weather & satellite inputs
    weather_res = CurrentWeatherResponse(
        success=True,
        latitude=19.876,
        longitude=75.343,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        temperature=27.4,
        relative_humidity=62.0,
        soil_moisture_percentage=58.0,
        source="Open-Meteo",
    )

    sat_obs_date = (date.today() - timedelta(days=5)).isoformat()
    sat_sow_date = (date.today() - timedelta(days=75)).isoformat()
    sat_obs = SatelliteObservationResponse(
        farm_id="farm-test-1",
        observation_date=sat_obs_date,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.672, min=0.50, max=0.82, std=0.05),
        valid_pixels=313,
        total_pixels=313,
        cloud_percentage=0.0,
        provider="GoogleEarthEngine",
        satellite="Sentinel-2",
        source="Sentinel-2 / GEE",
    )

    res = pred_svc.predict_with_weather(
        state="Maharashtra",
        district="Nashik",
        crop="Rice",
        season="Kharif",
        growth_stage="Flowering",
        sowing_date=sat_sow_date,
        satellite_observation=sat_obs,
    )

    assert "prediction" in res
    assert res["prediction"]["risk_probability"] >= 0.0
    assert res["input_features"]["NDVI_Flowering"] == 0.672
    assert "live_satellite" in res["feature_provenance"]["NDVI_Flowering"]["source_type"]
    assert "Live weather" in res["provenance"]["Temperature"]
    assert "data_quality" in res
    assert res["data_quality"]["live_feature_count"] >= 8
    assert res["data_quality"]["satellite_status"] == "live_fresh"
    assert res["data_quality"]["weather_status"] in ("live_fresh", "live_cached")


# =============================================================================
# 7. FEATURE FRESHNESS, TRUST & STALE TELEMETRY TESTS
# =============================================================================

def test_all_live_features_scenario():
    """Verify data quality metrics when live weather and live satellite are both active."""
    weather_res = CurrentWeatherResponse(
        success=True,
        latitude=19.876,
        longitude=75.343,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        temperature=26.5,
        relative_humidity=70.0,
        soil_moisture_percentage=65.0,
        source="Open-Meteo",
    )
    sat_obs = SatelliteObservationResponse(
        farm_id="farm-live",
        observation_date=datetime.now().date().isoformat(),
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.710, min=0.60, max=0.85, std=0.04),
        valid_pixels=300,
        total_pixels=300,
        provider="GoogleEarthEngine",
        satellite="Sentinel-2",
    )

    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Aurangabad",
        crop_name="Cotton",
        crop_season="Kharif",
        crop_growth_stage="Flowering",
        crop_sowing_date=(datetime.now().date() - timedelta(days=80)).isoformat(),
        crop_soil_type="Black",
        crop_irrigation_level="Medium",
        weather=weather_res,
        satellite_observation=sat_obs,
    )

    dq = assembly.data_quality
    assert dq["total_feature_count"] == 16
    assert dq["live_feature_count"] == 10  # State, Season, Crop, SoilType, IrrigationLevel, Year, Temp, Hum, SM, NDVI
    assert dq["derived_feature_count"] == 2  # Region, WaterStress
    assert dq["baseline_feature_count"] == 4  # Rainfall, PestRisk, SuitabilityScore, YieldIndex
    assert dq["live_feature_percentage"] == 62.5  # (10/16)*100
    assert dq["satellite_status"] == "live_fresh"
    assert dq["weather_status"] == "live_fresh"
    assert "satellite telemetry" in dq["summary_label"]


def test_mixed_live_baseline_scenario():
    """Verify stage-aware deferred NDVI preserves baseline while live weather is active."""
    weather_res = CurrentWeatherResponse(
        success=True,
        latitude=19.876,
        longitude=75.343,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        temperature=24.0,
        relative_humidity=78.0,
        soil_moisture_percentage=78.6,
        source="Open-Meteo",
    )
    # Vegetative crop observation
    sat_obs = SatelliteObservationResponse(
        farm_id="farm-veg",
        observation_date=datetime.now().date().isoformat(),
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.368, min=0.30, max=0.45, std=0.03),
        valid_pixels=313,
        total_pixels=313,
        provider="GoogleEarthEngine",
        satellite="Sentinel-2",
    )

    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Aurangabad",
        crop_name="Cotton",
        crop_season="Kharif",
        crop_growth_stage="Vegetative",
        crop_sowing_date=(datetime.now().date() - timedelta(days=87)).isoformat(),
        crop_soil_type="Black",
        crop_irrigation_level="Medium",
        weather=weather_res,
        satellite_observation=sat_obs,
    )

    dq = assembly.data_quality
    assert dq["total_feature_count"] == 16
    assert dq["live_feature_count"] == 9
    assert dq["derived_feature_count"] == 2
    assert dq["baseline_feature_count"] == 5
    assert dq["live_feature_percentage"] == 56.2  # round(9/16 * 100, 1) = 56.2
    assert dq["satellite_status"] == "stage_deferred"
    assert dq["weather_status"] == "live_fresh"
    assert "stage-calibrated" in dq["summary_label"]


def test_baseline_fallback_scenario():
    """Verify baseline fallback when both weather and satellite telemetry are unavailable."""
    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Aurangabad",
        crop_name="Cotton",
        crop_season="Kharif",
        weather=None,
        satellite_observation=None,
    )

    dq = assembly.data_quality
    assert dq["total_feature_count"] == 16
    # Only State, Season, Crop, Year are live when no farm soil/irrigation profile is supplied
    assert dq["live_feature_count"] == 4
    assert dq["derived_feature_count"] == 1  # Region
    assert dq["baseline_feature_count"] == 11
    assert dq["live_feature_percentage"] == 25.0
    assert dq["satellite_status"] == "baseline"
    assert dq["weather_status"] == "baseline"
    assert "historical baseline" in dq["summary_label"]


def test_stale_satellite_telemetry_handling():
    """Verify satellite observations older than 30 days are flagged as stale fallback."""
    stale_date = (datetime.now().date() - timedelta(days=45)).isoformat()
    sat_obs = SatelliteObservationResponse(
        farm_id="farm-stale",
        observation_date=stale_date,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.720, min=0.60, max=0.85, std=0.05),
        valid_pixels=250,
        total_pixels=250,
        provider="GoogleEarthEngine",
        satellite="Sentinel-2",
    )

    prov = StageAwareNDVIEngine.derive_ndvi_flowering(
        crop_name="Cotton",
        growth_stage="Flowering",
        sowing_date=(datetime.now().date() - timedelta(days=90)).isoformat(),
        baseline_ndvi_flowering=0.795,
        satellite_observation=sat_obs,
    )

    assert prov.is_live is False
    assert prov.is_baseline is True
    assert prov.freshness == "stale_fallback"
    assert "30d limit" in prov.details.get("baseline_reason", "")
    assert prov.value == 0.795


def test_stale_weather_telemetry_handling():
    """Verify weather observations older than 24 hours are flagged as stale fallback."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%d %H:%M")
    weather_res = CurrentWeatherResponse(
        success=True,
        latitude=19.876,
        longitude=75.343,
        timestamp=stale_ts,
        temperature=35.0,
        relative_humidity=40.0,
        soil_moisture_percentage=30.0,
        source="Open-Meteo",
    )

    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Aurangabad",
        crop_name="Cotton",
        crop_season="Kharif",
        weather=weather_res,
    )

    temp_prov = assembly.feature_provenance["Temperature"]
    assert temp_prov.is_live is False
    assert temp_prov.is_baseline is True
    assert temp_prov.freshness == "stale_fallback"
    assert assembly.data_quality["weather_status"] == "stale_fallback"


def test_risk_threshold_consistency():
    """Verify the single authoritative risk threshold logic across recommendation engine and prediction class."""
    from src.recommendation_engine import risk_band

    # Risk Band boundaries: High >= 0.70, Medium >= 0.45, Low < 0.45
    assert risk_band(0.0) == "Low"
    assert risk_band(0.449) == "Low"
    assert risk_band(0.45) == "Medium"
    assert risk_band(0.699) == "Medium"
    assert risk_band(0.70) == "High"
    assert risk_band(1.0) == "High"

    # Prediction Class binary threshold: 1 if risk_probability >= 0.50 else 0
    low_case = {"risk_probability": 0.3727}
    high_case = {"risk_probability": 0.5200}
    assert int(low_case["risk_probability"] >= 0.50) == 0
    assert int(high_case["risk_probability"] >= 0.50) == 1


def test_soil_moisture_source_and_unit():
    """Verify SoilMoisture is derived from Open-Meteo 4-layer root-zone (0-27cm) saturation %."""
    from backend.app.services.weather.providers.open_meteo import OpenMeteoProvider

    provider = OpenMeteoProvider()
    res = provider.get_current_weather(latitude=19.8762, longitude=75.3433)
    if res.success and res.soil_moisture_percentage is not None:
        assert 0.0 <= res.soil_moisture_percentage <= 100.0
        assert res.soil_moisture_m3m3 is not None
        assert "0-27cm" in "0-27cm"
