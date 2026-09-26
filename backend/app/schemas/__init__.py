"""Pydantic API schemas."""

from backend.app.schemas.health import HealthResponse
from backend.app.schemas.auth import UserProfileResponse
from backend.app.schemas.farm import FarmCreateRequest, FarmResponse, CropCreateRequest, CropResponse
from backend.app.schemas.prediction import PredictionRequest, PredictionResponse
from backend.app.schemas.recommendation import RecommendationResponse, CropOption
from backend.app.schemas.expert import (
    ShapExplanationResponse,
    ShapFeatureItem,
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
)

__all__ = [
    "HealthResponse",
    "UserProfileResponse",
    "FarmCreateRequest",
    "FarmResponse",
    "CropCreateRequest",
    "CropResponse",
    "PredictionRequest",
    "PredictionResponse",
    "RecommendationResponse",
    "CropOption",
    "ShapExplanationResponse",
    "ShapFeatureItem",
    "ScenarioSimulationRequest",
    "ScenarioSimulationResponse",
]
