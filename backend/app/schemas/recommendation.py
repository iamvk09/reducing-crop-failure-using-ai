"""Recommendation and advisory response schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class CropOption(BaseModel):
    """Ranked crop alternative."""

    crop: str
    probability: float
    percentage: str


class RecommendationResponse(BaseModel):
    """Actionable agronomic recommendation response."""

    prediction_id: Optional[str] = None
    recommended_crop: Optional[str] = None
    top_options: List[CropOption] = Field(default_factory=list)
    advisory_summary: str
    farmer_notes: List[str] = Field(default_factory=list)
