import pandas as pd

from src.create_map import create_map
from src.data_generator import generate_dataset
from src.digital_twin import run_digital_twin
from src.generate_predictions import generate_predictions
from src.shap_analysis import explain
from src.train_model import train


def run_pipeline():
    generate_dataset()
    train()
    generate_predictions()
    explain()
    create_map()
    print("Pipeline completed successfully.")


def search_district():
    df = pd.read_csv("data/district_summary.csv")
    district = input("Enter District Name: ").strip()

    if district not in df["District"].values:
        print("District not found.")
        return

    result = df[df["District"] == district].iloc[0]
    print("\nDistrict:", result["District"])
    print("State:", result["State"])
    print("Region:", result["Region"])
    print("Current Crop:", result["CurrentCrop"])
    print("Recommended Crop:", result["RecommendedCrop"])
    print("Risk Level:", result["RiskLevel"])
    print("Consensus Risk:", round(result["ConsensusRisk"] * 100, 2), "%")
    print("Advice:", result["RecommendationSummary"])


def simulate_district():
    predictions = pd.read_csv("data/district_predictions.csv")
    district = input("Enter District Name for digital twin simulation: ").strip()

    if district not in predictions["District"].values:
        print("District not found.")
        return

    candidate = (
        predictions[predictions["District"] == district]
        .sort_values("ConsensusRisk", ascending=False)
        .iloc[0]
    )
    from joblib import load

    bundle = load("models/agri_ai_bundle.pkl")
    model = bundle["failure_models"][bundle["best_failure_model_name"]]
    results = run_digital_twin(candidate[bundle["failure_features"]], model)
    print(results.to_string(index=False))


if __name__ == "__main__":
    print("1. Run full pipeline")
    print("2. Search district summary")
    print("3. Run district digital twin simulation")
    choice = input("Select an option: ").strip()

    if choice == "1":
        run_pipeline()
    elif choice == "2":
        search_district()
    elif choice == "3":
        simulate_district()
    else:
        print("Invalid option.")
