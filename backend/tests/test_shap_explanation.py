"""Comprehensive tests for SHAP Feature Attributions and Model Explainability.

Validates:
1. Exact 16-feature representation in SHAP attribution breakdown.
2. Mathematical consistency: explainer base value + sum(SHAP) == margin in log-odds space.
3. Directionality: phi > 0 increases model risk, phi < 0 reduces model risk.
4. Top contributor ranking: absolute magnitude descending order.
5. Non-causal, farmer-friendly explanation phrasing.
6. Stage-aware NDVI labeling (historical baseline in vegetative vs live Sentinel-2 in flowering).
7. End-to-end integration and persistence in PredictionService and PredictionResponse.
"""

from datetime import datetime
import pytest

from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.prediction import PredictionExplanation, ShapFeatureContribution
from backend.app.services.feature_service import FeatureAssembler
from backend.app.services.prediction_service import PredictionService, prediction_service
from backend.app.services.satellite.schemas import (
    NDVIStatistics,
    SatelliteObservationResponse,
    SatelliteObservationStatus,
)
from backend.app.services.weather.schemas import CurrentWeatherResponse
from src.live_prediction import get_prediction_explanation


EXPECTED_16_FEATURES = [
    "Year", "Rainfall", "Temperature", "Humidity", "SoilMoisture",
    "NDVI_Flowering", "WaterStress", "PestRisk", "SuitabilityScore", "YieldIndex",
    "State", "Region", "Season", "Crop", "SoilType", "IrrigationLevel"
]


def test_shap_explanation_returns_mathematically_consistent_contract():
    """Verify get_prediction_explanation returns base_value, sum_shap, margin, and all 16 features."""
    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Pune",
        crop_name="Soybean",
        crop_season="Kharif",
    )

    exp = get_prediction_explanation(assembly.features)

    assert exp["explainer_type"] in ("LinearExplainer", "TreeExplainer", "Explainer")
    assert exp["output_space"] == "log_odds"
    assert "base_value" in exp
    assert "sum_shap" in exp
    assert "margin_value" in exp
    assert "feature_attributions" in exp

    # Check 16 features are all present in aggregated feature attributions
    attr_map = exp["feature_attributions"]
    assert set(attr_map.keys()) == set(EXPECTED_16_FEATURES)

    # Base value + sum_shap == margin_value (within rounding)
    assert abs((exp["base_value"] + exp["sum_shap"]) - exp["margin_value"]) < 0.001


def test_build_prediction_explanation_structure_and_direction():
    """Verify build_explanation properly categorizes risk-increasing vs risk-reducing features."""
    service = PredictionService()

    assembly = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Pune",
        crop_name="Soybean",
        crop_season="Kharif",
    )

    explanation = service.build_explanation(
        input_features=assembly.features,
        feature_provenance=assembly.feature_provenance,
        crop_stage="Vegetative",
    )

    assert isinstance(explanation, PredictionExplanation)
    assert explanation.explainer_type == "LinearExplainer"
    assert explanation.output_space == "log_odds"
    assert len(explanation.all_features) == 16

    # Verify top risk increasing items have positive attribution
    for item in explanation.top_risk_increasing:
        assert item.attribution_value > 0
        assert item.direction == "increases_risk"
        assert item.direction_label == "Increases Risk"
        assert "increasing the model's predicted risk" in item.farmer_text

    # Verify top risk reducing items have negative attribution
    for item in explanation.top_risk_reducing:
        assert item.attribution_value < 0
        assert item.direction == "reduces_risk"
        assert item.direction_label == "Reduces Risk"
        assert "reducing the model's predicted risk" in item.farmer_text

    # Verify sorting by absolute attribution
    increasing_mags = [x.abs_attribution for x in explanation.top_risk_increasing]
    assert increasing_mags == sorted(increasing_mags, reverse=True)

    reducing_mags = [x.abs_attribution for x in explanation.top_risk_reducing]
    assert reducing_mags == sorted(reducing_mags, reverse=True)


def test_stage_aware_ndvi_labeling_in_explanation():
    """Verify vegetative stage NDVI is labeled as historical baseline in explanation, not live Sentinel-2."""
    service = PredictionService()

    import datetime
    recent_date = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    obs = SatelliteObservationResponse(
        farm_id="farm-veg-123",
        observation_date=recent_date,
        status=SatelliteObservationStatus.REAL_SATELLITE_DATA,
        ndvi=NDVIStatistics(mean=0.38, min=0.25, max=0.50, std=0.05),
        valid_pixels=300,
        total_pixels=300,
        cloud_percentage=0.0,
        provider="GoogleEarthEngine",
        satellite_source="Sentinel-2 L2A",
    )

    # 1. Vegetative stage (should use historical baseline)
    assembly_veg = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Pune",
        crop_name="Soybean",
        crop_season="Kharif",
        crop_growth_stage="Vegetative",
        satellite_observation=obs,
    )

    exp_veg = service.build_explanation(
        input_features=assembly_veg.features,
        feature_provenance=assembly_veg.feature_provenance,
        crop_stage="Vegetative",
    )

    ndvi_veg_item = next(x for x in exp_veg.all_features if x.feature_name == "NDVI_Flowering")
    assert ndvi_veg_item.display_name == "Historical Flowering Baseline"
    assert "Historical flowering baseline" in ndvi_veg_item.provenance_source

    # 2. Flowering stage (should use live Sentinel-2)
    assembly_flowering = FeatureAssembler.assemble_features(
        farm_state="Maharashtra",
        farm_district="Pune",
        crop_name="Soybean",
        crop_season="Kharif",
        crop_growth_stage="Flowering",
        satellite_observation=obs,
    )

    exp_flowering = service.build_explanation(
        input_features=assembly_flowering.features,
        feature_provenance=assembly_flowering.feature_provenance,
        crop_stage="Flowering",
    )

    ndvi_flowering_item = next(x for x in exp_flowering.all_features if x.feature_name == "NDVI_Flowering")
    assert ndvi_flowering_item.display_name == "Flowering Stage NDVI"
    assert ndvi_flowering_item.is_live is True


def test_predict_with_weather_returns_full_explanation_and_provenance():
    """Verify predict_with_weather outputs both data quality and SHAP explanation in payload."""
    service = PredictionService()

    res = service.predict_with_weather(
        state="Maharashtra",
        district="Pune",
        crop="Soybean",
        season="Kharif",
    )

    assert "explanation" in res
    exp = res["explanation"]
    assert isinstance(exp, PredictionExplanation)
    assert len(exp.all_features) == 16
    assert exp.summary_narrative != ""
    assert exp.disclaimer != ""


def test_prediction_response_includes_explanation():
    """Verify PredictionResponse serializes and parses explanation correctly."""
    service = PredictionService()

    res = service.predict_with_weather(
        state="Maharashtra",
        district="Pune",
        crop="Soybean",
        season="Kharif",
    )

    pred = res["prediction"]
    pred_payload = {
        "id": "pred-shap-test-01",
        "farm_id": "farm-shap-01",
        "crop": "Soybean",
        "district": "Pune",
        "state": "Maharashtra",
        "season": "Kharif",
        "risk_probability": pred["risk_probability"],
        "risk_level": pred["risk_level"],
        "prediction_class": pred["prediction"],
        "best_model_name": pred["best_model_name"],
        "input_features": res["input_features"],
        "provenance": res["provenance"],
        "data_quality": res.get("data_quality"),
        "explanation": res.get("explanation"),
        "weather_data": res.get("weather"),
    }

    resp = service._to_prediction_response(pred_payload)

    assert resp.explanation is not None
    assert resp.explanation.explainer_type == "LinearExplainer"
    assert len(resp.explanation.all_features) == 16
    assert resp.explanation.summary_narrative != ""
