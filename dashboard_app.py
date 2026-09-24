import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import pandas as pd
import streamlit as st

from src.digital_twin import DEFAULT_SCENARIOS, run_digital_twin, simulate_custom_scenario
from src.translations import LANGUAGES, localize_feature, localize_map_html, localize_value, translate


st.set_page_config(page_title="Agriculture AI Dashboard", layout="wide")

st.markdown(
    """
    <style>
        .block-container {max-width: 1320px; padding-top: 2rem;}
        [data-testid="stMetricValue"] {font-size: 1.65rem;}
        [data-testid="stSidebar"] {background: #111914; border-right: 1px solid #294332;}
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #18231c;
            border-color: #42664b;
        }
        .farmer-note {
            background: #183d27; border-left: 5px solid #55b879; border-radius: 8px;
            color: #f2fff5; padding: 1rem 1.15rem; margin: .4rem 0 1rem 0; font-size: 1.05rem;
        }
        .farmer-note strong {color: #ffffff;}
        .expert-note {
            background: #202932; border-left: 4px solid #95a2b3; border-radius: 8px;
            color: #f7fafc; padding: .75rem 1rem; margin-bottom: 1rem;
        }
        .data-badge {
            border-radius: 999px; color: white; display: inline-block; font-size: .88rem;
            font-weight: 700; margin: 0 0 .75rem 0; padding: .38rem .7rem;
        }
        .verified-badge {background: #16794a;}
        .modelled-badge {background: #5b6674;}
    </style>
    """,
    unsafe_allow_html=True,
)


RISK_COLORS = {"High": "#c53030", "Medium": "#dd6b20", "Low": "#2f855a"}
DIGITAL_TWIN_CONTROLS = [
    ("Rainfall", "Rainfall change (mm)", -80.0, 80.0, 1.0),
    ("Temperature", "Temperature change (°C)", -8.0, 8.0, 0.5),
    ("Humidity", "Humidity change (%)", -30.0, 30.0, 1.0),
    ("SoilMoisture", "Soil moisture change (%)", -30.0, 30.0, 1.0),
    ("NDVI_Flowering", "Crop greenness change", -0.30, 0.30, 0.01),
    ("WaterStress", "Water shortage change", -0.40, 0.40, 0.01),
]


@st.cache_data
def load_data():
    predictions = pd.read_csv("data/district_predictions.csv")
    summary = pd.read_csv("data/district_summary.csv")
    feature_importance = pd.read_csv("models/feature_importance.csv")
    performance = pd.read_csv("models/model_performance.csv")
    observed_path = "data/district_observed_dataset.csv"
    observed = pd.read_csv(observed_path) if os.path.exists(observed_path) else pd.DataFrame()
    return predictions, summary, feature_importance, performance, observed


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


def _styled_risk_badge(risk_level, label):
    color = RISK_COLORS.get(risk_level, "#4a5568")
    st.markdown(
        f"""
        <div style="background:{color};padding:0.55rem 0.8rem;border-radius:999px;
        color:white;font-weight:700;display:inline-block;">{label}</div>
        """,
        unsafe_allow_html=True,
    )


def _data_source_badge(observed_match):
    """Show provenance without implying that the dashboard risk score is observed."""
    if observed_match is not None:
        st.markdown(
            '<div class="data-badge verified-badge">Verified historical weather + DES outcome</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Rainfall, temperature, production, and yield below are observed historical values. "
            "The dashboard risk score remains a model output."
        )
    else:
        st.markdown(
            '<div class="data-badge modelled-badge">Risk estimate based on available regional data</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "A complete historical record is not available for this district and year. "
            "The estimated guidance uses available data from comparable areas and seasons."
        )


def _farmer_advice(row, language):
    """Return short, action-oriented guidance without exposing model jargon."""
    advice = []
    if row["RiskLevel"] == "High":
        advice.append(translate(language, "advice_high"))
    elif row["RiskLevel"] == "Medium":
        advice.append(translate(language, "advice_medium"))
    else:
        advice.append(translate(language, "advice_low"))

    if row["WaterStress"] >= 0.55 or row["SoilMoisture"] < 35:
        advice.append(translate(language, "advice_water"))
    if row["PestRisk"] >= 0.55:
        advice.append(translate(language, "advice_pest"))
    if row["RecommendedCrop"] != row["Crop"]:
        advice.append(translate(language, "advice_crop", crop=row["RecommendedCrop"]))
    return advice[:3]


predictions_df, summary_df, feature_importance_df, performance_df, observed_df = load_data()
bundle = load_bundle()
best_model = bundle["failure_models"][bundle["best_failure_model_name"]]

verified_keys = set()
if not observed_df.empty:
    verified_keys = set(
        observed_df[["State", "District"]].drop_duplicates().itertuples(index=False, name=None)
    )
predictions_df = predictions_df.copy()
predictions_df["HasVerifiedHistory"] = [
    key in verified_keys for key in zip(predictions_df["State"], predictions_df["District"])
]

sidebar = st.sidebar
language = sidebar.selectbox(
    "Language",
    list(LANGUAGES),
    format_func=lambda key: f"{LANGUAGES[key]} ({key})",
)
t = lambda key, **values: translate(language, key, **values)

st.title(t("app_title"))
st.caption(t("app_caption"))

sidebar.header(t("choose_field"))
sidebar.caption(t("choose_caption"))

verified_district_count = predictions_df.loc[predictions_df["HasVerifiedHistory"], ["State", "District"]].drop_duplicates().shape[0]
verified_locations = (
    observed_df[["State", "District"]].drop_duplicates().copy()
    if not observed_df.empty
    else pd.DataFrame(columns=["State", "District"])
)
model_keys = set(predictions_df[["State", "District"]].drop_duplicates().itertuples(index=False, name=None))
if not verified_locations.empty:
    verified_locations["HasModelData"] = [
        key in model_keys for key in verified_locations[["State", "District"]].itertuples(index=False, name=None)
    ]
scope_options = ["All Available Districts", "Verified Districts"]
district_scope = sidebar.radio(
    "District data",
    scope_options,
    index=0,
    help=(
        f"{predictions_df['District'].nunique()} districts available with full model predictions, "
        f"crop options, risk maps, and digital twin simulations."
    ),
)
if district_scope == "Verified Districts" and not verified_locations.empty:
    has_model_mask = verified_locations["HasModelData"]
    selection_df = (
        verified_locations[has_model_mask].assign(HasVerifiedHistory=True)
        if has_model_mask.any()
        else verified_locations.assign(HasVerifiedHistory=True)
    )
else:
    selection_df = predictions_df[["State", "District", "HasVerifiedHistory"]].drop_duplicates().copy()
    selection_df["HasModelData"] = True

district_options = (
    selection_df[["District", "HasVerifiedHistory"]].drop_duplicates()
    .sort_values(["HasVerifiedHistory", "District"], ascending=[False, True])["District"].tolist()
)
district = sidebar.selectbox(t("district"), district_options)
selected_state = selection_df.loc[selection_df["District"] == district, "State"].iloc[0]
district_df = predictions_df[predictions_df["District"] == district].copy()

if district_df.empty:
    historical_district_df = observed_df[
        (observed_df["State"] == selected_state) & (observed_df["District"] == district)
    ].sort_values("Year")
    historical_year = sidebar.selectbox(t("year"), sorted(historical_district_df["Year"].unique(), reverse=True))
    historical_row = historical_district_df[historical_district_df["Year"] == historical_year].iloc[0]

    st.subheader(f"{district}, {selected_state} | {historical_year}")
    _data_source_badge(historical_row)
    st.info("Some information needed to estimate the crop risk is missing, so we have not shown a risk score rather than giving you a potentially misleading result.")
    historical_metrics = st.columns(4)
    historical_metrics[0].metric("DES production", f"{historical_row['Production']:,.0f}")
    historical_metrics[1].metric("DES yield (t/ha)", f"{historical_row['YieldTonnesPerHectare']:.2f}")
    historical_metrics[2].metric("Observed rainfall", f"{historical_row['Rainfall']:.0f} mm")
    historical_metrics[3].metric("Observed temperature", f"{historical_row['Temperature']:.1f} °C")
    st.caption("Weather is measured at the district boundary centroid and aggregated by calendar year to align with the DES reporting year.")
    history_display = historical_district_df[[
        "Year", "ReportingYear", "Production", "YieldTonnesPerHectare", "Rainfall", "Temperature"
    ]].rename(columns={
        "YieldTonnesPerHectare": "DES yield (t/ha)",
        "Rainfall": "Observed rainfall (mm)",
        "Temperature": "Observed temperature (°C)",
    })
    st.subheader("Verified historical record by year")
    st.dataframe(history_display, width="stretch", hide_index=True)
    st.stop()

available_years = sorted(district_df["Year"].unique(), reverse=True)
if not observed_df.empty:
    observed_years = set(
        observed_df.loc[
            (observed_df["State"] == district_df["State"].iloc[0])
            & (observed_df["District"] == district),
            "Year",
        ]
    )
    verified_years = [candidate for candidate in available_years if candidate in observed_years]
    if district_scope == scope_options[0]:
        available_years = verified_years
    elif verified_years:
        # In the all-district view, lead with years that have real DES-weather
        # records instead of defaulting a verified district to a future model year.
        available_years = verified_years + [
            candidate for candidate in available_years if candidate not in observed_years
        ]
year = sidebar.selectbox(t("year"), available_years)
year_df = district_df[district_df["Year"] == year].copy()

season = sidebar.selectbox(
    t("season"),
    sorted(year_df["Season"].unique()),
    format_func=lambda value: localize_value(language, value),
)
season_df = year_df[year_df["Season"] == season].sort_values("ConsensusRisk", ascending=False).copy()

default_crop = (
    season_df.sort_values("ConsensusRisk", ascending=False)["Crop"].iloc[0]
    if not season_df.empty
    else None
)
crop = sidebar.selectbox(
    t("crop"),
    season_df["Crop"].tolist(),
    index=season_df["Crop"].tolist().index(default_crop),
    format_func=lambda value: localize_value(language, value),
)
selected_row = season_df[season_df["Crop"] == crop].iloc[0]

observed_match = None
if not observed_df.empty:
    match = observed_df[
        (observed_df["State"] == selected_row["State"])
        & (observed_df["District"] == district)
        & (observed_df["Year"] == year)
    ]
    if not match.empty:
        observed_match = match.iloc[0]

sidebar.divider()
sidebar.subheader(t("expert_heading"))
show_expert_tools = sidebar.checkbox(t("expert_toggle"), value=False)
sidebar.caption(t("expert_caption"))

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
top_recommendations["Crop"] = top_recommendations["Crop"].map(lambda value: localize_value(language, value))
top_recommendations["RiskLevel"] = top_recommendations["RiskLevel"].map(
    lambda value: t({"High": "high", "Medium": "medium", "Low": "low"}.get(value, "risk_level"))
)
top_recommendations.columns = [t("crop"), t("crop_risk"), t("risk_level")]

hero_left, hero_right = st.columns([1.35, 1])

with hero_left:
    st.subheader(f"{district}, {selected_row['State']} | {localize_value(language, season)} {year}")
    _data_source_badge(observed_match)
    st.write(t("soil_irrigation", soil=selected_row["SoilType"], irrigation=selected_row["IrrigationLevel"]))
    _styled_risk_badge(selected_row["RiskLevel"], t({"High": "high", "Medium": "medium", "Low": "low"}[selected_row["RiskLevel"]]))
    st.markdown(
        f'<div class="farmer-note"><strong>{t("what_means")}</strong> {" ".join(_farmer_advice(selected_row, language))}</div>',
        unsafe_allow_html=True,
    )

    metrics = st.columns(4)
    metrics[0].metric(t("crop_risk"), _format_percent(selected_row["ConsensusRisk"]))
    metrics[1].metric(t("your_crop"), localize_value(language, selected_row["Crop"]))
    metrics[2].metric(t("better_crop"), localize_value(language, selected_row["RecommendedCrop"]))
    metrics[3].metric(t("yield"), f"{selected_row['YieldIndex']:.1f}")

    if observed_match is not None:
        st.markdown("**Verified historical record**")
        observed_metrics = st.columns(4)
        observed_metrics[0].metric("DES production", f"{observed_match['Production']:,.0f}")
        observed_metrics[1].metric("DES yield (t/ha)", f"{observed_match['YieldTonnesPerHectare']:.2f}")
        observed_metrics[2].metric("Observed rainfall", f"{observed_match['Rainfall']:.0f} mm")
        observed_metrics[3].metric("Observed temperature", f"{observed_match['Temperature']:.1f} °C")
        st.caption("Weather is measured at the district boundary centroid and aggregated by calendar year to align with the DES reporting year.")

with hero_right:
    st.subheader(t("safer_options"))
    st.dataframe(top_recommendations, hide_index=True, width="stretch")
    st.caption(t("options_caption"))

overview_tab, comparison_tab, twin_tab, map_tab = st.tabs(
    [t("tab_field"), t("tab_compare"), t("tab_weather"), t("tab_map")]
)

with overview_tab:
    upper_left, upper_right = st.columns([1.2, 1])

    with upper_left:
        st.subheader(t("next_steps"))
        for advice in _farmer_advice(selected_row, language):
            st.markdown(f"- {advice}")

        st.subheader(t("risk_comparison"))
        crop_risk_df = season_df[["Crop", "ConsensusRisk"]].copy()
        crop_risk_df["Crop"] = crop_risk_df["Crop"].map(lambda value: localize_value(language, value))
        crop_risk_df = crop_risk_df.set_index("Crop")
        st.bar_chart(crop_risk_df)

    with upper_right:
        st.subheader(t("conditions"))
        condition_values = [
            observed_match["Rainfall"] if observed_match is not None else selected_row["Rainfall"],
            observed_match["Temperature"] if observed_match is not None else selected_row["Temperature"],
            selected_row["Humidity"],
            selected_row["SoilMoisture"],
            selected_row["NDVI_Flowering"],
            selected_row["WaterStress"],
            selected_row["PestRisk"],
        ]
        conditions_df = pd.DataFrame(
            {
                "Feature": [
                    localize_feature(language, "Rainfall"),
                    localize_feature(language, "Temperature"),
                    localize_feature(language, "Humidity"),
                    localize_feature(language, "SoilMoisture"),
                    localize_feature(language, "NDVI_Flowering"),
                    localize_feature(language, "WaterStress"),
                    localize_feature(language, "PestRisk"),
                ],
                "Current": condition_values,
            }
        ).set_index("Feature")
        st.bar_chart(conditions_df)

        st.subheader(t("glance"))
        st.markdown(
            f"""
            - {t('your_crop')}: **{localize_value(language, selected_row['Crop'])}**
            - {t('suggested_crop')}: **{localize_value(language, district_summary['RecommendedCrop'])}**
            - {t('risk_level')}: **{t({'High': 'high', 'Medium': 'medium', 'Low': 'low'}[selected_row['RiskLevel']])}**
            """
        )

with comparison_tab:
    st.subheader(t("compare_title"))
    st.caption(t("compare_caption"))
    display_df = season_df[["Crop", "ConsensusRisk", "RiskLevel", "RecommendedCrop"]].copy()
    display_df["Crop"] = display_df["Crop"].map(lambda value: localize_value(language, value))
    display_df["RecommendedCrop"] = display_df["RecommendedCrop"].map(lambda value: localize_value(language, value))
    display_df["ConsensusRisk"] = display_df["ConsensusRisk"].map(_format_percent)
    display_df["RiskLevel"] = display_df["RiskLevel"].map(lambda value: t({"High": "high", "Medium": "medium", "Low": "low"}[value]))
    display_df.columns = [t("crop"), t("crop_risk"), t("risk_level"), t("suggested_crop")]
    st.dataframe(display_df, width="stretch", hide_index=True)

if show_expert_tools:
    st.divider()
    st.header(t("expert_tools"))
    st.markdown(
        f'<div class="expert-note">{t("expert_note")}</div>',
        unsafe_allow_html=True,
    )

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
        st.subheader(t("weather_title"))
        preset_df = run_digital_twin(selected_row[bundle["failure_features"]], best_model)
        preset_df["RiskScore"] = preset_df["RiskScore"].map(lambda value: round(value * 100, 1))
        st.dataframe(preset_df, width="stretch", hide_index=True)
        st.caption(t("weather_caption"))

    with twin_right:
        st.subheader(t("custom_title"))
        st.caption(t("custom_caption"))
        custom_name = st.text_input(t("scenario_name"), value=t("field_change"))
        updates = {}
        for feature, label, min_value, max_value, step in DIGITAL_TWIN_CONTROLS:
            unit = f" ({label.split('(', 1)[1]}" if "(" in label else ""
            updates[feature] = st.slider(
                f"{localize_feature(language, feature)}{unit}",
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
        result_cols[0].metric(t("current_risk"), _format_percent(baseline_result["RiskScore"]))
        result_cols[1].metric(
            t("risk_after"),
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

        st.write(t("changed_values"))
        adjusted_view = pd.DataFrame(
            {
                "Feature": [localize_feature(language, feature) for feature in [
                    "Rainfall", "Temperature", "Humidity", "SoilMoisture", "NDVI_Flowering", "WaterStress"
                ]],
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
        st.subheader(t("map_title"))
        if os.path.exists("maps/india_risk_map.html"):
            with open("maps/india_risk_map.html", "r", encoding="utf-8") as map_file:
                st.components.v1.html(localize_map_html(map_file.read(), language), height=520)
        else:
            st.info("Run the pipeline first to generate the map.")

    with map_right:
        st.subheader(t("list_title"))
        leaderboard_df = summary_df.copy()
        leaderboard_df["HasVerifiedHistory"] = [
            key in verified_keys for key in zip(leaderboard_df["State"], leaderboard_df["District"])
        ]
        leaderboard_df["Data source"] = leaderboard_df["HasVerifiedHistory"].map(
            {True: "Verified history", False: "Modelled / demo"}
        )
        leaderboard_df = leaderboard_df.sort_values(
            ["HasVerifiedHistory", "ConsensusRisk"], ascending=[False, False]
        )[
            ["District", "State", "Data source", "CurrentCrop", "RecommendedCrop", "ConsensusRisk", "RiskLevel"]
        ].head(12)
        leaderboard_df = leaderboard_df.copy()
        leaderboard_df["CurrentCrop"] = leaderboard_df["CurrentCrop"].map(lambda value: localize_value(language, value))
        leaderboard_df["RecommendedCrop"] = leaderboard_df["RecommendedCrop"].map(lambda value: localize_value(language, value))
        leaderboard_df["RiskLevel"] = leaderboard_df["RiskLevel"].map(
            lambda value: t({"High": "high", "Medium": "medium", "Low": "low"}[value])
        )
        leaderboard_df["ConsensusRisk"] = leaderboard_df["ConsensusRisk"].map(_format_percent)
        st.dataframe(leaderboard_df, width="stretch", hide_index=True)

        with st.expander(t("weather_examples")):
            st.write(", ".join(DEFAULT_SCENARIOS.keys()))
