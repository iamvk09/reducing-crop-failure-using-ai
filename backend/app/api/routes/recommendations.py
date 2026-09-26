"""Crop recommendations and advisory routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import get_current_user, get_prediction_svc
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.recommendation import CropOption, RecommendationResponse
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/{district}/{crop}", response_model=RecommendationResponse, summary="Get Crop Recommendations")
def get_recommendations(
    district: str,
    crop: str,
    season: str = "Kharif",
    user: AuthenticatedUser = Depends(get_current_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> RecommendationResponse:
    """Retrieve ranked safer crop options and practical agronomic advice."""
    try:
        baseline = service.get_baseline(district=district, crop=crop, season=season)
        rec_data = service.get_recommendation(baseline["feature_baselines"], district=district)

        top_opts = [
            CropOption(
                crop=opt["crop"],
                probability=opt["probability"],
                percentage=opt["percentage"],
            )
            for opt in rec_data.get("top_options", [])
        ]

        return RecommendationResponse(
            recommended_crop=rec_data.get("recommended_crop"),
            top_options=top_opts,
            advisory_summary=rec_data.get("advisory_summary", ""),
            farmer_notes=[],
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations for the given profile.",
        )
