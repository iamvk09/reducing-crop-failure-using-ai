"""Model Service Boundary with Supabase Database Persistence.

Provides a clean service abstraction wrapping the existing ML pipeline:
- Bridges to `src/live_prediction.py` for pipeline loading and prediction
- Bridges to `backend/app/services/weather` (WeatherService) for provider-abstracted meteorological data
- Bridges to `src/recommendation_engine.py` for agronomic advisories
- Bridges to `src/digital_twin.py` for stress testing simulations
- Delegates persistence to `PredictionRepository` (Supabase PostgreSQL)

DO NOT duplicate ML algorithms here. All calculations delegate directly to the
existing, verified source modules.
"""

import datetime
import time
from typing import Any, Dict, List, Optional
import pandas as pd

from backend.app.core.logging import logger
from backend.app.core.security import AuthenticatedUser
from backend.app.repositories.prediction_repository import PredictionRepository, prediction_repository
from backend.app.schemas.prediction import PredictionResponse, RecommendationDetails
from backend.app.services.audit_service import audit_service
from backend.app.services.farm_service import farm_service
from backend.app.services.feature_service import FeatureAssembler, FeatureAssemblyResult
from backend.app.services.weather.service import WeatherService, weather_service
from src.digital_twin import run_digital_twin, simulate_custom_scenario
from src.live_prediction import (
    get_crop_recommendation,
    get_district_baseline,
    get_prediction_explanation,
    load_model_bundle,
    predict_new_case,
    validate_prediction_input,
)
from src.recommendation_engine import build_recommendation_summary, risk_band


class PredictionService:
    """Service abstraction for crop failure risk prediction, explainability, and history."""

    def __init__(
        self,
        bundle_path: Optional[str] = None,
        repository: Optional[PredictionRepository] = None,
        weather_svc: Optional[WeatherService] = None,
        satellite_svc: Optional[Any] = None,
    ):
        self.bundle_path = bundle_path
        self.repository = repository or prediction_repository
        self.weather_svc = weather_svc or weather_service
        self._satellite_svc = satellite_svc
        self._bundle = None

    @property
    def satellite_svc(self) -> Any:
        if self._satellite_svc is None:
            from backend.app.services.satellite.service import satellite_service
            self._satellite_svc = satellite_service
        return self._satellite_svc

    def _get_bundle(self) -> dict:
        """Lazy-load the model bundle via the existing bundle loader."""
        if self._bundle is None:
            if self.bundle_path:
                self._bundle = load_model_bundle(self.bundle_path)
            else:
                self._bundle = load_model_bundle()
        return self._bundle

    def warmup_artifacts(self) -> None:
        """Warm up model bundle and district baseline data in memory during startup.

        Eliminates the ~1.5-3.5s latency spike on the first prediction request.
        """
        try:
            self._get_bundle()
            get_district_baseline("Pune", "Soybean", "Kharif")
            logger.info("Crop Risk AI model bundle and baseline tables successfully preloaded.")
        except Exception as exc:
            logger.warning("Optional startup model warmup deferred: %s", exc)

    def get_baseline(
        self,
        district: str,
        crop: Optional[str] = None,
        season: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve empirical district-crop-season baseline."""
        return get_district_baseline(district=district, crop=crop, season=season)

    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute raw crop failure prediction on an assembled 16-feature vector."""
        if self.bundle_path:
            return predict_new_case(input_data, bundle_path=self.bundle_path)
        return predict_new_case(input_data)

    def predict_with_weather(
        self,
        state: str,
        district: str,
        crop: str,
        season: str,
        soil_type: Optional[str] = None,
        irrigation_level: Optional[str] = None,
        overrides: Optional[Dict[str, float]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        farm_id: Optional[str] = None,
        sowing_date: Optional[Any] = None,
        growth_stage: Optional[str] = None,
        satellite_observation: Optional[Any] = None,
        historical_weather: Optional[List[Any]] = None,
        historical_satellite: Optional[List[Any]] = None,
        persist_weather: bool = False,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble full feature vector with live weather, satellite, and phenology, then predict."""
        baseline_info = self.get_baseline(district=district, crop=crop, season=season)
        lat = latitude if latitude is not None else baseline_info["latitude"]
        lon = longitude if longitude is not None else baseline_info["longitude"]

        # 1. Fetch live weather via WeatherService
        weather_res = self.weather_svc.get_current_weather(
            latitude=lat,
            longitude=lon,
            farm_id=farm_id,
            persist=persist_weather,
            user_token=user_token,
        )
        weather_dict = weather_res.model_dump()

        # 2. Assemble 16-feature vector via unified FeatureAssembler
        assembly_result: FeatureAssemblyResult = FeatureAssembler.assemble_features(
            farm_state=state,
            farm_district=district,
            farm_region=baseline_info.get("region"),
            farm_soil_type=soil_type,
            farm_irrigation_level=irrigation_level,
            crop_name=crop,
            crop_season=season,
            crop_sowing_date=sowing_date,
            crop_growth_stage=growth_stage,
            crop_soil_type=soil_type,
            crop_irrigation_level=irrigation_level,
            weather=weather_res,
            historical_weather=historical_weather,
            satellite_observation=satellite_observation,
            historical_satellite=historical_satellite,
            baseline_info=baseline_info,
            overrides=overrides,
            bundle=self._get_bundle(),
        )

        feats = assembly_result.features
        provenance = assembly_result.provenance

        # 3. Predict
        pred_result = self.predict(feats)

        # 4. Generate SHAP Explanation matching the exact 16-feature vector
        explanation = self.build_explanation(
            input_features=feats,
            feature_provenance=assembly_result.feature_provenance,
            crop_stage=growth_stage,
        )

        return {
            "prediction": pred_result,
            "input_features": feats,
            "provenance": provenance,
            "feature_provenance": {k: v.__dict__ for k, v in assembly_result.feature_provenance.items()},
            "weather": weather_dict,
            "is_fallback_weather": assembly_result.is_fallback_weather,
            "is_fallback_satellite": assembly_result.is_fallback_satellite,
            "rainfall_metadata": assembly_result.rainfall_metadata,
            "satellite_metadata": assembly_result.satellite_metadata,
            "data_quality": assembly_result.data_quality,
            "explanation": explanation,
        }

    def get_recommendation(self, input_data: Dict[str, Any], district: str) -> Dict[str, Any]:
        """Generate crop recommendation and practical advisory text."""
        rec = get_crop_recommendation({**input_data, "District": district})
        advisory_summary = build_recommendation_summary(
            pd.Series(
                {
                    "ConsensusRisk": input_data.get("risk_probability", 0.5),
                    "WaterStress": input_data.get("WaterStress", 0.45),
                    "SoilMoisture": input_data.get("SoilMoisture", 45.0),
                    "Rainfall": input_data.get("Rainfall", 120.0),
                    "Temperature": input_data.get("Temperature", 28.0),
                    "PestRisk": input_data.get("PestRisk", 0.40),
                    "RecommendedCrop": rec.get("recommended_crop", input_data.get("Crop")),
                    "Crop": input_data.get("Crop"),
                }
            )
        )
        return {
            "recommended_crop": rec.get("recommended_crop"),
            "top_options": rec.get("top_options", []),
            "advisory_summary": advisory_summary,
        }

    # -------------------------------------------------------------------------
    # Farm Live Prediction & Persistence
    # -------------------------------------------------------------------------
    def predict_for_farm(
        self,
        farm_id: str,
        user: AuthenticatedUser,
        crop_id: Optional[str] = None,
        overrides: Optional[Dict[str, float]] = None,
        ip_address: Optional[str] = None,
        user_token: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[PredictionResponse]:
        """Execute risk prediction for a specific farm and persist result in Supabase."""
        t_start = time.perf_counter()

        # 1. Fetch farm and verify authorization
        farm = farm_service.get_farm(farm_id=farm_id, user=user)
        if not farm:
            return None

        # 2. Identify active crop cycle
        crops = farm_service.list_crops_for_farm(farm_id=farm_id, user=user)
        if not crops:
            raise ValueError(f"No crops registered for farm '{farm.name}'. Please add a crop cycle first.")

        target_crop = None
        if crop_id:
            for c in crops:
                if c.id == crop_id:
                    target_crop = c
                    break
            if not target_crop:
                raise ValueError(f"Crop cycle '{crop_id}' not found on farm '{farm_id}'.")
        else:
            # Pick active crop or first crop
            target_crop = next((c for c in crops if c.is_active), crops[0])

        # 3. Retrieve historical weather and satellite observations for stage-aware engineering
        hist_weather = None
        try:
            hist_weather = self.weather_svc.get_history(farm_id=farm_id, limit=90, user_token=user_token)
        except Exception as e:
            logger.warning("Could not fetch historical weather for farm %s: %s", farm_id, str(e))

        sat_obs = None
        hist_sat = None
        try:
            sat_obs = self.satellite_svc.get_latest_observation(farm=farm, user_token=user_token)
            sat_history_res = self.satellite_svc.get_historical_observations(farm=farm, days_back=90, user_token=user_token)
            hist_sat = sat_history_res.observations if sat_history_res else None
        except Exception as e:
            logger.warning("Could not fetch satellite observations for farm %s: %s", farm_id, str(e))

        # Duplicate-state protection (30-minute window for unchanged telemetry)
        if not force_refresh and not overrides:
            try:
                recent_preds = self.repository.list_for_farm(
                    farm_id=farm_id,
                    user_id=user.id,
                    role=user.role,
                    limit=1,
                    offset=0,
                    user_token=user_token,
                )
                if recent_preds:
                    latest = recent_preds[0]
                    if latest.get("crop_id") == target_crop.id or latest.get("crop") == target_crop.crop:
                        created_raw = latest.get("created_at")
                        if created_raw:
                            if isinstance(created_raw, str):
                                created_dt = datetime.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                            else:
                                created_dt = created_raw
                            if created_dt.tzinfo is None:
                                created_dt = created_dt.replace(tzinfo=datetime.timezone.utc)
                            now_dt = datetime.datetime.now(datetime.timezone.utc)
                            age_seconds = (now_dt - created_dt).total_seconds()
                            if 0 <= age_seconds <= 1800:
                                prov_meta = latest.get("provenance_metadata") or {}
                                prev_sat_date = None
                                if isinstance(prov_meta, dict):
                                    sat_meta = prov_meta.get("satellite_metadata")
                                    if isinstance(sat_meta, dict):
                                        prev_sat_date = sat_meta.get("observation_date") or sat_meta.get("observation_timestamp")
                                    if not prev_sat_date:
                                        feat_prov = prov_meta.get("features", {})
                                        if isinstance(feat_prov, dict):
                                            ndvi_prov = feat_prov.get("NDVI_Flowering")
                                            if isinstance(ndvi_prov, dict):
                                                prev_sat_date = ndvi_prov.get("observation_timestamp")

                                curr_sat_date = str(sat_obs.observation_date) if sat_obs and hasattr(sat_obs, "observation_date") and sat_obs.observation_date else None
                                dq = prov_meta.get("data_quality") or latest.get("data_quality") or {}
                                sat_status = dq.get("satellite_status") if isinstance(dq, dict) else None

                                sat_is_unchanged = (
                                    (prev_sat_date and prev_sat_date == curr_sat_date)
                                    or (sat_status in ("stage_deferred", "baseline", "stale_fallback") and (curr_sat_date is None or prev_sat_date == curr_sat_date or not sat_obs or not getattr(sat_obs, "success", False)))
                                    or (prev_sat_date is None and curr_sat_date is None)
                                )

                                if sat_is_unchanged:
                                    logger.info(
                                        "Duplicate-state protection (Option C): returning recent prediction %s for farm %s (age=%.1fs, sat_status=%s, sat_date=%s)",
                                        latest.get("id"),
                                        farm_id,
                                        age_seconds,
                                        sat_status,
                                        curr_sat_date,
                                    )
                                    return self._to_prediction_response(latest)
            except Exception as e:
                logger.warning("Error checking duplicate-state protection: %s", str(e))

        # 4. Assemble inputs and predict via FeatureAssembler & ML pipeline
        t_assemble_start = time.perf_counter()
        result = self.predict_with_weather(
            state=farm.state,
            district=farm.district,
            crop=target_crop.crop,
            season=target_crop.season,
            soil_type=target_crop.soil_type or farm.soil_type,
            irrigation_level=target_crop.irrigation_level or farm.irrigation_level,
            overrides=overrides,
            latitude=farm.latitude,
            longitude=farm.longitude,
            farm_id=farm.id,
            sowing_date=target_crop.sowing_date,
            growth_stage=target_crop.growth_stage,
            satellite_observation=sat_obs,
            historical_weather=hist_weather,
            historical_satellite=hist_sat,
            persist_weather=True,
            user_token=user_token,
        )
        t_assemble = (time.perf_counter() - t_assemble_start) * 1000

        pred = result["prediction"]
        t_rec_start = time.perf_counter()
        rec_data = self.get_recommendation(result["input_features"], district=farm.district)
        t_ml = (time.perf_counter() - t_rec_start) * 1000

        # 5. Persist to Database via Repository Layer
        t_db_start = time.perf_counter()
        pred_payload = {
            "farm_id": farm_id,
            "user_id": user.id,
            "crop_id": target_crop.id,
            "crop": target_crop.crop,
            "district": farm.district,
            "state": farm.state,
            "season": target_crop.season,
            "risk_probability": pred["risk_probability"],
            "risk_level": pred["risk_level"],
            "prediction_class": pred["prediction"],
            "best_model_name": pred["best_model_name"],
            "global_risk": pred.get("global_risk"),
            "region_risk": pred.get("region_risk"),
            "crop_risk": pred.get("crop_risk"),
            "consensus_risk": pred.get("consensus_risk"),
            "input_features": result["input_features"],
            "provenance": result["provenance"],
            "data_quality": result.get("data_quality"),
            "satellite_metadata": result.get("satellite_metadata"),
            "rainfall_metadata": result.get("rainfall_metadata"),
            "explanation": result.get("explanation").model_dump() if hasattr(result.get("explanation"), "model_dump") else result.get("explanation"),
            "weather_data": result.get("weather"),
            "weather_source": result.get("weather", {}).get("source", "Open-Meteo"),
            "is_fallback_weather": result.get("is_fallback_weather", False),
        }

        persisted = self.repository.create(
            prediction_data=pred_payload,
            recommendation_data=rec_data,
            user_token=user_token,
        )
        t_db = (time.perf_counter() - t_db_start) * 1000
        t_total = (time.perf_counter() - t_start) * 1000

        logger.info(
            "Prediction executed for farm '%s': total=%.1fms (assemble=%.1fms, ml=%.1fms, db=%.1fms)",
            farm_id,
            t_total,
            t_assemble,
            t_ml,
            t_db,
        )

        audit_service.log_action(
            action="prediction:create",
            resource_type="prediction",
            resource_id=persisted["id"],
            user_id=user.id,
            metadata={
                "farm_id": farm_id,
                "crop": target_crop.crop,
                "risk_level": pred["risk_level"],
                "risk_probability": pred["risk_probability"],
                "duration_ms": round(t_total, 2),
            },
            ip_address=ip_address,
        )

        pred_resp = self._to_prediction_response(persisted)

        # 6. Observation-driven Early Warning & Alert Evaluation
        try:
            from backend.app.services.alert_service import alert_service
            prev_pred_record = None
            try:
                past_preds = self.repository.list_for_farm(
                    farm_id=farm_id,
                    user_id=user.id,
                    role=user.role,
                    limit=2,
                    offset=0,
                    user_token=user_token,
                )
                if past_preds and len(past_preds) > 1:
                    prev_pred_record = past_preds[1]
                elif past_preds and len(past_preds) == 1 and past_preds[0].get("id") != persisted["id"]:
                    prev_pred_record = past_preds[0]
            except Exception as pe:
                logger.debug("Could not retrieve past prediction for alert evaluation: %s", str(pe))

            prev_pred_obj = self._to_prediction_response(prev_pred_record) if prev_pred_record else None
            alert_service.evaluate_alert_conditions(
                farm=farm,
                target_crop=target_crop,
                current_pred=pred_resp,
                previous_pred=prev_pred_obj,
                user=user,
                user_token=user_token,
            )
        except Exception as e:
            logger.warning("Error evaluating alerts for farm %s: %s", farm_id, str(e))

        return pred_resp

    def get_prediction(
        self,
        prediction_id: str,
        user: AuthenticatedUser,
        user_token: Optional[str] = None,
    ) -> Optional[PredictionResponse]:
        """Retrieve a specific prediction from database with tenant isolation enforcement."""
        record = self.repository.get_by_id(
            prediction_id=prediction_id,
            user_id=user.id,
            role=user.role,
            user_token=user_token,
        )
        if not record:
            return None

        return self._to_prediction_response(record)

    def list_predictions_for_farm(
        self,
        farm_id: str,
        user: AuthenticatedUser,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> Optional[List[PredictionResponse]]:
        """List historical predictions for a given farm, sorted newest first."""
        farm = farm_service.get_farm(farm_id=farm_id, user=user)
        if not farm:
            return None

        records = self.repository.list_for_farm(
            farm_id=farm_id,
            user_id=user.id,
            role=user.role,
            limit=limit,
            offset=offset,
            user_token=user_token,
        )
        return [self._to_prediction_response(r) for r in records]

    def list_predictions_for_user(
        self,
        user: AuthenticatedUser,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[PredictionResponse]:
        """List all historical predictions owned by the authenticated user."""
        records = self.repository.list_for_user(
            user_id=user.id,
            limit=limit,
            offset=offset,
            user_token=user_token,
        )
        return [self._to_prediction_response(r) for r in records]

    def clear(self) -> None:
        """Clear repository predictions (used for test teardown)."""
        self.repository.clear()

    # -------------------------------------------------------------------------
    # Explainability & Simulations
    # -------------------------------------------------------------------------
    def get_explanation(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate lazy SHAP explainability analysis."""
        return get_prediction_explanation(input_data)

    def build_explanation(
        self,
        input_features: Dict[str, Any],
        feature_provenance: Optional[Dict[str, Any]] = None,
        crop_stage: Optional[str] = None,
    ):
        """Construct a structured SHAP-based explanation matching the 16 features and data provenance."""
        from backend.app.schemas.prediction import PredictionExplanation, ShapFeatureContribution

        exp_data = self.get_explanation(input_features)
        attr_map = exp_data.get("feature_attributions", {})
        explainer_type = exp_data.get("explainer_type", "LinearExplainer")
        output_space = exp_data.get("output_space", "log_odds")
        base_val = float(exp_data.get("base_value", 0.0))
        sum_shap = float(exp_data.get("sum_shap", 0.0))
        margin_val = float(exp_data.get("margin_value", base_val + sum_shap))

        items: List[ShapFeatureContribution] = []
        is_flowering = bool(crop_stage and "flower" in crop_stage.lower())

        name_map = {
            "Rainfall": "Seasonal Rainfall",
            "Temperature": "Air Temperature",
            "Humidity": "Relative Humidity",
            "SoilMoisture": "Soil Moisture",
            "NDVI_Flowering": "Flowering Stage NDVI" if is_flowering else "Historical Flowering Baseline",
            "WaterStress": "Water Stress Index",
            "PestRisk": "Pest & Disease Pressure",
            "SuitabilityScore": "Agro-climatic Crop Suitability",
            "YieldIndex": "Regional Historical Yield Index",
            "State": "State Location",
            "Region": "Agro-climatic Region",
            "Season": "Cropping Season",
            "Crop": "Selected Crop",
            "SoilType": "Soil Type",
            "IrrigationLevel": "Irrigation Access",
            "Year": "Climate Trend Year",
        }

        for feat_name, raw_val in input_features.items():
            disp_name = name_map.get(feat_name, feat_name)

            if isinstance(raw_val, float):
                if feat_name == "Rainfall":
                    fmt_val = f"{raw_val:.1f} mm"
                elif feat_name == "Temperature":
                    fmt_val = f"{raw_val:.1f} °C"
                elif feat_name in ("Humidity", "SoilMoisture"):
                    fmt_val = f"{raw_val:.1f}%"
                elif feat_name == "NDVI_Flowering":
                    fmt_val = f"{raw_val:.3f}"
                elif feat_name in ("WaterStress", "PestRisk", "SuitabilityScore"):
                    fmt_val = f"{raw_val:.2f}"
                elif feat_name == "YieldIndex":
                    fmt_val = f"{raw_val:.1f}"
                else:
                    fmt_val = f"{raw_val:.2f}"
            else:
                fmt_val = str(raw_val)

            phi = float(attr_map.get(feat_name, 0.0))
            abs_phi = abs(phi)

            if phi > 0.0005:
                direction = "increases_risk"
                direction_label = "Increases Risk"
                farmer_text = f"{disp_name} ({fmt_val}) is currently increasing the model's predicted risk."
            elif phi < -0.0005:
                direction = "reduces_risk"
                direction_label = "Reduces Risk"
                farmer_text = f"{disp_name} ({fmt_val}) is currently reducing the model's predicted risk."
            else:
                direction = "neutral"
                direction_label = "Neutral"
                farmer_text = f"{disp_name} ({fmt_val}) is consistent with regional baseline."

            prov_item = feature_provenance.get(feat_name) if feature_provenance else None
            is_live = False
            is_baseline = False
            freshness_status = None
            prov_source = None

            if prov_item:
                if isinstance(prov_item, dict):
                    is_live = bool(prov_item.get("is_live", False))
                    is_baseline = bool(prov_item.get("is_baseline", False))
                    freshness_status = prov_item.get("freshness")
                    prov_source = prov_item.get("source_reference")
                else:
                    is_live = getattr(prov_item, "is_live", False)
                    is_baseline = getattr(prov_item, "is_baseline", False)
                    freshness_status = getattr(prov_item, "freshness", None)
                    prov_source = getattr(prov_item, "source_reference", None)

            if feat_name == "NDVI_Flowering" and not is_flowering:
                prov_source = "Historical flowering baseline"

            items.append(
                ShapFeatureContribution(
                    feature_name=feat_name,
                    display_name=disp_name,
                    feature_value=raw_val,
                    formatted_value=fmt_val,
                    attribution_value=round(phi, 4),
                    abs_attribution=round(abs_phi, 4),
                    direction=direction,
                    direction_label=direction_label,
                    farmer_text=farmer_text,
                    provenance_source=prov_source,
                    is_live=is_live,
                    is_baseline=is_baseline,
                    freshness_status=freshness_status,
                )
            )

        top_increasing = [item for item in items if item.direction == "increases_risk"]
        top_increasing.sort(key=lambda x: x.abs_attribution, reverse=True)
        top_increasing = top_increasing[:3]

        top_reducing = [item for item in items if item.direction == "reduces_risk"]
        top_reducing.sort(key=lambda x: x.abs_attribution, reverse=True)
        top_reducing = top_reducing[:3]

        all_sorted = sorted(items, key=lambda x: x.abs_attribution, reverse=True)

        if top_increasing and top_reducing:
            inc_names = ", ".join([f"{x.display_name} ({x.formatted_value})" for x in top_increasing[:2]])
            red_names = ", ".join([f"{x.display_name} ({x.formatted_value})" for x in top_reducing[:2]])
            narrative = f"The model's risk estimate is primarily driven upward by {inc_names}, while {red_names} are mitigating the predicted risk."
        elif top_increasing:
            inc_names = ", ".join([f"{x.display_name} ({x.formatted_value})" for x in top_increasing[:3]])
            narrative = f"The model's risk estimate is elevated primarily by {inc_names}."
        elif top_reducing:
            red_names = ", ".join([f"{x.display_name} ({x.formatted_value})" for x in top_reducing[:3]])
            narrative = f"The model's risk estimate is favorable and kept low primarily by {red_names}."
        else:
            narrative = "Observed feature metrics align closely with regional baseline conditions."

        return PredictionExplanation(
            explainer_type=explainer_type,
            output_space=output_space,
            base_value=base_val,
            sum_shap=sum_shap,
            margin_value=margin_val,
            top_risk_increasing=top_increasing,
            top_risk_reducing=top_reducing,
            all_features=all_sorted,
            summary_narrative=narrative,
        )

    def run_scenario(
        self,
        input_data: Dict[str, Any],
        scenario_name: str,
        updates: Dict[str, float],
    ) -> Dict[str, Any]:
        """Run custom Digital Twin scenario simulation."""
        bundle = self._get_bundle()
        model = bundle["failure_models"][bundle["best_failure_model_name"]]
        return simulate_custom_scenario(pd.Series(input_data), model, scenario_name, updates)

    def run_preset_scenarios(self, input_data: Dict[str, Any]) -> pd.DataFrame:
        """Run standard preset Digital Twin stress tests."""
        bundle = self._get_bundle()
        model = bundle["failure_models"][bundle["best_failure_model_name"]]
        return run_digital_twin(pd.Series(input_data), model)

    @staticmethod
    def _to_prediction_response(record: Dict[str, Any]) -> PredictionResponse:
        rec_details = None
        recs = record.get("recommendations")
        if recs:
            rec_details = RecommendationDetails(
                recommended_crop=recs.get("recommended_crop"),
                top_options=recs.get("top_options", []),
                advisory_summary=recs.get("advisory_text") or recs.get("advisory_summary", ""),
            )

        created_at = record.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at_dt = datetime.datetime.fromisoformat(created_at)
            except Exception:
                created_at_dt = datetime.datetime.now(datetime.timezone.utc)
        elif isinstance(created_at, datetime.datetime):
            created_at_dt = created_at
        else:
            created_at_dt = datetime.datetime.now(datetime.timezone.utc)

        prob = float(record.get("risk_probability", 0.0))

        # Parse Data Quality summary
        dq_data = record.get("data_quality")
        prov_raw = record.get("provenance_metadata") or record.get("provenance", {})
        if not dq_data and isinstance(prov_raw, dict):
            dq_data = prov_raw.get("data_quality")

        dq_obj = None
        if dq_data and isinstance(dq_data, dict):
            try:
                from backend.app.schemas.prediction import PredictionDataQuality
                dq_obj = PredictionDataQuality(**dq_data)
            except Exception:
                pass

        # Parse Explanation
        exp_data = record.get("explanation")
        if not exp_data and isinstance(prov_raw, dict):
            exp_data = prov_raw.get("explanation")

        exp_obj = None
        if exp_data and isinstance(exp_data, dict):
            try:
                from backend.app.schemas.prediction import PredictionExplanation
                exp_obj = PredictionExplanation(**exp_data)
            except Exception:
                pass
        elif exp_data is not None and hasattr(exp_data, "explainer_type"):
            exp_obj = exp_data

        if isinstance(prov_raw, dict) and "features" in prov_raw and isinstance(prov_raw["features"], dict):
            prov_map = prov_raw["features"]
        elif isinstance(prov_raw, dict):
            prov_map = {k: v for k, v in prov_raw.items() if k not in ("data_quality", "explanation", "feature_details")}
        else:
            prov_map = {}

        return PredictionResponse(
            prediction_id=record.get("id"),
            farm_id=record.get("farm_id"),
            crop_id=record.get("crop_id"),
            crop=record.get("crop", "Unknown"),
            district=record.get("district", ""),
            state=record.get("state", ""),
            season=record.get("season", ""),
            risk_probability=prob,
            risk_percentage=f"{prob * 100:.1f}%",
            risk_level=record.get("risk_level") or risk_band(prob),
            prediction_class=int(record.get("prediction_class", 0)),
            best_model_name=record.get("best_model_name", "agri_ai_runtime_bundle"),
            global_risk=record.get("global_risk"),
            region_risk=record.get("region_risk"),
            crop_risk=record.get("crop_risk"),
            consensus_risk=record.get("consensus_risk"),
            input_features=record.get("input_features", {}),
            provenance=prov_map,
            data_quality=dq_obj,
            explanation=exp_obj,
            weather_data=record.get("weather_data"),
            recommendations=rec_details,
            created_at=created_at_dt,
        )


# Global service singleton instance
prediction_service = PredictionService()
