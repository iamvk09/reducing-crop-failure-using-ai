"""Model Evaluation & Ground-Truth Validation Schemas.

Defines Pydantic response models for the read-only model evaluation endpoint.
All metrics are derived from real, non-synthetic, verified outcomes only.
No causal language is used in any field name or description.
Expert/Admin access only — never exposed to farmers.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EligibilityReason(BaseModel):
    """Explanation of why a prediction-outcome pair was included or excluded from evaluation."""

    eligible: bool = Field(..., description="Whether this pair passed all eligibility criteria.")
    reason: str = Field(..., description="Human-readable eligibility determination.")


class PredictionOutcomePair(BaseModel):
    """A single matched prediction → ground-truth outcome record used in evaluation."""

    prediction_id: str
    crop_id: str
    farm_id: str
    crop: Optional[str] = None
    season: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    region: Optional[str] = None
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    feature_provenance: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Feature provenance classification: LIVE, DERIVED, BASELINE",
    )
    risk_probability: float
    risk_level: str
    prediction_class: int  # 0 or 1
    ground_truth_label: int  # 0=success, 1=failure
    outcome_status: str  # harvested | failed
    predicted_at: Optional[str] = None
    outcome_recorded_at: Optional[str] = None
    lead_time_days: Optional[float] = None
    is_correct: bool
    is_true_positive: bool
    is_false_positive: bool
    is_true_negative: bool
    is_false_negative: bool


class ConfusionMatrix(BaseModel):
    """Binary confusion matrix at threshold=0.5."""

    true_positive: int = Field(..., description="Predicted failure=1, actual failure=1")
    false_positive: int = Field(..., description="Predicted failure=1, actual success=0")
    true_negative: int = Field(..., description="Predicted success=0, actual success=0")
    false_negative: int = Field(..., description="Predicted success=0, actual failure=1")
    total: int


class ClassificationMetrics(BaseModel):
    """Complete binary classification metric set. All metrics computed at threshold=0.5."""

    n_eligible_pairs: int = Field(..., description="Number of prediction-outcome pairs used in evaluation.")
    accuracy: Optional[float] = Field(None, description="(TP+TN)/total")
    precision: Optional[float] = Field(None, description="TP/(TP+FP) — of predicted failures, fraction that were real failures.")
    recall: Optional[float] = Field(None, description="TP/(TP+FN) — of actual failures, fraction the model flagged.")
    f1_score: Optional[float] = Field(None, description="Harmonic mean of precision and recall.")
    specificity: Optional[float] = Field(None, description="TN/(TN+FP) — true negative rate.")
    false_positive_rate: Optional[float] = Field(None, description="FP/(FP+TN)")
    false_negative_rate: Optional[float] = Field(None, description="FN/(FN+TP)")
    roc_auc: Optional[float] = Field(None, description="Area under ROC curve. Requires both classes to be present.")
    pr_auc: Optional[float] = Field(None, description="Area under precision-recall curve.")
    brier_score: Optional[float] = Field(None, description="Mean squared error of predicted probabilities vs actual labels.")
    confusion_matrix: Optional[ConfusionMatrix] = None
    threshold_used: float = Field(0.5, description="Decision threshold for binary classification.")
    notes: Optional[str] = None


class CalibrationBin(BaseModel):
    """One bin in a reliability diagram / calibration table."""

    bin_lower: float
    bin_upper: float
    bin_center: float
    predicted_mean_probability: float
    actual_fraction_positive: float
    n_samples: int
    calibration_gap: float = Field(..., description="actual_fraction - predicted_mean. Positive = under-confident, negative = over-confident.")


class SubgroupMetrics(BaseModel):
    """Classification metrics for a specific subgroup slice."""

    subgroup_key: str = Field(..., description="E.g. 'crop', 'season', 'region'")
    subgroup_value: str = Field(..., description="E.g. 'Cotton', 'Kharif', 'Central'")
    n_pairs: int
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    roc_auc: Optional[float] = None
    false_positive_rate: Optional[float] = None
    false_negative_rate: Optional[float] = None
    notes: Optional[str] = None


class ShapErrorRecord(BaseModel):
    """Non-causal SHAP context for a misclassified prediction.
    Presented as a correlation observation only — not as causal attribution.
    """

    prediction_id: str
    error_type: str  # false_positive | false_negative
    ground_truth_label: int
    predicted_class: int
    risk_probability: float
    top_shap_contributors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top SHAP contributors from the stored explanation. Non-causal observation only.",
    )
    disclaimer: str = Field(
        "SHAP values describe model feature weights for this prediction. They do not explain why the outcome occurred in the real world.",
        description="Non-causal disclaimer always included.",
    )


class DataLeakageAudit(BaseModel):
    """Static audit of training features for potential data leakage."""

    feature_name: str
    leakage_risk: str  # none | low | medium | high
    reason: str
    training_source: Optional[str] = None
    live_source: Optional[str] = None
    provenance_type: Optional[str] = Field("BASELINE", description="Feature provenance classification: LIVE, DERIVED, BASELINE")
    recommendation: Optional[str] = None


class TrainTestProvenanceRecord(BaseModel):
    """Documented provenance of the model training/evaluation split."""

    dataset_file: str
    total_rows: int
    feature_count: int
    target_column: str
    class_distribution: Dict[str, int]
    class_balance_ratio: float
    test_size: float
    test_rows: int
    train_rows: int
    random_state: int
    stratified: bool
    model_selection_metric: str
    best_model_name: str
    best_model_roc_auc: float
    best_model_f1: float
    all_model_results: List[Dict[str, Any]]


class ModelVersionRecord(BaseModel):
    """Summary of a stored model artifact."""

    artifact_file: str
    best_model_name: str
    models_in_bundle: List[str]
    feature_count: int
    numeric_features: List[str]
    categorical_features: List[str]
    target_column: str
    training_dataset_rows: Optional[int] = None
    training_roc_auc: Optional[float] = None
    training_f1: Optional[float] = None
    note: str = "Read from runtime bundle. Do NOT retrain."


class ModelEvaluationReport(BaseModel):
    """Top-level model evaluation report returned by GET /api/v1/experts/model-evaluation.

    Populated only from real, non-synthetic, verified ground-truth outcomes linked to
    persisted predictions. If no eligible pairs exist, metrics fields will be None and
    notes will explain the situation.

    Expert and Admin access only. Never exposed to farmers.
    """

    report_generated_at: str
    evaluation_period_label: str = Field(
        "All time (since prediction persistence began)",
        description="Describes the time window evaluated.",
    )

    # Eligibility summary
    total_predictions_in_db: int
    total_crop_cycles_with_outcome: int
    eligible_pair_count: int
    ineligible_pair_count: int
    eligibility_filter_rules: List[str] = Field(
        default_factory=list,
        description="Rules applied to determine eligibility. No synthetic or unverified outcomes.",
    )

    # Classification metrics (None if < 2 eligible pairs)
    metrics: Optional[ClassificationMetrics] = None

    # Calibration table (None if insufficient data)
    calibration_bins: List[CalibrationBin] = Field(default_factory=list)
    calibration_note: Optional[str] = None

    # Subgroup analysis
    subgroup_analysis: List[SubgroupMetrics] = Field(default_factory=list)
    subgroup_analysis_note: Optional[str] = None

    # Lead time analysis
    lead_time_groups: List[SubgroupMetrics] = Field(default_factory=list)
    lead_time_analysis_note: Optional[str] = None

    # Error analysis (SHAP context, non-causal)
    false_positive_examples: List[ShapErrorRecord] = Field(default_factory=list, max_length=5)
    false_negative_examples: List[ShapErrorRecord] = Field(default_factory=list, max_length=5)
    shap_error_analysis_note: str = Field(
        "SHAP values in error examples describe the model's feature weightings at prediction time. "
        "They do not explain why the real-world outcome differed. No causal inference should be drawn.",
    )

    # Data leakage audit
    leakage_audit: List[DataLeakageAudit] = Field(default_factory=list)

    # Training provenance
    train_test_provenance: Optional[TrainTestProvenanceRecord] = None

    # Model versioning
    model_version: Optional[ModelVersionRecord] = None

    # General disclaimer
    disclaimer: str = Field(
        "This report is derived from a limited set of real, non-synthetic, expert-verified crop outcomes "
        "matched to historical predictions. Metrics may not be statistically representative if the "
        "eligible pair count is small. Do NOT retrain the model based on this report alone. "
        "SHAP values are correlation observations, not causal explanations."
    )


# ---------------------------------------------------------------------------
# Evaluation Readiness & Queue Models (Milestone 12)
# ---------------------------------------------------------------------------

class PendingEvaluationCropItem(BaseModel):
    """Crop cycle actively growing with predictions waiting for eventual harvest/failure."""

    farm_id: str
    farm_name: str
    crop_id: str
    crop: str
    season: str
    status: str
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    prediction_count: int
    earliest_prediction_date: Optional[str] = None
    latest_prediction_date: Optional[str] = None
    readiness_status: str = Field(
        "awaiting_harvest",
        description="Current evaluation lifecycle stage: awaiting_harvest",
    )


class OutcomeVerificationQueueItem(BaseModel):
    """Crop outcome recorded by farmer or expert awaiting validation."""

    farm_id: str
    farm_name: str
    crop_id: str
    crop: str
    season: str
    status: str  # harvested | failed
    actual_harvest_date: Optional[str] = None
    reported_yield_kg_per_ha: Optional[float] = None
    outcome_notes: Optional[str] = None
    recorded_at: Optional[str] = None
    prediction_count: int
    potential_eligible_pairs_count: int
    verification_status: str = Field(
        "pending",
        description="Verification state: 'pending' (farmer reported), 'verified' (expert approved), 'synthetic', 'invalid'",
    )
    is_verified_ground_truth: bool = False
    is_synthetic: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    verification_notes: Optional[str] = None


class EvaluationReadinessSummary(BaseModel):
    """High-level readiness metrics for the evaluation pipeline."""

    total_predictions: int
    total_crop_cycles: int
    predictions_awaiting_outcome: int
    crop_cycles_awaiting_outcome: int
    verified_outcomes: int
    unverified_outcomes: int
    synthetic_outcomes: int
    invalid_outcomes: int
    eligible_prediction_outcome_pairs: int
    ineligible_predictions: int
    evaluation_coverage_percentage: float = Field(
        ...,
        description="eligible_pairs / predictions_linked_to_crops — proportion of trackable predictions that have passed verified ground-truth validation (not a measure of model accuracy)",
    )
    coverage_definition: str = Field(
        "eligible_pairs / predictions_linked_to_crops — proportion of trackable predictions that have passed verified ground-truth validation (not a measure of accuracy)",
        description="Explicit definition of evaluation coverage",
    )


class EvaluationReadinessResponse(BaseModel):
    """Evaluation readiness diagnostic response (GET /api/v1/experts/evaluation-readiness).

    Expert and Admin access only. Never exposed to farmers.
    """

    report_generated_at: str
    summary: EvaluationReadinessSummary
    pending_queue: List[PendingEvaluationCropItem] = Field(default_factory=list)
    verification_queue: List[OutcomeVerificationQueueItem] = Field(default_factory=list)
    exclusions_breakdown: Dict[str, int] = Field(default_factory=dict)
    average_lead_time_days: Optional[float] = None
    lead_time_distribution: Dict[str, int] = Field(default_factory=dict)
    model_version_breakdown: Dict[str, int] = Field(default_factory=dict)
    disclaimer: str = Field(
        "Model performance metrics require verified crop outcomes. "
        "Evaluation coverage indicates dataset maturity, not model accuracy.",
        description="Explicit non-causal and non-accuracy disclaimer",
    )

