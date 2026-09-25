import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import pandas as pd
import streamlit as st

from src.digital_twin import DEFAULT_SCENARIOS, run_digital_twin, simulate_custom_scenario
from src.live_prediction import (
    get_crop_recommendation,
    get_district_baseline,
    get_prediction_explanation,
    predict_new_case,
)
from src.translations import LANGUAGES, localize_feature, localize_map_html, localize_value, translate
from src.weather_service import get_current_weather


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

live_tab, overview_tab, comparison_tab, twin_tab, map_tab = st.tabs(
    ["🔮 " + t("tab_live"), t("tab_field"), t("tab_compare"), t("tab_weather"), t("tab_map")]
)

with live_tab:
    st.header(t("live_prediction_heading"))
    st.caption(
        "Real-time crop failure risk evaluation combining live Open-Meteo weather with the trained agricultural ML pipeline."
    )

    mode_c1, mode_c2 = st.columns([1.2, 2.8])
    with mode_c1:
        live_ui_mode = st.radio(
            "Interface Mode",
            [t("live_farmer_mode"), t("live_expert_mode")],
            index=1 if show_expert_tools else 0,
            horizontal=True,
            help="Farmer mode provides clean guidance; Expert mode unlocks SHAP analysis, data provenance, and digital twin simulation.",
        )
    is_expert = live_ui_mode == t("live_expert_mode")

    st.subheader(t("choose_field"))
    all_states = sorted(selection_df["State"].dropna().unique().tolist())
    default_state_idx = all_states.index(selected_state) if selected_state in all_states else 0

    sel_c1, sel_c2, sel_c3 = st.columns(3)
    with sel_c1:
        live_state = st.selectbox(
            t("state"),
            all_states,
            index=default_state_idx,
            key="live_state_selector",
        )

    state_districts = sorted(
        selection_df[selection_df["State"] == live_state]["District"].dropna().unique().tolist()
    )
    default_dist_idx = (
        state_districts.index(district) if district in state_districts else 0
    )
    with sel_c2:
        live_district = st.selectbox(
            t("district"),
            state_districts,
            index=default_dist_idx,
            key="live_district_selector",
        )

    district_baseline = get_district_baseline(live_district)
    available_crops = district_baseline["available_crops"]
    default_crop_idx = available_crops.index(crop) if crop in available_crops else 0

    with sel_c3:
        live_crop = st.selectbox(
            t("crop"),
            available_crops,
            index=default_crop_idx,
            format_func=lambda val: localize_value(language, val),
            key="live_crop_selector",
        )

    baseline_info = get_district_baseline(live_district, live_crop)
    district_coords = (baseline_info["latitude"], baseline_info["longitude"])

    # Live Weather Integration
    st.subheader(t("live_weather"))
    with st.spinner("Fetching current live weather from Open-Meteo..."):
        weather_data = get_current_weather(district_coords[0], district_coords[1])

    w_col1, w_col2, w_col3, w_col4 = st.columns(4)
    if weather_data["success"]:
        w_col1.metric("Temperature", f"{weather_data['temperature']} °C")
        w_col2.metric("Humidity", f"{weather_data['humidity']} %")
        w_col3.metric("Precipitation", f"{weather_data['precipitation']} mm")
        if weather_data.get("soil_moisture_percentage") is not None:
            w_col4.metric(
                "Soil Moisture (Root-zone)",
                f"{weather_data['soil_moisture_percentage']} %",
                help=f"Volumetric: {weather_data.get('soil_moisture_m3m3')} m³/m³",
            )
        else:
            w_col4.metric(
                "Precipitation (7-day sum)",
                f"{weather_data.get('precipitation_sum_7d', 0.0)} mm",
            )
        st.caption(
            f"Source: Open-Meteo · Coordinates: ({district_coords[0]}°N, {district_coords[1]}°E) · Updated: {weather_data['timestamp']}"
        )
    else:
        st.warning(
            f"⚠️ Live weather unavailable ({weather_data.get('error')}). Using historical district baseline weather."
        )
        w_col1.metric("Baseline Temp", f"{baseline_info['feature_baselines']['Temperature']} °C")
        w_col2.metric("Baseline Humidity", f"{baseline_info['feature_baselines']['Humidity']} %")
        w_col3.metric("Baseline Rainfall", f"{baseline_info['feature_baselines']['Rainfall']} mm")
        w_col4.metric("Baseline Soil Moisture", f"{baseline_info['feature_baselines']['SoilMoisture']} %")
        st.caption("Source: Historical district dataset baseline")

    # Feature Assembly and Provenance Tracking
    base_feats = baseline_info["feature_baselines"].copy()
    feature_provenance = baseline_info["feature_sources"].copy()

    if weather_data["success"]:
        if weather_data["temperature"] is not None:
            base_feats["Temperature"] = float(weather_data["temperature"])
            feature_provenance["Temperature"] = "Live weather (Open-Meteo)"
        if weather_data["humidity"] is not None:
            base_feats["Humidity"] = float(weather_data["humidity"])
            feature_provenance["Humidity"] = "Live weather (Open-Meteo)"
        if weather_data.get("soil_moisture_percentage") is not None:
            base_feats["SoilMoisture"] = float(weather_data["soil_moisture_percentage"])
            feature_provenance["SoilMoisture"] = "Derived from live weather (Open-Meteo root-zone moisture)"

    overridden_feats = base_feats.copy()
    soil_options = [
        "Sandy Loam", "Sandy", "Black", "Loam", "Alluvial",
        "Red Loam", "Red Sandy Loam", "Laterite", "Clay Loam",
        "Loamy Sand", "Medium Black",
    ]
    irrigation_options = ["Low", "Medium", "High"]

    with st.expander("🛠️ " + t("advanced_inputs") + (" (Expert Controls)" if is_expert else "")):
        st.caption(
            "Model features that cannot be obtained from live weather are populated from verified district/crop historical baselines. "
            "You may review or override any value below:"
        )
        adv_c1, adv_c2, adv_c3 = st.columns(3)
        with adv_c1:
            adv_rain = st.number_input(
                "Seasonal Rainfall (mm)",
                min_value=0.0,
                max_value=350.0,
                value=float(base_feats["Rainfall"]),
                step=5.0,
                help="Cumulative seasonal rainfall for this crop cycle",
                key="adv_live_rain",
            )
            adv_sm = st.number_input(
                "Soil Moisture (%)",
                min_value=5.0,
                max_value=100.0,
                value=float(base_feats["SoilMoisture"]),
                step=1.0,
                key="adv_live_sm",
            )
            soil_idx = (
                soil_options.index(base_feats["SoilType"])
                if base_feats["SoilType"] in soil_options
                else 0
            )
            adv_soil = st.selectbox(
                "Soil Type",
                soil_options,
                index=soil_idx,
                key="adv_live_soil",
            )
        with adv_c2:
            adv_ndvi = st.number_input(
                "Crop Greenness (NDVI Flowering)",
                min_value=0.10,
                max_value=0.99,
                value=float(base_feats["NDVI_Flowering"]),
                step=0.01,
                key="adv_live_ndvi",
            )
            adv_water_stress = st.number_input(
                "Water Shortage Index",
                min_value=0.01,
                max_value=0.99,
                value=float(base_feats["WaterStress"]),
                step=0.01,
                key="adv_live_water_stress",
            )
            irr_idx = (
                irrigation_options.index(base_feats["IrrigationLevel"])
                if base_feats["IrrigationLevel"] in irrigation_options
                else 1
            )
            adv_irrigation = st.selectbox(
                "Irrigation Level",
                irrigation_options,
                index=irr_idx,
                key="adv_live_irr",
            )
        with adv_c3:
            adv_pest = st.number_input(
                "Pest Risk Index",
                min_value=0.01,
                max_value=0.99,
                value=float(base_feats["PestRisk"]),
                step=0.01,
                key="adv_live_pest",
            )
            adv_suitability = st.number_input(
                "Crop Suitability Score",
                min_value=0.05,
                max_value=1.00,
                value=float(base_feats["SuitabilityScore"]),
                step=0.01,
                key="adv_live_suitability",
            )
            adv_yield_idx = st.number_input(
                "Expected Yield Index",
                min_value=10.0,
                max_value=100.0,
                value=float(base_feats["YieldIndex"]),
                step=1.0,
                key="adv_live_yield",
            )

        if adv_rain != base_feats["Rainfall"]:
            overridden_feats["Rainfall"] = adv_rain
            feature_provenance["Rainfall"] = "User override (Advanced Inputs)"
        if adv_sm != base_feats["SoilMoisture"]:
            overridden_feats["SoilMoisture"] = adv_sm
            feature_provenance["SoilMoisture"] = "User override (Advanced Inputs)"
        if adv_soil != base_feats["SoilType"]:
            overridden_feats["SoilType"] = adv_soil
            feature_provenance["SoilType"] = "User override (Advanced Inputs)"
        if adv_ndvi != base_feats["NDVI_Flowering"]:
            overridden_feats["NDVI_Flowering"] = adv_ndvi
            feature_provenance["NDVI_Flowering"] = "User override (Advanced Inputs)"
        if adv_water_stress != base_feats["WaterStress"]:
            overridden_feats["WaterStress"] = adv_water_stress
            feature_provenance["WaterStress"] = "User override (Advanced Inputs)"
        if adv_irrigation != base_feats["IrrigationLevel"]:
            overridden_feats["IrrigationLevel"] = adv_irrigation
            feature_provenance["IrrigationLevel"] = "User override (Advanced Inputs)"
        if adv_pest != base_feats["PestRisk"]:
            overridden_feats["PestRisk"] = adv_pest
            feature_provenance["PestRisk"] = "User override (Advanced Inputs)"
        if adv_suitability != base_feats["SuitabilityScore"]:
            overridden_feats["SuitabilityScore"] = adv_suitability
            feature_provenance["SuitabilityScore"] = "User override (Advanced Inputs)"
        if adv_yield_idx != base_feats["YieldIndex"]:
            overridden_feats["YieldIndex"] = adv_yield_idx
            feature_provenance["YieldIndex"] = "User override (Advanced Inputs)"

    st.write("")
    predict_clicked = st.button(t("predict_button"), type="primary", use_container_width=True)

    # Initialize or update prediction session state
    if predict_clicked or "live_case_input" not in st.session_state:
        st.session_state["live_case_input"] = overridden_feats
        st.session_state["live_case_provenance"] = feature_provenance
        st.session_state["live_case_district"] = live_district
        st.session_state["live_case_crop"] = live_crop
        st.session_state["live_case_state"] = live_state

    # Execute predictions using the active session case
    active_input = st.session_state["live_case_input"]
    active_provenance = st.session_state["live_case_provenance"]
    current_district = st.session_state["live_case_district"]
    current_crop = st.session_state["live_case_crop"]
    current_state = st.session_state["live_case_state"]

    prediction_result = predict_new_case(active_input)
    rec_data = get_crop_recommendation({**active_input, "District": current_district})
    explanation_result = get_prediction_explanation(active_input)

    st.divider()
    res_left, res_right = st.columns([1.3, 1])

    with res_left:
        st.subheader(
            f"{t('crop')}: {localize_value(language, current_crop)} · {t('district')}: {current_district}, {current_state}"
        )

        r_col1, r_col2 = st.columns([1.2, 1])
        with r_col1:
            st.metric(
                t("estimated_risk"),
                f"{prediction_result['risk_probability'] * 100:.1f}%",
            )
        with r_col2:
            _styled_risk_badge(
                prediction_result["risk_level"],
                t(
                    {"High": "high", "Medium": "medium", "Low": "low"}.get(
                        prediction_result["risk_level"], "risk_level"
                    )
                ),
            )

        st.info(
            f"ℹ️ **{t('disclaimer_title')}**: {t('disclaimer_text')}"
        )

        # Farmer guidance note
        farmer_advice_list = _farmer_advice(
            {
                "RiskLevel": prediction_result["risk_level"],
                "WaterStress": active_input["WaterStress"],
                "SoilMoisture": active_input["SoilMoisture"],
                "PestRisk": active_input["PestRisk"],
                "RecommendedCrop": rec_data.get("recommended_crop", current_crop),
                "Crop": current_crop,
            },
            language,
        )
        st.markdown(
            f'<div class="farmer-note"><strong>{t("what_means")}</strong> {" ".join(farmer_advice_list)}</div>',
            unsafe_allow_html=True,
        )

    with res_right:
        st.subheader(t("recommended_crops_title"))
        if rec_data.get("success") and rec_data.get("recommended_crop"):
            st.success(
                f"**{t('better_crop')}**: {localize_value(language, rec_data['recommended_crop'])}"
            )
            st.markdown(f"**{t('safer_options')}:**")
            rec_table = pd.DataFrame(rec_data["top_options"])[["crop", "percentage"]].rename(
                columns={"crop": t("crop"), "percentage": "Model Confidence"}
            )
            rec_table[t("crop")] = rec_table[t("crop")].map(lambda c: localize_value(language, c))
            st.dataframe(rec_table, hide_index=True, width="stretch")
        else:
            st.info("Crop recommendation not available for this profile.")

    # Expert Mode Tools
    if is_expert:
        st.divider()
        st.header(f"🔬 {t('expert_tools')} — Live Case")

        exp_c1, exp_c2 = st.columns([1.1, 1])
        with exp_c1:
            st.subheader("Model Diagnostic Details")
            st.markdown(f"- **Primary Architecture**: `{prediction_result['best_model_name']}`")
            st.markdown(f"- **Explainer Engine**: `{explanation_result['explainer_type']}`")

            if (
                prediction_result.get("region_risk") is not None
                or prediction_result.get("crop_risk") is not None
            ):
                contrib_data = {
                    "Model Component": [
                        "Global Model",
                        "Region-Specific Model",
                        "Crop-Specific Model",
                        "Consensus Risk",
                    ],
                    "Failure Risk": [
                        f"{prediction_result['global_risk'] * 100:.1f}%",
                        (
                            f"{prediction_result['region_risk'] * 100:.1f}%"
                            if prediction_result["region_risk"] is not None
                            else "N/A"
                        ),
                        (
                            f"{prediction_result['crop_risk'] * 100:.1f}%"
                            if prediction_result["crop_risk"] is not None
                            else "N/A"
                        ),
                        f"{prediction_result['consensus_risk'] * 100:.1f}%",
                    ],
                }
                st.dataframe(pd.DataFrame(contrib_data), hide_index=True, width="stretch")

            st.subheader(f"📊 {t('why_risk')}")
            st.write(explanation_result.get("summary", ""))
            shap_items = explanation_result.get("top_features", [])
            if shap_items:
                shap_df = pd.DataFrame(shap_items)[
                    ["display_name", "impact", "direction"]
                ].rename(
                    columns={
                        "display_name": "Feature",
                        "impact": "SHAP Impact Score",
                        "direction": "Effect on Risk",
                    }
                )
                st.dataframe(shap_df, hide_index=True, width="stretch")

        with exp_c2:
            st.subheader(f"📋 {t('data_provenance')}")
            st.caption(
                "Every feature's exact source is audited below to guarantee data integrity."
            )
            provenance_rows = [
                {
                    "Feature": f,
                    "Value": str(active_input[f]),
                    "Data Provenance": active_provenance.get(f, "System"),
                }
                for f in bundle["failure_features"]
            ]
            st.dataframe(pd.DataFrame(provenance_rows), hide_index=True, width="stretch")

        # Integrated Digital Twin connected to the Live Case
        st.divider()
        st.subheader(f"🌱 {t('digital_twin_live_title')}")
        st.caption(
            "Simulate environmental stress scenarios on this exact live case using the trained Digital Twin."
        )

        dt_left, dt_right = st.columns([1, 1.15])
        with dt_left:
            st.markdown("**Preset Stress Scenarios**")
            live_twin_presets = run_digital_twin(pd.Series(active_input), best_model)
            live_twin_presets["RiskScore"] = live_twin_presets["RiskScore"].map(
                lambda v: f"{v * 100:.1f}%"
            )
            st.dataframe(
                live_twin_presets[
                    ["Scenario", "RiskScore", "Temperature", "Rainfall", "SoilMoisture"]
                ],
                hide_index=True,
                width="stretch",
            )

        with dt_right:
            st.markdown("**Interactive Scenario Simulator**")
            sim_c1, sim_c2 = st.columns(2)
            with sim_c1:
                dt_rain = st.slider(
                    "Rainfall adjustment (mm)",
                    -80.0,
                    80.0,
                    0.0,
                    5.0,
                    key="dt_live_rain",
                )
                dt_temp = st.slider(
                    "Temperature adjustment (°C)",
                    -6.0,
                    6.0,
                    0.0,
                    0.5,
                    key="dt_live_temp",
                )
            with sim_c2:
                dt_hum = st.slider(
                    "Humidity adjustment (%)",
                    -30.0,
                    30.0,
                    0.0,
                    2.0,
                    key="dt_live_hum",
                )
                dt_sm = st.slider(
                    "Soil moisture adjustment (%)",
                    -30.0,
                    30.0,
                    0.0,
                    2.0,
                    key="dt_live_sm",
                )

            dt_custom_res = simulate_custom_scenario(
                pd.Series(active_input),
                best_model,
                "Live Simulation",
                {
                    "Rainfall": dt_rain,
                    "Temperature": dt_temp,
                    "Humidity": dt_hum,
                    "SoilMoisture": dt_sm,
                },
            )
            base_risk_val = prediction_result["global_risk"]
            sim_risk_val = dt_custom_res["RiskScore"]

            dt_res_cols = st.columns(2)
            dt_res_cols[0].metric(t("current_risk"), f"{base_risk_val * 100:.1f}%")
            dt_res_cols[1].metric(
                t("risk_after"),
                f"{sim_risk_val * 100:.1f}%",
                _risk_delta_text(sim_risk_val, base_risk_val),
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
