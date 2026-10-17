"""Farm, crop, prediction, and weather management routes with multi-tenant isolation and ownership checks."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from backend.app.api.deps import (
    get_alert_svc,
    get_any_authenticated_user,
    get_client_ip,
    get_farm_svc,
    get_farmer_user,
    get_monitoring_svc,
    get_prediction_svc,
    get_raw_token,
    get_satellite_svc,
    get_weather_svc,
)
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertResolveRequest,
    FarmAlertResponse,
)
from backend.app.schemas.farm import (
    CropCreateRequest,
    CropResponse,
    CropUpdateRequest,
    FarmCreateRequest,
    FarmResponse,
    FarmUpdateRequest,
)
from backend.app.schemas.monitoring import (
    CropOutcomeRequest,
    CropOutcomeResponse,
    FarmFeedbackRequest,
    FarmFeedbackResponse,
    FarmMonitoringResponse,
    MonitoringDiagnosticsResponse,
    RiskTrendResponse,
)
from backend.app.schemas.prediction import FarmPredictionRequest, PredictionResponse
from backend.app.services.alert_service import AlertService
from backend.app.services.farm_service import FarmService
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.prediction_service import PredictionService
from backend.app.services.satellite import (
    FarmVegetationSummary,
    SatelliteHistoryResponse,
    SatelliteObservationResponse,
    SatelliteService,
)
from backend.app.services.weather import (
    CurrentWeatherResponse,
    WeatherForecastResponse,
    WeatherObservationRecord,
    WeatherService,
)

router = APIRouter(prefix="/farms", tags=["Farms, Crops, Weather & Satellite"])


# -----------------------------------------------------------------------------
# Farm Endpoints
# -----------------------------------------------------------------------------
@router.get("", response_model=List[FarmResponse], summary="List Accessible Farms")
def list_farms(
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> List[FarmResponse]:
    """Retrieve farms accessible to the user.

    - Farmers see only their own farms.
    - Experts and Admins can see all registered farms.
    """
    return farm_svc.list_farms(user=user, user_token=raw_token)


@router.post(
    "",
    response_model=FarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Farm",
)
def create_farm(
    farm_in: FarmCreateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> FarmResponse:
    """Register a new farm plot with geo-coordinates, location, and soil metadata."""
    ip_address = get_client_ip(request)
    return farm_svc.create_farm(farm_in=farm_in, user=user, ip_address=ip_address, user_token=raw_token)


@router.get("/{farm_id}", response_model=FarmResponse, summary="Get Farm Details")
def get_farm(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> FarmResponse:
    """Retrieve details for a specific farm. Enforces ownership isolation for farmers."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user, user_token=raw_token)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )
    return farm


@router.patch("/{farm_id}", response_model=FarmResponse, summary="Update Farm Details")
def update_farm(
    farm_id: str,
    farm_update: FarmUpdateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> FarmResponse:
    """Partially update farm attributes. Only the owner or an admin may modify the farm."""
    ip_address = get_client_ip(request)
    farm = farm_svc.update_farm(
        farm_id=farm_id, farm_update=farm_update, user=user, ip_address=ip_address, user_token=raw_token
    )
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or you do not have permission to modify it.",
        )
    return farm


@router.delete(
    "/{farm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Farm",
)
def delete_farm(
    farm_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> Response:
    """Delete a farm and its associated crops. Only the owner or an admin may delete."""
    ip_address = get_client_ip(request)
    success = farm_svc.delete_farm(farm_id=farm_id, user=user, ip_address=ip_address, user_token=raw_token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or you do not have permission to delete it.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------------------------------------
# Crop Cycle Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/{farm_id}/crops",
    response_model=CropResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Crop Cycle on Farm",
)
def register_crop_cycle(
    farm_id: str,
    crop_in: CropCreateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> CropResponse:
    """Record an active crop planting cycle on a farm owned by the user."""
    ip_address = get_client_ip(request)
    crop = farm_svc.register_crop(
        farm_id=farm_id, crop_in=crop_in, user=user, ip_address=ip_address, user_token=raw_token
    )
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or you do not have permission to register crops on it.",
        )
    return crop


@router.get(
    "/{farm_id}/crops",
    response_model=List[CropResponse],
    summary="List Crops for Farm",
)
def list_farm_crops(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> List[CropResponse]:
    """Retrieve all crop cycles recorded for a specific farm."""
    crops = farm_svc.list_crops_for_farm(farm_id=farm_id, user=user, user_token=raw_token)
    if crops is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )
    return crops


@router.patch(
    "/{farm_id}/crops/{crop_id}",
    response_model=CropResponse,
    summary="Update Crop Cycle",
)
def update_crop_cycle(
    farm_id: str,
    crop_id: str,
    crop_update: CropUpdateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> CropResponse:
    """Update details of a crop cycle. Enforces farm ownership."""
    ip_address = get_client_ip(request)
    crop = farm_svc.update_crop(
        farm_id=farm_id,
        crop_id=crop_id,
        crop_update=crop_update,
        user=user,
        ip_address=ip_address,
        user_token=raw_token,
    )
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crop '{crop_id}' on Farm '{farm_id}' not found or unauthorized.",
        )
    return crop


@router.delete(
    "/{farm_id}/crops/{crop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Crop Cycle",
)
def delete_crop_cycle(
    farm_id: str,
    crop_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_farmer_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> Response:
    """Delete a crop cycle from a farm. Enforces farm ownership."""
    ip_address = get_client_ip(request)
    success = farm_svc.delete_crop(
        farm_id=farm_id, crop_id=crop_id, user=user, ip_address=ip_address, user_token=raw_token
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crop '{crop_id}' on Farm '{farm_id}' not found or unauthorized.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------------------------------------
# Farm Prediction Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/{farm_id}/predictions",
    response_model=PredictionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute Crop Risk Prediction for Farm",
)
def predict_for_farm(
    farm_id: str,
    request: Request,
    pred_req: Optional[FarmPredictionRequest] = None,
    force_refresh: bool = Query(False, description="Bypass recent duplicate telemetry and force fresh assessment"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    pred_svc: PredictionService = Depends(get_prediction_svc),
    raw_token: Optional[str] = Depends(get_raw_token),
) -> PredictionResponse:
    """Execute live crop failure prediction for a farm with registered crop & live weather."""
    ip_address = get_client_ip(request)

    overrides = None
    crop_id = None
    effective_force_refresh = force_refresh
    if pred_req:
        crop_id = pred_req.crop_id
        if pred_req.force_refresh:
            effective_force_refresh = True
        active_overrides = {
            "rainfall_override": pred_req.rainfall_override,
            "temperature_override": pred_req.temperature_override,
            "humidity_override": pred_req.humidity_override,
            "soil_moisture_override": pred_req.soil_moisture_override,
            "ndvi_override": pred_req.ndvi_override,
            "water_stress_override": pred_req.water_stress_override,
            "pest_risk_override": pred_req.pest_risk_override,
            "suitability_score_override": pred_req.suitability_score_override,
            "yield_index_override": pred_req.yield_index_override,
        }
        filtered = {k: v for k, v in active_overrides.items() if v is not None}
        if filtered:
            overrides = filtered

    try:
        pred_res = pred_svc.predict_for_farm(
            farm_id=farm_id,
            user=user,
            crop_id=crop_id,
            overrides=overrides,
            ip_address=ip_address,
            user_token=raw_token,
            force_refresh=effective_force_refresh,
        )
        if not pred_res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Farm '{farm_id}' not found or unauthorized.",
            )
        return pred_res
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get(
    "/{farm_id}/predictions",
    response_model=List[PredictionResponse],
    summary="List Prediction History for Farm",
)
def list_farm_predictions(
    farm_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    pred_svc: PredictionService = Depends(get_prediction_svc),
) -> List[PredictionResponse]:
    """Retrieve all historical risk assessments recorded for a farm."""
    history = pred_svc.list_predictions_for_farm(
        farm_id=farm_id, user=user, limit=limit, offset=offset
    )
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )
    return history


# -----------------------------------------------------------------------------
# Farm Weather Endpoints (Current, Multi-Day Forecast, Historical Observations)
# -----------------------------------------------------------------------------
@router.get(
    "/{farm_id}/weather/current",
    response_model=CurrentWeatherResponse,
    summary="Get Current Farm Weather",
)
def get_farm_current_weather(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    weather_svc: WeatherService = Depends(get_weather_svc),
) -> CurrentWeatherResponse:
    """Retrieve normalized live weather observations for a farm plot from configured provider."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    res = weather_svc.get_current_weather(
        latitude=farm.latitude,
        longitude=farm.longitude,
        farm_id=farm.id,
        persist=True,
    )
    return res


@router.get(
    "/{farm_id}/weather/forecast",
    response_model=WeatherForecastResponse,
    summary="Get Multi-Day Weather Forecast",
)
def get_farm_weather_forecast(
    farm_id: str,
    days: int = Query(7, ge=1, le=16, description="Forecast days projection"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    weather_svc: WeatherService = Depends(get_weather_svc),
) -> WeatherForecastResponse:
    """Retrieve multi-day meteorological weather forecast for a farm."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    res = weather_svc.get_forecast(
        latitude=farm.latitude,
        longitude=farm.longitude,
        farm_id=farm.id,
        days=days,
    )
    return res


@router.get(
    "/{farm_id}/weather/history",
    response_model=List[WeatherObservationRecord],
    summary="Get Persisted Weather Observation History",
)
def get_farm_weather_history(
    farm_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    farm_svc: FarmService = Depends(get_farm_svc),
    weather_svc: WeatherService = Depends(get_weather_svc),
) -> List[WeatherObservationRecord]:
    """Retrieve historical persisted weather observations for a farm plot."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    return weather_svc.get_history(farm_id=farm.id, limit=limit, offset=offset)


# -----------------------------------------------------------------------------
# Satellite & Vegetation Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/{farm_id}/satellite/latest",
    response_model=SatelliteObservationResponse,
    summary="Get Latest Sentinel-2 Vegetation Observation",
)
def get_farm_satellite_latest(
    farm_id: str,
    max_cloud_percent: float = Query(30.0, ge=0.0, le=100.0, description="Max acceptable cloud percentage"),
    days_back: int = Query(45, ge=5, le=180, description="Search window in days"),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    farm_svc: FarmService = Depends(get_farm_svc),
    satellite_svc: SatelliteService = Depends(get_satellite_svc),
) -> SatelliteObservationResponse:
    """Retrieve the most recent cloud-masked Sentinel-2 NDVI observation for a farm."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    return satellite_svc.get_latest_observation(
        farm=farm,
        max_cloud_percent=max_cloud_percent,
        days_back=days_back,
        persist=True,
        user_token=raw_token,
    )


@router.get(
    "/{farm_id}/satellite/history",
    response_model=SatelliteHistoryResponse,
    summary="Get Historical Sentinel-2 Vegetation Observations",
)
def get_farm_satellite_history(
    farm_id: str,
    days_back: int = Query(90, ge=15, le=365, description="Historical query window in days"),
    max_cloud_percent: float = Query(40.0, ge=0.0, le=100.0),
    limit: int = Query(12, ge=1, le=50),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    farm_svc: FarmService = Depends(get_farm_svc),
    satellite_svc: SatelliteService = Depends(get_satellite_svc),
) -> SatelliteHistoryResponse:
    """Retrieve multi-temporal Sentinel-2 NDVI observations for time-series analysis."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    return satellite_svc.get_historical_observations(
        farm=farm,
        days_back=days_back,
        max_cloud_percent=max_cloud_percent,
        limit=limit,
        user_token=raw_token,
    )


@router.get(
    "/{farm_id}/vegetation",
    response_model=FarmVegetationSummary,
    summary="Get Farmer-Friendly Vegetation Health Summary",
)
def get_farm_vegetation_summary(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    farm_svc: FarmService = Depends(get_farm_svc),
    satellite_svc: SatelliteService = Depends(get_satellite_svc),
) -> FarmVegetationSummary:
    """Retrieve simplified vegetation health status and canopy condition for a farm."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )

    return satellite_svc.get_vegetation_summary(farm=farm, user_token=raw_token)


# -----------------------------------------------------------------------------
# Closed-Loop Monitoring, Risk Trend, Feedback & Outcomes
# -----------------------------------------------------------------------------
@router.get(
    "/{farm_id}/monitoring",
    response_model=FarmMonitoringResponse,
    summary="Get Farm Monitoring Summary & Temporal Risk Trend",
)
def get_farm_monitoring_summary(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> FarmMonitoringResponse:
    """Retrieve full closed-loop monitoring state, temporal risk delta, and telemetry changes."""
    try:
        return monitoring_svc.get_farm_monitoring_summary(
            farm_id=farm_id,
            user=user,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{farm_id}/predictions/trend",
    response_model=RiskTrendResponse,
    summary="Get Risk Trend Between Consecutive Assessments",
)
def get_farm_risk_trend(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> RiskTrendResponse:
    """Retrieve directional risk delta (increasing, decreasing, stable) between consecutive runs."""
    try:
        return monitoring_svc.get_risk_trend_for_farm(
            farm_id=farm_id,
            user=user,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{farm_id}/feedback",
    response_model=FarmFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log Farmer Management Action or Field Note",
)
def log_farm_feedback(
    farm_id: str,
    feedback_in: FarmFeedbackRequest,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> FarmFeedbackResponse:
    """Record an on-field agronomic action or ground note taken in response to risk alerts."""
    try:
        return monitoring_svc.log_feedback(
            farm_id=farm_id,
            user=user,
            feedback_in=feedback_in,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{farm_id}/feedback",
    response_model=List[FarmFeedbackResponse],
    summary="List Farm Feedback and Field Action Trail",
)
def list_farm_feedback(
    farm_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> List[FarmFeedbackResponse]:
    """Retrieve chronologically ordered record of farmer actions and field feedback."""
    try:
        return monitoring_svc.list_feedback_for_farm(
            farm_id=farm_id,
            user=user,
            limit=limit,
            offset=offset,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{farm_id}/crops/{crop_id}/outcome",
    response_model=CropOutcomeResponse,
    summary="Record Verified Harvest or Failure Outcome",
)
def record_crop_outcome(
    farm_id: str,
    crop_id: str,
    outcome_in: CropOutcomeRequest,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> CropOutcomeResponse:
    """Record ground-truth harvest yield or failure outcome for closed-loop evaluation."""
    try:
        return monitoring_svc.record_outcome(
            farm_id=farm_id,
            crop_id=crop_id,
            user=user,
            outcome_in=outcome_in,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{farm_id}/crops/{crop_id}/outcome",
    response_model=Optional[CropOutcomeResponse],
    summary="Get Recorded Crop Outcome",
)
def get_crop_outcome(
    farm_id: str,
    crop_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> Optional[CropOutcomeResponse]:
    """Retrieve ground-truth outcome recorded for a crop cycle if available."""
    try:
        return monitoring_svc.get_crop_outcome(
            farm_id=farm_id,
            crop_id=crop_id,
            user=user,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{farm_id}/feedback/{feedback_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Farm Feedback Entry",
)
def delete_farm_feedback(
    farm_id: str,
    feedback_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> Response:
    """Safely delete a feedback/action record by ID."""
    try:
        success = monitoring_svc.delete_feedback(
            farm_id=farm_id,
            feedback_id=feedback_id,
            user=user,
            user_token=raw_token,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feedback '{feedback_id}' on Farm '{farm_id}' not found.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{farm_id}/crops/{crop_id}/outcome",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear Recorded Crop Outcome and Restore to Active State",
)
def clear_crop_outcome(
    farm_id: str,
    crop_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> Response:
    """Safely clear ground-truth harvest/failure outcome and restore crop cycle to active Vegetative state."""
    try:
        monitoring_svc.clear_crop_outcome(
            farm_id=farm_id,
            crop_id=crop_id,
            user=user,
            user_token=raw_token,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{farm_id}/diagnostics",
    response_model=MonitoringDiagnosticsResponse,
    summary="Get Model Telemetry and Monitoring Diagnostics",
)
def get_monitoring_diagnostics(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    monitoring_svc: MonitoringService = Depends(get_monitoring_svc),
) -> MonitoringDiagnosticsResponse:
    """Retrieve operational diagnostics covering telemetry freshness, fallback rates, and feedback."""
    return monitoring_svc.get_diagnostics()


@router.get(
    "/{farm_id}/alerts",
    response_model=List[FarmAlertResponse],
    summary="List Farm Early Warning Alerts",
)
def list_farm_alerts(
    farm_id: str,
    alert_status: Optional[str] = Query(None, alias="status", description="Filter by status (active, acknowledged, resolved)"),
    severity: Optional[str] = Query(None, description="Filter by severity (info, warning, critical)"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    farm_svc: FarmService = Depends(get_farm_svc),
    alert_svc: AlertService = Depends(get_alert_svc),
) -> List[FarmAlertResponse]:
    """Retrieve early warning alerts for a farm with tenant isolation."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )
    try:
        return alert_svc.list_alerts_for_farm(
            farm_id=farm_id,
            user=user,
            status=alert_status,
            severity=severity,
            alert_type=alert_type,
            limit=limit,
            offset=offset,
            user_token=raw_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )



@router.post(
    "/{farm_id}/alerts/{alert_id}/acknowledge",
    response_model=FarmAlertResponse,
    summary="Acknowledge Farm Alert",
)
def acknowledge_farm_alert(
    farm_id: str,
    alert_id: str,
    body: Optional[AlertAcknowledgeRequest] = None,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    farm_svc: FarmService = Depends(get_farm_svc),
    alert_svc: AlertService = Depends(get_alert_svc),
) -> FarmAlertResponse:
    """Acknowledge an early warning alert (farmers and experts)."""
    farm = farm_svc.get_farm(farm_id=farm_id, user=user)
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm '{farm_id}' not found or access denied.",
        )
    try:
        notes = body.notes if body else None
        return alert_svc.acknowledge_alert(
            farm_id=farm_id,
            alert_id=alert_id,
            user=user,
            notes=notes,
            user_token=raw_token,
        )

    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)


@router.post(
    "/{farm_id}/alerts/{alert_id}/resolve",
    response_model=FarmAlertResponse,
    summary="Resolve Farm Alert",
)
def resolve_farm_alert(
    farm_id: str,
    alert_id: str,
    body: Optional[AlertResolveRequest] = None,
    user: AuthenticatedUser = Depends(get_any_authenticated_user),
    raw_token: Optional[str] = Depends(get_raw_token),
    alert_svc: AlertService = Depends(get_alert_svc),
) -> FarmAlertResponse:
    """Resolve an early warning alert (restricted to agricultural experts and administrators)."""
    try:
        res_notes = body.resolution_notes if body else None
        return alert_svc.resolve_alert(
            farm_id=farm_id,
            alert_id=alert_id,
            user=user,
            resolution_notes=res_notes,
            user_token=raw_token,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)


