"""Prediction and Recommendation Database Repository.

Provides a clean data-access layer for persisting and querying crop risk
predictions and agronomic recommendations in Supabase PostgreSQL:
- Enforces multi-tenant isolation and ownership checks
- Persists full prediction telemetry, model metadata, and provenance
- Manages 1-to-1/1-to-N relationships between predictions and recommendations
- Automatically routes between Supabase PostgREST API and local store in testing mode
"""

import datetime
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.supabase import SupabaseClient, SupabaseClientError, supabase_client


class PredictionRepository:
    """Repository managing prediction and recommendation persistence."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self.client = client or supabase_client
        # Local fallback store for offline development and pytest test isolation
        self._local_predictions: Dict[str, Dict[str, Any]] = {}
        self._local_recommendations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(
        self,
        prediction_data: Dict[str, Any],
        recommendation_data: Optional[Dict[str, Any]] = None,
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a new crop failure prediction and its associated recommendations."""
        prediction_id = prediction_data.get("id") or str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)

        prov_dict = prediction_data.get("provenance", {})
        prov_meta_in = prediction_data.get("provenance_metadata")
        if isinstance(prov_meta_in, dict):
            prov_metadata = prov_meta_in.copy()
            if "data_quality" not in prov_metadata and "data_quality" in prediction_data:
                prov_metadata["data_quality"] = prediction_data.get("data_quality")
            if "explanation" not in prov_metadata and "explanation" in prediction_data:
                prov_metadata["explanation"] = prediction_data.get("explanation")
            if "satellite_metadata" not in prov_metadata and "satellite_metadata" in prediction_data:
                prov_metadata["satellite_metadata"] = prediction_data.get("satellite_metadata")
            if "rainfall_metadata" not in prov_metadata and "rainfall_metadata" in prediction_data:
                prov_metadata["rainfall_metadata"] = prediction_data.get("rainfall_metadata")
        elif isinstance(prov_dict, dict):
            features_map = prov_dict.get("features", prov_dict) if "features" in prov_dict else prov_dict
            prov_metadata = {
                "features": {k: v for k, v in features_map.items() if k not in ("data_quality", "explanation", "feature_details", "satellite_metadata", "rainfall_metadata")},
                "data_quality": prediction_data.get("data_quality") or prov_dict.get("data_quality"),
                "explanation": prediction_data.get("explanation") or prov_dict.get("explanation"),
                "satellite_metadata": prediction_data.get("satellite_metadata") or prov_dict.get("satellite_metadata"),
                "rainfall_metadata": prediction_data.get("rainfall_metadata") or prov_dict.get("rainfall_metadata"),
            }
        else:
            prov_metadata = {
                "features": {},
                "data_quality": prediction_data.get("data_quality"),
                "explanation": prediction_data.get("explanation"),
                "satellite_metadata": prediction_data.get("satellite_metadata"),
                "rainfall_metadata": prediction_data.get("rainfall_metadata"),
            }

        db_pred_record = {
            "id": prediction_id,
            "farm_id": prediction_data.get("farm_id"),
            "user_id": prediction_data.get("user_id"),
            "crop_id": prediction_data.get("crop_id"),
            "crop": prediction_data.get("crop"),
            "season": prediction_data.get("season"),
            "state": prediction_data.get("state"),
            "district": prediction_data.get("district"),
            "risk_probability": float(prediction_data.get("risk_probability", 0.0)),
            "risk_level": prediction_data.get("risk_level"),
            "prediction_class": int(prediction_data.get("prediction_class", 0)),
            "best_model_name": prediction_data.get("best_model_name", "agri_ai_runtime_bundle"),
            "global_risk": prediction_data.get("global_risk"),
            "region_risk": prediction_data.get("region_risk"),
            "crop_risk": prediction_data.get("crop_risk"),
            "consensus_risk": prediction_data.get("consensus_risk"),
            "input_features": prediction_data.get("input_features", {}),
            "provenance_metadata": prov_metadata,
            "weather_data": prediction_data.get("weather_data"),
            "weather_source": prediction_data.get("weather_source", "Open-Meteo"),
            "is_fallback_weather": bool(prediction_data.get("is_fallback_weather", False)),
            "is_farmer_case": True,
            "created_at": now.isoformat(),
        }

        # 1. Attempt live Supabase persistence if configured
        if self.client.is_live_configured():
            try:
                inserted_pred = self.client.insert(
                    table="predictions",
                    data=db_pred_record,
                    user_token=user_token,
                )
                prediction_id = inserted_pred.get("id", prediction_id)
            except SupabaseClientError as e:
                logger.warning("Supabase prediction persistence unavailable (%s). Falling back to local state.", str(e))

        # 2. Update local state
        with self._lock:
            self._local_predictions[prediction_id] = db_pred_record.copy()

        # 3. Persist recommendations if provided
        saved_rec = None
        if recommendation_data:
            rec_id = str(uuid.uuid4())
            db_rec_record = {
                "id": rec_id,
                "prediction_id": prediction_id,
                "farm_id": prediction_data.get("farm_id"),
                "recommended_crop": recommendation_data.get("recommended_crop", prediction_data.get("crop")),
                "top_options": recommendation_data.get("top_options", []),
                "advisory_text": recommendation_data.get("advisory_summary", ""),
                "created_at": now.isoformat(),
            }

            if self.client.is_live_configured():
                try:
                    self.client.insert(
                        table="recommendations",
                        data=db_rec_record,
                        user_token=user_token,
                    )
                except SupabaseClientError as e:
                    logger.warning("Could not persist recommendation to Supabase: %s", str(e))

            with self._lock:
                self._local_recommendations[rec_id] = db_rec_record.copy()
            saved_rec = db_rec_record

        result = db_pred_record.copy()
        result["recommendations"] = saved_rec
        return result

    def get_by_id(
        self,
        prediction_id: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a specific prediction by ID, enforcing tenant isolation."""
        # 1. Try Supabase query if configured
        if self.client.is_live_configured():
            try:
                params = {"id": f"eq.{prediction_id}"}
                records = self.client.select("predictions", params=params, user_token=user_token)
                if records:
                    pred = records[0]
                    # Isolation check: Farmers can only access their own predictions
                    if role not in ["expert", "admin"] and user_id and pred.get("user_id") != user_id:
                        return None

                    # Attach recommendation
                    rec_params = {"prediction_id": f"eq.{prediction_id}"}
                    recs = self.client.select("recommendations", params=rec_params, user_token=user_token)
                    pred["recommendations"] = recs[0] if recs else None
                    return pred
            except SupabaseClientError as e:
                logger.warning("Supabase select failed for prediction %s: %s", prediction_id, str(e))

        # 2. Fallback to local store
        with self._lock:
            pred = self._local_predictions.get(prediction_id)
            if not pred:
                return None

            # Ownership check for farmers
            if role not in ["expert", "admin"] and user_id and pred.get("user_id") != user_id:
                return None

            res = pred.copy()
            rec = next(
                (r for r in self._local_recommendations.values() if r.get("prediction_id") == prediction_id),
                None,
            )
            res["recommendations"] = rec
            return res

    def list_for_farm(
        self,
        farm_id: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical predictions for a given farm in reverse chronological order."""
        # 1. Try Supabase query if configured
        if self.client.is_live_configured():
            try:
                params = {
                    "farm_id": f"eq.{farm_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                }
                records = self.client.select("predictions", params=params, user_token=user_token)
                for pred in records:
                    rec_params = {"prediction_id": f"eq.{pred['id']}"}
                    recs = self.client.select("recommendations", params=rec_params, user_token=user_token)
                    pred["recommendations"] = recs[0] if recs else None
                # If live configured and query succeeded, return records directly (even if empty)
                return records
            except SupabaseClientError as e:
                logger.warning("Supabase list predictions failed for farm %s: %s. Falling back to local store.", farm_id, str(e))

        # 2. Fallback to local store
        with self._lock:
            preds = [p for p in self._local_predictions.values() if p.get("farm_id") == farm_id]

        # Ownership filter for farmers
        if role not in ["expert", "admin"] and user_id:
            preds = [p for p in preds if p.get("user_id") == user_id]

        preds.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        paginated = preds[offset : offset + limit]

        results = []
        with self._lock:
            for p in paginated:
                res = p.copy()
                rec = next(
                    (r for r in self._local_recommendations.values() if r.get("prediction_id") == p.get("id")),
                    None,
                )
                res["recommendations"] = rec
                results.append(res)

        return results

    def list_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        user_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve all historical predictions owned by a user across all their farms."""
        if self.client.is_live_configured():
            try:
                params = {
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                }
                records = self.client.select("predictions", params=params, user_token=user_token)
                for pred in records:
                    rec_params = {"prediction_id": f"eq.{pred['id']}"}
                    recs = self.client.select("recommendations", params=rec_params, user_token=user_token)
                    pred["recommendations"] = recs[0] if recs else None
                # If live configured and query succeeded, return records directly (even if empty)
                return records
            except SupabaseClientError as e:
                logger.warning("Supabase list predictions failed for user %s: %s. Falling back to local store.", user_id, str(e))

        with self._lock:
            preds = [p for p in self._local_predictions.values() if p.get("user_id") == user_id]

        preds.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        paginated = preds[offset : offset + limit]

        results = []
        with self._lock:
            for p in paginated:
                res = p.copy()
                rec = next(
                    (r for r in self._local_recommendations.values() if r.get("prediction_id") == p.get("id")),
                    None,
                )
                res["recommendations"] = rec
                results.append(res)

        return results

    def clear(self) -> None:
        """Reset in-memory storage (used for test isolation)."""
        with self._lock:
            self._local_predictions.clear()
            self._local_recommendations.clear()


prediction_repository = PredictionRepository()
