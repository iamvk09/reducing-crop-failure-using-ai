"""Early Warning & Alert Engine Service.

Evaluates observation-driven alert conditions after each prediction and
manages the alert lifecycle (create, acknowledge, resolve) with:
  - 6 alert types: RISK_THRESHOLD_CROSSED, RISK_TREND_INCREASING,
    TELEMETRY_DEGRADATION, SATELLITE_STALE, WEATHER_STALE,
    DATA_QUALITY_DEGRADED
  - 3 severity levels: info, warning, critical
  - Deduplication rules A–D
  - Non-causal SHAP context extraction
  - Tenant isolation (farmers can only manage their own farm's alerts)
  - Expert/admin can resolve alerts

Constraints:
  - Does NOT retrain the model.
  - Does NOT alter SHAP mathematics.
  - SHAP values presented as non-causal correlation observations only.
"""

import datetime
from typing import Any, Dict, List, Optional

from backend.app.core.logging import logger
from backend.app.core.security import AuthenticatedUser
from backend.app.repositories.alert_repository import AlertRepository, alert_repository
from backend.app.schemas.alert import FarmAlertResponse
from backend.app.schemas.prediction import PredictionResponse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_CRITICAL_THRESHOLD = 0.70
RISK_WARNING_THRESHOLD = 0.45
TREND_CRITICAL_DELTA_PP = 5.0   # +5pp absolute increase → critical
TREND_WARNING_DELTA_PP = 1.0    # +1pp absolute increase → warning
WEATHER_STALE_HOURS = 24
SATELLITE_STALE_DAYS = 30
COVERAGE_CRITICAL_THRESHOLD = 0.40  # < 40% live feature coverage
COVERAGE_WARNING_THRESHOLD = 0.60   # < 60% live feature coverage
DEDUP_PROB_TOLERANCE_PP = 5.0       # ±5 pp tolerance for Rule B dedup


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_response(record: Dict[str, Any]) -> FarmAlertResponse:
    """Convert raw dict record to FarmAlertResponse, normalising types."""
    shap_ctx = record.get("shap_context") or []
    # Supabase may return JSONB as a string
    if isinstance(shap_ctx, str):
        try:
            import json
            shap_ctx = json.loads(shap_ctx)
        except Exception:
            shap_ctx = []

    def _parse_dt(val):
        if val is None:
            return None
        if isinstance(val, datetime.datetime):
            return val
        try:
            return datetime.datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            return None

    return FarmAlertResponse(
        id=record.get("id", ""),
        farm_id=record.get("farm_id", ""),
        crop_id=record.get("crop_id"),
        created_at=_parse_dt(record.get("created_at")) or datetime.datetime.now(datetime.timezone.utc),
        alert_type=record.get("alert_type", "UNKNOWN"),
        severity=record.get("severity", "info"),
        status=record.get("status", "active"),
        trigger_reason=record.get("trigger_reason", ""),
        prediction_id=record.get("prediction_id"),
        risk_probability=record.get("risk_probability"),
        previous_risk_probability=record.get("previous_risk_probability"),
        risk_delta_pp=record.get("risk_delta_pp"),
        recommended_action=record.get("recommended_action"),
        shap_context=shap_ctx if isinstance(shap_ctx, list) else [],
        acknowledged_at=_parse_dt(record.get("acknowledged_at")),
        acknowledged_by=record.get("acknowledged_by"),
        resolved_at=_parse_dt(record.get("resolved_at")),
        resolved_by=record.get("resolved_by"),
        resolution_notes=record.get("resolution_notes"),
    )


def _extract_shap_context(pred: Optional[PredictionResponse], max_n: int = 3) -> List[Dict[str, Any]]:
    """Extract top SHAP contributors from prediction explanation as non-causal context.

    Returns a list of dicts describing feature weights at prediction time.
    These are NOT causal explanations of the outcome.
    """
    if not pred or not pred.explanation:
        return []
    all_features = pred.explanation.all_features or []
    sorted_feats = sorted(all_features, key=lambda f: abs(f.attribution_value), reverse=True)
    return [
        {
            "feature_name": f.feature_name,
            "display_name": f.display_name,
            "shap_value": f.attribution_value,
            "feature_value": f.feature_value,
            "direction": f.direction,
            "disclaimer": "SHAP value describes model feature weighting, not causal outcome attribution.",
        }
        for f in sorted_feats[:max_n]
    ]


def _extract_recommended_action(pred: Optional[PredictionResponse]) -> Optional[str]:
    """Extract advisory action summary from prediction recommendations."""
    if not pred or not pred.recommendations:
        return None
    return pred.recommendations.advisory_summary or None


# ---------------------------------------------------------------------------
# Deduplication logic
# ---------------------------------------------------------------------------

def _is_duplicate_rule_a(
    existing_alerts: List[Dict[str, Any]],
    prediction_id: Optional[str],
    alert_type: str,
) -> bool:
    """Rule A: Same farm + same prediction_id + same alert_type → suppress."""
    if not prediction_id:
        return False
    return any(
        a.get("prediction_id") == prediction_id
        and a.get("alert_type") == alert_type
        and a.get("status") == "active"
        for a in existing_alerts
    )


def _is_duplicate_rule_b(
    existing_alerts: List[Dict[str, Any]],
    alert_type: str,
    severity: str,
    risk_probability: Optional[float],
) -> bool:
    """Rule B: Same farm + same alert_type + same severity + probability within ±5pp → suppress.

    Only applied to RISK_THRESHOLD_CROSSED.
    Escalation (warning→critical) is NOT suppressed — let it through.
    """
    if alert_type != "RISK_THRESHOLD_CROSSED" or risk_probability is None:
        return False
    for a in existing_alerts:
        if (
            a.get("alert_type") == alert_type
            and a.get("severity") == severity
            and a.get("status") == "active"
        ):
            existing_prob = a.get("risk_probability") or 0.0
            if abs(risk_probability - existing_prob) * 100 <= DEDUP_PROB_TOLERANCE_PP:
                return True
    return False


def _resolve_prior_alerts_for_type(
    existing_alerts: List[Dict[str, Any]],
    alert_type: str,
    repo: AlertRepository,
    user_token: Optional[str] = None,
) -> None:
    """Rule D: If same alert_type was previously resolved, allow new event (no suppression).
    If it's currently active and escalating (warning→critical), keep the new one.
    Resolved alerts do not count for deduplication.
    """
    # This is handled by not including resolved alerts in dedup checks
    pass


# ---------------------------------------------------------------------------
# AlertService
# ---------------------------------------------------------------------------

class AlertService:
    """Early warning alert engine with observation-driven condition evaluation."""

    def __init__(self, repo: Optional[AlertRepository] = None) -> None:
        self.repo = repo or alert_repository

    # ------------------------------------------------------------------
    # Condition evaluation (called after each prediction)
    # ------------------------------------------------------------------

    def evaluate_alert_conditions(
        self,
        farm: Any,
        target_crop: Any,
        current_pred: Optional[PredictionResponse],
        previous_pred: Optional[PredictionResponse],
        user: Optional[AuthenticatedUser] = None,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate all alert trigger conditions and create new alerts as needed.

        Returns list of newly created alert records.
        """
        if not current_pred:
            return []

        farm_id = str(getattr(farm, "id", "") or "")
        crop_id = str(getattr(target_crop, "id", "") if target_crop else "")
        prediction_id = current_pred.prediction_id
        risk_prob = current_pred.risk_probability or 0.0
        data_quality = current_pred.data_quality

        # Load existing active alerts for deduplication
        existing_active = self.repo.list_for_farm(
            farm_id=farm_id, status="active", limit=200, user_token=user_token
        )

        created_alerts = []
        shap_ctx = _extract_shap_context(current_pred)
        recommended_action = _extract_recommended_action(current_pred)

        # ----------------------------------------------------------------
        # Condition 1: RISK_THRESHOLD_CROSSED
        # ----------------------------------------------------------------
        if risk_prob >= RISK_CRITICAL_THRESHOLD:
            severity = "critical"
            trigger_reason = (
                f"Crop failure probability {risk_prob * 100:.1f}% exceeds critical threshold "
                f"({RISK_CRITICAL_THRESHOLD * 100:.0f}%). Immediate agronomic review recommended."
            )
        elif risk_prob >= RISK_WARNING_THRESHOLD:
            severity = "warning"
            trigger_reason = (
                f"Crop failure probability {risk_prob * 100:.1f}% exceeds warning threshold "
                f"({RISK_WARNING_THRESHOLD * 100:.0f}%). Monitor conditions closely."
            )
        else:
            severity = None

        if severity:
            alert_type = "RISK_THRESHOLD_CROSSED"
            # Check escalation: if existing warning and new is critical → allow (Rule C)
            existing_for_type = [
                a for a in existing_active
                if a.get("alert_type") == alert_type
            ]
            is_escalation = (
                severity == "critical"
                and any(a.get("severity") == "warning" for a in existing_for_type)
            )
            if is_escalation:
                # Mark prior warning as resolved before creating critical
                for a in existing_for_type:
                    if a.get("severity") == "warning":
                        self.repo.update_status(a["id"], "resolved", user_token=user_token)
                existing_active = [a for a in existing_active if a.get("alert_type") != alert_type or a.get("severity") != "warning"]

            if not _is_duplicate_rule_a(existing_active, prediction_id, alert_type) and \
               not _is_duplicate_rule_b(existing_active, alert_type, severity, risk_prob):
                alert = self.repo.create_alert(
                    farm_id=farm_id,
                    crop_id=crop_id or None,
                    alert_type=alert_type,
                    severity=severity,
                    trigger_reason=trigger_reason,
                    prediction_id=prediction_id,
                    risk_probability=risk_prob,
                    recommended_action=recommended_action,
                    shap_context=shap_ctx,
                    user_token=user_token,
                )
                created_alerts.append(alert)
                existing_active.append(alert)
            else:
                self.repo.record_deduplication()

        # ----------------------------------------------------------------
        # Condition 2: RISK_TREND_INCREASING
        # ----------------------------------------------------------------
        if previous_pred and previous_pred.risk_probability is not None:
            prev_prob = previous_pred.risk_probability
            delta_pp = (risk_prob - prev_prob) * 100

            trend_severity = None
            if delta_pp >= TREND_CRITICAL_DELTA_PP:
                trend_severity = "critical"
                trend_reason = (
                    f"Risk increased by {delta_pp:.1f} percentage points "
                    f"({prev_prob * 100:.1f}% → {risk_prob * 100:.1f}%). "
                    "Significant upward risk trend detected."
                )
            elif delta_pp >= TREND_WARNING_DELTA_PP:
                trend_severity = "warning"
                trend_reason = (
                    f"Risk increased by {delta_pp:.1f} percentage points "
                    f"({prev_prob * 100:.1f}% → {risk_prob * 100:.1f}%). "
                    "Upward risk trend observed."
                )

            if trend_severity:
                alert_type = "RISK_TREND_INCREASING"
                if not _is_duplicate_rule_a(existing_active, prediction_id, alert_type):
                    alert = self.repo.create_alert(
                        farm_id=farm_id,
                        crop_id=crop_id or None,
                        alert_type=alert_type,
                        severity=trend_severity,
                        trigger_reason=trend_reason,
                        prediction_id=prediction_id,
                        risk_probability=risk_prob,
                        previous_risk_probability=prev_prob,
                        risk_delta_pp=round(delta_pp, 2),
                        recommended_action=recommended_action,
                        shap_context=shap_ctx,
                        user_token=user_token,
                    )
                    created_alerts.append(alert)
                    existing_active.append(alert)
                else:
                    self.repo.record_deduplication()

        # ----------------------------------------------------------------
        # Condition 3: Weather staleness
        # ----------------------------------------------------------------
        if data_quality and data_quality.weather_status in ("stale_fallback", "baseline"):
            alert_type = "WEATHER_STALE"
            stale_reason = (
                f"Weather telemetry status is '{data_quality.weather_status}'. "
                "Live Open-Meteo data could not be retrieved. Prediction used stale or baseline weather."
            )
            if not any(
                a.get("alert_type") == alert_type and a.get("status") == "active"
                for a in existing_active
            ):
                alert = self.repo.create_alert(
                    farm_id=farm_id,
                    crop_id=crop_id or None,
                    alert_type=alert_type,
                    severity="warning",
                    trigger_reason=stale_reason,
                    prediction_id=prediction_id,
                    risk_probability=risk_prob,
                    user_token=user_token,
                )
                created_alerts.append(alert)
                existing_active.append(alert)

        # ----------------------------------------------------------------
        # Condition 4: Satellite staleness
        # ----------------------------------------------------------------
        if data_quality and data_quality.satellite_status in ("stale_fallback", "baseline"):
            alert_type = "SATELLITE_STALE"
            sat_reason = (
                f"Satellite (Sentinel-2) telemetry status is '{data_quality.satellite_status}'. "
                f"NDVI_Flowering used a stage-calibrated baseline, not a live Sentinel-2 observation. "
                "Not a raw Sentinel-2 reading."
            )
            if not any(
                a.get("alert_type") == alert_type and a.get("status") == "active"
                for a in existing_active
            ):
                alert = self.repo.create_alert(
                    farm_id=farm_id,
                    crop_id=crop_id or None,
                    alert_type=alert_type,
                    severity="info",
                    trigger_reason=sat_reason,
                    prediction_id=prediction_id,
                    risk_probability=risk_prob,
                    user_token=user_token,
                )
                created_alerts.append(alert)

        # ----------------------------------------------------------------
        # Condition 5: Data quality / feature coverage
        # ----------------------------------------------------------------
        if data_quality and data_quality.total_feature_count > 0:
            live_coverage = data_quality.live_feature_count / data_quality.total_feature_count
            if live_coverage < COVERAGE_CRITICAL_THRESHOLD:
                dq_severity = "critical"
                dq_reason = (
                    f"Live feature coverage is {live_coverage * 100:.0f}% "
                    f"({data_quality.live_feature_count}/{data_quality.total_feature_count} features). "
                    "Below 40% threshold — prediction reliability is significantly reduced."
                )
            elif live_coverage < COVERAGE_WARNING_THRESHOLD:
                dq_severity = "warning"
                dq_reason = (
                    f"Live feature coverage is {live_coverage * 100:.0f}% "
                    f"({data_quality.live_feature_count}/{data_quality.total_feature_count} features). "
                    "Below 60% threshold — verify telemetry sources."
                )
            else:
                dq_severity = None

            if dq_severity:
                alert_type = "DATA_QUALITY_DEGRADED"
                if not any(
                    a.get("alert_type") == alert_type and a.get("status") == "active"
                    for a in existing_active
                ):
                    alert = self.repo.create_alert(
                        farm_id=farm_id,
                        crop_id=crop_id or None,
                        alert_type=alert_type,
                        severity=dq_severity,
                        trigger_reason=dq_reason,
                        prediction_id=prediction_id,
                        risk_probability=risk_prob,
                        user_token=user_token,
                    )
                    created_alerts.append(alert)

        # ----------------------------------------------------------------
        # Automatic Alert Notification Dispatch (Failure Isolated)
        # ----------------------------------------------------------------
        if created_alerts and user:
            try:
                from backend.app.services.notification_service import notification_service
                from backend.app.services.user_service import user_service
                
                # Fetch fresh profile to check phone and channel consents
                user_prof = user_service.get_user_profile(user.id)
                farm_name = str(getattr(farm, "name", "Farm") or "Farm")
                
                sms_consent = getattr(user_prof, "sms_notifications_enabled", False) if user_prof else False
                whatsapp_consent = getattr(user_prof, "whatsapp_notifications_enabled", False) if user_prof else False
                phone = getattr(user_prof, "phone_number", None) if user_prof else None

                for new_alert in created_alerts:
                    if sms_consent:
                        notification_service.dispatch_alert_sms(
                            user_id=user.id,
                            phone_number=phone,
                            sms_consent=sms_consent,
                            farm_name=farm_name,
                            alert=new_alert,
                            farm_id=farm_id,
                            prediction_id=prediction_id,
                            user_token=user_token,
                        )
                    if whatsapp_consent:
                        notification_service.dispatch_alert_whatsapp(
                            user_id=user.id,
                            phone_number=phone,
                            whatsapp_consent=whatsapp_consent,
                            farm_name=farm_name,
                            alert=new_alert,
                            farm_id=farm_id,
                            prediction_id=prediction_id,
                            user_token=user_token,
                        )
            except Exception as notify_err:
                # Failure non-interference guarantee: Notification failure must NEVER abort prediction or alert creation
                logger.error("Notification dispatch failed non-critically: %s", notify_err)

        return created_alerts

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_alerts_for_farm(
        self,
        farm_id: str,
        user: Optional[AuthenticatedUser] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[FarmAlertResponse]:
        """List alerts for a farm. Farmers see their own farm's alerts; experts see all."""
        raw = self.repo.list_for_farm(
            farm_id=farm_id,
            status=status,
            alert_type=alert_type,
            severity=severity,
            limit=limit + offset,
            user_token=user_token,
        )
        paginated = raw[offset: offset + limit]
        return [_to_response(r) for r in paginated]

    def list_all_alerts(
        self,
        role: Optional[str] = None,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        alert_status: Optional[str] = None,
        limit: int = 100,
        user_token: Optional[str] = None,
    ) -> List[FarmAlertResponse]:
        """List all alerts across farms. Expert and Admin only."""
        if role not in ("expert", "admin"):
            raise PermissionError("Only expert or admin users can list all cross-farm alerts.")
        raw = self.repo.list_all(
            status=alert_status,
            alert_type=alert_type,
            severity=severity,
            limit=limit,
            user_token=user_token,
        )
        return [_to_response(r) for r in raw]

    # ------------------------------------------------------------------
    # Acknowledge
    # ------------------------------------------------------------------

    def acknowledge_alert(
        self,
        farm_id: str,
        alert_id: str,
        user: Optional[AuthenticatedUser] = None,
        notes: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> FarmAlertResponse:
        """Acknowledge an alert. Any authenticated user on the farm can acknowledge."""
        record = self.repo.get_by_id(alert_id, user_token=user_token)
        if not record:
            raise ValueError(f"Alert {alert_id} not found.")
        if record.get("farm_id") != farm_id:
            raise ValueError(f"Alert {alert_id} does not belong to farm {farm_id}.")
        if record.get("status") != "active":
            raise ValueError(f"Alert {alert_id} is not active (current status: {record.get('status')}).")

        user_id = str(getattr(user, "id", "")) if user else None
        updated = self.repo.update_status(
            alert_id=alert_id,
            new_status="acknowledged",
            user_id=user_id,
            notes=notes,
            user_token=user_token,
        )
        if not updated:
            raise ValueError(f"Failed to acknowledge alert {alert_id}.")
        return _to_response(updated)

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    def resolve_alert(
        self,
        farm_id: str,
        alert_id: str,
        user: Optional[AuthenticatedUser] = None,
        resolution_notes: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> FarmAlertResponse:
        """Resolve an alert. Expert and Admin only."""
        role = getattr(user, "role", "") if user else ""
        if role not in ("expert", "admin"):
            raise ValueError("Only expert or admin users can resolve alerts.")

        record = self.repo.get_by_id(alert_id, user_token=user_token)
        if not record:
            raise ValueError(f"Alert {alert_id} not found.")
        if record.get("farm_id") != farm_id:
            raise ValueError(f"Alert {alert_id} does not belong to farm {farm_id}.")
        if record.get("status") == "resolved":
            raise ValueError(f"Alert {alert_id} is already resolved.")

        user_id = str(getattr(user, "id", "")) if user else None
        updated = self.repo.update_status(
            alert_id=alert_id,
            new_status="resolved",
            user_id=user_id,
            notes=resolution_notes,
            user_token=user_token,
        )
        if not updated:
            raise ValueError(f"Failed to resolve alert {alert_id}.")
        return _to_response(updated)


# Module-level singleton
alert_service = AlertService()

