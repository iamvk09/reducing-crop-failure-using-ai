"""Prediction request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    """Payload to request crop failure risk prediction."""

    farm_id: Optional[str] = None
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


class PredictionResponse(BaseModel):
    """Structured crop failure risk response."""

    prediction_id: Optional[str] = None
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
    disclaimer: str = (
        "This is a machine-learning estimate based on available meteorological and "
        "agronomic data and is not a guarantee of crop failure."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
