"""Expert analytics, SHAP, and Digital Twin schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ShapFeatureItem(BaseModel):
    """Individual SHAP feature impact item."""

    feature: str
    display_name: str
    impact: float
    abs_impact: float
    direction: str


class ShapExplanationResponse(BaseModel):
    """Model explainability response."""

    explainer_type: str
    summary: str
    top_features: List[ShapFeatureItem] = Field(default_factory=list)


class ScenarioSimulationRequest(BaseModel):
    """Digital Twin custom scenario simulation request."""

    prediction_id: Optional[str] = None
    scenario_name: str = "Custom Stress Test"
    updates: Dict[str, float] = Field(
        ...,
        description="Feature adjustments (e.g. {'Temperature': 3.0, 'Rainfall': -30.0})"
    )


class ScenarioSimulationResponse(BaseModel):
    """Digital twin scenario output."""

    scenario: str
    risk_score: float
    risk_percentage: str
    adjusted_features: Dict[str, float]
