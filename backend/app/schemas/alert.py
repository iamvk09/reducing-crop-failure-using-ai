"""Early Warning & Alert Engine Schemas."""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlertAcknowledgeRequest(BaseModel):
    """Payload for acknowledging an active farm alert."""

    notes: Optional[str] = Field(None, description="Optional acknowledgement notes or farmer confirmation")


class AlertResolveRequest(BaseModel):
    """Payload for resolving an alert (experts/admins only)."""

    resolution_notes: Optional[str] = Field(None, description="Agronomic intervention notes or resolution rationale")


class FarmAlertResponse(BaseModel):
    """Unified early warning alert representation across API, monitoring, and UI."""

    id: str
    farm_id: str
    crop_id: Optional[str] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    alert_type: str  # RISK_THRESHOLD_CROSSED, RISK_TREND_INCREASING, TELEMETRY_DEGRADATION, SATELLITE_STALE, WEATHER_STALE, DATA_QUALITY_DEGRADED
    severity: str  # critical, warning, info
    status: str = "active"  # active, acknowledged, resolved
    trigger_reason: str
    prediction_id: Optional[str] = None
    risk_probability: Optional[float] = None
    previous_risk_probability: Optional[float] = None
    risk_delta_pp: Optional[float] = None
    recommended_action: Optional[str] = None
    shap_context: List[Dict[str, Any]] = Field(default_factory=list)
    acknowledged_at: Optional[datetime.datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime.datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None

