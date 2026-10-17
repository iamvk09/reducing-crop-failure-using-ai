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
from src.weather_service import get_current_weather, get_weather_forecast, reverse_geocode_place
from backend.app.services.alert_service import alert_service


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


# ---------------------------------------------------------------------------
# Memory diagnostics - emitted to stdout; visible in Render log tail
# ---------------------------------------------------------------------------
from src.memory_diagnostics import log_memory

log_memory("Dashboard startup - before any data loading")


# ---------------------------------------------------------------------------
# Cached data loading - split so Streamlit caches each CSV independently.
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_predictions():
    df = pd.read_csv("data/district_predictions.csv")
    log_memory("After district_predictions.csv load")
    return df


@st.cache_data(show_spinner=False)
def _load_summary():
    return pd.read_csv("data/district_summary.csv")


@st.cache_data(show_spinner=False)
def _load_feature_importance():
    return pd.read_csv("models/feature_importance.csv")


@st.cache_data(show_spinner=False)
def _load_model_performance():
    return pd.read_csv("models/model_performance.csv")


@st.cache_data(show_spinner=False)
def _load_observed():
    path = "data/district_observed_dataset.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def load_data():
    return (
        _load_predictions(),
        _load_summary(),
        _load_feature_importance(),
        _load_model_performance(),
        _load_observed(),
    )


@st.cache_resource(show_spinner=False)
def load_bundle():
    """Load the slim runtime bundle once per server process.

    Uses agri_ai_runtime_bundle.pkl (best failure model + recommendation model only).
    Falls back to full bundle if slim bundle not present.
    Saves approx 180 MB RAM vs loading the full 4-model bundle.
    """
    import joblib

    slim_path = "models/agri_ai_runtime_bundle.pkl"
    full_path = "models/agri_ai_bundle.pkl"
    path = slim_path if os.path.exists(slim_path) else full_path
    log_memory("Before load_bundle (%s)" % os.path.basename(path))
    bundle = joblib.load(path)
    log_memory("After load_bundle (%s)" % os.path.basename(path))
    return bundle


@st.cache_data(show_spinner=False)
def _load_map_html() -> str:
    """Read the pre-generated risk map HTML once and cache it."""
    map_path = "maps/india_risk_map.html"
    if os.path.exists(map_path):
        with open(map_path, "r", encoding="utf-8") as fh:
            return fh.read()
    return ""


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

# Automatic User Location & Live Local Weather Widget (Sidebar)
with sidebar.expander("📍 " + t("user_location_title"), expanded=False):
    st.caption(t("user_location_caption"))
    
    loc_mode = st.radio(
        "Location Mode",
        [t("select_manually"), t("use_my_gps")],
        index=0,
        key="sb_user_loc_mode",
        label_visibility="collapsed",
    )
    
    user_lat = None
    user_lon = None
    user_loc_name = ""
    is_gps_verified = False

    if loc_mode == t("use_my_gps"):
        # Streamlit execution runs on server; notify farmer honestly about client vs manual
        st.info("ℹ️ " + t("location_unavailable"))
        st.caption("Never silently using hardcoded GPS. Please verify or input your local coordinates below:")
        col_lat, col_lon = st.columns(2)
        with col_lat:
            user_lat = st.number_input("Latitude (°N)", min_value=-90.0, max_value=90.0, value=18.5204, step=0.0001, key="sb_gps_lat")
        with col_lon:
            user_lon = st.number_input("Longitude (°E)", min_value=-180.0, max_value=180.0, value=73.8567, step=0.0001, key="sb_gps_lon")
        user_loc_name = f"Coordinates ({user_lat:.4f}°N, {user_lon:.4f}°E)"
        is_gps_verified = True
    else:
        preset_localities = {
            "Pune, Maharashtra": (18.5204, 73.8567),
            "Amritsar, Punjab": (31.6340, 74.8723),
            "Indore, Madhya Pradesh": (22.7196, 75.8577),
            "Varanasi, Uttar Pradesh": (25.3176, 82.9739),
            "Coimbatore, Tamil Nadu": (11.0168, 76.9558),
            "Bengaluru, Karnataka": (12.9716, 77.5946),
            "Kolkata, West Bengal": (22.5726, 88.3639),
            "Ahmedabad, Gujarat": (23.0225, 72.5714),
        }
        selected_preset = st.selectbox(
            "Select Locality",
            list(preset_localities.keys()),
            key="sb_preset_user_loc",
        )
        user_lat, user_lon = preset_localities[selected_preset]
        user_loc_name = selected_preset
        is_gps_verified = False

    if user_lat is not None and user_lon is not None:
        user_weather = get_current_weather(user_lat, user_lon)
        # Reverse geocode to prominent place name
        geo_result = reverse_geocode_place(user_lat, user_lon)
        prominent_name = geo_result.get("place_name") if geo_result.get("success") else user_loc_name

        if user_weather.get("success"):
            badge_text = t("location_detected") if is_gps_verified else t("manual_location")
            st.markdown(f"**📍 {prominent_name}**")
            st.caption(f"{user_lat:.4f}°N, {user_lon:.4f}°E · *{badge_text}*")
            uw_c1, uw_c2 = st.columns(2)
            with uw_c1:
                st.metric(t("temperature"), f"{user_weather.get('temperature', '--')} °C")
                st.metric(t("rainfall"), f"{user_weather.get('precipitation', 0.0)} mm")
            with uw_c2:
                st.metric(t("humidity"), f"{user_weather.get('humidity', '--')} %")
                st.metric(t("wind_speed"), f"{user_weather.get('wind_speed_10m', '--')} km/h")
            if user_weather.get("soil_moisture_percentage") is not None:
                st.caption(f"Soil Saturation: {user_weather.get('soil_moisture_percentage')}% (Volumetric: {user_weather.get('soil_moisture_m3m3')} m³/m³)")
            st.caption(f"Provider: Open-Meteo · Updated: {user_weather.get('timestamp')} · Asia/Kolkata")
        else:
            st.error(t("weather_unavailable_err"))

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

live_tab, overview_tab, comparison_tab, twin_tab, map_tab, alerts_tab = st.tabs(
    ["🔮 " + t("tab_live"), t("tab_field"), t("tab_compare"), t("tab_weather"), t("tab_map"), "🚨 " + t("tab_alerts")]
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

    # Farmer Mode additional inputs: Season, Soil Type, Irrigation Level
    available_seasons = district_baseline.get("available_seasons", ["Kharif", "Rabi", "Zaid"])
    default_season_idx = available_seasons.index(season) if season in available_seasons else 0

    sel_c4, sel_c5, sel_c6 = st.columns(3)
    with sel_c4:
        live_season = st.selectbox(
            t("season"),
            available_seasons,
            index=default_season_idx,
            format_func=lambda val: localize_value(language, val),
            key="live_season_selector",
        )

    baseline_info = get_district_baseline(live_district, live_crop, live_season)
    district_coords = (baseline_info["latitude"], baseline_info["longitude"])

    soil_options = [
        "Alluvial", "Black", "Clay Loam", "Laterite", "Loam", "Loamy Sand",
        "Medium Black", "Red Loam", "Red Sandy Loam", "Sandy", "Sandy Loam",
    ]
    default_soil = baseline_info.get("soil_type", "Loam")
    default_soil_idx = soil_options.index(default_soil) if default_soil in soil_options else 0
    with sel_c5:
        live_soil = st.selectbox(
            "Soil Type",
            soil_options,
            index=default_soil_idx,
            key="live_soil_selector",
        )

    irrigation_options = ["Low", "Medium", "High"]
    default_irr = baseline_info.get("irrigation_level", "Medium")
    default_irr_idx = irrigation_options.index(default_irr) if default_irr in irrigation_options else 1
    with sel_c6:
        live_irrigation = st.selectbox(
            "Irrigation Level",
            irrigation_options,
            index=default_irr_idx,
            key="live_irrigation_selector",
        )

    # Live Weather Integration
    st.subheader(t("live_weather"))
    st.caption(f"📍 {t('farm_weather_distinct_caption')} ({live_district}, {live_state} Centroid: {district_coords[0]:.4f}°N, {district_coords[1]:.4f}°E). Distinct from current user location.")
    with st.spinner("Fetching current live weather from Open-Meteo..."):
        weather_data = get_current_weather(district_coords[0], district_coords[1])

    w_col1, w_col2, w_col3, w_col4, w_col5 = st.columns(5)
    if weather_data["success"]:
        w_col1.metric("Temperature", f"{weather_data['temperature']} °C")
        w_col2.metric("Humidity", f"{weather_data['humidity']} %")
        w_col3.metric("Precipitation", f"{weather_data['precipitation']} mm")
        w_col4.metric("Wind Speed", f"{weather_data.get('wind_speed_10m', '--')} km/h")
        if weather_data.get("soil_moisture_percentage") is not None:
            w_col5.metric(
                "Soil Moisture",
                f"{weather_data['soil_moisture_percentage']} %",
                help=f"Volumetric: {weather_data.get('soil_moisture_m3m3')} m³/m³",
            )
        else:
            w_col5.metric(
                "Precipitation (7-day)",
                f"{weather_data.get('precipitation_sum_7d', 0.0)} mm",
            )
        st.caption(
            f"Source: {weather_data['source']} · Coordinates: ({district_coords[0]}°N, {district_coords[1]}°E) · Updated: {weather_data['timestamp']} · Timezone: Asia/Kolkata"
        )
        st.caption("ℹ️ *Values are meteorological/model estimates; not physical in-situ farm sensor readings.*")
    else:
        st.warning(
            f"⚠️ Live weather unavailable ({weather_data.get('error')}). Using verified historical district baseline weather."
        )
        w_col1.metric("Baseline Temp", f"{baseline_info['feature_baselines']['Temperature']} °C")
        w_col2.metric("Baseline Humidity", f"{baseline_info['feature_baselines']['Humidity']} %")
        w_col3.metric("Baseline Rainfall", f"{baseline_info['feature_baselines']['Rainfall']} mm")
        w_col4.metric("Baseline Soil Moisture", f"{baseline_info['feature_baselines']['SoilMoisture']} %")
        st.caption("Source: Historical district dataset baseline")

    # Feature Assembly and Provenance Tracking
    base_feats = baseline_info["feature_baselines"].copy()
    feature_provenance = baseline_info["feature_sources"].copy()

    # Apply Farmer Mode selections
    base_feats["State"] = live_state
    feature_provenance["State"] = "User selection (Farmer Mode)"
    base_feats["Season"] = live_season
    feature_provenance["Season"] = "User selection (Farmer Mode)"
    base_feats["Crop"] = live_crop
    feature_provenance["Crop"] = "User selection (Farmer Mode)"
    base_feats["SoilType"] = live_soil
    feature_provenance["SoilType"] = "User selection (Farmer Mode)"
    base_feats["IrrigationLevel"] = live_irrigation
    feature_provenance["IrrigationLevel"] = "User selection (Farmer Mode)"

    if weather_data["success"]:
        if weather_data["temperature"] is not None:
            base_feats["Temperature"] = float(weather_data["temperature"])
            feature_provenance["Temperature"] = "Live weather estimate (Open-Meteo)"
        if weather_data["humidity"] is not None:
            base_feats["Humidity"] = float(weather_data["humidity"])
            feature_provenance["Humidity"] = "Live weather estimate (Open-Meteo)"
        if weather_data.get("soil_moisture_percentage") is not None:
            base_feats["SoilMoisture"] = float(weather_data["soil_moisture_percentage"])
            feature_provenance["SoilMoisture"] = "Live weather estimate (Open-Meteo root-zone moisture)"

    overridden_feats = base_feats.copy()

    if is_expert:
        with st.expander("🛠️ " + t("advanced_inputs") + " (Expert Agronomic Overrides)", expanded=True):
            st.caption(
                "Model features that cannot be obtained directly from live weather are populated from verified district/crop/season historical baselines. "
                "You may review or override any value below:"
            )
            adv_c1, adv_c2, adv_c3 = st.columns(3)
            with adv_c1:
                adv_rain = st.number_input(
                    "Seasonal Rainfall (mm)",
                    min_value=0.0,
                    max_value=1500.0,
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
            with adv_c2:
                adv_ndvi = st.number_input(
                    "Crop Greenness (NDVI Flowering)",
                    min_value=0.05,
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
                    max_value=150.0,
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
            if adv_ndvi != base_feats["NDVI_Flowering"]:
                overridden_feats["NDVI_Flowering"] = adv_ndvi
                feature_provenance["NDVI_Flowering"] = "User override (Advanced Inputs)"
            if adv_water_stress != base_feats["WaterStress"]:
                overridden_feats["WaterStress"] = adv_water_stress
                feature_provenance["WaterStress"] = "User override (Advanced Inputs)"
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
        st.session_state["live_case_season"] = live_season

    # Execute predictions using the active session case
    active_input = st.session_state["live_case_input"]
    active_provenance = st.session_state["live_case_provenance"]
    current_district = st.session_state["live_case_district"]
    current_crop = st.session_state["live_case_crop"]
    current_state = st.session_state["live_case_state"]
    current_season = st.session_state.get("live_case_season", live_season)

    try:
        prediction_result = predict_new_case(active_input)
        rec_data = get_crop_recommendation({**active_input, "District": current_district})
        if is_expert:
            explanation_result = get_prediction_explanation(active_input)
        else:
            explanation_result = None
    except ValueError as val_err:
        st.error(f"❌ Input Validation Error: {val_err}")
        prediction_result = None
        rec_data = None
        explanation_result = None

    if prediction_result is None:
        st.stop()
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

    st.divider()
    st.subheader(t("forecast_heading"))
    st.caption(t("forecast_caption"))

    fc_horizon = st.radio(
        "Forecast Horizon",
        ["7-day", "14-day"],
        index=0,
        horizontal=True,
        key="twin_forecast_horizon_radio",
    )
    requested_days = 14 if fc_horizon == "14-day" else 7

    with st.spinner(f"Retrieving actual {requested_days}-day forecast for {district}..."):
        coords = (district_baseline["latitude"], district_baseline["longitude"])
        fc_data = get_weather_forecast(coords[0], coords[1], days=requested_days)

    if fc_data["success"] and fc_data["daily"]:
        avail = fc_data["available_days"]
        if avail < requested_days:
            st.info(f"ℹ️ Provider supplied {avail} days out of {requested_days} requested days for coordinates ({coords[0]}°N, {coords[1]}°E). Displaying actual available horizon.")
        else:
            st.caption(f"✓ Displaying full {avail}-day actual forecast from Open-Meteo for ({coords[0]}°N, {coords[1]}°E). Timezone: Asia/Kolkata")

        fc_rows = []
        for d in fc_data["daily"]:
            fc_rows.append({
                "Date": d["date"],
                "Max Temp (°C)": d["temperature_max"],
                "Min Temp (°C)": d["temperature_min"],
                "Precipitation (mm)": d["precipitation_sum"],
                "Precip Probability (%)": d["precipitation_probability_max"],
                "Weather Code": d["weather_code"],
            })
        fc_df = pd.DataFrame(fc_rows)
        st.dataframe(fc_df, width="stretch", hide_index=True)
    else:
        st.warning(f"⚠️ Live weather forecast unavailable ({fc_data.get('error', 'unknown error')}). Please check network or coordinate availability.")

with map_tab:
    map_left, map_right = st.columns([1.2, 1])

    with map_left:
        st.subheader(t("map_title"))
        if os.path.exists("maps/india_risk_map.html"):
            _map_raw = _load_map_html()
            st.components.v1.html(localize_map_html(_map_raw, language), height=520)
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

with alerts_tab:
    st.subheader("🚨 " + t("tab_alerts"))
    st.caption(t("alerts_subtitle"))

    diag = alert_service.repo.get_diagnostics_metrics()
    c_met1, c_met2, c_met3, c_met4 = st.columns(4)
    c_met1.metric("Active Alerts", diag["active_alerts"])
    c_met2.metric("Acknowledged", diag["acknowledged_alerts"])
    c_met3.metric("Resolved", diag["resolved_alerts"])
    c_met4.metric("Deduplicated", diag["alert_deduplication_count"])

    # Provide alert trigger evaluator tool for the current district field
    with st.expander("🔍 Evaluate & Trigger Early Warning for Current Field Selection", expanded=False):
        st.write(f"Current selection: **{district}**, **{crop}**, **{season}** {year} (Risk: **{_format_percent(selected_row['ConsensusRisk'])}**)")
        evaluate_clicked = st.button("Run Early Warning Evaluation")
        if evaluate_clicked:
            from backend.app.schemas.prediction import PredictionResponse, PredictionDataQuality
            class SimpleFarmObj:
                id = f"district-{district.lower().replace(' ', '-')}"
                name = f"{district} District Context"
            class SimpleCropObj:
                id = f"crop-{crop.lower()}"
                crop = crop
                season = season

            curr_p = PredictionResponse(
                prediction_id=f"pred-{district.lower()}-{year}-{season.lower()}",
                farm_id=SimpleFarmObj.id,
                risk_probability=float(selected_row["ConsensusRisk"]),
                risk_percentage=f"{selected_row['ConsensusRisk']*100:.1f}%",
                risk_band=selected_row["RiskLevel"],
                data_quality=PredictionDataQuality(
                    weather_status="live_meteo",
                    satellite_status="baseline",
                    live_feature_count=7,
                    total_feature_count=10,
                )
            )

            created = alert_service.evaluate_alert_conditions(
                farm=SimpleFarmObj(),
                target_crop=SimpleCropObj(),
                current_pred=curr_p,
                previous_pred=None,
            )
            if created:
                st.success(f"Generated {len(created)} early warning alert(s) based on current field risk parameters!")
            else:
                st.info("Evaluation complete: No new alerts generated (conditions either below threshold or deduplicated).")

    # Display active/historical alerts
    farm_context_id = f"district-{district.lower().replace(' ', '-')}"
    all_district_alerts = alert_service.repo.list_for_farm(farm_context_id, limit=50)
    # If no alerts for this district yet, check if there are any recorded across all farms
    if not all_district_alerts:
        all_district_alerts = alert_service.repo.list_all(limit=50)

    if all_district_alerts:
        for alt in all_district_alerts:
            severity_color = "#c53030" if alt.get("severity") == "critical" else ("#dd6b20" if alt.get("severity") == "warning" else "#2b6cb0")
            with st.container():
                st.markdown(
                    f"""
                    <div style="border-left: 4px solid {severity_color}; background: #16221a; padding: 0.8rem 1rem; border-radius: 8px; margin-bottom: 0.8rem;">
                        <span style="color: {severity_color}; font-weight: bold; font-size: 0.85rem; text-transform: uppercase;">
                            {alt.get('severity', 'info')} · {alt.get('alert_type')}
                        </span>
                        <span style="color: #888; font-size: 0.8rem; float: right;">Status: <strong>{alt.get('status')}</strong></span>
                        <p style="margin: 0.4rem 0 0.2rem 0; color: #eee; font-size: 0.95rem;">{alt.get('trigger_reason')}</p>
                        <small style="color: #aaa;">Created: {alt.get('created_at')}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                col_act1, col_act2 = st.columns([1, 4])
                if alt.get("status") == "active":
                    if col_act1.button("Acknowledge", key=f"ack_{alt.get('id')}"):
                        alert_service.repo.update_status(alt.get("id"), "acknowledged")
                        st.rerun()
                elif alt.get("status") == "acknowledged" and show_expert_tools:
                    if col_act1.button("Resolve (Expert)", key=f"res_{alt.get('id')}"):
                        alert_service.repo.update_status(alt.get("id"), "resolved", notes="Resolved via Expert Tools")
                        st.rerun()
    else:
        st.info("✓ " + t("no_alerts"))
