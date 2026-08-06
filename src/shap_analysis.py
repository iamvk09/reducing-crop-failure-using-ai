from pathlib import Path

import joblib
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import shap


matplotlib.use("Agg")


MODEL_BUNDLE_PATH = "models/agri_ai_bundle.pkl"
DATA_PATH = "data/district_dataset.csv"
SHAP_IMAGE_PATH = "models/shap_summary.png"
FEATURE_IMPORTANCE_PATH = "models/feature_importance.csv"


def explain(
    bundle_path=MODEL_BUNDLE_PATH,
    data_path=DATA_PATH,
    image_path=SHAP_IMAGE_PATH,
    feature_importance_path=FEATURE_IMPORTANCE_PATH,
):
    bundle = joblib.load(bundle_path)
    df = pd.read_csv(data_path)

    best_model_name = bundle["best_failure_model_name"]
    pipeline = bundle["failure_models"][best_model_name]
    features = bundle["failure_features"]

    sample = df[features].sample(min(len(df), 250), random_state=42)
    preprocessor = pipeline.named_steps["preprocessor"]
    estimator = pipeline.named_steps["model"]
    transformed = preprocessor.transform(sample)
    feature_names = preprocessor.get_feature_names_out()

    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()

    Path(image_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        explainer = shap.TreeExplainer(estimator)
        shap_values = explainer.shap_values(transformed)
        positive_class_values = shap_values[1] if isinstance(shap_values, list) else shap_values

        plt.figure()
        shap.summary_plot(
            positive_class_values,
            transformed,
            feature_names=feature_names,
            show=False,
            max_display=12,
        )
        plt.tight_layout()
        plt.savefig(image_path, dpi=220, bbox_inches="tight")
        plt.close()

        importances = pd.DataFrame(
            {
                "Feature": feature_names,
                "Importance": abs(positive_class_values).mean(axis=0),
            }
        ).sort_values("Importance", ascending=False)
    except Exception:
        if not hasattr(estimator, "feature_importances_"):
            raise
        importances = pd.DataFrame(
            {"Feature": feature_names, "Importance": estimator.feature_importances_}
        ).sort_values("Importance", ascending=False)

        plt.figure(figsize=(10, 6))
        plt.barh(
            importances["Feature"].head(12)[::-1],
            importances["Importance"].head(12)[::-1],
            color="#2f855a",
        )
        plt.xlabel("Importance")
        plt.ylabel("Feature")
        plt.title(f"Top Features for {best_model_name}")
        plt.tight_layout()
        plt.savefig(image_path, dpi=220, bbox_inches="tight")
        plt.close()

    importances.to_csv(feature_importance_path, index=False)
    print(f"Explainability chart saved to {image_path}")
    print(f"Feature importance saved to {feature_importance_path}")


if __name__ == "__main__":
    explain()
