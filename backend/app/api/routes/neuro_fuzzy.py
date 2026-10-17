"""Experimental Neuro-Fuzzy Crop Failure Risk routes for Experts and Researchers."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.deps import get_any_authenticated_user, get_expert_user
from backend.app.core.config import settings
from backend.app.core.rate_limiter import check_rate_limit, prediction_limiter
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.neuro_fuzzy import (
    NeuroFuzzyModelStatusResponse,
    NeuroFuzzyPredictionRequest,
    NeuroFuzzyPredictionResponse,
    NeuroFuzzyRuleExplanationSchema,
)
from src.neuro_fuzzy import NeuroFuzzyCropFailureModel, FEATURE_NAMES

router = APIRouter(prefix="/experimental/neuro-fuzzy", tags=["Experimental Neuro-Fuzzy Model"])

_MODEL_PATH = Path("models/neuro_fuzzy_model.json")
_COMPARISON_PATH = Path("models/neuro_fuzzy_comparison.csv")
_LOADED_MODEL: Optional[NeuroFuzzyCropFailureModel] = None


def get_neuro_fuzzy_model() -> Optional[NeuroFuzzyCropFailureModel]:
    """Lazy singleton loader for persisted Neuro-Fuzzy model."""
    global _LOADED_MODEL
    if _LOADED_MODEL is not None and _LOADED_MODEL.is_trained:
        return _LOADED_MODEL

    if _MODEL_PATH.exists():
        try:
            _LOADED_MODEL = NeuroFuzzyCropFailureModel.load(_MODEL_PATH)
            return _LOADED_MODEL
        except Exception:
            return None
    return None


@router.get("/status", response_model=NeuroFuzzyModelStatusResponse, summary="Get Neuro-Fuzzy Model Status")
def get_model_status(
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
) -> NeuroFuzzyModelStatusResponse:
    """Retrieve operational status, rule base, and version of the experimental neuro-fuzzy model."""
    model = get_neuro_fuzzy_model()
    comparison_records: List[Dict[str, Any]] = []
    if _COMPARISON_PATH.exists():
        try:
            df = pd.read_csv(_COMPARISON_PATH)
            comparison_records = df.to_dict(orient="records")
        except Exception:
            comparison_records = []

    if not model or not model.is_trained:
        return NeuroFuzzyModelStatusResponse(
            is_available=False,
            version="1.0.0-uninitialized",
            n_rules=0,
            optimal_threshold=0.50,
            feature_names=FEATURE_NAMES,
            training_metadata={"status": "not_trained"},
            comparison_summary=comparison_records,
        )

    return NeuroFuzzyModelStatusResponse(
        is_available=True,
        version=model.VERSION,
        n_rules=model.n_rules,
        optimal_threshold=round(model.optimal_threshold, 4),
        feature_names=model.feature_names,
        training_metadata=model.training_metadata,
        comparison_summary=comparison_records,
    )


@router.post("/predict", response_model=NeuroFuzzyPredictionResponse, summary="Predict Risk with Neuro-Fuzzy Model")
def predict_neuro_fuzzy(
    req: NeuroFuzzyPredictionRequest,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
) -> NeuroFuzzyPredictionResponse:
    """Evaluate validated continuous agricultural inputs through the Sugeno Neuro-Fuzzy inference system."""
    rate_key = f"nf_user_{user.id}" if user and user.id else "nf_anon"
    check_rate_limit(
        rate_key,
        prediction_limiter,
        limit=settings.RATE_LIMIT_PREDICTIONS_PER_MIN,
        error_message="Neuro-fuzzy prediction rate limit exceeded. Please wait before submitting another prediction.",
    )

    model = get_neuro_fuzzy_model()
    if not model or not model.is_trained:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Experimental Neuro-Fuzzy model is currently unavailable or not trained.",
        )

    input_dict = {
        "Rainfall": req.rainfall,
        "Temperature": req.temperature,
        "Humidity": req.humidity,
        "SoilMoisture": req.soil_moisture,
        "NDVI_Flowering": req.ndvi_flowering,
        "WaterStress": req.water_stress,
        "PestRisk": req.pest_risk,
        "SuitabilityScore": req.suitability_score,
    }

    try:
        explanation = model.explain_prediction(input_dict)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error in Neuro-Fuzzy reasoning engine: {e}",
        )

    rules_schemas = [
        NeuroFuzzyRuleExplanationSchema(
            rule_index=r.rule_index,
            rule_name=r.rule_name,
            description=r.description,
            firing_strength=r.firing_strength,
            normalized_weight=r.normalized_weight,
            consequent_score=r.consequent_score,
            rule_contribution=r.rule_contribution,
            antecedent_memberships=r.antecedent_memberships,
        )
        for r in explanation.activated_rules
    ]

    dom = explanation.dominant_rule
    dominant_schema = NeuroFuzzyRuleExplanationSchema(
        rule_index=dom.rule_index,
        rule_name=dom.rule_name,
        description=dom.description,
        firing_strength=dom.firing_strength,
        normalized_weight=dom.normalized_weight,
        consequent_score=dom.consequent_score,
        rule_contribution=dom.rule_contribution,
        antecedent_memberships=dom.antecedent_memberships,
    )

    return NeuroFuzzyPredictionResponse(
        model_version=explanation.model_version,
        risk_score=explanation.risk_score,
        risk_percentage=f"{explanation.risk_score * 100:.1f}%",
        risk_band=explanation.risk_band,
        failure_predicted=explanation.failure_predicted,
        threshold=explanation.threshold,
        dominant_rule=dominant_schema,
        activated_rules=rules_schemas,
        calibrated_probability=explanation.calibrated_probability,
        feature_provenance=explanation.feature_provenance,
    )


@router.get("/comparison", summary="Get Fair Model Comparison Metrics")
def get_model_comparison(
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
) -> List[Dict[str, Any]]:
    """Retrieve held-out test evaluation benchmarks across Neuro-Fuzzy and baseline classifiers."""
    if not _COMPARISON_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation benchmark record not found on server.",
        )
    try:
        df = pd.read_csv(_COMPARISON_PATH)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load comparison benchmarks: {e}",
        )
