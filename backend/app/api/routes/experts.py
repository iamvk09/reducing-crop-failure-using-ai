"""Expert analytics, SHAP explanations, Digital Twin, Alerts, and Model Evaluation routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.app.api.deps import (
    get_alert_svc,
    get_any_authenticated_user,
    get_evaluation_svc,
    get_expert_user,
    get_monitoring_svc,
    get_prediction_svc,
    get_raw_token,
)
from backend.app.core.config import settings
from backend.app.core.rate_limiter import check_rate_limit, diagnostics_limiter
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.alert import FarmAlertResponse
from backend.app.schemas.evaluation import EvaluationReadinessResponse, ModelEvaluationReport
from backend.app.schemas.expert import (
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
    ShapExplanationResponse,
    ShapFeatureItem,
)
from backend.app.schemas.monitoring import CropOutcomeResponse, OutcomeVerificationRequest
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/experts", tags=["Expert Analytics"])


@router.post("/explain", response_model=ShapExplanationResponse, summary="SHAP Model Explanation")
def explain_prediction(
    district: str,
    crop: str,
    season: str = "Kharif",
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> ShapExplanationResponse:
    """Generate SHAP feature attribution explanation for all authenticated users."""
    rate_key = f"diag_user_{user.id}" if user and user.id else "diag_anon"
    check_rate_limit(
        rate_key,
        diagnostics_limiter,
        limit=settings.RATE_LIMIT_DIAGNOSTICS_PER_MIN,
        error_message="SHAP explanation rate limit exceeded. Please wait before requesting another explanation.",
    )

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
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    service: PredictionService = Depends(get_prediction_svc),
) -> ScenarioSimulationResponse:
    """Simulate custom environmental stress scenarios on a crop profile."""
    rate_key = f"diag_user_{user.id}" if user and user.id else "diag_anon"
    check_rate_limit(
        rate_key,
        diagnostics_limiter,
        limit=settings.RATE_LIMIT_DIAGNOSTICS_PER_MIN,
        error_message="Simulation rate limit exceeded. Please wait before submitting another scenario.",
    )

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


@router.get("/alerts", response_model=List[FarmAlertResponse], summary="List All Cross-Farm Alerts (Expert)")
def list_all_expert_alerts(
    alert_type: Optional[str] = Query(None, description="Filter by alert_type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    alert_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    user: AuthenticatedUser = Depends(get_expert_user),
    alert_svc=Depends(get_alert_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> List[FarmAlertResponse]:
    """Retrieve all alerts across all farms. Expert and Admin access only."""
    try:
        alerts = alert_svc.list_all_alerts(
            role=user.role,
            alert_type=alert_type,
            severity=severity,
            alert_status=alert_status,
            limit=limit,
            user_token=raw_token,
        )
        return alerts
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list cross-farm alerts: {exc}",
        )


@router.get(
    "/model-evaluation",
    response_model=ModelEvaluationReport,
    summary="Model Evaluation & Ground-Truth Validation Report",
)
def get_model_evaluation(
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    eval_svc=Depends(get_evaluation_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> ModelEvaluationReport:
    """Return a read-only model evaluation report derived from real, non-synthetic,
    verified ground-truth crop outcomes linked to historical predictions.

    Available to all authenticated users in the open workbench.

    Notes:
    - Do NOT retrain the model based on this report.
    - SHAP values shown in error analysis are correlation observations, not causal explanations.
    - Metrics may not be statistically representative if eligible pair count is small.
    """
    try:
        report = eval_svc.generate_report(user_token=raw_token)
        return report
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate model evaluation report: {exc}",
        )


@router.get(
    "/evaluation-readiness",
    response_model=EvaluationReadinessResponse,
    summary="Evaluation Readiness Diagnostic & Queue",
)
def get_evaluation_readiness(
    user: AuthenticatedUser = Depends(get_expert_user),
    eval_svc=Depends(get_evaluation_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> EvaluationReadinessResponse:
    """Diagnostic endpoint returning crop cycles awaiting outcome, outcome verification queue,
    eligibility preview, and evaluation coverage metrics.
    """
    try:
        return eval_svc.get_evaluation_readiness(user_token=raw_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate evaluation readiness report: {exc}",
        )


@router.post(
    "/crops/{crop_id}/verify-outcome",
    response_model=CropOutcomeResponse,
    summary="Verify or Reject Crop Outcome (Expert)",
)
def verify_crop_outcome_expert(
    crop_id: str,
    body: OutcomeVerificationRequest,
    farm_id: Optional[str] = Query(None, description="Optional farm ID associated with the crop"),
    user: AuthenticatedUser = Depends(get_expert_user),
    monitoring_svc=Depends(get_monitoring_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> CropOutcomeResponse:
    """Verify or reject a recorded crop outcome for ground-truth model evaluation.

    Restricted to Agricultural Experts and System Administrators.
    """
    try:
        # If farm_id not provided, find the farm from the crop cycle
        target_farm_id = farm_id
        if not target_farm_id:
            from backend.app.repositories.farm_repository import farm_repository
            with farm_repository._lock:
                crop = farm_repository._local_crops.get(crop_id)
            if crop:
                target_farm_id = crop.get("farm_id")

        if not target_farm_id:
            # Try fetching from Supabase
            if supabase_client.is_live_configured():
                records = supabase_client.select("farm_crops", params={"id": f"eq.{crop_id}"}, user_token=raw_token)
                if records:
                    target_farm_id = records[0].get("farm_id")

        if not target_farm_id:
            raise ValueError(f"Crop cycle '{crop_id}' not found.")

        return monitoring_svc.verify_crop_outcome(
            farm_id=target_farm_id,
            crop_id=crop_id,
            user=user,
            action=body.action,
            verification_notes=body.verification_notes,
            user_token=raw_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify crop outcome: {exc}",
        )


