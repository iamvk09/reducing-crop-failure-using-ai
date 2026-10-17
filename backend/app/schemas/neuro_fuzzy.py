"""Pydantic schemas for Experimental Neuro-Fuzzy Crop Failure Risk Model."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NeuroFuzzyRuleExplanationSchema(BaseModel):
    rule_index: int
    rule_name: str
    description: str
    firing_strength: float = Field(ge=0.0, le=1.0)
    normalized_weight: float = Field(ge=0.0, le=1.0)
    consequent_score: float
    rule_contribution: float
    antecedent_memberships: Dict[str, float]


class NeuroFuzzyPredictionRequest(BaseModel):
    rainfall: float = Field(ge=0.0, le=2000.0, description="Total season/monthly rainfall in mm")
    temperature: float = Field(ge=-20.0, le=60.0, description="Mean temperature in Celsius")
    humidity: float = Field(ge=0.0, le=100.0, description="Relative humidity percentage")
    soil_moisture: float = Field(ge=0.0, le=100.0, description="Soil moisture percentage")
    ndvi_flowering: float = Field(ge=0.0, le=1.0, description="Canopy NDVI proxy from Sentinel-2 satellite")
    water_stress: float = Field(ge=0.0, le=1.0, description="Crop water stress coefficient (0 = optimal, 1 = severe drought)")
    pest_risk: float = Field(ge=0.0, le=1.0, description="Pest & pathogen pressure risk index (0-1)")
    suitability_score: float = Field(ge=0.0, le=1.0, description="Soil & regional suitability score (0-1)")
    farm_id: Optional[str] = None
    crop: Optional[str] = None


class NeuroFuzzyPredictionResponse(BaseModel):
    model_version: str
    model_type: str = "First-Order Takagi-Sugeno-Kang (TSK) Neuro-Fuzzy"
    risk_score: float = Field(ge=0.0, le=1.0, description="Continuous failure risk score")
    risk_percentage: str
    risk_band: str  # "Low", "Medium", "High"
    failure_predicted: bool
    threshold: float
    dominant_rule: NeuroFuzzyRuleExplanationSchema
    activated_rules: List[NeuroFuzzyRuleExplanationSchema]
    calibrated_probability: float
    production_model_comparison: Optional[Dict[str, Any]] = None
    feature_provenance: Dict[str, float]
    disclaimer: str = (
        "Experimental Neuro-Fuzzy Model: For agricultural expert evaluation and advisory research. "
        "Do not use as sole guidance for critical farm management decisions without field verification."
    )


class NeuroFuzzyModelStatusResponse(BaseModel):
    is_available: bool
    version: str
    n_rules: int
    optimal_threshold: float
    feature_names: List[str]
    training_metadata: Dict[str, Any]
    comparison_summary: List[Dict[str, Any]]
