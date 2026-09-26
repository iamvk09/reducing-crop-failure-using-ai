"""Expert analytics, SHAP explanations, and Digital Twin routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import get_expert_user, get_prediction_svc
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.expert import (
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
    ShapExplanationResponse,
    ShapFeatureItem,
)
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/experts", tags=["Expert Analytics"])


@router.post("/explain", response_model=ShapExplanationResponse, summary="SHAP Model Explanation")
def explain_prediction(
    district: str,
    crop: str,
    season: str = "Kharif",
    user: AuthenticatedUser = Depends(get_expert_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> ShapExplanationResponse:
    """Generate SHAP feature attribution explanation (restricted to Experts and Admins)."""
    try:
        baseline = service.get_baseline(district=district, crop=crop, season=season)
        exp_result = service.get_explanation(baseline["feature_baselines"])

        items = [
            ShapFeatureItem(
                feature=it["feature"],
                display_name=it["display_name"],
                impact=it["impact"],
                abs_impact=it["abs_impact"],
                direction=it["direction"],
            )
            for it in exp_result.get("top_features", [])
        ]

        return ShapExplanationResponse(
            explainer_type=exp_result.get("explainer_type", "LinearExplainer"),
            summary=exp_result.get("summary", ""),
            top_features=items,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate SHAP explanation.",
        )


@router.post("/simulate", response_model=ScenarioSimulationResponse, summary="Digital Twin Stress Simulation")
def simulate_scenario(
    req: ScenarioSimulationRequest,
    district: str = "Pune",
    crop: str = "Soybean",
    season: str = "Kharif",
    user: AuthenticatedUser = Depends(get_expert_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> ScenarioSimulationResponse:
    """Simulate custom environmental stress scenarios on a crop profile."""
    try:
        baseline = service.get_baseline(district=district, crop=crop, season=season)
        res = service.run_scenario(
            baseline["feature_baselines"],
            scenario_name=req.scenario_name,
            updates=req.updates,
        )
        return ScenarioSimulationResponse(
            scenario=res["Scenario"],
            risk_score=res["RiskScore"],
            risk_percentage=f"{res['RiskScore'] * 100:.1f}%",
            adjusted_features={
                "Rainfall": res["Rainfall"],
                "Temperature": res["Temperature"],
                "Humidity": res["Humidity"],
                "SoilMoisture": res["SoilMoisture"],
                "NDVI_Flowering": res["NDVI_Flowering"],
                "WaterStress": res["WaterStress"],
            },
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run Digital Twin simulation.",
        )
