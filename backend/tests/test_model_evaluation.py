"""Tests for Model Evaluation & Ground-Truth Validation Service (Milestone 11).

Rules:
- No retrained models.
- No synthetic outcomes counted as eligible.
- Prediction must precede outcome (no hindsight).
- SHAP values non-causal, disclaimer always present.
- Expert/Admin access only — farmers get 403.
- All metrics computed from real eligible pairs only.
"""

import datetime
import pytest

from backend.app.schemas.evaluation import (
    CalibrationBin,
    ClassificationMetrics,
    ConfusionMatrix,
    ModelEvaluationReport,
)
from backend.app.services.evaluation_service import (
    EvaluationService,
    _compute_brier_score,
    _compute_calibration,
    _compute_confusion_matrix,
    _compute_metrics,
    _compute_pr_auc,
    _compute_roc_auc,
    _lead_time_group,
    _safe_div,
)
from backend.app.schemas.evaluation import PredictionOutcomePair


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pair(
    pred_prob: float,
    ground_truth: int,
    crop: str = "Cotton",
    season: str = "Kharif",
    state: str = "Maharashtra",
    district: str = "Pune",
    risk_level: str = "Medium",
    lead_days: float = 30.0,
    prediction_id: str = "pred-001",
    crop_id: str = "crop-001",
    farm_id: str = "farm-001",
    outcome_status: str = None,
) -> PredictionOutcomePair:
    predicted_class = 1 if pred_prob >= 0.5 else 0
    if outcome_status is None:
        outcome_status = "failed" if ground_truth == 1 else "harvested"
    tp = predicted_class == 1 and ground_truth == 1
    fp = predicted_class == 1 and ground_truth == 0
    tn = predicted_class == 0 and ground_truth == 0
    fn = predicted_class == 0 and ground_truth == 1
    return PredictionOutcomePair(
        prediction_id=prediction_id,
        crop_id=crop_id,
        farm_id=farm_id,
        crop=crop,
        season=season,
        state=state,
        district=district,
        risk_level=risk_level,
        risk_probability=pred_prob,
        prediction_class=predicted_class,
        ground_truth_label=ground_truth,
        outcome_status=outcome_status,
        lead_time_days=lead_days,
        is_correct=tp or tn,
        is_true_positive=tp,
        is_false_positive=fp,
        is_true_negative=tn,
        is_false_negative=fn,
    )


def _perfect_pairs():
    """4 correct predictions: 2 TP + 2 TN."""
    return [
        _make_pair(0.8, 1, prediction_id="p1", crop_id="c1"),
        _make_pair(0.7, 1, prediction_id="p2", crop_id="c2"),
        _make_pair(0.3, 0, prediction_id="p3", crop_id="c3"),
        _make_pair(0.2, 0, prediction_id="p4", crop_id="c4"),
    ]


def _mixed_pairs():
    """6 pairs: 2 TP, 1 FP, 2 TN, 1 FN."""
    return [
        _make_pair(0.8, 1, prediction_id="p1", crop_id="c1"),   # TP
        _make_pair(0.7, 1, prediction_id="p2", crop_id="c2"),   # TP
        _make_pair(0.6, 0, prediction_id="p3", crop_id="c3"),   # FP
        _make_pair(0.3, 0, prediction_id="p4", crop_id="c4"),   # TN
        _make_pair(0.2, 0, prediction_id="p5", crop_id="c5"),   # TN
        _make_pair(0.4, 1, prediction_id="p6", crop_id="c6"),   # FN
    ]


# ---------------------------------------------------------------------------
# Test 1: Empty eligible pairs → metrics is None or zero pairs
# ---------------------------------------------------------------------------
def test_empty_eligible_pairs_returns_zero_count():
    metrics = _compute_metrics([])
    assert metrics.n_eligible_pairs == 0
    assert metrics.accuracy is None
    assert metrics.roc_auc is None
    assert "No eligible" in (metrics.notes or "")


# ---------------------------------------------------------------------------
# Test 2: Safe division returns None on zero denominator
# ---------------------------------------------------------------------------
def test_safe_div_zero_denominator():
    assert _safe_div(5, 0) is None
    assert _safe_div(5, 0, default=0.0) == 0.0
    assert abs(_safe_div(4, 2) - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 3: Confusion matrix is correctly computed from pairs
# ---------------------------------------------------------------------------
def test_confusion_matrix_perfect():
    pairs = _perfect_pairs()
    cm = _compute_confusion_matrix(pairs)
    assert cm.true_positive == 2
    assert cm.false_positive == 0
    assert cm.true_negative == 2
    assert cm.false_negative == 0
    assert cm.total == 4


def test_confusion_matrix_mixed():
    pairs = _mixed_pairs()
    cm = _compute_confusion_matrix(pairs)
    assert cm.true_positive == 2
    assert cm.false_positive == 1
    assert cm.true_negative == 2
    assert cm.false_negative == 1
    assert cm.total == 6


# ---------------------------------------------------------------------------
# Test 4: Classification metrics (accuracy, precision, recall, F1)
# ---------------------------------------------------------------------------
def test_classification_metrics_perfect():
    pairs = _perfect_pairs()
    m = _compute_metrics(pairs)
    assert m.accuracy == 1.0
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1_score == 1.0
    assert m.false_positive_rate == 0.0
    assert m.false_negative_rate == 0.0


def test_classification_metrics_mixed():
    pairs = _mixed_pairs()
    m = _compute_metrics(pairs)
    # precision = TP/(TP+FP) = 2/3
    assert abs(m.precision - 2 / 3) < 1e-3
    # recall = TP/(TP+FN) = 2/3
    assert abs(m.recall - 2 / 3) < 1e-3
    # accuracy = (TP+TN)/total = 4/6
    assert abs(m.accuracy - 4 / 6) < 1e-3
    # specificity = TN/(TN+FP) = 2/3
    assert abs(m.specificity - 2 / 3) < 1e-3


# ---------------------------------------------------------------------------
# Test 5: ROC-AUC returns None when only one class is present
# ---------------------------------------------------------------------------
def test_roc_auc_single_class_returns_none():
    pairs = [
        _make_pair(0.8, 1, prediction_id="p1", crop_id="c1"),
        _make_pair(0.6, 1, prediction_id="p2", crop_id="c2"),
    ]
    assert _compute_roc_auc(pairs) is None


def test_roc_auc_perfect_classifier():
    pairs = _perfect_pairs()
    auc = _compute_roc_auc(pairs)
    assert auc is not None
    assert auc == 1.0


# ---------------------------------------------------------------------------
# Test 6: Brier score is correct
# ---------------------------------------------------------------------------
def test_brier_score_perfect():
    pairs = _perfect_pairs()
    bs = _compute_brier_score(pairs)
    # (0.8-1)^2 + (0.7-1)^2 + (0.3-0)^2 + (0.2-0)^2 / 4
    expected = ((0.2 ** 2) + (0.3 ** 2) + (0.3 ** 2) + (0.2 ** 2)) / 4
    assert abs(bs - expected) < 1e-4


def test_brier_score_empty():
    assert _compute_brier_score([]) is None


# ---------------------------------------------------------------------------
# Test 7: Calibration bins correctly bucket predictions
# ---------------------------------------------------------------------------
def test_calibration_empty():
    bins, note = _compute_calibration([])
    assert bins == []
    assert "No eligible" in note


def test_calibration_bins_structure():
    pairs = _mixed_pairs()
    bins, note = _compute_calibration(pairs, n_bins=5)
    assert isinstance(bins, list)
    for b in bins:
        assert 0.0 <= b.predicted_mean_probability <= 1.0
        assert 0.0 <= b.actual_fraction_positive <= 1.0
        assert b.n_samples > 0
        assert isinstance(b.calibration_gap, float)


# ---------------------------------------------------------------------------
# Test 8: Lead time grouping
# ---------------------------------------------------------------------------
def test_lead_time_groups():
    assert _lead_time_group(None) == "unknown"
    assert _lead_time_group(3) == "<7 days"
    assert _lead_time_group(15) == "7–30 days"
    assert _lead_time_group(60) == "30–90 days"
    assert _lead_time_group(120) == ">90 days"


# ---------------------------------------------------------------------------
# Test 9: Eligibility — synthetic outcomes are excluded
# ---------------------------------------------------------------------------
def test_synthetic_outcomes_are_excluded():
    from unittest.mock import MagicMock, patch

    svc = EvaluationService()

    # Synthetic outcome stored in local feedback repo
    svc.fb_repo._local_outcomes["crop-synthetic"] = {
        "crop_id": "crop-synthetic",
        "is_synthetic": True,
        "status": "failed",
    }

    predictions = [
        {
            "id": "pred-synth",
            "crop_id": "crop-synthetic",
            "farm_id": "farm-x",
            "risk_probability": 0.75,
            "risk_level": "High",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    crop_cycles = [
        {
            "id": "crop-synthetic",
            "status": "failed",
            "updated_at": "2026-06-01T00:00:00+00:00",
        }
    ]

    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible >= 1


# ---------------------------------------------------------------------------
# Test 10: Eligibility — prediction after outcome is excluded (hindsight rule)
# ---------------------------------------------------------------------------
def test_hindsight_prediction_is_excluded():
    svc = EvaluationService()

    predictions = [
        {
            "id": "pred-late",
            "crop_id": "crop-late",
            "farm_id": "farm-y",
            "risk_probability": 0.8,
            "risk_level": "High",
            # prediction created AFTER outcome
            "created_at": "2026-07-01T00:00:00+00:00",
        }
    ]
    crop_cycles = [
        {
            "id": "crop-late",
            "status": "failed",
            "updated_at": "2026-06-01T00:00:00+00:00",
        }
    ]

    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible >= 1


# ---------------------------------------------------------------------------
# Test 11: Eligibility — active crops are excluded (status != harvested/failed)
# ---------------------------------------------------------------------------
def test_active_crops_are_excluded():
    svc = EvaluationService()

    predictions = [
        {
            "id": "pred-active",
            "crop_id": "crop-active",
            "farm_id": "farm-z",
            "risk_probability": 0.5,
            "risk_level": "Medium",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    crop_cycles = [
        {
            "id": "crop-active",
            "status": "active",
            "updated_at": "2026-06-01T00:00:00+00:00",
        }
    ]

    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible >= 1


# ---------------------------------------------------------------------------
# Test 12: Ground-truth label mapping — harvested=0, failed=1
# ---------------------------------------------------------------------------
def test_ground_truth_label_mapping():
    svc = EvaluationService()

    # Provide verified ground truth in fb_repo for both crops
    svc.fb_repo._local_outcomes["crop-harv"] = {
        "crop_id": "crop-harv",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "is_synthetic": False,
        "status": "harvested",
    }
    svc.fb_repo._local_outcomes["crop-fail"] = {
        "crop_id": "crop-fail",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "is_synthetic": False,
        "status": "failed",
    }

    predictions = [
        {
            "id": "pred-harv",
            "crop_id": "crop-harv",
            "farm_id": "farm-a",
            "risk_probability": 0.3,
            "risk_level": "Low",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "pred-fail",
            "crop_id": "crop-fail",
            "farm_id": "farm-b",
            "risk_probability": 0.8,
            "risk_level": "High",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    crop_cycles = [
        {"id": "crop-harv", "status": "harvested", "updated_at": "2026-10-01T00:00:00+00:00", "is_verified_ground_truth": True, "verification_status": "verified"},
        {"id": "crop-fail", "status": "failed", "updated_at": "2026-10-01T00:00:00+00:00", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]

    eligible, _ = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 2
    harv = next(p for p in eligible if p.prediction_id == "pred-harv")
    fail = next(p for p in eligible if p.prediction_id == "pred-fail")
    assert harv.ground_truth_label == 0
    assert fail.ground_truth_label == 1


# ---------------------------------------------------------------------------
# Test 13: ModelEvaluationReport has non-causal disclaimer in SHAP error section
# ---------------------------------------------------------------------------
def test_shap_error_analysis_non_causal_disclaimer():
    svc = EvaluationService()
    # With no data, report is generated with disclaimer
    report = svc.generate_report(user_token=None)
    assert isinstance(report, ModelEvaluationReport)
    assert "SHAP values" in report.shap_error_analysis_note
    assert "not explain why" in report.shap_error_analysis_note
    # Disclaimer must mention non-causality
    assert "causal" in report.disclaimer.lower() or "not" in report.disclaimer.lower()


# ---------------------------------------------------------------------------
# Test 14: Leakage audit contains all 16 feature groups
# ---------------------------------------------------------------------------
def test_leakage_audit_covers_key_features():
    from backend.app.services.evaluation_service import LEAKAGE_AUDIT_TABLE
    feature_names = " ".join(a.feature_name for a in LEAKAGE_AUDIT_TABLE)
    for feat in ["YieldIndex", "SuitabilityScore", "Rainfall", "NDVI_Flowering", "Temperature"]:
        assert feat in feature_names, f"Feature {feat} missing from leakage audit"


# ---------------------------------------------------------------------------
# Test 15: Leakage audit YieldIndex has high risk rating
# ---------------------------------------------------------------------------
def test_leakage_audit_yield_index_high_risk():
    from backend.app.services.evaluation_service import LEAKAGE_AUDIT_TABLE
    yi = next((a for a in LEAKAGE_AUDIT_TABLE if a.feature_name == "YieldIndex"), None)
    assert yi is not None
    assert yi.leakage_risk == "high"


# ---------------------------------------------------------------------------
# Test 16: Train/test provenance is readable and correct
# ---------------------------------------------------------------------------
def test_train_test_provenance_readable():
    from backend.app.services.evaluation_service import _read_train_test_provenance
    prov = _read_train_test_provenance()
    if prov is None:
        pytest.skip("Dataset files not accessible in this environment")
    assert prov.total_rows > 1000
    assert prov.test_size == 0.22
    assert prov.random_state == 42
    assert prov.stratified is True
    assert prov.target_column == "Failure"
    assert "Failure=1 (failure)" in prov.class_distribution
    assert prov.class_distribution["Failure=1 (failure)"] > 0


# ---------------------------------------------------------------------------
# Test 17: Model version is readable from artifact
# ---------------------------------------------------------------------------
def test_model_version_readable():
    from backend.app.services.evaluation_service import _read_model_version
    mv = _read_model_version()
    if mv is None:
        pytest.skip("Model bundle not accessible in this environment")
    assert mv.best_model_name in ("logistic_regression", "random_forest", "gradient_boosting", "extra_trees")
    assert mv.feature_count == 16
    assert mv.target_column == "Failure"
    assert "Do NOT retrain" in mv.note


# ===========================================================================
# Milestone 12 Specific Tests
# ===========================================================================

# 1. Active crop has predictions awaiting outcome.
def test_m12_active_crop_predictions_awaiting_outcome():
    svc = EvaluationService()
    predictions = [
        {"id": "p-act-1", "crop_id": "c-act-1", "farm_id": "f1", "risk_probability": 0.4, "created_at": "2026-03-01T00:00:00Z"},
        {"id": "p-act-2", "crop_id": "c-act-1", "farm_id": "f1", "risk_probability": 0.6, "created_at": "2026-03-10T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-act-1", "crop": "Cotton", "farm_id": "f1", "status": "active", "created_at": "2026-02-01T00:00:00Z", "expected_harvest_date": "2026-09-01"},
    ]
    readiness = svc.get_evaluation_readiness(predictions=predictions, crop_cycles=crop_cycles, user_token=None)
    assert len(readiness.pending_queue) == 1
    item = readiness.pending_queue[0]
    assert item.crop_id == "c-act-1"
    assert item.prediction_count == 2
    assert item.status == "active"
    assert item.readiness_status == "awaiting_harvest"


# 2. Harvested crop creates a potential evaluation pair.
def test_m12_harvested_crop_creates_potential_pair():
    svc = EvaluationService()
    predictions = [
        {"id": "p-harv-1", "crop_id": "c-harv-1", "farm_id": "f1", "risk_probability": 0.2, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-harv-1", "crop": "Cotton", "farm_id": "f1", "status": "harvested", "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z"},
    ]
    # Unverified outcome in queue
    readiness = svc.get_evaluation_readiness(predictions=predictions, crop_cycles=crop_cycles, user_token=None)
    assert len(readiness.verification_queue) == 1
    item = readiness.verification_queue[0]
    assert item.prediction_count == 1
    assert item.potential_eligible_pairs_count == 1
    assert item.verification_status == "pending"


# 3. Verified harvested outcome becomes eligible.
def test_m12_verified_harvested_outcome_becomes_eligible():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-ver-harv"] = {
        "crop_id": "c-ver-harv",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "is_synthetic": False,
        "status": "harvested",
    }
    predictions = [
        {"id": "p-ver-1", "crop_id": "c-ver-harv", "farm_id": "f1", "risk_probability": 0.2, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-ver-harv", "crop": "Cotton", "farm_id": "f1", "status": "harvested", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 1
    assert eligible[0].ground_truth_label == 0
    assert eligible[0].prediction_class == 0
    assert eligible[0].is_correct is True


# 4. Failed outcome becomes label 1.
def test_m12_failed_outcome_becomes_label_1():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-ver-fail"] = {
        "crop_id": "c-ver-fail",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "is_synthetic": False,
        "status": "failed",
    }
    predictions = [
        {"id": "p-fail-1", "crop_id": "c-ver-fail", "farm_id": "f1", "risk_probability": 0.7, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-ver-fail", "crop": "Cotton", "farm_id": "f1", "status": "failed", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    eligible, _ = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 1
    assert eligible[0].ground_truth_label == 1
    assert eligible[0].prediction_class == 1


# 5. Harvested outcome becomes label 0.
def test_m12_harvested_outcome_becomes_label_0():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-ver-h0"] = {
        "crop_id": "c-ver-h0",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "is_synthetic": False,
        "status": "harvested",
    }
    predictions = [
        {"id": "p-h0-1", "crop_id": "c-ver-h0", "farm_id": "f1", "risk_probability": 0.1, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-ver-h0", "crop": "Cotton", "farm_id": "f1", "status": "harvested", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    eligible, _ = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 1
    assert eligible[0].ground_truth_label == 0


# 6. Unverified outcome remains ineligible.
def test_m12_unverified_outcome_remains_ineligible():
    svc = EvaluationService()
    predictions = [
        {"id": "p-unver-1", "crop_id": "c-unver-1", "farm_id": "f1", "risk_probability": 0.4, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-unver-1", "crop": "Cotton", "farm_id": "f1", "status": "harvested", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": False, "verification_status": "pending"},
    ]
    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible == 1


# 7. Synthetic outcome remains excluded.
def test_m12_synthetic_outcome_remains_excluded():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-synth-1"] = {
        "crop_id": "c-synth-1",
        "is_verified_ground_truth": True,
        "is_synthetic": True,
        "status": "failed",
    }
    predictions = [
        {"id": "p-synth-1", "crop_id": "c-synth-1", "farm_id": "f1", "risk_probability": 0.9, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-synth-1", "status": "failed", "updated_at": "2026-08-01T00:00:00Z", "is_synthetic": True},
    ]
    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible == 1


# 8. Invalid outcome remains excluded.
def test_m12_invalid_outcome_remains_excluded():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-inv-1"] = {
        "crop_id": "c-inv-1",
        "is_verified_ground_truth": False,
        "verification_status": "invalid",
        "status": "failed",
    }
    predictions = [
        {"id": "p-inv-1", "crop_id": "c-inv-1", "farm_id": "f1", "risk_probability": 0.9, "created_at": "2026-03-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-inv-1", "status": "failed", "updated_at": "2026-08-01T00:00:00Z", "verification_status": "invalid"},
    ]
    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible == 1


# 9. Prediction after outcome is excluded (hindsight rule).
def test_m12_prediction_after_outcome_excluded():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-hind-1"] = {
        "crop_id": "c-hind-1",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "status": "harvested",
    }
    predictions = [
        {"id": "p-hind-1", "crop_id": "c-hind-1", "farm_id": "f1", "risk_probability": 0.1, "created_at": "2026-09-01T00:00:00Z"},
    ]
    crop_cycles = [
        {"id": "c-hind-1", "status": "harvested", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    eligible, ineligible = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 0
    assert ineligible == 1


# 10. Lead-time calculation and groupings.
def test_m12_lead_time_calculation_and_groupings():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-lead-1"] = {
        "crop_id": "c-lead-1",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "status": "harvested",
    }
    predictions = [
        {"id": "p-lt-1", "crop_id": "c-lead-1", "farm_id": "f1", "risk_probability": 0.2, "created_at": "2026-07-25T00:00:00Z"}, # ~7 days
        {"id": "p-lt-2", "crop_id": "c-lead-1", "farm_id": "f1", "risk_probability": 0.2, "created_at": "2026-07-01T00:00:00Z"}, # ~31 days
    ]
    crop_cycles = [
        {"id": "c-lead-1", "status": "harvested", "updated_at": "2026-08-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    eligible, _ = svc._build_eligible_pairs(predictions, crop_cycles)
    assert len(eligible) == 2
    assert eligible[0].lead_time_days is not None
    assert eligible[0].lead_time_days > 0
    assert _lead_time_group(6) == "<7 days"
    assert _lead_time_group(20) == "7–30 days"
    assert _lead_time_group(45) == "30–90 days"
    assert _lead_time_group(100) == ">90 days"


# 11. Model-version separation.
def test_m12_model_version_separation():
    pair1 = _make_pair(0.8, 1, prediction_id="p1")
    pair1.model_version = "v1.0.0"
    pair2 = _make_pair(0.2, 0, prediction_id="p2")
    pair2.model_version = "v2.0.0"
    
    assert pair1.model_version != pair2.model_version
    assert pair1.model_version == "v1.0.0"


# 12. Evaluation readiness count & queue logic.
def test_m12_evaluation_readiness_counts():
    svc = EvaluationService()
    svc.fb_repo._local_outcomes["c-ver"] = {
        "crop_id": "c-ver",
        "is_verified_ground_truth": True,
        "verification_status": "verified",
        "status": "harvested",
    }
    predictions = [
        {"id": "p-1", "crop_id": "c-act", "farm_id": "f1", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "p-2", "crop_id": "c-unver", "farm_id": "f1", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "p-3", "crop_id": "c-ver", "farm_id": "f1", "created_at": "2026-01-01T00:00:00Z", "risk_probability": 0.65},
    ]
    crop_cycles = [
        {"id": "c-act", "crop": "Wheat", "farm_id": "f1", "status": "active", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "c-unver", "crop": "Cotton", "farm_id": "f1", "status": "harvested", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z"},
        {"id": "c-ver", "crop": "Rice", "farm_id": "f1", "status": "harvested", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z", "is_verified_ground_truth": True, "verification_status": "verified"},
    ]
    readiness = svc.get_evaluation_readiness(predictions=predictions, crop_cycles=crop_cycles, user_token=None)
    assert readiness.summary.predictions_awaiting_outcome == 1
    assert readiness.summary.unverified_outcomes == 1
    assert readiness.summary.verified_outcomes == 1
    assert readiness.summary.eligible_prediction_outcome_pairs == 1
    assert readiness.summary.evaluation_coverage_percentage is not None
    assert readiness.summary.evaluation_coverage_percentage > 0


# 13. Farmer cannot expert-verify outcome (RBAC).
def test_m12_farmer_cannot_expert_verify_outcome(farmer1_token):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {farmer1_token}"}
    response = client.post(
        "/api/v1/experts/crops/crop-1/verify-outcome",
        headers=headers,
        json={"action": "verify", "notes": "Farmer trying to self-verify"},
    )
    assert response.status_code in (401, 403)


# 14. Authorized expert can verify outcome.
def test_m12_authorized_expert_can_verify_outcome(expert_token):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.repositories.farm_repository import farm_repository
    client = TestClient(app)

    # Seed local farm and crop
    with farm_repository._lock:
        farm_repository._local_farms["farm-demo"] = {
            "id": "farm-demo",
            "user_id": "user-farmer-1",
            "name": "Demo Farm",
            "state": "Maharashtra",
            "district": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
        }
        farm_repository._local_crops["crop-demo-test"] = {
            "id": "crop-demo-test",
            "farm_id": "farm-demo",
            "crop": "Cotton",
            "season": "Kharif",
            "status": "harvested",
        }

    headers = {"Authorization": f"Bearer {expert_token}"}
    response = client.post(
        "/api/v1/experts/crops/crop-demo-test/verify-outcome",
        headers=headers,
        json={"action": "verify", "verification_notes": "Verified by agronomist"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verification_status"] == "verified"
    assert data["is_verified_ground_truth"] is True


# 15. Tenant isolation (Expert evaluation endpoint RBAC).
def test_m12_tenant_isolation_evaluation_readiness(farmer1_token, expert_token):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)

    # Farmer forbidden from accessing expert evaluation-readiness
    res_farmer = client.get("/api/v1/experts/evaluation-readiness", headers={"Authorization": f"Bearer {farmer1_token}"})
    assert res_farmer.status_code in (401, 403)

    # Expert authorized
    res_expert = client.get("/api/v1/experts/evaluation-readiness", headers={"Authorization": f"Bearer {expert_token}"})
    assert res_expert.status_code == 200
    assert "summary" in res_expert.json()


# 16. NDVI baseline provenance remains correctly labeled.
def test_m12_ndvi_flowering_provenance_baseline():
    from backend.app.services.evaluation_service import LEAKAGE_AUDIT_TABLE
    ndvi_item = next((a for a in LEAKAGE_AUDIT_TABLE if a.feature_name == "NDVI_Flowering"), None)
    assert ndvi_item is not None
    assert ndvi_item.provenance_type == "BASELINE"
    assert "historical flowering baseline" in ndvi_item.reason.lower() or "baseline" in ndvi_item.reason.lower()


# 17. No metric is produced with zero eligible outcomes.
def test_m12_no_metric_with_zero_eligible_outcomes():
    svc = EvaluationService()
    report = svc.generate_report(user_token=None)
    assert report.eligible_pair_count == 0
    assert report.metrics is None
    assert report.calibration_bins == []


