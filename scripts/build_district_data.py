import json
import os
import pandas as pd

def build_data():
    df_pred = pd.read_csv("data/district_predictions.csv")
    df_obs = pd.read_csv("data/district_observed_dataset.csv")

    obs_map = {}
    for _, row in df_obs.iterrows():
        d = str(row["District"]).strip().lower()
        yr = int(row["Year"])
        k = f"{d}_{yr}"
        obs_map[k] = {
            "state": str(row["State"]),
            "district": str(row["District"]),
            "year": yr,
            "production": float(row["Production"]) if pd.notna(row["Production"]) else None,
            "yield_tonnes_per_ha": float(row["YieldTonnesPerHectare"]) if pd.notna(row["YieldTonnesPerHectare"]) else None,
            "rainfall": float(row["Rainfall"]) if pd.notna(row["Rainfall"]) else None,
            "temperature": float(row["Temperature"]) if pd.notna(row["Temperature"]) else None,
            "observation_status": str(row.get("ObservationStatus", "Observed historical record")),
            "crop_data_source": str(row.get("CropDataSource", "DES, Ministry of Agriculture")),
            "weather_data_source": str(row.get("WeatherDataSource", "Open-Meteo Historical Weather API")),
        }

    verified_districts = set(df_obs["District"].dropna().str.strip().str.lower().unique())

    summary_map = {}
    if os.path.exists("data/district_summary.csv"):
        df_sum = pd.read_csv("data/district_summary.csv")
        for _, row in df_sum.iterrows():
            d = str(row["District"]).strip().lower()
            summary_map[d] = {
                "latitude": float(row["Latitude"]) if pd.notna(row["Latitude"]) else None,
                "longitude": float(row["Longitude"]) if pd.notna(row["Longitude"]) else None,
                "consensus_risk": round(float(row["ConsensusRisk"]), 4) if pd.notna(row["ConsensusRisk"]) else None,
                "risk_level": str(row["RiskLevel"]) if pd.notna(row["RiskLevel"]) else "Medium",
                "current_crop": str(row.get("CurrentCrop", "")),
                "recommended_crop": str(row.get("RecommendedCrop", "")),
                "top_options": str(row.get("TopCropOptions", "")),
            }

    districts_meta = []
    seen_d = set()
    for _, row in df_pred[["District", "State"]].drop_duplicates().sort_values(["State", "District"]).iterrows():
        d_name = str(row["District"]).strip()
        if d_name.lower() in seen_d:
            continue
        seen_d.add(d_name.lower())
        sum_data = summary_map.get(d_name.lower(), {})
        districts_meta.append({
            "district": d_name,
            "state": str(row["State"]).strip(),
            "has_verified": d_name.lower() in verified_districts,
            "latitude": sum_data.get("latitude"),
            "longitude": sum_data.get("longitude"),
            "consensus_risk": sum_data.get("consensus_risk"),
            "risk_level": sum_data.get("risk_level", "Medium"),
            "current_crop": sum_data.get("current_crop", ""),
            "recommended_crop": sum_data.get("recommended_crop", ""),
            "top_options": sum_data.get("top_options", ""),
        })

    records = {}
    for _, row in df_pred.iterrows():
        d_name = str(row["District"]).strip()
        yr = int(row["Year"])
        sz = str(row["Season"]).strip()
        cr = str(row["Crop"]).strip()
        key = f"{d_name.lower()}_{yr}_{sz.lower()}_{cr.lower()}"

        top_opts = []
        top_str = str(row.get("TopCropOptions", ""))
        if top_str and top_str != "nan":
            parts = [p.strip() for p in top_str.split(",") if p.strip()]
            for p in parts:
                if "(" in p and ")" in p:
                    cname = p[:p.find("(")].strip()
                    pct = p[p.find("(") + 1:p.find(")")].strip()
                    top_opts.append({"crop": cname, "percentage": pct})

        records[key] = {
            "district": d_name,
            "state": str(row["State"]).strip(),
            "region": str(row.get("Region", "")),
            "year": yr,
            "season": sz,
            "crop": cr,
            "soil_type": str(row.get("SoilType", "Alluvial")),
            "irrigation_level": str(row.get("IrrigationLevel", "Medium")),
            "rainfall": round(float(row.get("Rainfall", 0)), 1),
            "temperature": round(float(row.get("Temperature", 0)), 1),
            "humidity": round(float(row.get("Humidity", 0)), 1),
            "soil_moisture": round(float(row.get("SoilMoisture", 0)), 1),
            "ndvi_flowering": round(float(row.get("NDVI_Flowering", 0)), 3),
            "water_stress": round(float(row.get("WaterStress", 0)), 3),
            "pest_risk": round(float(row.get("PestRisk", 0)), 3),
            "suitability_score": round(float(row.get("SuitabilityScore", 0)), 3),
            "yield_index": round(float(row.get("YieldIndex", 0)), 1),
            "consensus_risk": round(float(row.get("ConsensusRisk", 0)), 4),
            "risk_level": str(row.get("RiskLevel", "Medium")),
            "recommended_crop": str(row.get("RecommendedCrop", cr)),
            "recommendation_summary": str(row.get("RecommendationSummary", "")),
            "top_options": top_opts,
        }

    output = {
        "districts": districts_meta,
        "records": records,
        "observed": obs_map
    }

    out_dir = "apps/shared/data"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "district_guide_data.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"))

    meta_file = os.path.join(out_dir, "district_metadata.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(districts_meta, f, separators=(",", ":"))

    print(f"Written {out_file} successfully! Size: {os.path.getsize(out_file) / 1024:.1f} KB")
    print(f"Written {meta_file} successfully! Size: {os.path.getsize(meta_file) / 1024:.1f} KB")

if __name__ == "__main__":
    build_data()
