"""Prediction request and response schemas."""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FarmPredictionRequest(BaseModel):
    """Payload to trigger prediction for a registered farm."""

    crop_id: Optional[str] = Field(None, description="Optional specific crop cycle ID on this farm")
    rainfall_override: Optional[float] = Field(None, ge=0.0, le=1500.0)
    temperature_override: Optional[float] = Field(None, ge=-15.0, le=60.0)
    humidity_override: Optional[float] = Field(None, ge=0.0, le=100.0)
    soil_moisture_override: Optional[float] = Field(None, ge=0.0, le=100.0)
    ndvi_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    water_stress_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    pest_risk_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    suitability_score_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    yield_index_override: Optional[float] = Field(None, ge=0.0, le=250.0)
    force_refresh: bool = Field(False, description="If True, bypass recent prediction reuse and execute fresh telemetry assembly")


class PredictionRequest(BaseModel):
    """Payload to request crop failure risk prediction directly."""

    farm_id: Optional[str] = None
    crop_id: Optional[str] = None
    state: str = Field(..., description="Indian State")
    district: str = Field(..., description="District Name")
    crop: str = Field(..., description="Crop Name")
    season: str = Field(..., description="Season: Kharif, Rabi, Zaid")
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = None

    # Optional manual overrides (used in Expert Mode)
    rainfall_override: Optional[float] = Field(None, ge=0.0, le=1500.0)
    temperature_override: Optional[float] = Field(None, ge=-15.0, le=60.0)
    humidity_override: Optional[float] = Field(None, ge=0.0, le=100.0)
    soil_moisture_override: Optional[float] = Field(None, ge=0.0, le=100.0)
    ndvi_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    water_stress_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    pest_risk_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    suitability_score_override: Optional[float] = Field(None, ge=0.0, le=1.0)
    yield_index_override: Optional[float] = Field(None, ge=0.0, le=250.0)


class RecommendationDetails(BaseModel):
    """Agronomic recommendation generated alongside risk assessment."""

    recommended_crop: Optional[str] = None
    top_options: List[Dict[str, Any]] = Field(default_factory=list)
    advisory_summary: str = ""


class WeatherDetails(BaseModel):
    """Live weather metadata captured during inference."""

    success: bool = True
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: Optional[float] = None
    soil_moisture_percentage: Optional[float] = None
    source: str = "Open-Meteo"
    timestamp: Optional[str] = None


class PredictionDataQuality(BaseModel):
    """Compact summary of feature freshness and source quality."""

    live_feature_count: int = 0
    baseline_feature_count: int = 0
    derived_feature_count: int = 0
    total_feature_count: int = 16
    live_feature_percentage: float = 0.0
    satellite_status: str = "baseline"  # 'live_fresh', 'live_stale', 'stage_deferred', 'stale_fallback', 'baseline'
    weather_status: str = "live_fresh"    # 'live_fresh', 'live_cached', 'stale_fallback', 'baseline'
    summary_label: str = ""


class ShapFeatureContribution(BaseModel):
    """Detailed attribution for a single feature in the crop-failure model."""

    feature_name: str
    display_name: str
    feature_value: Any
    formatted_value: str = ""
    attribution_value: float  # SHAP value in log-odds decision margin space
    abs_attribution: float
    direction: str  # 'increases_risk', 'reduces_risk', 'neutral'
    direction_label: str  # 'Increases Risk', 'Reduces Risk', 'Neutral'
    farmer_text: str
    provenance_source: Optional[str] = None
    is_live: bool = False
    is_baseline: bool = False
    freshness_status: Optional[str] = None


class PredictionExplanation(BaseModel):
    """Explainable AI breakdown of model prediction using SHAP attributions."""

    explainer_type: str = "LinearExplainer"
    output_space: str = "log_odds"
    base_value: float = 0.0
    sum_shap: float = 0.0
    margin_value: float = 0.0
    top_risk_increasing: List[ShapFeatureContribution] = Field(default_factory=list)
    top_risk_reducing: List[ShapFeatureContribution] = Field(default_factory=list)
    all_features: List[ShapFeatureContribution] = Field(default_factory=list)
    summary_narrative: str = ""
    disclaimer: str = (
        "Attributions describe statistical feature contributions to the model's output margin, "
        "not definitive agronomic causation."
    )


class PredictionResponse(BaseModel):
    """Structured crop failure risk response."""

    prediction_id: Optional[str] = None
    farm_id: Optional[str] = None
    crop_id: Optional[str] = None
    crop: str
    district: str
    state: str
    season: str
    risk_probability: float
    risk_percentage: str
    risk_level: str  # 'Low', 'Medium', 'High'
    prediction_class: int  # 0 or 1
    best_model_name: str
    global_risk: Optional[float] = None
    region_risk: Optional[float] = None
    crop_risk: Optional[float] = None
    consensus_risk: Optional[float] = None
    input_features: Dict[str, Any]
    provenance: Dict[str, str]
    weather_data: Optional[Dict[str, Any]] = None
    data_quality: Optional[PredictionDataQuality] = None
    explanation: Optional[PredictionExplanation] = None
    recommendations: Optional[RecommendationDetails] = None
    disclaimer: str = (
        "This is a machine-learning estimate based on available meteorological and "
        "agronomic data and is not a guarantee of crop failure."
    )
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    @property
    def id(self) -> Optional[str]:
        return self.prediction_id
