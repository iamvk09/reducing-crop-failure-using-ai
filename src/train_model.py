from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_PATH = "data/district_dataset.csv"
MODEL_BUNDLE_PATH = "models/agri_ai_bundle.pkl"
METRICS_PATH = "models/model_performance.csv"

FAILURE_NUMERIC_FEATURES = [
    "Year",
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
FAILURE_CATEGORICAL_FEATURES = [
    "State",
    "Region",
    "Season",
    "Crop",
    "SoilType",
    "IrrigationLevel",
]
FAILURE_FEATURES = FAILURE_NUMERIC_FEATURES + FAILURE_CATEGORICAL_FEATURES

RECOMMENDATION_NUMERIC_FEATURES = [
    "Year",
    "Rainfall",
    "Temperature",
    "Humidity",
    "SoilMoisture",
]
RECOMMENDATION_CATEGORICAL_FEATURES = [
    "District",
    "State",
    "Region",
    "Season",
    "SoilType",
    "IrrigationLevel",
]
RECOMMENDATION_FEATURES = RECOMMENDATION_NUMERIC_FEATURES + RECOMMENDATION_CATEGORICAL_FEATURES


def _build_preprocessor(numeric_features, categorical_features):
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_features),
            ("cat", categorical_pipeline, categorical_features),
        ]
    )


def _build_failure_models():
    return {
        "logistic_regression": LogisticRegression(max_iter=1500, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=320,
            max_depth=14,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=320,
            max_depth=14,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
        ),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
    }


def _fit_pipeline(model, numeric_features, categorical_features, X_train, y_train):
    pipeline = Pipeline(
        steps=[
            ("preprocessor", _build_preprocessor(numeric_features, categorical_features)),
            ("model", model),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


def _evaluate_pipeline(name, pipeline, X_test, y_test):
    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "model_name": name,
        "roc_auc": roc_auc_score(y_test, probabilities),
        "f1_score": f1_score(y_test, predictions),
    }


def _train_specialized_models(df):
    region_models = {}
    crop_models = {}

    for region, region_df in df.groupby("Region"):
        if region_df["Failure"].nunique() < 2 or len(region_df) < 50:
            continue
        region_models[region] = _fit_pipeline(
            RandomForestClassifier(
                n_estimators=220,
                max_depth=10,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
            ),
            FAILURE_NUMERIC_FEATURES,
            [feature for feature in FAILURE_CATEGORICAL_FEATURES if feature != "Region"],
            region_df[FAILURE_FEATURES],
            region_df["Failure"],
        )

    for crop, crop_df in df.groupby("Crop"):
        if crop_df["Failure"].nunique() < 2 or len(crop_df) < 40:
            continue
        crop_models[crop] = _fit_pipeline(
            RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
            ),
            [feature for feature in FAILURE_NUMERIC_FEATURES if feature != "SuitabilityScore"],
            [feature for feature in FAILURE_CATEGORICAL_FEATURES if feature != "Crop"],
            crop_df[FAILURE_FEATURES],
            crop_df["Failure"],
        )

    return region_models, crop_models


def _build_recommendation_dataset(df):
    recommendation_df = (
        df.sort_values("SuitabilityScore", ascending=False)
        .groupby(["District", "Year", "Season"], as_index=False)
        .first()
        .copy()
    )
    recommendation_df["TargetCrop"] = recommendation_df["RecommendedCrop"]
    return recommendation_df


def train(data_path=DATA_PATH, bundle_path=MODEL_BUNDLE_PATH):
    df = pd.read_csv(data_path)

    X = df[FAILURE_FEATURES]
    y = df["Failure"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.22,
        random_state=42,
        stratify=y,
    )

    failure_models = {}
    metrics = []

    for model_name, estimator in _build_failure_models().items():
        pipeline = _fit_pipeline(
            estimator,
            FAILURE_NUMERIC_FEATURES,
            FAILURE_CATEGORICAL_FEATURES,
            X_train,
            y_train,
        )
        failure_models[model_name] = pipeline
        metrics.append(_evaluate_pipeline(model_name, pipeline, X_test, y_test))

    metrics_df = pd.DataFrame(metrics).sort_values(
        ["roc_auc", "f1_score"], ascending=False
    )
    best_failure_model_name = metrics_df.iloc[0]["model_name"]
    best_failure_model = failure_models[best_failure_model_name]

    best_predictions = best_failure_model.predict(X_test)
    print("Best failure model:", best_failure_model_name)
    print(metrics_df.to_string(index=False))
    print("\nClassification report for best model:\n")
    print(classification_report(y_test, best_predictions))

    recommendation_df = _build_recommendation_dataset(df)
    recommendation_X = recommendation_df[RECOMMENDATION_FEATURES]
    recommendation_y = recommendation_df["TargetCrop"]
    recommendation_model = _fit_pipeline(
        RandomForestClassifier(
            n_estimators=260,
            max_depth=12,
            min_samples_leaf=2,
            random_state=42,
        ),
        RECOMMENDATION_NUMERIC_FEATURES,
        RECOMMENDATION_CATEGORICAL_FEATURES,
        recommendation_X,
        recommendation_y,
    )

    region_models, crop_models = _train_specialized_models(df)

    bundle = {
        "failure_models": failure_models,
        "best_failure_model_name": best_failure_model_name,
        "crop_recommendation_model": recommendation_model,
        "region_models": region_models,
        "crop_models": crop_models,
        "failure_features": FAILURE_FEATURES,
        "failure_numeric_features": FAILURE_NUMERIC_FEATURES,
        "failure_categorical_features": FAILURE_CATEGORICAL_FEATURES,
        "recommendation_features": RECOMMENDATION_FEATURES,
        "recommendation_numeric_features": RECOMMENDATION_NUMERIC_FEATURES,
        "recommendation_categorical_features": RECOMMENDATION_CATEGORICAL_FEATURES,
        "metrics": metrics_df.to_dict(orient="records"),
    }

    Path(bundle_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, bundle_path)
    metrics_df.to_csv(METRICS_PATH, index=False)

    print(f"\nModel bundle saved to {bundle_path}")
    print(f"Metrics saved to {METRICS_PATH}")


if __name__ == "__main__":
    train()
