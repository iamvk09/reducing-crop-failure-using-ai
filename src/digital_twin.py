import pandas as pd


DEFAULT_SCENARIOS = {
    "Baseline": {},
    "Drought Stress": {"Rainfall": -35, "SoilMoisture": -18, "Temperature": 2.5, "NDVI_Flowering": -0.08},
    "Heatwave": {"Temperature": 4.0, "Humidity": -8, "WaterStress": 0.16},
    "Irrigation Support": {"SoilMoisture": 14, "WaterStress": -0.18, "NDVI_Flowering": 0.05},
}


def _bounded_adjustment(row, updates):
    adjusted = row.copy()
    bounds = {
        "Rainfall": (0, 260),
        "Temperature": (10, 45),
        "Humidity": (15, 100),
        "SoilMoisture": (5, 100),
        "NDVI_Flowering": (0.1, 0.95),
        "WaterStress": (0.01, 0.99),
    }

    for feature, delta in updates.items():
        if feature not in adjusted.index:
            continue
        adjusted[feature] = adjusted[feature] + delta
        if feature in bounds:
            low, high = bounds[feature]
            adjusted[feature] = min(max(adjusted[feature], low), high)

    return adjusted


def apply_scenario(row, updates=None):
    return _bounded_adjustment(row, updates or {})


def simulate_custom_scenario(row, model, scenario_name, updates=None):
    adjusted = apply_scenario(row, updates or {})
    risk = float(model.predict_proba(pd.DataFrame([adjusted]))[:, 1][0])
    return {
        "Scenario": scenario_name,
        "RiskScore": round(risk, 4),
        "Rainfall": round(float(adjusted["Rainfall"]), 2),
        "Temperature": round(float(adjusted["Temperature"]), 2),
        "Humidity": round(float(adjusted["Humidity"]), 2),
        "SoilMoisture": round(float(adjusted["SoilMoisture"]), 2),
        "NDVI_Flowering": round(float(adjusted["NDVI_Flowering"]), 3),
        "WaterStress": round(float(adjusted["WaterStress"]), 3),
    }


def run_digital_twin(row, model, scenarios=None):
    scenario_map = scenarios or DEFAULT_SCENARIOS
    results = []

    for name, updates in scenario_map.items():
        results.append(simulate_custom_scenario(row, model, name, updates))

    return pd.DataFrame(results).sort_values("RiskScore", ascending=False).reset_index(drop=True)
