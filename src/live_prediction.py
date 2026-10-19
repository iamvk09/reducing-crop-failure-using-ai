"""Live crop failure risk prediction, recommendation, and SHAP explainability.

Memory-optimised design for 512 MB Render instances:
- Loads only the slim runtime bundle (best model + recommendation model) at startup.
- Region and crop specialized models are loaded on-demand and cached in-process.
- SHAP is imported lazily (only when explanation is requested) to save ~100 MB at startup.
- Preserves consistent risk bands: Low (<0.45), Medium (0.45-0.70), High (>=0.70).
- Provides full data provenance tracking and strict input validation.
"""

from datetime import datetime
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

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

import threading

# Module-level caches — populated once, never re-loaded on Streamlit reruns
_CACHED_BUNDLE: Optional[dict] = None
_CACHED_BASELINES: Optional[pd.DataFrame] = None
_SPECIALIZED_CACHE: Dict[str, Any] = {}      # {prefix_name: model} – populated on first access
_CACHED_EXPLAINER: Optional[Any] = None      # Fitted SHAP explainer instance reused across requests
_CACHED_EXPLAINER_MODEL_NAME: Optional[str] = None
_MODEL_INIT_LOCK = threading.Lock()          # Prevents duplicate unpickling under concurrent cold requests



# ---------------------------------------------------------------------------
# Strict Schema & Validation Metadata
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "State": [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand",
        "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra", "Manipur",
        "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan",
        "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"
    ],
    "Region": [
        "Central Plateau", "Coastal Delta", "Deccan Plateau", "Himalayan Foothills",
        "Humid East", "Indo Gangetic Plains", "Northwest Dryland", "Northwest Irrigated",
        "Semi Arid West", "Southern Plateau", "Western Plateau"
    ],
    "Season": ["Kharif", "Rabi", "Zaid"],
    "Crop": ["Chickpea", "Cotton", "Groundnut", "Maize", "Millet", "Mustard", "Rice", "Soybean", "Wheat"],
    "SoilType": [
        "Alluvial", "Black", "Clay Loam", "Laterite", "Loam", "Loamy Sand",
        "Medium Black", "Red Loam", "Red Sandy Loam", "Sandy", "Sandy Loam"
    ],
    "IrrigationLevel": ["High", "Low", "Medium"],
}

# Defensible, agronomically sound aliases for categorical SoilType
# Strict mapping rules:
# - "Clayey" / "Clay" / "Heavy Clay" -> "Clay Loam" (the trained model's fine-textured clay taxonomy)
# - "Loamy" -> "Loam"
# - Ambiguous terms (e.g. "Silt", "Peat", "Chalky") are NOT silently mapped and must fail with clear guidance.
SOIL_TYPE_ALIASES: Dict[str, str] = {
    "clayey": "Clay Loam",
    "clay": "Clay Loam",
    "clayey soil": "Clay Loam",
    "heavy clay": "Clay Loam",
    "loamy": "Loam",
    "loamy soil": "Loam",
    "alluvial soil": "Alluvial",
    "black soil": "Black",
    "laterite soil": "Laterite",
    "sandy soil": "Sandy",
}

# Defensible, standard aliases / abbreviations for categorical State
STATE_NAME_ALIASES: Dict[str, str] = {
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "jammu & kashmir": "Jammu and Kashmir",
    "j&k": "Jammu and Kashmir",
    "up": "Uttar Pradesh",
    "mp": "Madhya Pradesh",
    "ap": "Andhra Pradesh",
    "wb": "West Bengal",
    "tn": "Tamil Nadu",
    "hp": "Himachal Pradesh",
}


def normalize_state(state: Optional[str]) -> Optional[str]:
    """Normalize user/farm state string into model's valid taxonomy.

    Returns the canonical categorical value if matched case-insensitively or via known alias,
    or the trimmed original string. Does NOT silently map unknown or ambiguous states to an arbitrary default.
    """
    if not state or not isinstance(state, str):
        return state

    cleaned = state.strip()
    # Check exact case-insensitive match against VALID_CATEGORIES["State"]
    for valid in VALID_CATEGORIES["State"]:
        if cleaned.lower() == valid.lower():
            return valid

    # Check known aliases/abbreviations
    alias_match = STATE_NAME_ALIASES.get(cleaned.lower())
    if alias_match:
        return alias_match

    return cleaned


def normalize_soil_type(soil: Optional[str]) -> Optional[str]:
    """Normalize user/farm soil type string into model's valid taxonomy.

    Returns the canonical categorical value if matched or aliased, or the trimmed original string.
    Does NOT silently substitute ambiguous or unknown values.
    """
    if not soil or not isinstance(soil, str):
        return soil

    cleaned = soil.strip()
    # Check exact case-insensitive match against VALID_CATEGORIES["SoilType"]
    for valid in VALID_CATEGORIES["SoilType"]:
        if cleaned.lower() == valid.lower():
            return valid

    # Check defensible aliases
    alias_match = SOIL_TYPE_ALIASES.get(cleaned.lower())
    if alias_match:
        return alias_match

    return cleaned


NUMERIC_BOUNDS = {
    "Year": (1990, 2100),
    "Rainfall": (0.0, 1500.0),
    "Temperature": (-15.0, 60.0),
    "Humidity": (0.0, 100.0),
    "SoilMoisture": (0.0, 100.0),
    "NDVI_Flowering": (0.0, 1.0),
    "WaterStress": (0.0, 1.0),
    "PestRisk": (0.0, 1.0),
    "SuitabilityScore": (0.0, 1.0),
    "YieldIndex": (0.0, 250.0),
}


def validate_prediction_input(
    input_data: Dict[str, Any],
    bundle: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate input feature dictionary against model schema and agronomic bounds.

    Returns
    -------
    Tuple[bool, Optional[str]]
        (True, None) if completely valid, or (False, error_description) if invalid.
    """
    if not isinstance(input_data, dict):
        return False, "Input data must be a dictionary."

    required_features = (
        bundle.get("failure_features") if bundle else list(NUMERIC_BOUNDS.keys()) + list(VALID_CATEGORIES.keys())
    )

    # 1. Check for missing or null entries
    missing = [f for f in required_features if f not in input_data or input_data[f] is None]
    if missing:
        return False, f"Missing required input features: {missing}"

    # 2. Categorical validation
    for cat_col, valid_vals in VALID_CATEGORIES.items():
        if cat_col in required_features:
            val = input_data.get(cat_col)
            if not isinstance(val, str) or not val.strip():
                return False, f"Categorical feature '{cat_col}' must be a non-empty string."

            # Apply state normalization if applicable
            if cat_col == "State":
                norm_state = normalize_state(val)
                if norm_state in valid_vals:
                    val = norm_state
                    input_data[cat_col] = norm_state

            # Apply soil type normalization if applicable
            if cat_col == "SoilType":
                norm_soil = normalize_soil_type(val)
                if norm_soil in valid_vals:
                    val = norm_soil
                    input_data[cat_col] = norm_soil

            if val not in valid_vals:
                return (
                    False,
                    f"Invalid value '{val}' for categorical feature '{cat_col}'. Expected one of: {valid_vals}",
                )

    # 3. Numeric validation
    for num_col, (min_v, max_v) in NUMERIC_BOUNDS.items():
        if num_col in required_features:
            val = input_data.get(num_col)
            try:
                f_val = float(val)
            except (ValueError, TypeError):
                return False, f"Numeric feature '{num_col}' must be a valid real number, got: {val}"

            if math.isnan(f_val) or math.isinf(f_val):
                return False, f"Numeric feature '{num_col}' cannot be NaN or Infinite."

            if not (min_v <= f_val <= max_v):
                return (
                    False,
                    f"Feature '{num_col}' value {f_val} is outside plausible agronomic range [{min_v}, {max_v}].",
                )

    return True, None


# ---------------------------------------------------------------------------
# Lazy specialized model loading
# ---------------------------------------------------------------------------

def _patch_imputer_attributes(estimator: Any, seen: Optional[set] = None) -> None:
    """Ensure SimpleImputer instances have _fill_dtype and _fit_dtype for forward compatibility across scikit-learn versions.

    Recursively traverses Pipelines, ColumnTransformers, and ensemble estimators while guarding
    against cyclic object references and safely ignoring passthrough/drop transformers.
    """
    if estimator is None or isinstance(estimator, str):
        return

    if seen is None:
        seen = set()

    obj_id = id(estimator)
    if obj_id in seen:
        return
    seen.add(obj_id)

    # 1. Pipeline traversal (steps or named_steps)
    if hasattr(estimator, "steps") and isinstance(estimator.steps, (list, tuple)):
        for step_tuple in estimator.steps:
            if isinstance(step_tuple, (list, tuple)) and len(step_tuple) >= 2:
                _patch_imputer_attributes(step_tuple[1], seen)
    elif hasattr(estimator, "named_steps") and isinstance(estimator.named_steps, dict):
        for step in estimator.named_steps.values():
            _patch_imputer_attributes(step, seen)

    # 2. ColumnTransformer traversal (transformers_ and transformers)
    if hasattr(estimator, "transformers_") and isinstance(estimator.transformers_, (list, tuple)):
        for item in estimator.transformers_:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                _patch_imputer_attributes(item[1], seen)
    if hasattr(estimator, "transformers") and isinstance(estimator.transformers, (list, tuple)):
        for item in estimator.transformers:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                _patch_imputer_attributes(item[1], seen)
    if hasattr(estimator, "named_transformers_") and isinstance(estimator.named_transformers_, dict):
        for trans in estimator.named_transformers_.values():
            _patch_imputer_attributes(trans, seen)

    # 3. Meta-estimators (CalibratedClassifierCV, VotingClassifier, etc.)
    if hasattr(estimator, "calibrated_classifiers_") and isinstance(estimator.calibrated_classifiers_, (list, tuple)):
        for cc in estimator.calibrated_classifiers_:
            base = getattr(cc, "base_estimator", None) or getattr(cc, "estimator", None)
            if base is not None:
                _patch_imputer_attributes(base, seen)
    if hasattr(estimator, "estimators_") and isinstance(estimator.estimators_, (list, tuple)):
        for sub_est in estimator.estimators_:
            _patch_imputer_attributes(sub_est, seen)

    # 4. Target SimpleImputer instance patching
    if estimator.__class__.__name__ == "SimpleImputer":
        # Resolve fitted dtype strictly from fitted attributes if available
        fit_dtype = getattr(estimator, "_fit_dtype", None)
        stat = getattr(estimator, "statistics_", None)
        stat_dtype = getattr(stat, "dtype", None) if stat is not None else None

        resolved_dtype = None
        if fit_dtype is not None:
            resolved_dtype = fit_dtype
        elif stat_dtype is not None:
            # If fitted on strings/categories, scikit-learn uses object or unicode array
            resolved_dtype = stat_dtype if stat_dtype != np.dtype("O") else object

        # Set _fill_dtype only when a valid fitted dtype can be determined and attribute is missing
        if resolved_dtype is not None:
            if not hasattr(estimator, "_fill_dtype"):
                estimator._fill_dtype = resolved_dtype
            if not hasattr(estimator, "_fit_dtype"):
                estimator._fit_dtype = resolved_dtype


class _LazyModelDict:
    """Dict-like container that loads specialized models on first access only.

    Keeps all 20 specialized models off-memory until a user's selected region/crop
    triggers a lookup. Each loaded model is cached in ``_SPECIALIZED_CACHE``
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
                    f"Specialized model not found: {path}. "
                    "Re-run the training pipeline to regenerate specialized models."
                )
            loaded_model = joblib.load(str(path))
            _patch_imputer_attributes(loaded_model)
            _SPECIALIZED_CACHE[cache_key] = loaded_model
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
    available. Region and crop specialized models are injected as
    ``_LazyModelDict`` instances so they are loaded on-demand only.
    """
    global _CACHED_BUNDLE
    if _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE

    with _MODEL_INIT_LOCK:
        if _CACHED_BUNDLE is not None:
            return _CACHED_BUNDLE

        try:
            from src.memory_diagnostics import log_memory
        except ModuleNotFoundError:
            from memory_diagnostics import log_memory

        log_memory("Before bundle load")
        path = Path(bundle_path)
        if not path.exists():
            path = Path(_FULL_BUNDLE_PATH)
            if not path.exists():
                raise FileNotFoundError(f"Model bundle not found at: {path.resolve()}")

        bundle = joblib.load(str(path))
        log_memory("After bundle load", f"bundle={path.name}")

        required_keys = ["failure_models", "best_failure_model_name", "failure_features"]
        missing_keys = [k for k in required_keys if k not in bundle]
        if missing_keys:
            raise KeyError(f"Bundle missing required keys: {missing_keys}")

        # Inject lazy specialized model dictionaries if specialized/ directory exists
        if "region_models" not in bundle or not bundle["region_models"]:
            region_keys = _discover_specialized_keys("region")
            bundle["region_models"] = _LazyModelDict("region", region_keys)
        if "crop_models" not in bundle or not bundle["crop_models"]:
            crop_keys = _discover_specialized_keys("crop")
            bundle["crop_models"] = _LazyModelDict("crop", crop_keys)

        # Ensure all models in bundle have _fill_dtype attribute for imputer compatibility
        for m in bundle.get("failure_models", {}).values():
            _patch_imputer_attributes(m)
        _patch_imputer_attributes(bundle.get("crop_recommendation_model"))

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

    with _MODEL_INIT_LOCK:
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
    season: Optional[str] = None,
    dataset_path: str = DEFAULT_DATASET_PATH,
) -> Dict[str, Any]:
    """Return empirical baseline feature values and metadata for a district/crop/season profile.

    Parameters
    ----------
    district : str
        Target district name.
    crop : str, optional
        Target crop name. If omitted or not found, defaults to first crop for district.
    season : str, optional
        Target season ('Kharif', 'Rabi', 'Zaid'). If omitted, defaults to prevailing season.
    dataset_path : str, optional
        Path to district baseline CSV.

    Returns
    -------
    dict
        Empirical baselines, metadata, available crops/seasons, and provenance dictionary.
    """
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
        soil_type = district_df["SoilType"].mode()[0] if "SoilType" in district_df else first_row["SoilType"]
        irrigation_level = (
            district_df["IrrigationLevel"].mode()[0]
            if "IrrigationLevel" in district_df
            else first_row["IrrigationLevel"]
        )

    available_crops = sorted(district_df["Crop"].dropna().unique().tolist())
    target_crop = crop if (crop and crop in available_crops) else (available_crops[0] if available_crops else "Rice")

    crop_df = district_df[district_df["Crop"] == target_crop]
    if crop_df.empty:
        crop_df = district_df

    available_seasons = sorted(crop_df["Season"].dropna().unique().tolist())
    if not available_seasons:
        available_seasons = ["Kharif", "Rabi", "Zaid"]

    if season and season in available_seasons:
        target_season = season
        season_df = crop_df[crop_df["Season"] == target_season]
        if season_df.empty:
            season_df = crop_df
    else:
        target_season = crop_df["Season"].mode()[0] if "Season" in crop_df else "Kharif"
        season_df = crop_df

    if "SoilType" in season_df and not season_df["SoilType"].empty:
        soil_type = season_df["SoilType"].mode()[0]
    if "IrrigationLevel" in season_df and not season_df["IrrigationLevel"].empty:
        irrigation_level = season_df["IrrigationLevel"].mode()[0]

    num_cols = [
        "Rainfall", "Temperature", "Humidity", "SoilMoisture",
        "NDVI_Flowering", "WaterStress", "PestRisk", "SuitabilityScore", "YieldIndex"
    ]
    medians = {col: round(float(season_df[col].median()), 3) for col in num_cols if col in season_df}

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
        "Season": target_season,
        "Crop": target_crop,
        "SoilType": soil_type,
        "IrrigationLevel": irrigation_level,
    }

    feature_sources = {
        "State": "User selection / Historical district mapping",
        "Region": "Historical district mapping",
        "Season": "User selection / District-crop baseline",
        "Crop": "User selection",
        "SoilType": "User selection (District empirical baseline)",
        "IrrigationLevel": "User selection (District empirical baseline)",
        "Year": "Current calendar year",
        "Temperature": "Live weather estimate (Open-Meteo)",
        "Humidity": "Live weather estimate (Open-Meteo)",
        "Rainfall": "Historical seasonal baseline (District-Crop-Season median)",
        "SoilMoisture": "Live weather estimate (Open-Meteo root-zone moisture)",
        "NDVI_Flowering": "Historical baseline (District-Crop-Season median)",
        "WaterStress": "Historical baseline (District-Crop-Season median)",
        "PestRisk": "Historical baseline (District-Crop-Season median)",
        "SuitabilityScore": "Historical baseline (District-Crop median)",
        "YieldIndex": "Historical baseline (District-Crop median)",
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
        "available_seasons": available_seasons,
        "selected_season": target_season,
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
    """Predict crop failure risk using the saved sklearn pipeline directly.

    Validates that:
    - All required features are present and non-null.
    - Categorical variables match known model encodings.
    - Numeric variables lie in realistic physiological bounds.
    - No silent zero-substitution occurs.
    """
    bundle = load_model_bundle(bundle_path)
    best_model_name = bundle["best_failure_model_name"]
    best_pipeline = bundle["failure_models"][best_model_name]
    failure_features = bundle["failure_features"]

    # Strict validation before invoking model
    is_valid, err_msg = validate_prediction_input(input_data, bundle)
    if not is_valid:
        raise ValueError(f"Input validation error: {err_msg}")

    input_row = {feature: input_data[feature] for feature in failure_features}
    df = pd.DataFrame([input_row])[failure_features]

    for num_col in bundle.get("failure_numeric_features", []):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    for cat_col in bundle.get("failure_categorical_features", []):
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype(str)

    # Direct predict_proba on the scikit-learn Pipeline
    probabilities = best_pipeline.predict_proba(df)[0]
    global_risk = float(probabilities[1])

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
    at application startup. The import is free on subsequent calls because
    Python caches module objects in sys.modules.
    """
    shap_module = None
    try:
        import shap as shap_module  # noqa: PLC0415 (intentional deferred import)
    except (ImportError, ModuleNotFoundError) as err:
        logger.warning("SHAP library unavailable for explanation: %s. Using transparent model attribution fallback.", type(err).__name__)

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

    # Explainer caching: reuse fitted explainer instance to avoid recomputing background statistics
    global _CACHED_EXPLAINER, _CACHED_EXPLAINER_MODEL_NAME
    feature_names = preprocessor.get_feature_names_out()
    shap_values_row = None
    explainer_type = "LinearExplainer"

    expected_value = 0.0
    try:
        if shap_module is None:
            raise RuntimeError("SHAP module is not installed or available.")

        if _CACHED_EXPLAINER is not None and _CACHED_EXPLAINER_MODEL_NAME == best_model_name:
            explainer = _CACHED_EXPLAINER
            explainer_type = getattr(explainer, "__class__", type(explainer)).__name__
            shap_vals = explainer.shap_values(row_trans)
            if isinstance(shap_vals, list):
                shap_values_row = shap_vals[1][0] if len(shap_vals) > 1 else shap_vals[0]
            elif getattr(shap_vals, "ndim", 1) > 1:
                shap_values_row = shap_vals[0]
            else:
                shap_values_row = shap_vals
            if hasattr(explainer, "expected_value"):
                expected_value = explainer.expected_value
        elif hasattr(estimator, "coef_"):
            explainer_type = "LinearExplainer"
            explainer = shap_module.LinearExplainer(estimator, bg_trans)
            _CACHED_EXPLAINER = explainer
            _CACHED_EXPLAINER_MODEL_NAME = best_model_name
            shap_vals = explainer.shap_values(row_trans)
            shap_values_row = shap_vals[0] if getattr(shap_vals, "ndim", 1) > 1 else shap_vals
            if hasattr(explainer, "expected_value"):
                expected_value = explainer.expected_value
        elif hasattr(estimator, "feature_importances_"):
            explainer_type = "TreeExplainer"
            explainer = shap_module.TreeExplainer(estimator)
            _CACHED_EXPLAINER = explainer
            _CACHED_EXPLAINER_MODEL_NAME = best_model_name
            shap_vals = explainer.shap_values(row_trans)
            if isinstance(shap_vals, list):
                shap_values_row = shap_vals[1][0]
            elif getattr(shap_vals, "ndim", 0) == 3:
                shap_values_row = shap_vals[0, :, 1]
            else:
                shap_values_row = shap_vals[0]
            if hasattr(explainer, "expected_value"):
                expected_value = explainer.expected_value
        else:
            explainer_type = "Explainer"
            explainer = shap_module.Explainer(estimator, bg_trans)
            shap_vals = explainer(row_trans)
            shap_values_row = shap_vals.values[0]
            if hasattr(explainer, "expected_value"):
                expected_value = explainer.expected_value
    except Exception as exc:
        logger.info("Using analytical attribution fallback for explanation: %s", type(exc).__name__)
        if hasattr(estimator, "coef_"):
            explainer_type = "LinearAttribution (Fallback)"
            diff = row_trans[0] - bg_trans.mean(axis=0)
            shap_values_row = estimator.coef_[0] * diff
            if hasattr(estimator, "intercept_"):
                expected_value = float(estimator.intercept_[0])
        elif hasattr(estimator, "feature_importances_"):
            explainer_type = "FeatureImportance (Fallback)"
            shap_values_row = estimator.feature_importances_
        else:
            explainer_type = "Baseline (Fallback)"
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

    # Map transformed contributions back to the 16 original failure features
    aggregated_attributions = {feat: 0.0 for feat in failure_features}
    for raw, impact in zip(feature_names, shap_values_row):
        if raw.startswith("num__"):
            base_feat = raw.replace("num__", "")
        elif raw.startswith("cat__"):
            base_feat = raw.split("__")[1].split("_")[0]
        else:
            base_feat = raw
        if base_feat in aggregated_attributions:
            aggregated_attributions[base_feat] += float(impact)
        else:
            aggregated_attributions[base_feat] = float(impact)

    # Round aggregated attributions for numerical precision
    aggregated_attributions = {k: round(v, 4) for k, v in aggregated_attributions.items()}

    exp_val_float = float(expected_value[0]) if isinstance(expected_value, (list, np.ndarray)) else float(expected_value)
    total_shap_val = float(np.sum(shap_values_row)) if shap_values_row is not None else 0.0

    increasing = [i["display_name"] for i in top_items if i["direction"] == "Increases Risk"][:3]
    decreasing = [i["display_name"] for i in top_items if i["direction"] == "Decreases Risk"][:2]

    parts = []
    if increasing:
        parts.append(f"Risk is elevated primarily by: {', '.join(increasing)}.")
    if decreasing:
        parts.append(f"Risk is mitigated by: {', '.join(decreasing)}.")

    return {
        "explainer_type": explainer_type,
        "output_space": "log_odds",
        "base_value": round(exp_val_float, 4),
        "sum_shap": round(total_shap_val, 4),
        "margin_value": round(exp_val_float + total_shap_val, 4),
        "top_features": top_items,
        "feature_attributions": aggregated_attributions,
        "summary": " ".join(parts) if parts else "Features are balanced near regional average.",
    }
