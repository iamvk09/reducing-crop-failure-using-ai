"""Unit and integration tests for Closed-Loop Crop Risk Intelligence & Farm Monitoring.

Covers:
1. Risk trend calculation (increasing, decreasing, stable, insufficient_history).
2. Telemetry changes classification (DIRECT_LIVE_CHANGE, DERIVED_CHANGE, BASELINE_UNCHANGED).
3. Non-causal product language enforcement in trend and telemetry descriptions.
4. SHAP attribution shifts comparison between sequential predictions.
5. Farmer feedback logging and tenant-isolated retrieval.
6. Ground-truth harvest outcome recording and retrieval.
7. Operational diagnostics metrics.
8. Duplicate-state protection and force_refresh bypass.
9. FastAPI REST endpoints for monitoring, trend, feedback, outcomes, and diagnostics.
"""

import datetime
from typing import Dict
import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import AuthenticatedUser
from backend.app.main import app
from backend.app.repositories.feedback_repository import FeedbackRepository
from backend.app.schemas.monitoring import (
    CropOutcomeRequest,
    FarmFeedbackRequest,
    RiskTrend,
)
from backend.app.schemas.prediction import (
    PredictionDataQuality,
    PredictionExplanation,
    PredictionResponse,
    ShapFeatureContribution,
)
from backend.app.services.farm_service import farm_service
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.prediction_service import prediction_service


@pytest.fixture
def mock_farmer():
    return AuthenticatedUser(
        id="farmer-uuid-001",
        email="farmer1@example.com",
        role="farmer",
        is_active=True,
    )


@pytest.fixture
def mock_other_farmer():
    return AuthenticatedUser(
        id="farmer-uuid-002",
        email="farmer2@example.com",
        role="farmer",
        is_active=True,
    )


@pytest.fixture
def mock_expert():
    return AuthenticatedUser(
        id="expert-uuid-001",
        email="expert@example.com",
        role="expert",
        is_active=True,
    )


def make_dummy_prediction(
    risk_prob: float,
    pred_id: str = "pred-1",
    farm_id: str = "farm-1",
    rainfall: float = 850.0,
    temp: float = 28.5,
    humidity: float = 65.0,
    soil_moisture: float = 40.0,
    ndvi: float = 0.55,
    water_stress: float = 0.3,
    created_at: datetime.datetime = None,
) -> PredictionResponse:
    """Helper to build consistent PredictionResponse fixtures."""
    now = created_at or datetime.datetime.now(datetime.timezone.utc)
    features = {
        "Year": 2026,
        "Rainfall": rainfall,
        "Temperature": temp,
        "Humidity": humidity,
        "SoilMoisture": soil_moisture,
        "NDVI_Flowering": ndvi,
        "WaterStress": water_stress,
        "PestRisk": 0.25,
        "SuitabilityScore": 0.75,
        "YieldIndex": 105.0,
        "State": "Maharashtra",
        "Region": "Western",
        "Season": "Kharif",
        "Crop": "Soybean",
        "SoilType": "Medium Black",
        "IrrigationLevel": "Rainfed",
    }
    
    # Simple SHAP attributions based on risk_prob
    shap_rainfall = 0.15 if rainfall < 700 else -0.10
    shap_soil = 0.20 if soil_moisture < 35 else -0.15
    shap_temp = 0.05
    shap_ndvi = -0.12 if ndvi > 0.5 else 0.18

    top_inc = [
        ShapFeatureContribution(
            feature_name="SoilMoisture",
            display_name="Soil Moisture",
            feature_value=soil_moisture,
            formatted_value=f"{soil_moisture:.1f}%",
            attribution_value=shap_soil,
            abs_attribution=abs(shap_soil),
            direction="increases_risk" if shap_soil > 0 else "reduces_risk",
            direction_label="Increases Risk" if shap_soil > 0 else "Reduces Risk",
            farmer_text=f"Soil moisture at {soil_moisture:.1f}% is associated with higher risk.",
            is_live=True,
        )
    ]
    top_red = [
        ShapFeatureContribution(
            feature_name="NDVI_Flowering",
            display_name="Canopy Health (NDVI)",
            feature_value=ndvi,
            formatted_value=f"{ndvi:.3f}",
            attribution_value=shap_ndvi,
            abs_attribution=abs(shap_ndvi),
            direction="reduces_risk" if shap_ndvi < 0 else "increases_risk",
            direction_label="Reduces Risk" if shap_ndvi < 0 else "Increases Risk",
            farmer_text=f"Green canopy index at {ndvi:.3f} indicates healthy biomass.",
            is_live=True,
        )
    ]

    all_feat = top_inc + top_red

    explanation = PredictionExplanation(
        explainer_type="LinearExplainer",
        output_space="log_odds",
        base_value=-0.116,
        sum_shap=round(shap_rainfall + shap_soil + shap_temp + shap_ndvi, 4),
        margin_value=round(-0.116 + shap_rainfall + shap_soil + shap_temp + shap_ndvi, 4),
        top_risk_increasing=top_inc,
        top_risk_reducing=top_red,
        all_features=all_feat,
        summary_narrative="Evaluation shows primary risk contributors.",
    )

    return PredictionResponse(
        prediction_id=pred_id,
        farm_id=farm_id,
        crop="Soybean",
        district="Pune",
        state="Maharashtra",
        season="Kharif",
        risk_probability=risk_prob,
        risk_percentage=f"{risk_prob * 100:.1f}%",
        risk_level="High" if risk_prob >= 0.6 else "Medium" if risk_prob >= 0.3 else "Low",
        prediction_class=1 if risk_prob >= 0.5 else 0,
        best_model_name="CalibratedClassifierCV",
        input_features=features,
        provenance={k: "live" if k in ("Rainfall", "Temperature", "Humidity", "SoilMoisture", "NDVI_Flowering") else "baseline" for k in features},
        data_quality=PredictionDataQuality(
            live_feature_count=5,
            baseline_feature_count=11,
            total_feature_count=16,
            live_feature_percentage=31.2,
            satellite_status="live_fresh",
            weather_status="live_fresh",
            summary_label="Verified live telemetry + baselines",
        ),
        explanation=explanation,
        created_at=now,
    )


# -----------------------------------------------------------------------------
# 1. RISK TREND ENGINE TESTS
# -----------------------------------------------------------------------------
def test_risk_trend_insufficient_history():
    """Verify single baseline assessment returns insufficient_history with clear guidance."""
    pred1 = make_dummy_prediction(risk_prob=0.35, pred_id="p1")
    trend = MonitoringService.calculate_risk_trend(pred1, previous_pred=None, total_history_count=1)

    assert trend.trend_direction == "insufficient_history"
    assert trend.previous_risk_probability is None
    assert trend.risk_delta_percentage_points is None
    assert trend.assessment_count == 1
    assert "Baseline Assessment" in trend.trend_label


def test_risk_trend_increasing():
    """Verify delta >= +1.0 percentage points triggers 'increasing' risk trend."""
    # Previous: 35.0%, Current: 42.5% -> Delta = +7.5 pp
    pred_prev = make_dummy_prediction(risk_prob=0.350, pred_id="p1")
    pred_curr = make_dummy_prediction(risk_prob=0.425, pred_id="p2")

    trend = MonitoringService.calculate_risk_trend(pred_curr, pred_prev, total_history_count=2)

    assert trend.trend_direction == "increasing"
    assert trend.risk_delta_percentage_points == 7.5
    assert trend.current_risk_probability == 0.425
    assert trend.previous_risk_probability == 0.350
    assert "+7.5 pp" in trend.trend_label
    # Verify non-causal language in description
    assert "higher than the previous assessment" in trend.trend_description
    assert "caused" not in trend.trend_description.lower()


def test_risk_trend_decreasing():
    """Verify delta <= -1.0 percentage points triggers 'decreasing' risk trend."""
    # Previous: 45.0%, Current: 38.0% -> Delta = -7.0 pp
    pred_prev = make_dummy_prediction(risk_prob=0.450, pred_id="p1")
    pred_curr = make_dummy_prediction(risk_prob=0.380, pred_id="p2")

    trend = MonitoringService.calculate_risk_trend(pred_curr, pred_prev, total_history_count=2)

    assert trend.trend_direction == "decreasing"
    assert trend.risk_delta_percentage_points == -7.0
    assert "-7.0 pp" in trend.trend_label
    assert "lower than the previous assessment" in trend.trend_description
    assert "caused" not in trend.trend_description.lower()


def test_risk_trend_stable():
    """Verify |delta| < 1.0 percentage point triggers 'stable' risk trend."""
    # Previous: 38.0%, Current: 38.5% -> Delta = +0.5 pp (below 1.0 pp threshold)
    pred_prev = make_dummy_prediction(risk_prob=0.380, pred_id="p1")
    pred_curr = make_dummy_prediction(risk_prob=0.385, pred_id="p2")

    trend = MonitoringService.calculate_risk_trend(pred_curr, pred_prev, total_history_count=2)

    assert trend.trend_direction == "stable"
    assert trend.risk_delta_percentage_points == 0.5
    assert "Stable" in trend.trend_label
    assert "within normal variance" in trend.trend_description


# -----------------------------------------------------------------------------
# 2. TELEMETRY CHANGES AND NON-CAUSAL DESCRIPTIONS
# -----------------------------------------------------------------------------
def test_telemetry_changes_classification_and_non_causal_language():
    """Verify telemetry changes are accurately categorized and described non-causally."""
    pred_prev = make_dummy_prediction(
        risk_prob=0.30,
        rainfall=600.0,
        soil_moisture=25.0,
        ndvi=0.45,
    )
    pred_curr = make_dummy_prediction(
        risk_prob=0.42,
        rainfall=680.0,  # +80 mm live
        soil_moisture=32.0,  # +7% live
        ndvi=0.45,  # unchanged
    )

    changes = MonitoringService.calculate_telemetry_changes(pred_curr, pred_prev)
    assert len(changes) > 0

    change_types = {c.feature_name: c.change_type for c in changes}
    assert change_types.get("Rainfall") == "DIRECT_LIVE_CHANGE"
    assert change_types.get("SoilMoisture") == "DIRECT_LIVE_CHANGE"
    assert change_types.get("State") == "BASELINE_UNCHANGED"

    # Non-causal phrasing check across all items
    for item in changes:
        desc_lower = item.description.lower()
        assert "caused" not in desc_lower
        assert "responsible for" not in desc_lower


# -----------------------------------------------------------------------------
# 3. SHAP ATTRIBUTION SHIFTS COMPARISON
# -----------------------------------------------------------------------------
def test_shap_trend_comparison():
    """Verify SHAP attribution shift computation between sequential assessments."""
    pred_prev = make_dummy_prediction(risk_prob=0.30, soil_moisture=40.0)
    pred_curr = make_dummy_prediction(risk_prob=0.45, soil_moisture=25.0)

    shap_comp = MonitoringService.calculate_shap_trend(pred_curr, pred_prev)
    assert shap_comp is not None
    assert isinstance(shap_comp.all_shifts, list)
    assert len(shap_comp.all_shifts) > 0

    # Ensure delta_phi is calculated
    for shift in shap_comp.all_shifts:
        assert hasattr(shift, "delta_phi")
        assert shift.direction_shift in ("increased_contribution", "decreased_contribution", "unchanged")


# -----------------------------------------------------------------------------
# 4. FEEDBACK & OUTCOME REPOSITORY TESTS
# -----------------------------------------------------------------------------
def test_feedback_logging_and_tenant_isolation(mock_farmer, mock_other_farmer):
    """Verify feedback action logging and tenant isolation between farmers."""
    repo = FeedbackRepository()

    fb_in = FarmFeedbackRequest(
        action_type="irrigation_applied",
        notes="Applied 40mm drip irrigation to mitigate water stress.",
    )

    created = repo.create_feedback(
        farm_id="farm-test-1",
        user_id=mock_farmer.id,
        action_type=fb_in.action_type,
        notes=fb_in.notes,
    )

    assert created["id"] is not None
    assert created["action_type"] == "irrigation_applied"
    assert created["user_id"] == mock_farmer.id

    # Farmer 1 can see their feedback
    farmer1_feedback = repo.list_feedback(
        farm_id="farm-test-1",
        user_id=mock_farmer.id,
        role="farmer",
    )
    assert len(farmer1_feedback) == 1
    assert farmer1_feedback[0]["id"] == created["id"]

    # Farmer 2 cannot see Farmer 1's feedback
    farmer2_feedback = repo.list_feedback(
        farm_id="farm-test-1",
        user_id=mock_other_farmer.id,
        role="farmer",
    )
    assert len(farmer2_feedback) == 0

    # Expert can see all feedback
    expert_feedback = repo.list_feedback(
        farm_id="farm-test-1",
        user_id="expert-1",
        role="expert",
    )
    assert len(expert_feedback) == 1


def test_crop_outcome_recording():
    """Verify ground-truth outcome recording persists harvest yield and status."""
    repo = FeedbackRepository()

    outcome_in = CropOutcomeRequest(
        crop_status="harvested",
        actual_harvest_date=datetime.date(2026, 10, 15),
        reported_yield_kg_per_ha=2450.0,
        outcome_notes="Successful harvest with high seed quality.",
    )

    saved = repo.record_crop_outcome(
        crop_id="crop-cycle-1",
        farm_id="farm-test-1",
        status=outcome_in.crop_status,
        actual_harvest_date=outcome_in.actual_harvest_date,
        reported_yield_kg_per_ha=outcome_in.reported_yield_kg_per_ha,
        outcome_notes=outcome_in.outcome_notes,
    )

    assert saved["crop_id"] == "crop-cycle-1"
    assert saved["status"] == "harvested"
    assert saved["reported_yield_kg_per_ha"] == 2450.0

    retrieved = repo.get_crop_outcome(crop_id="crop-cycle-1")
    assert retrieved is not None
    assert retrieved["status"] == "harvested"
    assert retrieved["reported_yield_kg_per_ha"] == 2450.0


# -----------------------------------------------------------------------------
# 5. DIAGNOSTICS & TELEMETRY HEALTH METRICS
# -----------------------------------------------------------------------------
def test_monitoring_diagnostics():
    """Verify monitoring diagnostics gathers operational metrics without errors."""
    svc = MonitoringService()
    diag = svc.get_diagnostics()

    assert hasattr(diag, "total_predictions")
    assert hasattr(diag, "risk_distribution")
    assert hasattr(diag, "average_live_feature_coverage")
    assert hasattr(diag, "stale_telemetry_rate")
    assert hasattr(diag, "shap_availability_rate")
    assert "disclaimer" in diag.model_dump()


# -----------------------------------------------------------------------------
# 6. REST API INTEGRATION & DUPLICATE PROTECTION TESTS
# -----------------------------------------------------------------------------
def test_monitoring_api_lifecycle(client, farmer1_token, farmer2_token, expert_token):
    """End-to-end integration test of monitoring, feedback, and outcome API routes."""
    headers1 = {"Authorization": f"Bearer {farmer1_token}"}
    headers2 = {"Authorization": f"Bearer {farmer2_token}"}
    expert_headers = {"Authorization": f"Bearer {expert_token}"}

    # 1. Create farm for Farmer 1
    farm_res = client.post(
        "/api/v1/farms",
        json={
            "name": "Sahyadri Bio Farms",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "size_hectares": 3.5,
            "soil_type": "Black",
            "irrigation_level": "Medium",
        },
        headers=headers1,
    )
    assert farm_res.status_code == 201
    farm_id = farm_res.json()["id"]

    # 2. Add crop cycle
    crop_res = client.post(
        f"/api/v1/farms/{farm_id}/crops",
        json={
            "crop": "Soybean",
            "season": "Kharif",
            "growth_stage": "Flowering",
            "sowing_date": "2026-06-15",
            "expected_harvest_date": "2026-10-25",
        },
        headers=headers1,
    )
    assert crop_res.status_code == 201
    crop_id = crop_res.json()["id"]

    # 3. First prediction (Baseline run)
    pred1_res = client.post(
        f"/api/v1/farms/{farm_id}/predictions",
        json={"crop_id": crop_id},
        headers=headers1,
    )
    assert pred1_res.status_code == 201, f"Prediction 1 error: {pred1_res.json()}"
    pred1_data = pred1_res.json()
    assert pred1_data["risk_probability"] is not None

    # Duplicate-state check: calling immediately without force_refresh returns existing prediction
    pred_dup_res = client.post(
        f"/api/v1/farms/{farm_id}/predictions",
        json={"crop_id": crop_id, "force_refresh": False},
        headers=headers1,
    )
    assert pred_dup_res.status_code == 201
    assert pred_dup_res.json()["prediction_id"] == pred1_data["prediction_id"]

    # Force refresh bypasses duplicate-state protection
    pred_force_res = client.post(
        f"/api/v1/farms/{farm_id}/predictions",
        json={"crop_id": crop_id, "force_refresh": True},
        headers=headers1,
    )
    assert pred_force_res.status_code == 201
    assert pred_force_res.json()["prediction_id"] != pred1_data["prediction_id"]

    # 4. Check GET /farms/{farm_id}/monitoring
    mon_res = client.get(f"/api/v1/farms/{farm_id}/monitoring", headers=headers1)
    assert mon_res.status_code == 200
    mon_data = mon_res.json()
    assert mon_data["farm_id"] == farm_id
    assert mon_data["monitoring_status"] in ("optimal", "active", "attention_needed")
    assert mon_data["risk_trend"] is not None
    assert "assessment_count" in mon_data["risk_trend"]

    # 5. Check GET /farms/{farm_id}/predictions/trend
    trend_res = client.get(f"/api/v1/farms/{farm_id}/predictions/trend", headers=headers1)
    assert trend_res.status_code == 200
    trend_data = trend_res.json()
    assert trend_data["risk_trend"]["trend_direction"] in ("increasing", "decreasing", "stable", "insufficient_history")

    # 6. Log Farmer Management Action (POST /farms/{farm_id}/feedback)
    fb_res = client.post(
        f"/api/v1/farms/{farm_id}/feedback",
        json={
            "action_type": "irrigation_applied",
            "prediction_id": pred1_data["prediction_id"],
            "notes": "Supplemental furrow irrigation applied after heat alert.",
        },
        headers=headers1,
    )
    assert fb_res.status_code == 201
    fb_data = fb_res.json()
    assert fb_data["action_type"] == "irrigation_applied"
    assert fb_data["action_label"] == "Irrigation Applied"

    # 7. List Farmer Feedback (GET /farms/{farm_id}/feedback)
    fb_list_res = client.get(f"/api/v1/farms/{farm_id}/feedback", headers=headers1)
    assert fb_list_res.status_code == 200
    assert len(fb_list_res.json()) >= 1

    # Tenant Isolation: Farmer 2 cannot see Farmer 1's monitoring or feedback
    unauth_mon = client.get(f"/api/v1/farms/{farm_id}/monitoring", headers=headers2)
    assert unauth_mon.status_code == 404

    # 8. Record Ground-Truth Crop Outcome (POST /farms/{farm_id}/crops/{crop_id}/outcome)
    outcome_post = client.post(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome",
        json={
            "crop_status": "harvested",
            "actual_harvest_date": "2026-10-20",
            "reported_yield_kg_per_ha": 2600.0,
            "outcome_notes": "Harvest completed with minimal pod damage.",
        },
        headers=headers1,
    )
    assert outcome_post.status_code == 200
    outcome_data = outcome_post.json()
    assert outcome_data["status"] == "harvested"
    assert outcome_data["reported_yield_kg_per_ha"] == 2600.0

    # 9. Get Recorded Crop Outcome (GET /farms/{farm_id}/crops/{crop_id}/outcome)
    outcome_get = client.get(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome",
        headers=headers1,
    )
    assert outcome_get.status_code == 200
    assert outcome_get.json()["status"] == "harvested"

    # 10. Diagnostics Endpoint (GET /farms/{farm_id}/diagnostics)
    diag_res = client.get(f"/api/v1/farms/{farm_id}/diagnostics", headers=expert_headers)
    assert diag_res.status_code == 200
    diag_data = diag_res.json()
    assert diag_data["total_predictions"] >= 2
    assert diag_data["feedback_count"] >= 1
    assert diag_data["outcomes_recorded_count"] >= 1

    # 11. Test Safe Deletion of Feedback (DELETE /farms/{farm_id}/feedback/{feedback_id})
    del_fb_res = client.delete(
        f"/api/v1/farms/{farm_id}/feedback/{fb_data['id']}",
        headers=headers1,
    )
    assert del_fb_res.status_code == 204

    # Verify feedback count decreased
    fb_list_after_del = client.get(f"/api/v1/farms/{farm_id}/feedback", headers=headers1)
    assert fb_list_after_del.status_code == 200
    assert not any(f["id"] == fb_data["id"] for f in fb_list_after_del.json())

    # 12. Test Safe Restoration of Crop Outcome (DELETE /farms/{farm_id}/crops/{crop_id}/outcome)
    del_out_res = client.delete(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome",
        headers=headers1,
    )
    assert del_out_res.status_code == 204

    # Verify crop outcome is cleared and crop restored to active
    out_after_clear = client.get(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome",
        headers=headers1,
    )
    assert out_after_clear.status_code == 200
    assert out_after_clear.json() is None

    crops_after_clear = client.get(f"/api/v1/farms/{farm_id}/crops", headers=headers1)
    assert crops_after_clear.status_code == 200
    restored_crop = next((c for c in crops_after_clear.json() if c["id"] == crop_id), None)
    assert restored_crop is not None
    assert restored_crop["status"] == "active"
    assert restored_crop["growth_stage"] == "Flowering"

    # 13. Ground-truth evaluation safety: synthetic outcomes flagged
    synth_outcome_res = client.post(
        f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome",
        json={
            "crop_status": "harvested",
            "actual_harvest_date": "2026-10-25",
            "reported_yield_kg_per_ha": 2500.0,
            "outcome_notes": "[TEST_VERIFICATION] Automated regression verification test run",
            "is_verified_ground_truth": False,
            "is_synthetic": True,
        },
        headers=headers1,
    )
    assert synth_outcome_res.status_code == 200
    synth_data = synth_outcome_res.json()
    assert synth_data["is_verified_ground_truth"] is False
    assert synth_data["is_synthetic"] is True

    # Teardown: clear test outcome
    client.delete(f"/api/v1/farms/{farm_id}/crops/{crop_id}/outcome", headers=headers1)
