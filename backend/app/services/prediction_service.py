"""Model Service Boundary.

Provides a clean service abstraction wrapping the existing ML pipeline:
- Bridges to `src/live_prediction.py` for pipeline loading and prediction
- Bridges to `src/weather_service.py` for live meteorological data
- Bridges to `src/recommendation_engine.py` for agronomic advisories
- Bridges to `src/digital_twin.py` for stress testing simulations

DO NOT duplicate ML algorithms here. All calculations delegate directly to the
existing, verified source modules.
"""

from typing import Any, Dict, List, Optional
import pandas as pd

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
from src.weather_service import get_current_weather


class PredictionService:
    """Service abstraction for crop failure risk prediction and explainability."""

    def __init__(self, bundle_path: Optional[str] = None):
        self.bundle_path = bundle_path
        self._bundle = None

    def _get_bundle(self) -> dict:
        """Lazy-load the model bundle via the existing bundle loader."""
        if self._bundle is None:
            if self.bundle_path:
                self._bundle = load_model_bundle(self.bundle_path)
            else:
                self._bundle = load_model_bundle()
        return self._bundle

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
    ) -> Dict[str, Any]:
        """Assemble full feature vector with live Open-Meteo weather and predict.

        Workflow:
        1. Fetch district baseline & coordinate centroids.
        2. Query Open-Meteo for live weather.
        3. Merge live weather / fallback baseline.
        4. Apply user agronomic inputs and optional expert overrides.
        5. Validate schema and execute prediction pipeline.
        """
        baseline_info = self.get_baseline(district=district, crop=crop, season=season)
        lat, lon = baseline_info["latitude"], baseline_info["longitude"]

        # 1. Fetch weather
        weather = get_current_weather(lat, lon)

        # 2. Build feature vector
        feats = baseline_info["feature_baselines"].copy()
        provenance = baseline_info["feature_sources"].copy()

        feats["State"] = state
        provenance["State"] = "User selection"
        feats["Crop"] = crop
        provenance["Crop"] = "User selection"
        feats["Season"] = season
        provenance["Season"] = "User selection"

        if soil_type:
            feats["SoilType"] = soil_type
            provenance["SoilType"] = "User selection"
        if irrigation_level:
            feats["IrrigationLevel"] = irrigation_level
            provenance["IrrigationLevel"] = "User selection"

        if weather.get("success"):
            if weather.get("temperature") is not None:
                feats["Temperature"] = float(weather["temperature"])
                provenance["Temperature"] = "Live weather estimate (Open-Meteo)"
            if weather.get("humidity") is not None:
                feats["Humidity"] = float(weather["humidity"])
                provenance["Humidity"] = "Live weather estimate (Open-Meteo)"
            if weather.get("soil_moisture_percentage") is not None:
                feats["SoilMoisture"] = float(weather["soil_moisture_percentage"])
                provenance["SoilMoisture"] = "Live weather estimate (Open-Meteo root-zone moisture)"

        # 3. Apply expert overrides if provided
        if overrides:
            mapping = {
                "rainfall_override": "Rainfall",
                "temperature_override": "Temperature",
                "humidity_override": "Humidity",
                "soil_moisture_override": "SoilMoisture",
                "ndvi_override": "NDVI_Flowering",
                "water_stress_override": "WaterStress",
                "pest_risk_override": "PestRisk",
                "suitability_score_override": "SuitabilityScore",
                "yield_index_override": "YieldIndex",
            }
            for override_key, feat_name in mapping.items():
                val = overrides.get(override_key)
                if val is not None:
                    feats[feat_name] = float(val)
                    provenance[feat_name] = "User override (Advanced Inputs)"

        # 4. Predict
        pred_result = self.predict(feats)

        return {
            "prediction": pred_result,
            "input_features": feats,
            "provenance": provenance,
            "weather": weather,
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

    def get_explanation(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate lazy SHAP explainability analysis."""
        return get_prediction_explanation(input_data)

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


# Global service singleton instance
prediction_service = PredictionService()
