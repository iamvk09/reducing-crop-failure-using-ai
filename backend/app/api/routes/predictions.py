"""Crop failure risk prediction routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from backend.app.api.deps import get_any_authenticated_user, get_client_ip, get_prediction_svc
from backend.app.core.config import settings
from backend.app.core.rate_limiter import check_rate_limit, prediction_limiter
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.prediction import PredictionRequest, PredictionResponse, RecommendationDetails
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("", response_model=PredictionResponse, summary="Predict Crop Failure Risk")
def create_prediction(
    req: PredictionRequest,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> PredictionResponse:
    """Predict crop failure risk for a field profile using live weather and ML pipeline."""
    # Defense-in-depth rate limiting per authenticated user (or IP fallback)
    rate_key = f"pred_user_{user.id}" if user and user.id else "pred_anon"
    check_rate_limit(
        rate_key,
        prediction_limiter,
        limit=settings.RATE_LIMIT_PREDICTIONS_PER_MIN,
        error_message="Prediction request rate limit exceeded. Please wait before submitting another prediction.",
    )

    try:
        overrides = {
            "rainfall_override": req.rainfall_override,
            "temperature_override": req.temperature_override,
            "humidity_override": req.humidity_override,
            "soil_moisture_override": req.soil_moisture_override,
            "ndvi_override": req.ndvi_override,
            "water_stress_override": req.water_stress_override,
            "pest_risk_override": req.pest_risk_override,
            "suitability_score_override": req.suitability_score_override,
            "yield_index_override": req.yield_index_override,
        }
        active_overrides = {k: v for k, v in overrides.items() if v is not None}

        result = service.predict_with_weather(
            state=req.state,
            district=req.district,
            crop=req.crop,
            season=req.season,
            soil_type=req.soil_type,
            irrigation_level=req.irrigation_level,
            overrides=active_overrides if active_overrides else None,
        )

        pred = result["prediction"]
        rec_data = service.get_recommendation(result["input_features"], district=req.district)
        rec_details = RecommendationDetails(
            recommended_crop=rec_data.get("recommended_crop"),
            top_options=rec_data.get("top_options", []),
            advisory_summary=rec_data.get("advisory_summary", ""),
        )

        return PredictionResponse(
            farm_id=req.farm_id,
            crop_id=req.crop_id,
            crop=req.crop,
            district=req.district,
            state=req.state,
            season=req.season,
            risk_probability=pred["risk_probability"],
            risk_percentage=f"{pred['risk_probability'] * 100:.1f}%",
            risk_level=pred["risk_level"],
            prediction_class=pred["prediction"],
            best_model_name=pred["best_model_name"],
            global_risk=pred.get("global_risk"),
            region_risk=pred.get("region_risk"),
            crop_risk=pred.get("crop_risk"),
            consensus_risk=pred.get("consensus_risk"),
            input_features=result["input_features"],
            provenance=result["provenance"],
            weather_data=result.get("weather"),
            data_quality=result.get("data_quality"),
            explanation=result.get("explanation"),
            recommendations=rec_details,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate crop failure prediction: {e}",
        )


@router.get("/history", response_model=List[PredictionResponse], summary="List My Prediction History")
@router.get("/my-history", response_model=List[PredictionResponse], summary="List My Prediction History (Alias)")
def list_my_predictions(
    limit: int = 50,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> List[PredictionResponse]:
    """Retrieve full persisted historical predictions for the currently authenticated user."""
    return service.list_predictions_for_user(user=user, limit=limit, offset=offset)


@router.get("/{prediction_id}", response_model=PredictionResponse, summary="Get Prediction by ID")
def get_prediction(
    prediction_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> PredictionResponse:
    """Retrieve details and audit metadata for a specific prediction with tenant isolation."""
    pred = service.get_prediction(prediction_id=prediction_id, user=user)
    if not pred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction '{prediction_id}' not found or access denied.",
        )
    return pred
