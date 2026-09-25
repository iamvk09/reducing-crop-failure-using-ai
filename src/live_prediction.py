"""Live crop failure risk prediction, recommendation, and SHAP explainability.

Integrates real new inputs with the existing trained ML pipeline bundle:
- Uses the saved scikit-learn Pipeline directly with no manual preprocessing reproduction.
- Uses bundle["best_failure_model_name"], bundle["failure_models"], and bundle["crop_recommendation_model"].
- Preserves consistent risk bands: Low (<0.45), Medium (0.45-0.70), High (>=0.70).
- Provides data provenance tracking distinguishing live weather, baselines, and user overrides.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import shap

try:
    from src.recommendation_engine import risk_band
except ModuleNotFoundError:
    from recommendation_engine import risk_band


DEFAULT_BUNDLE_PATH = "models/agri_ai_bundle.pkl"
DEFAULT_DATASET_PATH = "data/district_dataset.csv"

_CACHED_BUNDLE = None
_CACHED_BASELINES = None


def load_model_bundle(bundle_path: str = DEFAULT_BUNDLE_PATH) -> dict:
    """Load the trained model bundle using joblib with in-memory caching."""
    global _CACHED_BUNDLE
    if _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE

    path = Path(bundle_path)
    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found at: {path.resolve()}")

    bundle = joblib.load(str(path))
    required_keys = ["failure_models", "best_failure_model_name", "failure_features"]
    missing_keys = [k for k in required_keys if k not in bundle]
    if missing_keys:
        raise KeyError(f"Bundle missing required keys: {missing_keys}")

    _CACHED_BUNDLE = bundle
    return _CACHED_BUNDLE


def _load_baseline_data(dataset_path: str = DEFAULT_DATASET_PATH) -> pd.DataFrame:
    """Load and cache the baseline dataset for feature defaults and distributions."""
    global _CACHED_BASELINES
    if _CACHED_BASELINES is not None:
        return _CACHED_BASELINES

    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"District dataset not found at: {path.resolve()}")

    df = pd.read_csv(str(path))
    _CACHED_BASELINES = df
    return _CACHED_BASELINES


def get_district_baseline(
    district: str,
    crop: Optional[str] = None,
    dataset_path: str = DEFAULT_DATASET_PATH,
) -> Dict[str, Any]:
    """Retrieve empirical baseline values and metadata for a given district and crop.

    Parameters
    ----------
    district : str
        District name (e.g. 'Jaipur', 'Pune', 'Ludhiana').
    crop : str, optional
        Crop name (e.g. 'Rice', 'Wheat', 'Cotton').
    dataset_path : str, optional
        Path to the district dataset CSV.

    Returns
    -------
    dict
        Dictionary containing:
        - 'district_info': State, Region, Latitude, Longitude, SoilType, IrrigationLevel
        - 'feature_baselines': Empirical median values for all model features
        - 'feature_sources': Label for each feature explaining its exact provenance
        - 'available_crops': List of crops historically grown in this district
    """
    df = _load_baseline_data(dataset_path)

    district_mask = df["District"].str.lower() == district.strip().lower()
    if not district_mask.any():
        # Fallback to first district or global median if district is unknown
        district_df = df
        district_name = district
        state = df["State"].mode()[0]
        region = df["Region"].mode()[0]
        latitude = float(df["Latitude"].median())
        longitude = float(df["Longitude"].median())
        soil_type = df["SoilType"].mode()[0]
        irrigation_level = df["IrrigationLevel"].mode()[0]
    else:
        district_df = df[district_mask]
        first_row = district_df.iloc[0]
        district_name = first_row["District"]
        state = first_row["State"]
        region = first_row["Region"]
        latitude = float(first_row["Latitude"])
        longitude = float(first_row["Longitude"])
        soil_type = first_row["SoilType"]
        irrigation_level = first_row["IrrigationLevel"]

    available_crops = sorted(district_df["Crop"].dropna().unique().tolist())
    target_crop = crop if (crop and crop in available_crops) else (available_crops[0] if available_crops else "Rice")

    crop_df = district_df[district_df["Crop"] == target_crop]
    if crop_df.empty:
        crop_df = district_df

    season = crop_df["Season"].mode()[0] if "Season" in crop_df else "Kharif"

    num_cols = [
        "Rainfall",
        "Temperature",
        "Humidity",
        "SoilMoisture",
        "NDVI_Flowering",
        "WaterStress",
        "PestRisk",
        "SuitabilityScore",
        "YieldIndex",
    ]
    medians = {col: round(float(crop_df[col].median()), 3) for col in num_cols if col in crop_df}

    feature_baselines = {
        "Year": datetime.now().year,
        "Rainfall": medians.get("Rainfall", 120.0),
        "Temperature": medians.get("Temperature", 28.0),
        "Humidity": medians.get("Humidity", 60.0),
        "SoilMoisture": medians.get("SoilMoisture", 45.0),
        "NDVI_Flowering": medians.get("NDVI_Flowering", 0.55),
        "WaterStress": medians.get("WaterStress", 0.45),
        "PestRisk": medians.get("PestRisk", 0.40),
        "SuitabilityScore": medians.get("SuitabilityScore", 0.65),
        "YieldIndex": medians.get("YieldIndex", 60.0),
        "State": state,
        "Region": region,
        "Season": season,
        "Crop": target_crop,
        "SoilType": soil_type,
        "IrrigationLevel": irrigation_level,
    }

    feature_sources = {
        "State": "Historical dataset (District mapping)",
        "Region": "Historical dataset (District mapping)",
        "Season": "Historical dataset (Crop-season profile)",
        "Crop": "User selection",
        "SoilType": "Historical dataset (District baseline)",
        "IrrigationLevel": "Historical dataset (District baseline)",
        "Year": "Current year",
        "Temperature": "Live weather (Open-Meteo)",
        "Humidity": "Live weather (Open-Meteo)",
        "Rainfall": "Historical dataset (District seasonal baseline)",
        "SoilMoisture": "Derived from live weather / District baseline",
        "NDVI_Flowering": "Baseline/default (Historical district-crop median)",
        "WaterStress": "Baseline/default (Historical district-crop median)",
        "PestRisk": "Baseline/default (Historical district-crop median)",
        "SuitabilityScore": "Baseline/default (Historical district-crop median)",
        "YieldIndex": "Baseline/default (Historical district-crop median)",
    }

    return {
        "district": district_name,
        "state": state,
        "region": region,
        "latitude": latitude,
        "longitude": longitude,
        "soil_type": soil_type,
        "irrigation_level": irrigation_level,
        "available_crops": available_crops,
        "feature_baselines": feature_baselines,
        "feature_sources": feature_sources,
    }


def predict_new_case(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
) -> Dict[str, Any]:
    """Predict crop failure risk for a newly provided case using the trained pipeline directly.

    Parameters
    ----------
    input_data : dict
        Dictionary of feature values containing all expected failure features.
    bundle_path : str, optional
        Path to the model bundle file.

    Returns
    -------
    dict
        Dictionary containing risk_probability, risk_level, prediction,
        best_model_name, input_features, and specialized consensus scores.
    """
    bundle = load_model_bundle(bundle_path)
    best_model_name = bundle["best_failure_model_name"]
    best_pipeline = bundle["failure_models"][best_model_name]
    failure_features = bundle["failure_features"]

    # Validate that all required failure features are provided
    missing_features = [f for f in failure_features if f not in input_data or input_data[f] is None]
    if missing_features:
        raise ValueError(f"Missing required model features for prediction: {missing_features}")

    # Build exact dataframe schema
    input_row = {feature: input_data[feature] for feature in failure_features}
    df = pd.DataFrame([input_row])[failure_features]

    # Cast numeric features to float, categoricals to str
    for num_col in bundle.get("failure_numeric_features", []):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    for cat_col in bundle.get("failure_categorical_features", []):
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype(str)

    # Predict using the sklearn Pipeline directly
    probabilities = best_pipeline.predict_proba(df)[0]
    # Class 1 probability represents Crop Failure Risk
    global_risk = float(probabilities[1])

    # Calculate region and crop specialized models if available
    region_risk = None
    region = input_data.get("Region")
    if region and region in bundle.get("region_models", {}):
        reg_model = bundle["region_models"][region]
        region_risk = float(reg_model.predict_proba(df)[:, 1][0])

    crop_risk = None
    crop = input_data.get("Crop")
    if crop and crop in bundle.get("crop_models", {}):
        cr_model = bundle["crop_models"][crop]
        crop_risk = float(cr_model.predict_proba(df)[:, 1][0])

    # Consensus weighting matching generate_predictions.py
    scores = [(global_risk, 0.5)]
    weights = [0.5]
    if region_risk is not None:
        scores.append((region_risk, 0.25))
        weights.append(0.25)
    if crop_risk is not None:
        scores.append((crop_risk, 0.25))
        weights.append(0.25)

    consensus_risk = sum(val * wt for val, wt in scores) / sum(weights)
    risk_probability = round(consensus_risk, 4)
    level = risk_band(risk_probability)
    prediction = int(risk_probability >= 0.5)

    return {
        "risk_probability": risk_probability,
        "risk_level": level,
        "prediction": prediction,
        "best_model_name": best_model_name,
        "input_features": input_row,
        "global_risk": round(global_risk, 4),
        "region_risk": round(region_risk, 4) if region_risk is not None else None,
        "crop_risk": round(crop_risk, 4) if crop_risk is not None else None,
        "consensus_risk": risk_probability,
    }


def get_crop_recommendation(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
) -> Dict[str, Any]:
    """Generate crop recommendations from the saved recommendation model.

    Parameters
    ----------
    input_data : dict
        Dictionary of input features.
    bundle_path : str, optional
        Path to the model bundle file.

    Returns
    -------
    dict
        Dictionary containing recommended_crop, top_options, and status.
    """
    bundle = load_model_bundle(bundle_path)
    rec_model = bundle.get("crop_recommendation_model")
    rec_features = bundle.get("recommendation_features", [])

    if rec_model is None:
        return {
            "success": False,
            "recommended_crop": None,
            "top_options": [],
            "error": "Crop recommendation model not found in bundle.",
        }

    missing = [f for f in rec_features if f not in input_data or input_data[f] is None]
    if missing:
        return {
            "success": False,
            "recommended_crop": None,
            "top_options": [],
            "error": f"Missing required recommendation features: {missing}",
        }

    row = {feature: input_data[feature] for feature in rec_features}
    df = pd.DataFrame([row])[rec_features]

    for num_col in bundle.get("recommendation_numeric_features", []):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    for cat_col in bundle.get("recommendation_categorical_features", []):
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype(str)

    probs = rec_model.predict_proba(df)[0]
    classes = rec_model.classes_

    ranking = sorted(zip(classes, probs), key=lambda x: x[1], reverse=True)[:3]
    top_options = [
        {
            "crop": crop_name,
            "probability": round(float(prob), 4),
            "percentage": f"{prob * 100:.1f}%",
        }
        for crop_name, prob in ranking
    ]

    recommended = top_options[0]["crop"] if top_options else None
    summary_str = ", ".join(f"{item['crop']} ({item['percentage']})" for item in top_options)

    return {
        "success": True,
        "recommended_crop": recommended,
        "top_options": top_options,
        "summary": summary_str,
        "error": None,
    }


def get_prediction_explanation(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
    dataset_path: str = DEFAULT_DATASET_PATH,
    background_samples: int = 80,
) -> Dict[str, Any]:
    """Generate SHAP explanation for the single new input prediction.

    Handles model architectures dynamically:
    - LinearExplainer for LogisticRegression
    - TreeExplainer for tree models (RandomForest, ExtraTrees, GradientBoosting)
    - Fallback feature attribution if SHAP encounters an issue.
    """
    bundle = load_model_bundle(bundle_path)
    best_model_name = bundle["best_failure_model_name"]
    pipeline = bundle["failure_models"][best_model_name]
    failure_features = bundle["failure_features"]

    input_row = {feature: input_data[feature] for feature in failure_features}
    single_df = pd.DataFrame([input_row])[failure_features]

    # Load background data for baseline distribution
    bg_full = _load_baseline_data(dataset_path)
    bg_sample = bg_full[failure_features].sample(
        min(len(bg_full), background_samples), random_state=42
    )

    preprocessor = pipeline.named_steps["preprocessor"]
    estimator = pipeline.named_steps["model"]

    # Transform input and background sample
    row_trans = preprocessor.transform(single_df)
    bg_trans = preprocessor.transform(bg_sample)

    if hasattr(row_trans, "toarray"):
        row_trans = row_trans.toarray()
    if hasattr(bg_trans, "toarray"):
        bg_trans = bg_trans.toarray()

    feature_names = preprocessor.get_feature_names_out()

    shap_values_row = None
    explainer_type = "LinearExplainer"

    try:
        if hasattr(estimator, "coef_"):
            # LogisticRegression: LinearExplainer is mathematically appropriate
            explainer_type = "LinearExplainer"
            explainer = shap.LinearExplainer(estimator, bg_trans)
            shap_values = explainer.shap_values(row_trans)
            shap_values_row = shap_values[0] if getattr(shap_values, "ndim", 1) > 1 else shap_values
        elif hasattr(estimator, "feature_importances_"):
            # Tree-based model: TreeExplainer
            explainer_type = "TreeExplainer"
            explainer = shap.TreeExplainer(estimator)
            shap_values = explainer.shap_values(row_trans)
            if isinstance(shap_values, list):
                shap_values_row = shap_values[1][0]
            elif getattr(shap_values, "ndim", 0) == 3:
                shap_values_row = shap_values[0, :, 1]
            else:
                shap_values_row = shap_values[0]
        else:
            explainer_type = "Explainer"
            explainer = shap.Explainer(estimator, bg_trans)
            shap_values = explainer(row_trans)
            shap_values_row = shap_values.values[0]

    except Exception:
        # Fallback to exact linear contribution or tree importance
        if hasattr(estimator, "coef_"):
            explainer_type = "LinearAttribution (Fallback)"
            diff = row_trans[0] - bg_trans.mean(axis=0)
            shap_values_row = estimator.coef_[0] * diff
        elif hasattr(estimator, "feature_importances_"):
            explainer_type = "FeatureImportance (Fallback)"
            shap_values_row = estimator.feature_importances_
        else:
            shap_values_row = np.zeros(len(feature_names))

    # Clean up feature names for clean UI display
    def _clean_name(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        if "_" in name and any(name.startswith(p) for p in ["State_", "Region_", "Season_", "Crop_", "SoilType_", "IrrigationLevel_"]):
            prefix, val = name.split("_", 1)
            return f"{prefix}: {val}"
        return name

    items = []
    for raw_name, impact in zip(feature_names, shap_values_row):
        clean = _clean_name(raw_name)
        val_impact = float(impact)
        items.append({
            "feature": raw_name,
            "display_name": clean,
            "impact": round(val_impact, 4),
            "abs_impact": round(abs(val_impact), 4),
            "direction": "Increases Risk" if val_impact > 0 else "Decreases Risk",
        })

    # Sort by absolute impact descending
    items.sort(key=lambda x: x["abs_impact"], reverse=True)
    top_items = items[:8]

    # Generate explanatory summary text
    increasing = [i["display_name"] for i in top_items if i["direction"] == "Increases Risk"][:3]
    decreasing = [i["display_name"] for i in top_items if i["direction"] == "Decreases Risk"][:2]

    explanation_parts = []
    if increasing:
        explanation_parts.append(f"Risk is elevated primarily by: {', '.join(increasing)}.")
    if decreasing:
        explanation_parts.append(f"Risk is mitigated by: {', '.join(decreasing)}.")

    summary_text = " ".join(explanation_parts) if explanation_parts else "Features are balanced near regional average."

    return {
        "explainer_type": explainer_type,
        "top_features": top_items,
        "summary": summary_text,
    }
