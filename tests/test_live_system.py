"""Lightweight automated test suite for Live Crop Risk Prediction and Open-Meteo weather integration.

Tests:
1. Model bundle loading and schema integrity.
2. Prediction on new inputs using saved scikit-learn pipeline directly.
3. Risk band mapping consistency (Low, Medium, High).
4. Validation and graceful handling of missing/invalid inputs.
5. Crop recommendation model predictions and ranking.
6. Open-Meteo live weather retrieval and fallback on invalid coordinates.
7. SHAP explainability using LinearExplainer for LogisticRegression.
8. Digital Twin integration with real live prediction cases.
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.digital_twin import run_digital_twin, simulate_custom_scenario
from src.live_prediction import (
    get_crop_recommendation,
    get_district_baseline,
    get_prediction_explanation,
    load_model_bundle,
    predict_new_case,
)
from src.weather_service import get_current_weather


class TestLiveCropRiskSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_model_bundle("models/agri_ai_bundle.pkl")
        cls.best_model_name = cls.bundle["best_failure_model_name"]
        cls.best_model = cls.bundle["failure_models"][cls.best_model_name]
        cls.failure_features = cls.bundle["failure_features"]

    def test_bundle_structure(self):
        """Verify model bundle contains all expected models and feature definitions."""
        self.assertIn("best_failure_model_name", self.bundle)
        self.assertIn("failure_models", self.bundle)
        self.assertIn("crop_recommendation_model", self.bundle)
        self.assertIn("failure_features", self.bundle)
        self.assertIn("recommendation_features", self.bundle)
        self.assertGreater(len(self.bundle["failure_features"]), 10)

    def test_district_baseline_derivation(self):
        """Verify baseline values and metadata are correctly derived from the existing dataset."""
        baseline = get_district_baseline("Jaipur", "Rice")
        self.assertEqual(baseline["district"], "Jaipur")
        self.assertEqual(baseline["state"], "Rajasthan")
        self.assertEqual(baseline["region"], "Northwest Dryland")
        self.assertIn("Rice", baseline["available_crops"])

        feats = baseline["feature_baselines"]
        for col in ["Rainfall", "Temperature", "Humidity", "SoilMoisture", "NDVI_Flowering", "WaterStress"]:
            self.assertIn(col, feats)
            self.assertIsInstance(feats[col], (int, float))

        # Check feature sources provenance tracking
        sources = baseline["feature_sources"]
        self.assertEqual(sources["Temperature"], "Live weather (Open-Meteo)")
        self.assertIn("Historical dataset", sources["Rainfall"])
        self.assertEqual(sources["Crop"], "User selection")

    def test_predict_new_case_valid(self):
        """Verify new-input prediction runs through pipeline directly without manual preprocessing."""
        baseline = get_district_baseline("Jaipur", "Rice")
        input_data = baseline["feature_baselines"].copy()

        result = predict_new_case(input_data)
        self.assertIn("risk_probability", result)
        self.assertIn("risk_level", result)
        self.assertIn("prediction", result)
        self.assertIn("best_model_name", result)
        self.assertIn("input_features", result)

        self.assertGreaterEqual(result["risk_probability"], 0.0)
        self.assertLessEqual(result["risk_probability"], 1.0)
        self.assertIn(result["risk_level"], ["Low", "Medium", "High"])
        self.assertIn(result["prediction"], [0, 1])
        self.assertEqual(result["best_model_name"], self.best_model_name)

    def test_predict_missing_features_raises_error(self):
        """Verify validation catches missing features before prediction."""
        incomplete_input = {"District": "Jaipur", "Crop": "Rice"}
        with self.assertRaises(ValueError):
            predict_new_case(incomplete_input)

    def test_crop_recommendation(self):
        """Verify crop recommendation model generates ranked options."""
        baseline = get_district_baseline("Jaipur", "Rice")
        input_data = {**baseline["feature_baselines"], "District": "Jaipur"}

        rec = get_crop_recommendation(input_data)
        self.assertTrue(rec["success"])
        self.assertIsNotNone(rec["recommended_crop"])
        self.assertGreaterEqual(len(rec["top_options"]), 1)
        self.assertIn("percentage", rec["top_options"][0])

    def test_shap_explanation(self):
        """Verify SHAP explanation runs with appropriate explainer for the best model."""
        baseline = get_district_baseline("Jaipur", "Rice")
        input_data = baseline["feature_baselines"]

        exp = get_prediction_explanation(input_data, background_samples=40)
        self.assertIn("explainer_type", exp)
        self.assertIn("top_features", exp)
        self.assertIn("summary", exp)
        self.assertGreaterEqual(len(exp["top_features"]), 3)
        self.assertIn("impact", exp["top_features"][0])
        self.assertIn("direction", exp["top_features"][0])

    def test_open_meteo_live_weather(self):
        """Verify live weather fetches real data from Open-Meteo without API key."""
        weather = get_current_weather(26.9124, 75.7873)
        self.assertTrue(weather["success"])
        self.assertIsNotNone(weather["temperature"])
        self.assertIsNotNone(weather["humidity"])
        self.assertIsNotNone(weather["precipitation"])
        self.assertEqual(weather["source"], "Open-Meteo")

    def test_open_meteo_invalid_coords(self):
        """Verify graceful error handling for invalid coordinates without crashing."""
        weather = get_current_weather(999.0, 999.0)
        self.assertFalse(weather["success"])
        self.assertIsNotNone(weather["error"])
        self.assertIsNone(weather["temperature"])

    def test_digital_twin_integration(self):
        """Verify existing Digital Twin seamlessly operates on live prediction row."""
        import pandas as pd
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
