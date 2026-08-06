import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import pandas as pd
import streamlit as st

from src.digital_twin import DEFAULT_SCENARIOS, run_digital_twin, simulate_custom_scenario


st.set_page_config(page_title="Agriculture AI Dashboard", layout="wide")


RISK_COLORS = {"High": "#c53030", "Medium": "#dd6b20", "Low": "#2f855a"}
DIGITAL_TWIN_CONTROLS = [
    ("Rainfall", "Rainfall delta (mm)", -80.0, 80.0, 1.0),
    ("Temperature", "Temperature delta (C)", -8.0, 8.0, 0.5),
    ("Humidity", "Humidity delta (%)", -30.0, 30.0, 1.0),
    ("SoilMoisture", "Soil moisture delta (%)", -30.0, 30.0, 1.0),
    ("NDVI_Flowering", "NDVI delta", -0.30, 0.30, 0.01),
    ("WaterStress", "Water stress delta", -0.40, 0.40, 0.01),
]


@st.cache_data
def load_data():
    predictions = pd.read_csv("data/district_predictions.csv")
    summary = pd.read_csv("data/district_summary.csv")
    feature_importance = pd.read_csv("models/feature_importance.csv")
    performance = pd.read_csv("models/model_performance.csv")
    return predictions, summary, feature_importance, performance


@st.cache_resource
def load_bundle():
    import joblib

    return joblib.load("models/agri_ai_bundle.pkl")


def _format_percent(value):
    return f"{value * 100:.1f}%"


def _risk_delta_text(new_risk, base_risk):
    delta = (new_risk - base_risk) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f} pts vs baseline"


def _styled_risk_badge(label):
    color = RISK_COLORS.get(label, "#4a5568")
    st.markdown(
        f"""
        <div style="background:{color};padding:0.55rem 0.8rem;border-radius:999px;
        color:white;font-weight:700;display:inline-block;">{label} Risk</div>
        """,
        unsafe_allow_html=True,
    )


predictions_df, summary_df, feature_importance_df, performance_df = load_data()
bundle = load_bundle()
best_model = bundle["failure_models"][bundle["best_failure_model_name"]]

st.title("Agriculture AI Control Center")
st.caption(
    "Interactive dashboard for multi-model crop failure prediction, explainability, crop recommendation, and digital twin scenario simulation."
)

sidebar = st.sidebar
sidebar.header("Scenario Filters")

district = sidebar.selectbox("District", sorted(predictions_df["District"].unique()))
district_df = predictions_df[predictions_df["District"] == district].copy()

year = sidebar.selectbox("Year", sorted(district_df["Year"].unique(), reverse=True))
year_df = district_df[district_df["Year"] == year].copy()

season = sidebar.selectbox("Season", sorted(year_df["Season"].unique()))
season_df = year_df[year_df["Season"] == season].sort_values("ConsensusRisk", ascending=False).copy()

default_crop = (
    season_df.sort_values("ConsensusRisk", ascending=False)["Crop"].iloc[0]
    if not season_df.empty
    else None
)
crop = sidebar.selectbox("Crop", season_df["Crop"].tolist(), index=season_df["Crop"].tolist().index(default_crop))
selected_row = season_df[season_df["Crop"] == crop].iloc[0]

district_summary_match = summary_df[
    (summary_df["District"] == district) & (summary_df["Season"] == season)
]
if district_summary_match.empty:
    district_summary = (
        summary_df[summary_df["District"] == district].sort_values("ConsensusRisk", ascending=False).iloc[0]
    )
else:
    district_summary = district_summary_match.iloc[0]

top_recommendations = season_df.sort_values("ConsensusRisk").head(3)[
    ["Crop", "ConsensusRisk", "RiskLevel"]
].copy()
top_recommendations["ConsensusRisk"] = top_recommendations["ConsensusRisk"].map(_format_percent)

hero_left, hero_right = st.columns([1.35, 1])

with hero_left:
    st.subheader(f"{district}, {selected_row['State']} | {season} {year}")
    st.write(
        f"Region: `{selected_row['Region']}` | Soil: `{selected_row['SoilType']}` | Irrigation: `{selected_row['IrrigationLevel']}`"
    )
    _styled_risk_badge(selected_row["RiskLevel"])
    st.write(selected_row["RecommendationSummary"])

    metrics = st.columns(4)
    metrics[0].metric("Consensus Risk", _format_percent(selected_row["ConsensusRisk"]))
    metrics[1].metric("Current Crop", selected_row["Crop"])
    metrics[2].metric("Recommended Crop", selected_row["RecommendedCrop"])
    metrics[3].metric("Yield Index", f"{selected_row['YieldIndex']:.1f}")

with hero_right:
    st.subheader("Best Crop Options")
    st.dataframe(top_recommendations, hide_index=True, width="stretch")
    st.caption(f"Model ranking: {selected_row['TopCropOptions']}")

overview_tab, model_tab, twin_tab, map_tab = st.tabs(
    ["Overview", "Model Lens", "Digital Twin", "Regional Map"]
)

with overview_tab:
    upper_left, upper_right = st.columns([1.2, 1])

    with upper_left:
        st.subheader("Crop Risk Comparison")
        crop_risk_df = season_df[["Crop", "ConsensusRisk"]].set_index("Crop")
        st.bar_chart(crop_risk_df)

        st.subheader("Per-Crop Detail")
        display_df = season_df[
            [
                "Crop",
                "GlobalRiskScore",
                "RegionRiskScore",
                "CropSpecificRiskScore",
                "ConsensusRisk",
                "RiskLevel",
                "RecommendedCrop",
            ]
        ].copy()
        for column in [
            "GlobalRiskScore",
            "RegionRiskScore",
            "CropSpecificRiskScore",
            "ConsensusRisk",
        ]:
            display_df[column] = display_df[column].map(_format_percent)
        st.dataframe(display_df, width="stretch", hide_index=True)

    with upper_right:
        st.subheader("Field Conditions")
        conditions_df = pd.DataFrame(
            {
                "Feature": [
                    "Rainfall",
                    "Temperature",
                    "Humidity",
                    "SoilMoisture",
                    "NDVI_Flowering",
                    "WaterStress",
                    "PestRisk",
                ],
                "Current": [
                    selected_row["Rainfall"],
                    selected_row["Temperature"],
                    selected_row["Humidity"],
                    selected_row["SoilMoisture"],
                    selected_row["NDVI_Flowering"],
                    selected_row["WaterStress"],
                    selected_row["PestRisk"],
                ],
            }
        ).set_index("Feature")
        st.bar_chart(conditions_df)

        st.subheader("Action Summary")
        st.markdown(
            f"""
            - Failure label in dataset: `{int(selected_row['Failure'])}`
            - Current crop suitability score: `{selected_row['SuitabilityScore']:.3f}`
            - Recommended crop for this district-season: `{district_summary['RecommendedCrop']}`
            - Current district-season risk band: `{selected_row['RiskLevel']}`
            """
        )

with model_tab:
    model_left, model_right = st.columns([1.1, 1])

    with model_left:
        st.subheader("Model Contribution View")
        contributions_df = pd.DataFrame(
            {
                "Model": ["Global", "Region-Specific", "Crop-Specific"],
                "RiskScore": [
                    selected_row["GlobalRiskScore"],
                    selected_row["RegionRiskScore"],
                    selected_row["CropSpecificRiskScore"],
                ],
            }
        ).dropna()
        contributions_df = contributions_df.set_index("Model")
        st.bar_chart(contributions_df)

        st.subheader("Model Performance")
        perf_df = performance_df.copy()
        perf_df["roc_auc"] = perf_df["roc_auc"].round(3)
        perf_df["f1_score"] = perf_df["f1_score"].round(3)
        st.dataframe(perf_df, width="stretch", hide_index=True)

    with model_right:
        st.subheader("Explainability")
        st.bar_chart(feature_importance_df.head(12).set_index("Feature"))
        if os.path.exists("models/shap_summary.png"):
            st.image("models/shap_summary.png", caption="Feature impact summary")

with twin_tab:
    twin_left, twin_right = st.columns([1.05, 1.15])

    with twin_left:
        st.subheader("Preset Scenarios")
        preset_df = run_digital_twin(selected_row[bundle["failure_features"]], best_model)
        preset_df["RiskScore"] = preset_df["RiskScore"].map(lambda value: round(value * 100, 1))
        st.dataframe(preset_df, width="stretch", hide_index=True)
        st.caption("RiskScore shown as percent risk after each scenario is applied.")

    with twin_right:
        st.subheader("Interactive Scenario Builder")
        custom_name = st.text_input("Scenario name", value="Custom Intervention")
        updates = {}
        for feature, label, min_value, max_value, step in DIGITAL_TWIN_CONTROLS:
            updates[feature] = st.slider(
                label,
                min_value=min_value,
                max_value=max_value,
                value=0.0,
                step=step,
            )

        custom_result = simulate_custom_scenario(
            selected_row[bundle["failure_features"]],
            best_model,
            custom_name,
            updates,
        )
        baseline_result = simulate_custom_scenario(
            selected_row[bundle["failure_features"]],
            best_model,
            "Baseline",
            {},
        )

        result_cols = st.columns(2)
        result_cols[0].metric("Baseline Risk", _format_percent(baseline_result["RiskScore"]))
        result_cols[1].metric(
            "Custom Risk",
            _format_percent(custom_result["RiskScore"]),
            _risk_delta_text(custom_result["RiskScore"], baseline_result["RiskScore"]),
        )

        comparison_df = pd.DataFrame(
            [
                {"Scenario": "Baseline", "RiskScore": baseline_result["RiskScore"]},
                {"Scenario": custom_name, "RiskScore": custom_result["RiskScore"]},
            ]
        ).set_index("Scenario")
        st.bar_chart(comparison_df)

        st.write("Adjusted field values")
        adjusted_view = pd.DataFrame(
            {
                "Feature": [
                    "Rainfall",
                    "Temperature",
                    "Humidity",
                    "SoilMoisture",
                    "NDVI_Flowering",
                    "WaterStress",
                ],
                "Value": [
                    custom_result["Rainfall"],
                    custom_result["Temperature"],
                    custom_result["Humidity"],
                    custom_result["SoilMoisture"],
                    custom_result["NDVI_Flowering"],
                    custom_result["WaterStress"],
                ],
            }
        )
        st.dataframe(adjusted_view, width="stretch", hide_index=True)

with map_tab:
    map_left, map_right = st.columns([1.2, 1])

    with map_left:
        st.subheader("District Map")
        if os.path.exists("maps/india_risk_map.html"):
            with open("maps/india_risk_map.html", "r", encoding="utf-8") as map_file:
                st.components.v1.html(map_file.read(), height=520)
        else:
            st.info("Run the pipeline first to generate the map.")

    with map_right:
        st.subheader("District Leaderboard")
        leaderboard_df = summary_df.sort_values("ConsensusRisk", ascending=False)[
            ["District", "State", "CurrentCrop", "RecommendedCrop", "ConsensusRisk", "RiskLevel"]
        ].head(12)
        leaderboard_df = leaderboard_df.copy()
        leaderboard_df["ConsensusRisk"] = leaderboard_df["ConsensusRisk"].map(_format_percent)
        st.dataframe(leaderboard_df, width="stretch", hide_index=True)

        st.subheader("Preset Library")
        st.write(", ".join(DEFAULT_SCENARIOS.keys()))
