import joblib
import numpy as np
import pandas as pd

try:
    from src.recommendation_engine import build_recommendation_summary, risk_band
except ModuleNotFoundError:
    from recommendation_engine import build_recommendation_summary, risk_band


MODEL_BUNDLE_PATH = "models/agri_ai_bundle.pkl"
DATA_PATH = "data/district_dataset.csv"
PREDICTIONS_PATH = "data/district_predictions.csv"
SUMMARY_PATH = "data/district_summary.csv"


def _weighted_consensus(row):
    scores = []
    weights = []
    for value, weight in [
        (row["GlobalRiskScore"], 0.5),
        (row["RegionRiskScore"], 0.25),
        (row["CropSpecificRiskScore"], 0.25),
    ]:
        if pd.notna(value):
            scores.append(value * weight)
            weights.append(weight)
    return sum(scores) / sum(weights) if weights else row["GlobalRiskScore"]


def _score_specialized_models(df, models, group_column, feature_columns, output_column):
    scores = pd.Series(np.nan, index=df.index, dtype="float")

    for group_value, model in models.items():
        mask = df[group_column] == group_value
        if not mask.any():
            continue
        scores.loc[mask] = model.predict_proba(df.loc[mask, feature_columns])[:, 1]

    df[output_column] = scores


def generate_predictions(
    data_path=DATA_PATH,
    bundle_path=MODEL_BUNDLE_PATH,
    predictions_path=PREDICTIONS_PATH,
    summary_path=SUMMARY_PATH,
):
    bundle = joblib.load(bundle_path)
    df = pd.read_csv(data_path)

    best_model_name = bundle["best_failure_model_name"]
    best_failure_model = bundle["failure_models"][best_model_name]

    failure_features = bundle["failure_features"]
    recommendation_features = bundle["recommendation_features"]

    df["GlobalRiskScore"] = best_failure_model.predict_proba(df[failure_features])[:, 1]
    df["BestFailureModel"] = best_model_name

    _score_specialized_models(
        df,
        bundle["region_models"],
        "Region",
        failure_features,
        "RegionRiskScore",
    )
    _score_specialized_models(
        df,
        bundle["crop_models"],
        "Crop",
        failure_features,
        "CropSpecificRiskScore",
    )
    df["ConsensusRisk"] = df.apply(_weighted_consensus, axis=1)
    df["Prediction"] = (df["ConsensusRisk"] >= 0.5).astype(int)
    df["RiskLevel"] = df["ConsensusRisk"].apply(risk_band)

    recommendation_model = bundle["crop_recommendation_model"]
    scenario_df = (
        df.sort_values("SuitabilityScore", ascending=False)
        .groupby(["District", "Year", "Season"], as_index=False)
        .first()
        .copy()
    )
    recommendation_probabilities = recommendation_model.predict_proba(
        scenario_df[recommendation_features]
    )
    recommendation_labels = recommendation_model.classes_
    top_crops = []

    for probability_row in recommendation_probabilities:
        ranking = sorted(
            zip(recommendation_labels, probability_row),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        top_crops.append(
            {
                "PredictedRecommendedCrop": ranking[0][0],
                "PredictedTopCropOptions": ", ".join(
                    f"{crop} ({score * 100:.1f}%)" for crop, score in ranking
                ),
            }
        )

    scenario_df = pd.concat([scenario_df.reset_index(drop=True), pd.DataFrame(top_crops)], axis=1)
    df = df.merge(
        scenario_df[
            [
                "District",
                "Year",
                "Season",
                "PredictedRecommendedCrop",
                "PredictedTopCropOptions",
            ]
        ],
        on=["District", "Year", "Season"],
        how="left",
    )
    df["RecommendedCrop"] = df["PredictedRecommendedCrop"]
    df["TopCropOptions"] = df["PredictedTopCropOptions"]
    df["RecommendationSummary"] = df.apply(build_recommendation_summary, axis=1)

    latest_year = int(df["Year"].max())
    district_summary = (
        df[df["Year"] == latest_year]
        .sort_values(["District", "ConsensusRisk"], ascending=[True, False])
        .groupby("District", as_index=False)
        .first()[
            [
                "District",
                "State",
                "Region",
                "Season",
                "Crop",
                "RecommendedCrop",
                "TopCropOptions",
                "Latitude",
                "Longitude",
                "ConsensusRisk",
                "RiskLevel",
                "RecommendationSummary",
            ]
        ]
        .rename(columns={"Crop": "CurrentCrop"})
    )

    df.to_csv(predictions_path, index=False)
    district_summary.to_csv(summary_path, index=False)

    print(f"Predictions saved to {predictions_path}")
    print(f"District summary saved to {summary_path}")


if __name__ == "__main__":
    generate_predictions()
