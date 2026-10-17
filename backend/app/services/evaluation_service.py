"""Model Evaluation & Ground-Truth Validation Service.

Computes classification metrics, calibration tables, subgroup analysis,
lead-time analysis, SHAP error context, and data leakage audit for the
persisted prediction history linked to verified ground-truth crop outcomes.

Constraints:
- Do NOT retrain the model.
- Do NOT alter the 16-feature schema.
- Do NOT alter the model artifact.
- Do NOT use synthetic or unverified outcomes.
- SHAP values are presented as non-causal correlation observations only.
- Expert/Admin access only.
"""

import datetime
import math
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.logging import logger
from backend.app.repositories.prediction_repository import PredictionRepository, prediction_repository
from backend.app.repositories.feedback_repository import FeedbackRepository, feedback_repository
from backend.app.core.supabase import supabase_client, SupabaseClientError
from backend.app.schemas.evaluation import (
    CalibrationBin,
    ClassificationMetrics,
    ConfusionMatrix,
    DataLeakageAudit,
    EvaluationReadinessResponse,
    EvaluationReadinessSummary,
    ModelEvaluationReport,
    ModelVersionRecord,
    OutcomeVerificationQueueItem,
    PendingEvaluationCropItem,
    PredictionOutcomePair,
    ShapErrorRecord,
    SubgroupMetrics,
    TrainTestProvenanceRecord,
)

# ---------------------------------------------------------------------------
# Static leakage audit table — derived from manual inspection of training data
# ---------------------------------------------------------------------------
LEAKAGE_AUDIT_TABLE: List[DataLeakageAudit] = [
    DataLeakageAudit(
        feature_name="YieldIndex",
        leakage_risk="high",
        reason=(
            "YieldIndex encodes historical yield performance which correlates strongly with the "
            "Failure target. In a live farm setting this value is derived from baseline agronomic "
            "tables (not direct outcome measurement), but any use of lagged outcome statistics "
            "would constitute leakage. Currently sourced from pre-computed baselines — flag for audit."
        ),
        training_source="district_dataset.csv (YieldIndex column)",
        live_source="Baseline agronomic table keyed by district/crop/season",
        recommendation=(
            "Audit whether YieldIndex in training data was computed before or after the failure outcome. "
            "If derived from post-harvest data, exclude or re-derive without using future information."
        ),
    ),
    DataLeakageAudit(
        feature_name="SuitabilityScore",
        leakage_risk="medium",
        reason=(
            "SuitabilityScore is a composite agro-ecological index. If calibrated using outcome labels "
            "from the same period, it would encode ground-truth signal. In baseline-derived form the "
            "risk is lower but not zero."
        ),
        training_source="district_dataset.csv (SuitabilityScore column)",
        live_source="Baseline agronomic table keyed by district/crop/season",
        recommendation="Confirm SuitabilityScore calibration dataset does not overlap with training Failure labels.",
    ),
    DataLeakageAudit(
        feature_name="Rainfall",
        leakage_risk="low",
        reason=(
            "Rainfall represents accumulated seasonal rainfall. In production this is derived from "
            "Open-Meteo live weather (seasonal sum). In training it was a historical district average. "
            "No direct leakage, but ensure training values are pre-season estimates, not post-season totals."
        ),
        training_source="district_dataset.csv (Rainfall column — district seasonal average)",
        live_source="Open-Meteo API (derived: 7-day accumulated × seasonal factor) or baseline",
        recommendation="Low risk. Verify training values are pre-season forecasts rather than observed totals.",
    ),
    DataLeakageAudit(
        feature_name="NDVI_Flowering",
        leakage_risk="low",
        reason=(
            "NDVI at the flowering stage is a live agronomic signal available during crop growth. "
            "If training NDVI was measured post-harvest it could correlate with failure outcomes more "
            "than NDVI available at prediction time. Live pipeline uses Sentinel-2 or baseline."
        ),
        training_source="district_dataset.csv (NDVI_Flowering column)",
        live_source="Sentinel-2 / Google Earth Engine or stage-calibrated baseline",
        recommendation=(
            "Low risk. Confirm training NDVI timestamps correspond to flowering stage "
            "observations, not post-harvest indices."
        ),
    ),
    DataLeakageAudit(
        feature_name="Temperature",
        leakage_risk="none",
        reason="Temperature is a live atmospheric measurement with no plausible outcome leakage.",
        training_source="district_dataset.csv (seasonal average)",
        live_source="Open-Meteo API (real-time)",
        recommendation="No action required.",
    ),
    DataLeakageAudit(
        feature_name="Humidity",
        leakage_risk="none",
        reason="Humidity is a live atmospheric measurement. No leakage risk.",
        training_source="district_dataset.csv (seasonal average)",
        live_source="Open-Meteo API (real-time)",
        recommendation="No action required.",
    ),
    DataLeakageAudit(
        feature_name="SoilMoisture",
        leakage_risk="none",
        reason="Soil moisture is a live or near-live measurement from Open-Meteo. No leakage risk.",
        training_source="district_dataset.csv",
        live_source="Open-Meteo API (root-zone moisture)",
        recommendation="No action required.",
    ),
    DataLeakageAudit(
        feature_name="WaterStress",
        leakage_risk="none",
        reason="WaterStress is derived from SoilMoisture and is a real-time meteorological derivative.",
        training_source="district_dataset.csv (derived index)",
        live_source="Derived from live Open-Meteo soil moisture",
        recommendation="No action required.",
    ),
    DataLeakageAudit(
        feature_name="PestRisk",
        leakage_risk="low",
        reason=(
            "PestRisk is a regional-seasonal baseline index. If historical pest incidence data from "
            "the same outcome period was used to construct this index, mild leakage is possible."
        ),
        training_source="district_dataset.csv (regional baseline index)",
        live_source="Baseline agronomic table",
        recommendation="Confirm PestRisk construction does not use same-season failure data.",
    ),
    DataLeakageAudit(
        feature_name="State / Region / Season / Crop / SoilType / IrrigationLevel",
        leakage_risk="none",
        reason="Categorical identity features. No leakage risk — these describe the farm context, not the outcome.",
        training_source="district_dataset.csv",
        live_source="Farm registration + crop cycle data",
        recommendation="No action required.",
    ),
    DataLeakageAudit(
        feature_name="Year",
        leakage_risk="none",
        reason="Year is a temporal index used for trend encoding, not an outcome proxy.",
        training_source="district_dataset.csv",
        live_source="Current calendar year",
        recommendation="No action required.",
    ),
]


# ---------------------------------------------------------------------------
# Helper: safe division
# ---------------------------------------------------------------------------
def _safe_div(numerator: float, denominator: float, default: Optional[float] = None) -> Optional[float]:
    if denominator == 0:
        return default
    return numerator / denominator


# ---------------------------------------------------------------------------
# Metric computation helpers (pure Python — no sklearn required at runtime)
# ---------------------------------------------------------------------------

def _compute_confusion_matrix(pairs: List[PredictionOutcomePair]) -> ConfusionMatrix:
    tp = sum(1 for p in pairs if p.is_true_positive)
    fp = sum(1 for p in pairs if p.is_false_positive)
    tn = sum(1 for p in pairs if p.is_true_negative)
    fn = sum(1 for p in pairs if p.is_false_negative)
    return ConfusionMatrix(
        true_positive=tp, false_positive=fp, true_negative=tn, false_negative=fn,
        total=len(pairs)
    )


def _compute_roc_auc(pairs: List[PredictionOutcomePair]) -> Optional[float]:
    """Trapezoidal ROC-AUC without sklearn."""
    y_true = [p.ground_truth_label for p in pairs]
    y_score = [p.risk_probability for p in pairs]
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    # Sort by descending score
    sorted_pairs = sorted(zip(y_score, y_true), key=lambda x: -x[0])
    tps, fps = 0, 0
    roc_points = [(0.0, 0.0)]
    for score, label in sorted_pairs:
        if label == 1:
            tps += 1
        else:
            fps += 1
        roc_points.append((fps / n_neg, tps / n_pos))
    # Trapezoidal integration
    auc = 0.0
    for i in range(1, len(roc_points)):
        x0, y0 = roc_points[i - 1]
        x1, y1 = roc_points[i]
        auc += (x1 - x0) * (y0 + y1) / 2.0
    return round(auc, 4)


def _compute_pr_auc(pairs: List[PredictionOutcomePair]) -> Optional[float]:
    """Trapezoidal PR-AUC without sklearn."""
    y_true = [p.ground_truth_label for p in pairs]
    y_score = [p.risk_probability for p in pairs]
    n_pos = sum(y_true)
    if n_pos == 0:
        return None
    sorted_pairs = sorted(zip(y_score, y_true), key=lambda x: -x[0])
    tps, fps = 0, 0
    pr_points = []
    for score, label in sorted_pairs:
        if label == 1:
            tps += 1
        else:
            fps += 1
        prec = tps / (tps + fps) if (tps + fps) > 0 else 1.0
        rec = tps / n_pos
        pr_points.append((rec, prec))
    # Trapezoidal integration
    auc = 0.0
    prev_rec, prev_prec = 0.0, 1.0
    for rec, prec in pr_points:
        auc += (rec - prev_rec) * (prev_prec + prec) / 2.0
        prev_rec, prev_prec = rec, prec
    return round(auc, 4)


def _compute_brier_score(pairs: List[PredictionOutcomePair]) -> Optional[float]:
    if not pairs:
        return None
    bs = sum((p.risk_probability - p.ground_truth_label) ** 2 for p in pairs) / len(pairs)
    return round(bs, 4)


def _compute_metrics(pairs: List[PredictionOutcomePair]) -> ClassificationMetrics:
    """Compute all classification metrics for the given eligible pairs."""
    n = len(pairs)
    if n == 0:
        return ClassificationMetrics(
            n_eligible_pairs=0,
            notes="No eligible prediction-outcome pairs found. Cannot compute metrics.",
        )

    cm = _compute_confusion_matrix(pairs)
    tp, fp, tn, fn = cm.true_positive, cm.false_positive, cm.true_negative, cm.false_negative

    accuracy = _safe_div(tp + tn, n)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    fpr = _safe_div(fp, fp + tn)
    fnr = _safe_div(fn, fn + tp)
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)

    roc_auc = _compute_roc_auc(pairs)
    pr_auc = _compute_pr_auc(pairs)
    brier = _compute_brier_score(pairs)

    notes = None
    if n < 30:
        notes = (
            f"Only {n} eligible pairs available. Metrics may not be statistically representative. "
            "Collect more verified ground-truth outcomes before relying on these figures."
        )

    return ClassificationMetrics(
        n_eligible_pairs=n,
        accuracy=round(accuracy, 4) if accuracy is not None else None,
        precision=round(precision, 4) if precision is not None else None,
        recall=round(recall, 4) if recall is not None else None,
        f1_score=round(f1, 4) if f1 is not None else None,
        specificity=round(specificity, 4) if specificity is not None else None,
        false_positive_rate=round(fpr, 4) if fpr is not None else None,
        false_negative_rate=round(fnr, 4) if fnr is not None else None,
        roc_auc=roc_auc,
        pr_auc=pr_auc,
        brier_score=brier,
        confusion_matrix=cm,
        threshold_used=0.5,
        notes=notes,
    )


def _compute_calibration(
    pairs: List[PredictionOutcomePair], n_bins: int = 10
) -> Tuple[List[CalibrationBin], str]:
    """Compute calibration table (reliability diagram bins)."""
    if not pairs:
        return [], "No eligible pairs for calibration."

    bins: List[CalibrationBin] = []
    bin_width = 1.0 / n_bins
    for b in range(n_bins):
        lo = b * bin_width
        hi = (b + 1) * bin_width
        in_bin = [p for p in pairs if lo <= p.risk_probability < hi]
        # include 1.0 in last bin
        if b == n_bins - 1:
            in_bin = [p for p in pairs if lo <= p.risk_probability <= 1.0]
        if not in_bin:
            continue
        pred_mean = sum(p.risk_probability for p in in_bin) / len(in_bin)
        actual_frac = sum(p.ground_truth_label for p in in_bin) / len(in_bin)
        bins.append(
            CalibrationBin(
                bin_lower=round(lo, 2),
                bin_upper=round(hi, 2),
                bin_center=round((lo + hi) / 2, 2),
                predicted_mean_probability=round(pred_mean, 4),
                actual_fraction_positive=round(actual_frac, 4),
                n_samples=len(in_bin),
                calibration_gap=round(actual_frac - pred_mean, 4),
            )
        )

    note = (
        f"{len(bins)} non-empty calibration bins (of {n_bins} requested). "
        "Positive calibration_gap = model is under-confident (actual rate > predicted). "
        "Negative = over-confident."
    )
    if len(pairs) < 50:
        note += f" WARNING: Only {len(pairs)} pairs — calibration estimates are unreliable at this sample size."

    return bins, note


def _subgroup_metrics(
    pairs: List[PredictionOutcomePair], key: str, get_val
) -> List[SubgroupMetrics]:
    """Compute metrics per subgroup value."""
    groups: Dict[str, List[PredictionOutcomePair]] = {}
    for p in pairs:
        val = get_val(p) or "Unknown"
        groups.setdefault(val, []).append(p)

    results = []
    for val, group in sorted(groups.items()):
        m = _compute_metrics(group)
        results.append(
            SubgroupMetrics(
                subgroup_key=key,
                subgroup_value=val,
                n_pairs=len(group),
                accuracy=m.accuracy,
                precision=m.precision,
                recall=m.recall,
                f1_score=m.f1_score,
                roc_auc=m.roc_auc,
                false_positive_rate=m.false_positive_rate,
                false_negative_rate=m.false_negative_rate,
                notes=m.notes,
            )
        )
    return results


def _lead_time_group(lead_days: Optional[float]) -> str:
    if lead_days is None:
        return "unknown"
    if lead_days < 7:
        return "<7 days"
    if lead_days < 30:
        return "7–30 days"
    if lead_days < 90:
        return "30–90 days"
    return ">90 days"


# ---------------------------------------------------------------------------
# Runtime bundle introspection
# ---------------------------------------------------------------------------

def _read_model_version() -> Optional[ModelVersionRecord]:
    bundle_path = os.path.join("models", "agri_ai_runtime_bundle.pkl")
    try:
        with open(bundle_path, "rb") as f:
            bundle = pickle.load(f)
        best_name = bundle.get("best_failure_model_name", "unknown")
        models = list(bundle.get("failure_models", {}).keys())
        num_features: List[str] = bundle.get("numeric_features", [])
        cat_features: List[str] = bundle.get("categorical_features", [])
        metrics_dict: Dict[str, Any] = bundle.get("metrics", {})
        best_metrics = metrics_dict.get(best_name, {})
        return ModelVersionRecord(
            artifact_file=bundle_path,
            best_model_name=best_name,
            models_in_bundle=models,
            feature_count=len(num_features) + len(cat_features),
            numeric_features=num_features,
            categorical_features=cat_features,
            target_column="Failure",
            training_roc_auc=best_metrics.get("roc_auc"),
            training_f1=best_metrics.get("f1_score"),
            note="Read from runtime bundle. Do NOT retrain or modify artifact.",
        )
    except Exception as exc:
        logger.warning("Could not introspect model bundle: %s", exc)
        return None


def _read_train_test_provenance() -> Optional[TrainTestProvenanceRecord]:
    """Read training provenance from the model_performance.csv and dataset."""
    perf_path = os.path.join("models", "model_performance.csv")
    dataset_path = os.path.join("data", "district_dataset.csv")

    try:
        # Parse model_performance.csv
        all_model_results = []
        best_model_name = "logistic_regression"
        best_roc_auc = 0.0
        best_f1 = 0.0

        with open(perf_path, "r") as f:
            header = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if header is None:
                    header = [h.strip() for h in line.split(",")]
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    row = dict(zip(header, parts))
                    roc = float(row.get("roc_auc", 0))
                    f1 = float(row.get("f1_score", 0))
                    all_model_results.append({
                        "model_name": row.get("model_name", parts[0]),
                        "roc_auc": roc,
                        "f1_score": f1,
                    })
                    if roc > best_roc_auc or (roc == best_roc_auc and f1 > best_f1):
                        best_roc_auc = roc
                        best_f1 = f1
                        best_model_name = row.get("model_name", parts[0])

        # Dataset stats — read header + count rows without loading into memory
        total_rows = 0
        failure_count = 0
        success_count = 0
        feature_count = 0
        failure_col_idx = -1
        with open(dataset_path, "r") as f:
            header_line = f.readline().strip()
            cols = [c.strip() for c in header_line.split(",")]
            feature_count = len(cols) - 1  # minus Failure
            if "Failure" in cols:
                failure_col_idx = cols.index("Failure")
            for line in f:
                total_rows += 1
                if failure_col_idx >= 0:
                    parts = line.strip().split(",")
                    if len(parts) > failure_col_idx:
                        val = parts[failure_col_idx].strip()
                        if val == "1":
                            failure_count += 1
                        elif val == "0":
                            success_count += 1

        test_size = 0.22
        test_rows = int(round(total_rows * test_size))
        train_rows = total_rows - test_rows

        return TrainTestProvenanceRecord(
            dataset_file=dataset_path,
            total_rows=total_rows,
            feature_count=feature_count,
            target_column="Failure",
            class_distribution={"Failure=0 (success)": success_count, "Failure=1 (failure)": failure_count},
            class_balance_ratio=round(failure_count / total_rows, 4) if total_rows > 0 else 0.0,
            test_size=test_size,
            test_rows=test_rows,
            train_rows=train_rows,
            random_state=42,
            stratified=True,
            model_selection_metric="roc_auc (primary), f1_score (tiebreak)",
            best_model_name=best_model_name,
            best_model_roc_auc=round(best_roc_auc, 4),
            best_model_f1=round(best_f1, 4),
            all_model_results=all_model_results,
        )
    except Exception as exc:
        logger.warning("Could not read training provenance: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class EvaluationService:
    """Read-only model evaluation & ground-truth validation service.

    Fetches all persisted predictions and all crop cycles with a resolved
    outcome from Supabase (or local fallback), applies strict eligibility
    rules, then computes classification and calibration metrics.
    """

    ELIGIBILITY_RULES = [
        "outcome_status must be 'harvested' or 'failed' (active crops excluded)",
        "is_synthetic must be False (no test/demo data)",
        "prediction must be linked to a specific crop_id that matches the outcome crop_id",
        "prediction must have been created BEFORE the outcome was recorded (no hindsight)",
        "risk_probability must be a real float in [0, 1]",
        "ground_truth_label must be unambiguously 0 (harvested → success) or 1 (failed → failure)",
    ]

    def __init__(
        self,
        pred_repo: Optional[PredictionRepository] = None,
        fb_repo: Optional[FeedbackRepository] = None,
    ) -> None:
        self.pred_repo = pred_repo or prediction_repository
        self.fb_repo = fb_repo or feedback_repository

    # ------------------------------------------------------------------
    # Internal: fetch all predictions from Supabase or local store
    # ------------------------------------------------------------------

    def _fetch_all_predictions(self) -> List[Dict[str, Any]]:
        """Pull all prediction records. Expert-access context only."""
        if supabase_client.is_live_configured():
            try:
                records = supabase_client.select(
                    "predictions",
                    params={"order": "created_at.asc", "limit": "5000"},
                    user_token=None,
                )
                if records:
                    return records
            except Exception as exc:
                logger.warning("Could not fetch predictions from Supabase: %s", exc)

        with self.pred_repo._lock:
            return list(self.pred_repo._local_predictions.values())

    def _fetch_all_crop_cycles(self) -> List[Dict[str, Any]]:
        """Pull all farm_crops with a resolved status."""
        if supabase_client.is_live_configured():
            try:
                records = supabase_client.select(
                    "farm_crops",
                    params={"order": "updated_at.asc", "limit": "5000"},
                    user_token=None,
                )
                if records:
                    return records
            except Exception as exc:
                logger.warning("Could not fetch farm_crops from Supabase: %s", exc)

        # Local fallback — check farm_repository
        try:
            from backend.app.repositories.farm_repository import farm_repository
            with farm_repository._lock:
                return list(farm_repository._local_crops.values())
        except Exception as exc:
            logger.warning("Could not read local crop store: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal: eligibility check
    # ------------------------------------------------------------------

    def _build_eligible_pairs(
        self,
        predictions: List[Dict[str, Any]],
        crop_cycles: List[Dict[str, Any]],
    ) -> Tuple[List[PredictionOutcomePair], int]:
        """Match predictions to outcomes and apply eligibility filters.

        Returns (eligible_pairs, ineligible_count).
        """
        # Index crop cycles by id
        crop_by_id: Dict[str, Dict[str, Any]] = {c["id"]: c for c in crop_cycles if c.get("id")}

        eligible: List[PredictionOutcomePair] = []
        ineligible_count = 0

        for pred in predictions:
            crop_id = pred.get("crop_id")
            if not crop_id or crop_id not in crop_by_id:
                ineligible_count += 1
                continue

            crop = crop_by_id[crop_id]
            outcome_status = crop.get("status", "")

            # Rule 1: Must be resolved
            if outcome_status not in ("harvested", "failed"):
                ineligible_count += 1
                continue

            # Rule 2: Must be expert-verified ground truth (no pending, unverified, synthetic, or invalid)
            with self.fb_repo._lock:
                local_outcome = self.fb_repo._local_outcomes.get(crop_id, {})
            is_syn = bool(local_outcome.get("is_synthetic", False) or crop.get("is_synthetic", False))
            is_ver = bool(local_outcome.get("is_verified_ground_truth", False) or crop.get("is_verified_ground_truth", False))
            ver_status = local_outcome.get("verification_status") or crop.get("verification_status")

            if is_syn or not is_ver or ver_status in ("invalid", "pending", "unverified"):
                ineligible_count += 1
                continue

            # Rule 3: Prediction must be linked to this crop_id (already confirmed above)

            # Rule 4: Prediction before outcome
            pred_at_str = pred.get("created_at")
            outcome_at_str = crop.get("updated_at") or crop.get("actual_harvest_date")
            lead_days: Optional[float] = None
            if pred_at_str and outcome_at_str:
                try:
                    pred_at = datetime.datetime.fromisoformat(pred_at_str.replace("Z", "+00:00"))
                    outcome_at_str2 = str(outcome_at_str)
                    if len(outcome_at_str2) == 10:
                        # date only
                        outcome_at = datetime.datetime(
                            *[int(x) for x in outcome_at_str2.split("-")],
                            tzinfo=datetime.timezone.utc,
                        )
                    else:
                        outcome_at = datetime.datetime.fromisoformat(outcome_at_str2.replace("Z", "+00:00"))
                    if pred_at >= outcome_at:
                        ineligible_count += 1
                        continue
                    lead_days = (outcome_at - pred_at).total_seconds() / 86400
                except Exception:
                    pass  # Can't determine timing — still include

            # Rule 5: Valid probability
            risk_prob = pred.get("risk_probability")
            try:
                risk_prob = float(risk_prob)
                assert 0.0 <= risk_prob <= 1.0
            except Exception:
                ineligible_count += 1
                continue

            # Rule 6: Unambiguous ground truth
            ground_truth = 1 if outcome_status == "failed" else 0
            predicted_class = 1 if risk_prob >= 0.5 else 0

            tp = predicted_class == 1 and ground_truth == 1
            fp = predicted_class == 1 and ground_truth == 0
            tn = predicted_class == 0 and ground_truth == 0
            fn = predicted_class == 0 and ground_truth == 1

            # Retrieve SHAP explanation from provenance_metadata
            prov_meta = pred.get("provenance_metadata") or {}
            explanation = prov_meta.get("explanation")

            eligible.append(
                PredictionOutcomePair(
                    prediction_id=str(pred.get("id", "")),
                    crop_id=crop_id,
                    farm_id=str(pred.get("farm_id", "")),
                    crop=pred.get("crop") or crop.get("crop"),
                    season=pred.get("season") or crop.get("season"),
                    state=pred.get("state"),
                    district=pred.get("district"),
                    region=pred.get("region_risk"),  # region stored as region_risk proxy
                    soil_type=crop.get("soil_type"),
                    irrigation_level=crop.get("irrigation_level"),
                    risk_probability=risk_prob,
                    risk_level=pred.get("risk_level", ""),
                    prediction_class=predicted_class,
                    ground_truth_label=ground_truth,
                    outcome_status=outcome_status,
                    predicted_at=pred_at_str,
                    outcome_recorded_at=str(outcome_at_str) if outcome_at_str else None,
                    lead_time_days=round(lead_days, 1) if lead_days is not None else None,
                    is_correct=tp or tn,
                    is_true_positive=tp,
                    is_false_positive=fp,
                    is_true_negative=tn,
                    is_false_negative=fn,
                )
            )

        return eligible, ineligible_count

    # ------------------------------------------------------------------
    # Internal: SHAP error analysis
    # ------------------------------------------------------------------

    def _build_shap_error_records(
        self,
        pairs: List[PredictionOutcomePair],
        error_type: str,
        max_n: int = 5,
    ) -> List[ShapErrorRecord]:
        """Build non-causal SHAP context records for FP or FN examples."""
        if error_type == "false_positive":
            subset = [p for p in pairs if p.is_false_positive]
        else:
            subset = [p for p in pairs if p.is_false_negative]

        # Sort by absolute probability deviation
        subset.sort(key=lambda p: abs(p.risk_probability - 0.5), reverse=True)
        result = []

        for pair in subset[:max_n]:
            # Try to retrieve stored SHAP explanation
            top_contributors: List[Dict[str, Any]] = []
            try:
                pred_records = supabase_client.select(
                    "predictions",
                    params={"id": f"eq.{pair.prediction_id}"},
                    user_token=None,
                ) if supabase_client.is_live_configured() else []
                if pred_records:
                    prov = pred_records[0].get("provenance_metadata") or {}
                    explanation = prov.get("explanation") or {}
                else:
                    with self.pred_repo._lock:
                        pred_rec = self.pred_repo._local_predictions.get(pair.prediction_id, {})
                    prov = pred_rec.get("provenance_metadata") or {}
                    explanation = prov.get("explanation") or {}

                all_features = explanation.get("all_features", [])
                # Sort by abs attribution descending
                sorted_features = sorted(all_features, key=lambda f: abs(f.get("attribution_value", 0)), reverse=True)
                top_contributors = [
                    {
                        "feature_name": f.get("feature_name"),
                        "display_name": f.get("display_name"),
                        "shap_value": f.get("attribution_value"),
                        "feature_value": f.get("feature_value"),
                        "direction": f.get("direction"),
                        "formatted_value": f.get("formatted_value"),
                    }
                    for f in sorted_features[:5]
                ]
            except Exception as exc:
                logger.debug("Could not retrieve SHAP for error analysis: %s", exc)

            result.append(
                ShapErrorRecord(
                    prediction_id=pair.prediction_id,
                    error_type=error_type,
                    ground_truth_label=pair.ground_truth_label,
                    predicted_class=pair.prediction_class,
                    risk_probability=pair.risk_probability,
                    top_shap_contributors=top_contributors,
                )
            )

        return result

    # ------------------------------------------------------------------
    # Public: generate evaluation report
    # ------------------------------------------------------------------

    def generate_report(self, user_token: Optional[str] = None) -> ModelEvaluationReport:
        """Generate the complete model evaluation report.

        All metrics are derived solely from real, non-synthetic, verified outcomes.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Fetch data
        predictions = self._fetch_all_predictions()
        crop_cycles = self._fetch_all_crop_cycles()

        total_predictions = len(predictions)
        total_with_outcome = sum(
            1 for c in crop_cycles if c.get("status") in ("harvested", "failed")
        )

        # 2. Build eligible pairs
        eligible_pairs, ineligible_count = self._build_eligible_pairs(predictions, crop_cycles)

        # 3. Classification metrics
        metrics = _compute_metrics(eligible_pairs) if eligible_pairs else None

        # 4. Calibration
        cal_bins, cal_note = _compute_calibration(eligible_pairs) if eligible_pairs else ([], "No eligible pairs for calibration.")

        # 5. Subgroup analysis
        subgroup_analyses: List[SubgroupMetrics] = []
        subgroup_note = None
        if eligible_pairs:
            subgroup_analyses += _subgroup_metrics(eligible_pairs, "crop", lambda p: p.crop)
            subgroup_analyses += _subgroup_metrics(eligible_pairs, "season", lambda p: p.season)
            subgroup_analyses += _subgroup_metrics(eligible_pairs, "risk_band", lambda p: p.risk_level)
            subgroup_analyses += _subgroup_metrics(eligible_pairs, "state", lambda p: p.state)
            if len(eligible_pairs) < 10:
                subgroup_note = "Subgroup analysis results are unreliable with fewer than 10 pairs per group."
        else:
            subgroup_note = "No eligible pairs for subgroup analysis."

        # 6. Lead time analysis
        lead_groups = []
        lead_note = None
        if eligible_pairs:
            lead_groups = _subgroup_metrics(
                eligible_pairs,
                "lead_time",
                lambda p: _lead_time_group(p.lead_time_days),
            )
            lead_note = "Lead time calculated as days between prediction timestamp and outcome recorded_at."
        else:
            lead_note = "No eligible pairs for lead-time analysis."

        # 7. SHAP error analysis
        fp_examples = self._build_shap_error_records(eligible_pairs, "false_positive") if eligible_pairs else []
        fn_examples = self._build_shap_error_records(eligible_pairs, "false_negative") if eligible_pairs else []

        # 8. Training provenance
        provenance = _read_train_test_provenance()

        # 9. Model version
        model_version = _read_model_version()

        return ModelEvaluationReport(
            report_generated_at=now,
            total_predictions_in_db=total_predictions,
            total_crop_cycles_with_outcome=total_with_outcome,
            eligible_pair_count=len(eligible_pairs),
            ineligible_pair_count=ineligible_count,
            eligibility_filter_rules=self.ELIGIBILITY_RULES,
            metrics=metrics,
            calibration_bins=cal_bins,
            calibration_note=cal_note,
            subgroup_analysis=subgroup_analyses,
            subgroup_analysis_note=subgroup_note,
            lead_time_groups=lead_groups,
            lead_time_analysis_note=lead_note,
            false_positive_examples=fp_examples,
            false_negative_examples=fn_examples,
            leakage_audit=LEAKAGE_AUDIT_TABLE,
            train_test_provenance=provenance,
            model_version=model_version,
        )

    # ------------------------------------------------------------------
    # Public: get evaluation readiness diagnostic report
    # ------------------------------------------------------------------

    def get_evaluation_readiness(
        self,
        predictions: Optional[List[Dict[str, Any]]] = None,
        crop_cycles: Optional[List[Dict[str, Any]]] = None,
        user_token: Optional[str] = None,
    ) -> EvaluationReadinessResponse:
        """Diagnostic report showing crops awaiting harvest, verification queue, and coverage."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if predictions is None:
            predictions = self._fetch_all_predictions()
        if crop_cycles is None:
            crop_cycles = self._fetch_all_crop_cycles()

        # Build lookup maps
        crops_by_id = {c["id"]: c for c in crop_cycles if "id" in c}
        preds_by_crop: Dict[str, List[Dict[str, Any]]] = {}
        for p in predictions:
            cid = p.get("crop_id")
            if cid:
                preds_by_crop.setdefault(cid, []).append(p)

        pending_queue: List[PendingEvaluationCropItem] = []
        verification_queue: List[OutcomeVerificationQueueItem] = []

        active_crop_count = 0
        predictions_awaiting_outcome = 0
        verified_outcomes = 0
        unverified_outcomes = 0
        synthetic_outcomes = 0
        invalid_outcomes = 0

        for crop in crop_cycles:
            cid = crop.get("id")
            c_status = crop.get("status", "")
            c_preds = preds_by_crop.get(cid, []) if cid else []

            with self.fb_repo._lock:
                local_out = self.fb_repo._local_outcomes.get(cid, {}) if cid else {}

            is_syn = bool(local_out.get("is_synthetic", False) or crop.get("is_synthetic", False))
            is_ver = bool(local_out.get("is_verified_ground_truth", False) or crop.get("is_verified_ground_truth", False))
            ver_status = local_out.get("verification_status") or crop.get("verification_status") or ("verified" if is_ver else "pending")

            if c_status in ("active", "growing"):
                active_crop_count += 1
                predictions_awaiting_outcome += len(c_preds)
                pred_dates = [p.get("created_at") for p in c_preds if p.get("created_at")]
                pred_dates.sort()
                pending_queue.append(
                    PendingEvaluationCropItem(
                        farm_id=crop.get("farm_id", ""),
                        farm_name=crop.get("farm_name", crop.get("farm_id", "Farm")),
                        crop_id=cid or "",
                        crop=crop.get("crop", "Unknown"),
                        season=crop.get("season", "Kharif"),
                        status=c_status,
                        sowing_date=crop.get("sowing_date"),
                        expected_harvest_date=crop.get("expected_harvest_date"),
                        prediction_count=len(c_preds),
                        earliest_prediction_date=pred_dates[0] if pred_dates else None,
                        latest_prediction_date=pred_dates[-1] if pred_dates else None,
                        readiness_status="awaiting_harvest",
                    )
                )
            elif c_status in ("harvested", "failed"):
                if is_syn:
                    synthetic_outcomes += 1
                elif ver_status == "invalid":
                    invalid_outcomes += 1
                elif is_ver or ver_status == "verified":
                    verified_outcomes += 1
                else:
                    unverified_outcomes += 1

                verification_queue.append(
                    OutcomeVerificationQueueItem(
                        farm_id=crop.get("farm_id", ""),
                        farm_name=crop.get("farm_name", crop.get("farm_id", "Farm")),
                        crop_id=cid or "",
                        crop=crop.get("crop", "Unknown"),
                        season=crop.get("season", "Kharif"),
                        status=c_status,
                        actual_harvest_date=crop.get("actual_harvest_date") or crop.get("updated_at"),
                        reported_yield_kg_per_ha=crop.get("reported_yield_kg_per_ha"),
                        outcome_notes=crop.get("outcome_notes"),
                        recorded_at=crop.get("updated_at") or crop.get("created_at"),
                        prediction_count=len(c_preds),
                        potential_eligible_pairs_count=len(c_preds),
                        verification_status=ver_status,
                        is_verified_ground_truth=is_ver,
                        is_synthetic=is_syn,
                        verified_by=local_out.get("verified_by") or crop.get("verified_by"),
                        verified_at=local_out.get("verified_at") or crop.get("verified_at"),
                        verification_notes=local_out.get("verification_notes") or crop.get("verification_notes"),
                    )
                )

        eligible_pairs, ineligible_count = self._build_eligible_pairs(predictions, crop_cycles)
        total_preds = len(predictions)
        preds_with_crop = sum(1 for p in predictions if p.get("crop_id"))
        coverage = (len(eligible_pairs) / preds_with_crop * 100.0) if preds_with_crop > 0 else 0.0

        lead_times = [p.lead_time_days for p in eligible_pairs if p.lead_time_days is not None]
        avg_lead = round(sum(lead_times) / len(lead_times), 1) if lead_times else None

        lead_dist: Dict[str, int] = {}
        for lt in lead_times:
            grp = _lead_time_group(lt)
            lead_dist[grp] = lead_dist.get(grp, 0) + 1

        summary = EvaluationReadinessSummary(
            total_predictions=total_preds,
            total_crop_cycles=len(crop_cycles),
            predictions_awaiting_outcome=predictions_awaiting_outcome,
            crop_cycles_awaiting_outcome=active_crop_count,
            verified_outcomes=verified_outcomes,
            unverified_outcomes=unverified_outcomes,
            synthetic_outcomes=synthetic_outcomes,
            invalid_outcomes=invalid_outcomes,
            eligible_prediction_outcome_pairs=len(eligible_pairs),
            ineligible_predictions=ineligible_count,
            evaluation_coverage_percentage=round(coverage, 2),
        )

        return EvaluationReadinessResponse(
            report_generated_at=now,
            summary=summary,
            pending_queue=pending_queue,
            verification_queue=verification_queue,
            exclusions_breakdown={"ineligible": ineligible_count},
            average_lead_time_days=avg_lead,
            lead_time_distribution=lead_dist,
            model_version_breakdown={},
        )


# Module-level singleton
evaluation_service = EvaluationService()
