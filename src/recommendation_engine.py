def build_recommendation_summary(row):
    recommendations = []

    if row["ConsensusRisk"] >= 0.7:
        recommendations.append("High alert: prioritize crop protection and weekly field scouting.")
    elif row["ConsensusRisk"] >= 0.45:
        recommendations.append("Moderate alert: monitor the field closely and prepare contingency inputs.")
    else:
        recommendations.append("Low alert: maintain the current crop plan with routine monitoring.")

    if row["WaterStress"] >= 0.55 or row["SoilMoisture"] < 40:
        recommendations.append("Increase irrigation scheduling or moisture conservation practices.")
    elif row["Rainfall"] > 160:
        recommendations.append("Improve field drainage and watch for waterlogging.")

    if row["Temperature"] >= 33:
        recommendations.append("Heat stress risk is elevated; avoid sensitive field operations during peak heat.")
    elif row["Temperature"] <= 18:
        recommendations.append("Cold stress is possible; use tolerant varieties or adjust sowing windows.")

    if row["PestRisk"] >= 0.55:
        recommendations.append("Pest pressure is rising; activate preventive scouting and threshold-based control.")

    if row["RecommendedCrop"] != row["Crop"]:
        recommendations.append(
            f"Better fit detected: consider {row['RecommendedCrop']} for this district-season profile."
        )

    return " ".join(recommendations[:4])


def risk_band(score):
    if score >= 0.7:
        return "High"
    if score >= 0.45:
        return "Medium"
    return "Low"
