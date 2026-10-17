"""Closed-Loop Farm Monitoring, Risk Trends, Feedback, and Outcome Tracking Schemas."""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.schemas.alert import FarmAlertResponse
from backend.app.schemas.prediction import (
    PredictionDataQuality,
    PredictionExplanation,
    PredictionResponse,
    RecommendationDetails,
)


class RiskTrend(BaseModel):
    """Calculated risk progression between sequential crop risk assessments."""

    current_risk_probability: float
    previous_risk_probability: Optional[float] = None
    risk_delta_percentage_points: Optional[float] = None
    trend_direction: str = "insufficient_history"  # 'increasing', 'decreasing', 'stable', 'insufficient_history'
    trend_label: str = "First Assessment"
    trend_description: str = ""
    assessment_count: int = 1
    current_prediction_id: Optional[str] = None
    previous_prediction_id: Optional[str] = None
    current_prediction_timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    previous_prediction_timestamp: Optional[datetime.datetime] = None


class TelemetryChangeItem(BaseModel):
    """Environmental or phenological metric change between prediction cycles."""

    feature_name: str
    display_name: str
    current_value: Any
    previous_value: Any
    delta: Optional[float] = None
    formatted_current: str
    formatted_previous: str
    change_type: str = "BASELINE_UNCHANGED"  # 'DIRECT_LIVE_CHANGE', 'DERIVED_CHANGE', 'BASELINE_UNCHANGED'
    statement: str = ""
    description: str = ""


class ShapAttributionShiftItem(BaseModel):
    """Shift in a single feature's model attribution magnitude and direction."""

    feature_name: str
    display_name: str
    current_phi: float
    previous_phi: Optional[float] = None
    delta_phi: float = 0.0
    abs_delta_phi: float = 0.0
    direction_shift: str = "unchanged"  # 'increased_contribution', 'decreased_contribution', 'unchanged'
    statement: str = ""


class ShapTrendComparison(BaseModel):
    """Comparison of SHAP attributions between sequential model predictions."""

    top_newly_increasing: List[ShapAttributionShiftItem] = Field(default_factory=list)
    top_newly_reducing: List[ShapAttributionShiftItem] = Field(default_factory=list)
    all_shifts: List[ShapAttributionShiftItem] = Field(default_factory=list)
    summary_narrative: str = ""


class FarmFeedbackRequest(BaseModel):
    """Farmer action, advisory acknowledgment, or management note."""

    action_type: str = Field(
        ...,
        description="Type of action: 'recommendation_viewed', 'recommendation_acknowledged', "
                    "'irrigation_applied', 'fertilizer_applied', 'pest_control_applied', 'farmer_note'"
    )
    prediction_id: Optional[str] = Field(None, description="Optional prediction ID this action responds to")
    notes: Optional[str] = Field("", max_length=1000, description="Farmer or expert descriptive note")
    action_date: Optional[datetime.datetime] = Field(
        None, description="Date action was taken (defaults to current time)"
    )


class FarmFeedbackResponse(BaseModel):
    """Recorded farmer feedback or management action record."""

    id: str
    farm_id: str
    user_id: str
    prediction_id: Optional[str] = None
    action_type: str
    action_label: str
    notes: Optional[str] = ""
    action_date: datetime.datetime
    created_at: datetime.datetime


class CropOutcomeRequest(BaseModel):
    """Ground-truth harvest or failure outcome recorded by farmer or expert."""

    crop_status: str = Field(..., description="Outcome status: 'active', 'harvested', 'failed'")
    actual_harvest_date: Optional[datetime.date] = Field(None, description="Date crop was harvested or marked failed")
    reported_yield_kg_per_ha: Optional[float] = Field(None, ge=0.0, le=50000.0, description="Yield in kg/hectare")
    outcome_notes: Optional[str] = Field(None, max_length=2000, description="Field outcome observations and context")
    is_verified_ground_truth: bool = Field(
        False,
        description="Whether this outcome is verified ground truth suitable for model evaluation datasets. Defaults to False for farmer reports.",
    )
    is_synthetic: bool = Field(
        False,
        description="Flag indicating synthetic or automated testing outcome to be excluded from evaluation",
    )


class OutcomeVerificationRequest(BaseModel):
    """Payload for agricultural expert / admin to verify or reject a crop outcome."""

    action: str = Field(..., description="Verification action: 'verify' to approve ground truth, 'reject' to mark invalid")
    verification_notes: Optional[str] = Field(None, max_length=2000, description="Expert agronomic assessment notes")


class CropOutcomeResponse(BaseModel):
    """Structured ground-truth crop cycle outcome record."""

    crop_id: str
    farm_id: str
    crop: str
    season: str
    status: str
    actual_harvest_date: Optional[datetime.date] = None
    reported_yield_kg_per_ha: Optional[float] = None
    outcome_notes: Optional[str] = None
    verification_status: str = "pending"  # pending | verified | invalid | synthetic
    is_verified_ground_truth: bool = False
    is_synthetic: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    verification_notes: Optional[str] = None
    recorded_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class RiskTrendResponse(BaseModel):
    """Stand-alone crop risk progression and telemetry change endpoint response."""

    farm_id: str
    risk_trend: RiskTrend
    telemetry_changes: List[TelemetryChangeItem] = Field(default_factory=list)
    shap_comparison: Optional[ShapTrendComparison] = None
    telemetry_summary: str = ""


class FarmMonitoringResponse(BaseModel):
    """Unified closed-loop farm monitoring state."""

    farm_id: str
    farm_name: str
    district: str
    state: str
    active_crop: Optional[str] = None
    growth_stage: Optional[str] = None
    monitoring_status: str = "active"  # 'optimal', 'active', 'attention_needed', 'insufficient_history'
    status_reason: str = ""
    latest_prediction: Optional[PredictionResponse] = None
    previous_prediction: Optional[PredictionResponse] = None
    risk_trend: RiskTrend
    telemetry_changes: List[TelemetryChangeItem] = Field(default_factory=list)
    shap_comparison: Optional[ShapTrendComparison] = None
    telemetry_freshness: Optional[PredictionDataQuality] = None
    latest_satellite_date: Optional[str] = None
    latest_weather_timestamp: Optional[str] = None
    latest_recommendations: Optional[RecommendationDetails] = None
    recent_actions: List[FarmFeedbackResponse] = Field(default_factory=list)
    crop_outcome: Optional[CropOutcomeResponse] = None
    active_alert_count: int = 0
    unacknowledged_alert_count: int = 0
    highest_active_severity: Optional[str] = None
    latest_alert: Optional[FarmAlertResponse] = None
    last_evaluated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class MonitoringDiagnosticsResponse(BaseModel):
    """Operational diagnostics for closed-loop monitoring pipeline."""

    total_predictions: int = 0
    farm_count: int = 0
    risk_distribution: Dict[str, int] = Field(default_factory=dict)
    average_live_feature_coverage: float = 0.0
    fallback_frequency: Dict[str, int] = Field(default_factory=dict)
    stale_telemetry_rate: float = 0.0
    shap_availability_rate: float = 100.0
    feedback_count: int = 0
    outcomes_recorded_count: int = 0
    total_alerts: int = 0
    active_alerts: int = 0
    acknowledged_alerts: int = 0
    resolved_alerts: int = 0
    alerts_by_severity: Dict[str, int] = Field(default_factory=dict)
    alerts_by_type: Dict[str, int] = Field(default_factory=dict)
    alert_deduplication_count: int = 0
    stale_data_alerts_count: int = 0
    disclaimer: str = (
        "Operational metrics reflect telemetry completeness and prediction distribution; "
        "model accuracy evaluation requires verified crop outcome reports."
    )
