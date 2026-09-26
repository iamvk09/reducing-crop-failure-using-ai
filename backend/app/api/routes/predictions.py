"""Crop failure risk prediction routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import get_current_user, get_prediction_svc
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.prediction import PredictionRequest, PredictionResponse
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("", response_model=PredictionResponse, summary="Predict Crop Failure Risk")
def create_prediction(
    req: PredictionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> PredictionResponse:
    """Predict crop failure risk for a field profile using live weather and ML pipeline."""
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
        # Filter non-None overrides
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
        return PredictionResponse(
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
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate crop failure prediction.",
        )
