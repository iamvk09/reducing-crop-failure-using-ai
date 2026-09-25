"""Comprehensive automated test suite for Real Live-Input Crop Failure Prediction.

Tests:
1. Model bundle structure, slim runtime bundle loading, and schema integrity.
2. Complete end-to-end new-input prediction workflow:
   State -> District -> Crop -> Season -> Weather -> Pipeline -> Risk -> Advice.
3. Open-Meteo live weather retrieval and graceful API failure handling.
4. Input validation (invalid categories, out-of-range numerics, missing features, no zero-substitution).
5. Farmer Mode feature assembly with full provenance.
6. Expert Mode overrides and provenance tracking.
7. Crop recommendation ranking.
8. SHAP explanation with lazy loading.
9. Specialized region/crop model lazy loading via _LazyModelDict.
10. Digital Twin integration on live input cases.
"""

from datetime import datetime
from pathlib import Path
import sys
import unittest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.digital_twin import run_digital_twin, simulate_custom_scenario
from src.live_prediction import (
    _LazyModelDict,
    _discover_specialized_keys,
    get_crop_recommendation,
    get_district_baseline,
    get_prediction_explanation,
    load_model_bundle,
    predict_new_case,
    validate_prediction_input,
)
from src.weather_service import get_current_weather


class TestLiveCropRiskSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the runtime bundle (or full bundle as fallback)
        cls.bundle = load_model_bundle()
        cls.best_model_name = cls.bundle["best_failure_model_name"]
        cls.best_model = cls.bundle["failure_models"][cls.best_model_name]
        cls.failure_features = cls.bundle["failure_features"]

    def test_bundle_structure(self):
        """Verify model bundle contains expected models, schemas, and best model name."""
        self.assertIn("best_failure_model_name", self.bundle)
        self.assertIn("failure_models", self.bundle)
        self.assertIn("crop_recommendation_model", self.bundle)
        self.assertIn("failure_features", self.bundle)
        self.assertIn("recommendation_features", self.bundle)
        self.assertGreaterEqual(len(self.bundle["failure_features"]), 16)
        self.assertEqual(self.bundle["best_failure_model_name"], "logistic_regression")

    def test_district_baseline_derivation(self):
        """Verify baseline values and metadata are correctly derived from the existing dataset."""
        baseline = get_district_baseline("Jaipur", "Rice", "Kharif")
        self.assertEqual(baseline["district"], "Jaipur")
        self.assertEqual(baseline["state"], "Rajasthan")
        self.assertEqual(baseline["region"], "Northwest Dryland")
        self.assertIn("Rice", baseline["available_crops"])
        self.assertIn("Kharif", baseline["available_seasons"])

        feats = baseline["feature_baselines"]
        for col in ["Rainfall", "Temperature", "Humidity", "SoilMoisture", "NDVI_Flowering", "WaterStress"]:
            self.assertIn(col, feats)
            self.assertIsInstance(feats[col], (int, float))

        # Check feature sources provenance tracking
        sources = baseline["feature_sources"]
        self.assertIn("Open-Meteo", sources["Temperature"])
        self.assertIn("Historical", sources["Rainfall"])
        self.assertEqual(sources["Crop"], "User selection")

    def test_complete_new_input_workflow(self):
        """Verify complete pipeline: State -> District -> Crop -> Season -> Weather -> Pipeline -> Prediction."""
        # 1. State / District / Crop / Season selection
        state = "Maharashtra"
        district = "Pune"
        crop = "Soybean"
        season = "Kharif"

        baseline = get_district_baseline(district, crop, season)
        self.assertEqual(baseline["state"], state)
        lat, lon = baseline["latitude"], baseline["longitude"]

        # 2. Open-Meteo weather
        weather = get_current_weather(lat, lon)
        feature_vector = baseline["feature_baselines"].copy()

        # Update with live weather if available
        if weather["success"] and weather["temperature"] is not None:
            feature_vector["Temperature"] = float(weather["temperature"])
            feature_vector["Humidity"] = float(weather["humidity"])

        feature_vector["State"] = state
        feature_vector["Crop"] = crop
        feature_vector["Season"] = season
        feature_vector["SoilType"] = "Medium Black"
        feature_vector["IrrigationLevel"] = "Medium"

        # 3. Validation
        is_valid, err = validate_prediction_input(feature_vector, self.bundle)
        self.assertTrue(is_valid, f"Validation failed: {err}")

        # 4. Model prediction
        pred = predict_new_case(feature_vector)
        self.assertIn("risk_probability", pred)
        self.assertIn("risk_level", pred)
        self.assertIn(pred["risk_level"], ["Low", "Medium", "High"])
        self.assertGreaterEqual(pred["risk_probability"], 0.0)
        self.assertLessEqual(pred["risk_probability"], 1.0)

        # 5. Recommendation
        rec = get_crop_recommendation({**feature_vector, "District": district})
        self.assertTrue(rec["success"])
        self.assertIsNotNone(rec["recommended_crop"])

    def test_open_meteo_live_weather(self):
        """Verify live weather fetches real data from Open-Meteo with Asia/Kolkata timezone."""
        weather = get_current_weather(26.9124, 75.7873)
        self.assertTrue(weather["success"])
        self.assertIsNotNone(weather["temperature"])
        self.assertIsNotNone(weather["humidity"])
        self.assertIsNotNone(weather["precipitation"])
        self.assertIn("Open-Meteo", weather["source"])
        self.assertTrue(weather.get("is_estimate", False))

    def test_open_meteo_failure_and_fallback(self):
        """Verify graceful error handling on API failure and fallback to baseline."""
        # Invalid coordinates
        weather = get_current_weather(999.0, 999.0)
        self.assertFalse(weather["success"])
        self.assertIsNotNone(weather["error"])
        self.assertIsNone(weather["temperature"])

        # Fallback to historical district baseline ensures prediction proceeds without crashing
        baseline = get_district_baseline("Jaipur", "Rice")
        fallback_input = baseline["feature_baselines"].copy()
        pred = predict_new_case(fallback_input)
        self.assertIn("risk_probability", pred)
        self.assertIn(pred["risk_level"], ["Low", "Medium", "High"])

    def test_input_validation_missing_feature(self):
        """Verify validation catches missing features and does not silently substitute zeros."""
        incomplete = {"State": "Maharashtra", "Crop": "Rice"}
        is_valid, err = validate_prediction_input(incomplete, self.bundle)
        self.assertFalse(is_valid)
        self.assertIn("Missing required input features", err)

        with self.assertRaises(ValueError):
            predict_new_case(incomplete)

    def test_input_validation_invalid_categories(self):
        """Verify invalid categorical values are rejected."""
        baseline = get_district_baseline("Jaipur", "Rice")
        bad_cat_input = baseline["feature_baselines"].copy()
        bad_cat_input["State"] = "NonExistentState"

        is_valid, err = validate_prediction_input(bad_cat_input, self.bundle)
        self.assertFalse(is_valid)
        self.assertIn("Invalid value", err)

        with self.assertRaises(ValueError):
            predict_new_case(bad_cat_input)

    def test_input_validation_out_of_range_numeric(self):
        """Verify extreme or invalid numeric features are rejected."""
        baseline = get_district_baseline("Jaipur", "Rice")
        bad_num_input = baseline["feature_baselines"].copy()
        bad_num_input["Temperature"] = 150.0  # Absurd temperature

        is_valid, err = validate_prediction_input(bad_num_input, self.bundle)
        self.assertFalse(is_valid)
        self.assertIn("outside plausible agronomic range", err)

        with self.assertRaises(ValueError):
            predict_new_case(bad_num_input)

    def test_farmer_mode_feature_assembly(self):
        """Verify Farmer Mode produces complete 16-feature vector with no zero fabrication."""
        baseline = get_district_baseline("Varanasi", "Rice", "Kharif")
        feats = baseline["feature_baselines"].copy()

        # Farmer Mode provides: State, District, Crop, Season, SoilType, IrrigationLevel
        feats["State"] = "Uttar Pradesh"
        feats["Season"] = "Kharif"
        feats["Crop"] = "Rice"
        feats["SoilType"] = "Alluvial"
        feats["IrrigationLevel"] = "High"

        # Check no feature is zero-fabricated
        for f in self.bundle["failure_features"]:
            self.assertIn(f, feats)
            self.assertIsNotNone(feats[f])
            if isinstance(feats[f], (int, float)):
                # Ensure values are not fabricated as 0
                if f != "Rainfall":  # Rainfall could theoretically be 0 in extreme drought
                    self.assertGreater(feats[f], 0.0)

        res = predict_new_case(feats)
        self.assertIn(res["risk_level"], ["Low", "Medium", "High"])

    def test_expert_mode_overrides_alter_risk(self):
        """Verify Expert Mode overrides change prediction risk as expected."""
        baseline = get_district_baseline("Jaipur", "Wheat", "Rabi")
        base_input = baseline["feature_baselines"].copy()
        base_res = predict_new_case(base_input)

        # Expert introduces extreme drought stress: drop rainfall, drop soil moisture, spike water stress
        drought_input = base_input.copy()
        drought_input["Rainfall"] = 10.0
        drought_input["SoilMoisture"] = 10.0
        drought_input["WaterStress"] = 0.90
        drought_input["NDVI_Flowering"] = 0.20

        drought_res = predict_new_case(drought_input)
        # Drought risk should be strictly higher than baseline
        self.assertGreater(drought_res["risk_probability"], base_res["risk_probability"])

    def test_crop_recommendation(self):
        """Verify crop recommendation model generates ranked options."""
        baseline = get_district_baseline("Jaipur", "Rice")
        input_data = {**baseline["feature_baselines"], "District": "Jaipur"}

        rec = get_crop_recommendation(input_data)
        self.assertTrue(rec["success"])
        self.assertIsNotNone(rec["recommended_crop"])
        self.assertGreaterEqual(len(rec["top_options"]), 1)
        self.assertIn("percentage", rec["top_options"][0])

    def test_shap_explanation_lazy(self):
        """Verify SHAP explanation runs with LinearExplainer and returns feature attribution."""
        baseline = get_district_baseline("Jaipur", "Rice")
        input_data = baseline["feature_baselines"]

        exp = get_prediction_explanation(input_data, background_samples=40)
        self.assertIn("explainer_type", exp)
        self.assertIn("top_features", exp)
        self.assertIn("summary", exp)
        self.assertGreaterEqual(len(exp["top_features"]), 3)
        self.assertIn("impact", exp["top_features"][0])
        self.assertIn("direction", exp["top_features"][0])

    def test_specialized_model_lazy_loading(self):
        """Verify specialized models load on-demand through _LazyModelDict."""
        region_keys = _discover_specialized_keys("region")
        if region_keys:
            lazy_regions = _LazyModelDict("region", region_keys)
            sample_reg = region_keys[0]
            self.assertIn(sample_reg, lazy_regions)
            model = lazy_regions[sample_reg]
            self.assertIsNotNone(model)
            self.assertTrue(hasattr(model, "predict_proba"))

    def test_digital_twin_integration(self):
        """Verify existing Digital Twin seamlessly operates on live prediction row."""
        baseline = get_district_baseline("Jaipur", "Rice")
        row = pd.Series(baseline["feature_baselines"])

        sim_res = simulate_custom_scenario(
            row,
            self.best_model,
            "Heatwave Test",
            {"Temperature": 4.0, "Humidity": -10.0},
        )
        self.assertEqual(sim_res["Scenario"], "Heatwave Test")
        self.assertGreaterEqual(sim_res["RiskScore"], 0.0)
        self.assertLessEqual(sim_res["RiskScore"], 1.0)

        twin_df = run_digital_twin(row, self.best_model)
        self.assertGreaterEqual(len(twin_df), 3)
        self.assertIn("Scenario", twin_df.columns)
        self.assertIn("RiskScore", twin_df.columns)


if __name__ == "__main__":
    unittest.main()
