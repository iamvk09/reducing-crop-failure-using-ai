"""Live crop failure risk prediction, recommendation, and SHAP explainability.

Memory-optimised design for 512 MB Render instances:
- Loads only the slim runtime bundle (best model + recommendation model) at startup.
- Region and crop specialized models are loaded on-demand and cached in-process.
- SHAP is imported lazily (only when explanation is requested) to save ~100 MB at startup.
- Preserves consistent risk bands: Low (<0.45), Medium (0.45-0.70), High (>=0.70).
- Provides full data provenance tracking.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

try:
    from src.recommendation_engine import risk_band
except ModuleNotFoundError:
    from recommendation_engine import risk_band


# Prefer the slim runtime bundle (best model only) to save ~180 MB RAM.
# Falls back to the full bundle if the slim bundle hasn't been generated yet.
_SLIM_BUNDLE_PATH = "models/agri_ai_runtime_bundle.pkl"
_FULL_BUNDLE_PATH = "models/agri_ai_bundle.pkl"
DEFAULT_BUNDLE_PATH = _SLIM_BUNDLE_PATH if Path(_SLIM_BUNDLE_PATH).exists() else _FULL_BUNDLE_PATH
DEFAULT_DATASET_PATH = "data/district_dataset.csv"
SPECIALIZED_DIR = Path("models/specialized")

# Module-level caches — populated once, never re-loaded on Streamlit reruns
_CACHED_BUNDLE: Optional[dict] = None
_CACHED_BASELINES: Optional[pd.DataFrame] = None
_SPECIALIZED_CACHE: Dict[str, Any] = {}      # {prefix_name: model} – populated on first access


# ---------------------------------------------------------------------------
# Lazy specialized model loading
# ---------------------------------------------------------------------------

class _LazyModelDict:
    """Dict-like container that loads specialized models on first access only.

    Keeps all 20 specialized models off-memory until a user's selected region/crop
    triggers a lookup.  Each loaded model is cached in ``_SPECIALIZED_CACHE``
    so subsequent accesses within the same Streamlit session are free.
    """

    def __init__(self, prefix: str, available_keys: List[str]):
        self._prefix = prefix
        self._available_keys = set(available_keys)

    def __contains__(self, key: str) -> bool:
        return key in self._available_keys

    def get(self, key: str, default=None):
        return self[key] if key in self else default

    def __getitem__(self, key: str):
        if key not in self._available_keys:
            raise KeyError(key)
        cache_key = f"{self._prefix}_{key}"
        if cache_key not in _SPECIALIZED_CACHE:
            safe = key.replace(" ", "_")
            path = SPECIALIZED_DIR / f"{self._prefix}_{safe}.pkl"
            if not path.exists():
                raise FileNotFoundError(
                    f"Specialized model not found: {path}.  "
                    "Re-run the training pipeline to regenerate specialized models."
                )
            _SPECIALIZED_CACHE[cache_key] = joblib.load(str(path))
        return _SPECIALIZED_CACHE[cache_key]


def _discover_specialized_keys(prefix: str) -> List[str]:
    """Discover available specialized model keys from the specialized/ directory."""
    if not SPECIALIZED_DIR.exists():
        return []
    keys = []
    for p in SPECIALIZED_DIR.glob(f"{prefix}_*.pkl"):
        stem = p.stem[len(prefix) + 1:]          # strip "region_" or "crop_"
        keys.append(stem.replace("_", " "))
    return keys


# ---------------------------------------------------------------------------
# Bundle loading
# ---------------------------------------------------------------------------

def load_model_bundle(bundle_path: str = DEFAULT_BUNDLE_PATH) -> dict:
    """Load the trained model bundle with in-process caching.

    The slim runtime bundle (``agri_ai_runtime_bundle.pkl``) is preferred when
    available.  Region and crop specialized models are injected as
    ``_LazyModelDict`` instances so they are loaded on-demand only.
    """
    global _CACHED_BUNDLE
    if _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE

    try:
        from src.memory_diagnostics import log_memory
    except ModuleNotFoundError:
        from memory_diagnostics import log_memory

    log_memory("Before bundle load")
    path = Path(bundle_path)
    if not path.exists():
        # Try full bundle as a last resort
        path = Path(_FULL_BUNDLE_PATH)
        if not path.exists():
            raise FileNotFoundError(f"Model bundle not found at: {path.resolve()}")

    bundle = joblib.load(str(path))
    log_memory("After bundle load", f"bundle={path.name}")

    required_keys = ["failure_models", "best_failure_model_name", "failure_features"]
    missing_keys = [k for k in required_keys if k not in bundle]
    if missing_keys:
        raise KeyError(f"Bundle missing required keys: {missing_keys}")

    # Inject lazy specialized model dictionaries if the specialized/ directory exists
    if "region_models" not in bundle or not bundle["region_models"]:
        region_keys = _discover_specialized_keys("region")
        bundle["region_models"] = _LazyModelDict("region", region_keys)
    if "crop_models" not in bundle or not bundle["crop_models"]:
        crop_keys = _discover_specialized_keys("crop")
        bundle["crop_models"] = _LazyModelDict("crop", crop_keys)

    _CACHED_BUNDLE = bundle
    return _CACHED_BUNDLE


# ---------------------------------------------------------------------------
# Baseline data loading (lightweight CSV – used only for feature defaults)
# ---------------------------------------------------------------------------

def _load_baseline_data(dataset_path: str = DEFAULT_DATASET_PATH) -> pd.DataFrame:
    """Load and cache the district baseline dataset for feature defaults."""
    global _CACHED_BASELINES
    if _CACHED_BASELINES is not None:
        return _CACHED_BASELINES

    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"District dataset not found at: {path.resolve()}")

    # Read only the columns needed for baseline lookup and SHAP background samples.
    # Year must be included because it is a failure model feature.
    needed_cols = [
        "Year", "District", "State", "Region", "Latitude", "Longitude",
        "Crop", "Season", "SoilType", "IrrigationLevel",
        "Rainfall", "Temperature", "Humidity", "SoilMoisture",
        "NDVI_Flowering", "WaterStress", "PestRisk", "SuitabilityScore", "YieldIndex",
    ]
    # Read only available columns so the function works even if the dataset
    # is an older version missing some columns.
    available_cols = pd.read_csv(str(path), nrows=0).columns.tolist()
    cols_to_read = [c for c in needed_cols if c in available_cols]
    df = pd.read_csv(str(path), usecols=cols_to_read)
    _CACHED_BASELINES = df
    return _CACHED_BASELINES


# ---------------------------------------------------------------------------
# District baseline & feature provenance
# ---------------------------------------------------------------------------

def get_district_baseline(
    district: str,
    crop: Optional[str] = None,
    dataset_path: str = DEFAULT_DATASET_PATH,
) -> Dict[str, Any]:
    """Return empirical baseline feature values and metadata for a district/crop pair."""
    df = _load_baseline_data(dataset_path)

    district_mask = df["District"].str.lower() == district.strip().lower()
    if not district_mask.any():
        district_df = df
        state = df["State"].mode()[0]
        region = df["Region"].mode()[0]
        latitude = float(df["Latitude"].median())
        longitude = float(df["Longitude"].median())
        soil_type = df["SoilType"].mode()[0]
        irrigation_level = df["IrrigationLevel"].mode()[0]
        district_name = district
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

    num_cols = ["Rainfall", "Temperature", "Humidity", "SoilMoisture",
                "NDVI_Flowering", "WaterStress", "PestRisk", "SuitabilityScore", "YieldIndex"]
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


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def predict_new_case(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
) -> Dict[str, Any]:
    """Predict crop failure risk using the saved sklearn pipeline directly."""
    bundle = load_model_bundle(bundle_path)
    best_model_name = bundle["best_failure_model_name"]
    best_pipeline = bundle["failure_models"][best_model_name]
    failure_features = bundle["failure_features"]

    missing_features = [f for f in failure_features if f not in input_data or input_data[f] is None]
    if missing_features:
        raise ValueError(f"Missing required model features: {missing_features}")

    input_row = {feature: input_data[feature] for feature in failure_features}
    df = pd.DataFrame([input_row])[failure_features]

    for num_col in bundle.get("failure_numeric_features", []):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    for cat_col in bundle.get("failure_categorical_features", []):
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype(str)

    global_risk = float(best_pipeline.predict_proba(df)[0][1])

    # Specialized models: loaded lazily, only when the model file exists on disk
    region_risk = None
    region = input_data.get("Region")
    if region and region in bundle.get("region_models", {}):
        try:
            reg_model = bundle["region_models"][region]
            region_risk = float(reg_model.predict_proba(df)[:, 1][0])
        except (FileNotFoundError, KeyError):
            region_risk = None

    crop_risk = None
    crop = input_data.get("Crop")
    if crop and crop in bundle.get("crop_models", {}):
        try:
            cr_model = bundle["crop_models"][crop]
            crop_risk = float(cr_model.predict_proba(df)[:, 1][0])
        except (FileNotFoundError, KeyError):
            crop_risk = None

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


# ---------------------------------------------------------------------------
# Crop recommendation
# ---------------------------------------------------------------------------

def get_crop_recommendation(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
) -> Dict[str, Any]:
    """Generate crop recommendations from the saved recommendation model."""
    bundle = load_model_bundle(bundle_path)
    rec_model = bundle.get("crop_recommendation_model")
    rec_features = bundle.get("recommendation_features", [])

    if rec_model is None:
        return {"success": False, "recommended_crop": None, "top_options": [],
                "error": "Crop recommendation model not found in bundle."}

    missing = [f for f in rec_features if f not in input_data or input_data[f] is None]
    if missing:
        return {"success": False, "recommended_crop": None, "top_options": [],
                "error": f"Missing recommendation features: {missing}"}

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
        {"crop": c, "probability": round(float(p), 4), "percentage": f"{p * 100:.1f}%"}
        for c, p in ranking
    ]
    summary_str = ", ".join(f"{item['crop']} ({item['percentage']})" for item in top_options)

    return {
        "success": True,
        "recommended_crop": top_options[0]["crop"] if top_options else None,
        "top_options": top_options,
        "summary": summary_str,
        "error": None,
    }


# ---------------------------------------------------------------------------
# SHAP explanation — import is deferred until this function is called
# ---------------------------------------------------------------------------

def get_prediction_explanation(
    input_data: Dict[str, Any],
    bundle_path: str = DEFAULT_BUNDLE_PATH,
    dataset_path: str = DEFAULT_DATASET_PATH,
    background_samples: int = 80,
) -> Dict[str, Any]:
    """Generate SHAP explanation for a single prediction.

    SHAP is imported lazily inside this function to avoid the ~100 MB overhead
    at application startup.  The import is free on subsequent calls because
    Python caches module objects in sys.modules.
    """
    # Lazy SHAP import — avoids the cost at startup
    import shap  # noqa: PLC0415  (intentional deferred import)

    try:
        from src.memory_diagnostics import log_memory
    except ModuleNotFoundError:
        from memory_diagnostics import log_memory

    log_memory("Before SHAP explanation")

    bundle = load_model_bundle(bundle_path)
    best_model_name = bundle["best_failure_model_name"]
    pipeline = bundle["failure_models"][best_model_name]
    failure_features = bundle["failure_features"]

    input_row = {feature: input_data[feature] for feature in failure_features}
    single_df = pd.DataFrame([input_row])[failure_features]

    bg_full = _load_baseline_data(dataset_path)
    bg_sample = bg_full[failure_features].sample(
        min(len(bg_full), background_samples), random_state=42
    )

    preprocessor = pipeline.named_steps["preprocessor"]
    estimator = pipeline.named_steps["model"]

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
            explainer_type = "LinearExplainer"
            explainer = shap.LinearExplainer(estimator, bg_trans)
            shap_vals = explainer.shap_values(row_trans)
            shap_values_row = shap_vals[0] if getattr(shap_vals, "ndim", 1) > 1 else shap_vals
        elif hasattr(estimator, "feature_importances_"):
            explainer_type = "TreeExplainer"
            explainer = shap.TreeExplainer(estimator)
            shap_vals = explainer.shap_values(row_trans)
            if isinstance(shap_vals, list):
                shap_values_row = shap_vals[1][0]
            elif getattr(shap_vals, "ndim", 0) == 3:
                shap_values_row = shap_vals[0, :, 1]
            else:
                shap_values_row = shap_vals[0]
        else:
            explainer_type = "Explainer"
            explainer = shap.Explainer(estimator, bg_trans)
            shap_vals = explainer(row_trans)
            shap_values_row = shap_vals.values[0]
    except Exception:
        if hasattr(estimator, "coef_"):
            explainer_type = "LinearAttribution (Fallback)"
            diff = row_trans[0] - bg_trans.mean(axis=0)
            shap_values_row = estimator.coef_[0] * diff
        elif hasattr(estimator, "feature_importances_"):
            explainer_type = "FeatureImportance (Fallback)"
            shap_values_row = estimator.feature_importances_
        else:
            shap_values_row = np.zeros(len(feature_names))

    log_memory("After SHAP explanation")

    def _clean_name(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        if "_" in name and any(
            name.startswith(p)
            for p in ["State_", "Region_", "Season_", "Crop_", "SoilType_", "IrrigationLevel_"]
        ):
            prefix, val = name.split("_", 1)
            return f"{prefix}: {val}"
        return name

    items = [
        {
            "feature": raw,
            "display_name": _clean_name(raw),
            "impact": round(float(impact), 4),
            "abs_impact": round(abs(float(impact)), 4),
            "direction": "Increases Risk" if float(impact) > 0 else "Decreases Risk",
        }
        for raw, impact in zip(feature_names, shap_values_row)
    ]
    items.sort(key=lambda x: x["abs_impact"], reverse=True)
    top_items = items[:8]

    increasing = [i["display_name"] for i in top_items if i["direction"] == "Increases Risk"][:3]
    decreasing = [i["display_name"] for i in top_items if i["direction"] == "Decreases Risk"][:2]

    parts = []
    if increasing:
        parts.append(f"Risk is elevated primarily by: {', '.join(increasing)}.")
    if decreasing:
        parts.append(f"Risk is mitigated by: {', '.join(decreasing)}.")

    return {
        "explainer_type": explainer_type,
        "top_features": top_items,
        "summary": " ".join(parts) if parts else "Features are balanced near regional average.",
    }
