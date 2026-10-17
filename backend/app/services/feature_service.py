"""Stage-Aware Live Feature Engineering and Feature Assembly Layer.

Responsible for assembling the exact 16 features required by the trained
crop-failure ML model bundle:
- 6 Categorical: State, Region, Season, Crop, SoilType, IrrigationLevel
- 10 Numerical: Year, Rainfall, Temperature, Humidity, SoilMoisture,
               NDVI_Flowering, WaterStress, PestRisk, SuitabilityScore, YieldIndex

Design Principles:
1. Agronomic Integrity: Does NOT silently substitute instantaneous Sentinel-2 NDVI
   for NDVI_Flowering without verifying crop flowering phenology.
2. Defensible Weather Accumulation: Accumulates historical precipitation when
   crop dates and observations exist; falls back gracefully to empirical medians.
3. Strict Schema Compatibility: Guarantees exact 16-feature names, types, and bounds.
4. Comprehensive Provenance: Tracks every feature's liveness, source, and transformation.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.app.core.logging import logger
from backend.app.services.satellite.schemas import SatelliteObservationResponse
from backend.app.services.weather.schemas import CurrentWeatherResponse, WeatherObservationRecord
from src.live_prediction import NUMERIC_BOUNDS, VALID_CATEGORIES, normalize_soil_type, normalize_state, validate_prediction_input


# Agronomic flowering windows (Days After Sowing - DAS) for major Indian crops
CROP_FLOWERING_WINDOWS: Dict[str, Tuple[int, int]] = {
    "rice": (55, 90),
    "wheat": (60, 90),
    "maize": (45, 75),
    "cotton": (70, 115),
    "soybean": (45, 75),
    "groundnut": (40, 75),
    "chickpea": (50, 80),
    "mustard": (45, 75),
    "pigeonpea": (70, 120),
    "sugarcane": (120, 240),
    "millet": (45, 70),
}
DEFAULT_FLOWERING_WINDOW: Tuple[int, int] = (50, 90)

# Typical crop cycle duration in days
CROP_TOTAL_DURATION_DAYS: Dict[str, int] = {
    "rice": 120,
    "wheat": 120,
    "maize": 100,
    "cotton": 160,
    "soybean": 100,
    "groundnut": 110,
    "chickpea": 110,
    "mustard": 105,
    "pigeonpea": 160,
    "sugarcane": 360,
    "millet": 90,
}
DEFAULT_CROP_DURATION_DAYS = 120

FLOWERING_STAGE_KEYWORDS = {"flowering", "reproductive", "grain formation", "silking", "tasseling", "podding"}


@dataclass
class FeatureProvenanceItem:
    """Detailed provenance for an individual assembled model feature."""

    feature_name: str
    value: Any
    source_type: str  # 'live_farm', 'live_weather', 'live_satellite', 'historical_baseline', 'expert_override', 'derived'
    source_reference: str  # e.g., 'Open-Meteo', 'Sentinel-2 L2A', 'district_dataset.csv'
    is_live: bool
    is_baseline: bool
    is_derived: bool = False
    observation_timestamp: Optional[str] = None
    freshness: str = "fresh"  # 'fresh', 'acceptable', 'stale_fallback', 'stage_fallback', 'fallback', 'static', 'override', 'current'
    calculation_method: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_summary_string(self) -> str:
        """User/expert facing summary string."""
        if self.source_type == "expert_override":
            return f"User override ({self.source_reference})"
        if self.source_type == "live_satellite":
            obs_d = self.observation_timestamp or self.details.get("observation_date", "")
            stage = self.details.get("stage_context", "")
            return f"Live Sentinel-2 NDVI ({obs_d}, {stage})"
        if self.source_type == "live_weather":
            return f"Live weather ({self.source_reference})"
        if self.source_type == "accumulated_weather":
            acc_mm = self.details.get("rainfall_accumulation_mm")
            start_d = self.details.get("rainfall_period_start", "")
            end_d = self.details.get("rainfall_period_end", "")
            return f"Accumulated rainfall ({acc_mm:.1f}mm from {start_d} to {end_d})"
        if self.source_type == "historical_baseline":
            reason = self.details.get("baseline_reason", "District-crop median")
            return f"Historical baseline ({reason})"
        if self.source_type == "live_farm":
            return f"Farm profile ({self.source_reference})"
        return f"{self.source_reference} ({self.calculation_method})"


@dataclass
class FeatureAssemblyResult:
    """Result of feature assembly containing exact 16 inputs, provenance, and metadata."""

    features: Dict[str, Any]
    provenance: Dict[str, str]
    feature_provenance: Dict[str, FeatureProvenanceItem]
    is_valid: bool
    validation_error: Optional[str] = None
    is_fallback_weather: bool = False
    is_fallback_satellite: bool = True
    rainfall_metadata: Dict[str, Any] = field(default_factory=dict)
    satellite_metadata: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)


class StageAwareNDVIEngine:
    """Evaluates crop growth stage and derives phenology-aware NDVI_Flowering."""

    @classmethod
    def derive_ndvi_flowering(
        cls,
        crop_name: str,
        growth_stage: Optional[str],
        sowing_date: Optional[Union[date, str]],
        baseline_ndvi_flowering: float,
        satellite_observation: Optional[SatelliteObservationResponse],
        historical_observations: Optional[List[SatelliteObservationResponse]] = None,
    ) -> FeatureProvenanceItem:
        """Derive NDVI_Flowering safely with phenology verification.

        Rules:
        1. If satellite observation is missing or invalid: use baseline.
        2. If crop growth stage is explicitly flowering or DAS is within flowering window:
           use Sentinel-2 observation ndvi_mean.
        3. If crop is in a non-flowering stage (Sowing, Vegetative, Maturity, Harvest):
           keep historical baseline to avoid distorting peak vigor representation.
        """
        crop_key = (crop_name or "").strip().lower()
        flowering_window = CROP_FLOWERING_WINDOWS.get(crop_key, DEFAULT_FLOWERING_WINDOW)

        # Parse sowing date
        sow_d: Optional[date] = None
        if isinstance(sowing_date, str) and sowing_date.strip():
            try:
                sow_d = date.fromisoformat(sowing_date.strip())
            except ValueError:
                sow_d = None
        elif isinstance(sowing_date, date):
            sow_d = sowing_date

        stage_str = (growth_stage or "").strip().lower()

        # Check if we have satellite observations
        candidate_obs: List[SatelliteObservationResponse] = []
        if satellite_observation and satellite_observation.success and satellite_observation.ndvi is not None:
            candidate_obs.append(satellite_observation)
        if historical_observations:
            for obs in historical_observations:
                if obs.success and obs.ndvi is not None and obs not in candidate_obs:
                    candidate_obs.append(obs)

        if not candidate_obs:
            return FeatureProvenanceItem(
                feature_name="NDVI_Flowering",
                value=float(baseline_ndvi_flowering),
                source_type="historical_baseline",
                source_reference="district_dataset.csv",
                is_live=False,
                is_baseline=True,
                is_derived=False,
                freshness="fallback",
                calculation_method="District-Crop-Season Median",
                details={
                    "baseline_reason": "No satellite telemetry available",
                    "baseline_value": baseline_ndvi_flowering,
                },
            )

        # Evaluate candidate observations against flowering context
        today = date.today()
        for obs in candidate_obs:
            obs_d: Optional[date] = None
            if obs.observation_date:
                try:
                    obs_d = date.fromisoformat(str(obs.observation_date))
                except ValueError:
                    obs_d = None

            # Freshness rule: Satellite observations older than 30 days are considered stale
            is_stale_sat = False
            if obs_d and (today - obs_d).days > 30:
                is_stale_sat = True

            das: Optional[int] = (obs_d - sow_d).days if (obs_d and sow_d) else None

            sat_name = getattr(obs, "satellite", getattr(obs, "source", "Sentinel-2"))
            sat_prov = getattr(obs, "provider", "GoogleEarthEngine")
            valid_px = obs.ndvi.valid_pixels if obs.ndvi else getattr(obs, "valid_pixels", None)
            cloud_pct = obs.ndvi.scene_cloud_percent if obs.ndvi else getattr(obs, "cloud_percentage", None)

            if is_stale_sat:
                # Stale observation: fallback to baseline and record reason
                obs_age = (today - obs_d).days if obs_d else "unknown"
                return FeatureProvenanceItem(
                    feature_name="NDVI_Flowering",
                    value=float(baseline_ndvi_flowering),
                    source_type="historical_baseline",
                    source_reference="district_dataset.csv",
                    is_live=False,
                    is_baseline=True,
                    is_derived=False,
                    observation_timestamp=str(obs.observation_date) if obs.observation_date else None,
                    freshness="stale_fallback",
                    calculation_method="District-Crop-Season Median (Telemetry older than 30 days)",
                    details={
                        "baseline_reason": f"Satellite observation from {obs.observation_date} is {obs_age} days old (>30d limit)",
                        "baseline_value": baseline_ndvi_flowering,
                        "observation_date": str(obs.observation_date),
                        "age_days": obs_age,
                    },
                )

            # Case A: Explicit Flowering Growth Stage
            if any(k in stage_str for k in FLOWERING_STAGE_KEYWORDS):
                ndvi_val = float(obs.ndvi.mean)
                return FeatureProvenanceItem(
                    feature_name="NDVI_Flowering",
                    value=round(ndvi_val, 4),
                    source_type="live_satellite",
                    source_reference=f"{sat_prov} ({sat_name})",
                    is_live=True,
                    is_baseline=False,
                    is_derived=False,
                    observation_timestamp=str(obs.observation_date) if obs.observation_date else None,
                    freshness="fresh",
                    calculation_method="Sentinel-2 L2A 10m NDVI during flowering stage",
                    details={
                        "observation_date": str(obs.observation_date),
                        "stage_context": f"Active growth stage '{growth_stage}'",
                        "raw_ndvi_mean": obs.ndvi.mean,
                        "raw_ndvi_min": obs.ndvi.min,
                        "raw_ndvi_max": obs.ndvi.max,
                        "valid_pixels": valid_px,
                        "cloud_percentage": cloud_pct,
                        "geometry_fingerprint": obs.raw_metadata.get("geometry_fingerprint") if obs.raw_metadata else None,
                    },
                )

            # Case B: Days After Sowing (DAS) in Flowering Window (and not explicitly non-flowering stage)
            NON_FLOWERING_STAGE_KEYWORDS = {"vegetative", "sowing", "seedling", "maturity", "harvest", "ripening"}
            if das is not None and flowering_window[0] <= das <= flowering_window[1] and not any(k in stage_str for k in NON_FLOWERING_STAGE_KEYWORDS):
                ndvi_val = float(obs.ndvi.mean)
                return FeatureProvenanceItem(
                    feature_name="NDVI_Flowering",
                    value=round(ndvi_val, 4),
                    source_type="live_satellite",
                    source_reference=f"{sat_prov} ({sat_name})",
                    is_live=True,
                    is_baseline=False,
                    is_derived=False,
                    observation_timestamp=str(obs.observation_date) if obs.observation_date else None,
                    freshness="fresh",
                    calculation_method=f"Sentinel-2 L2A 10m NDVI during flowering window (DAS={das}, range={flowering_window[0]}-{flowering_window[1]}d)",
                    details={
                        "observation_date": str(obs.observation_date),
                        "stage_context": f"Flowering window verified (DAS={das})",
                        "das": das,
                        "flowering_window": list(flowering_window),
                        "raw_ndvi_mean": obs.ndvi.mean,
                        "valid_pixels": valid_px,
                        "cloud_percentage": cloud_pct,
                    },
                )

        # Case C: Telemetry exists, but observation date is NOT in flowering stage
        # Keep baseline and document explicitly
        first_obs = candidate_obs[0]
        obs_d_str = str(first_obs.observation_date or "recent")
        calc_das = (date.fromisoformat(obs_d_str) - sow_d).days if (sow_d and obs_d_str != "recent") else "unknown"
        reason_msg = (
            f"Crop in '{growth_stage or 'Vegetative'}' stage (DAS={calc_das}); "
            f"instantaneous Sentinel-2 NDVI ({first_obs.ndvi.mean:.3f}) not representative of peak flowering canopy vigor"
        )

        return FeatureProvenanceItem(
            feature_name="NDVI_Flowering",
            value=float(baseline_ndvi_flowering),
            source_type="historical_baseline",
            source_reference="district_dataset.csv",
            is_live=False,
            is_baseline=True,
            is_derived=False,
            observation_timestamp=obs_d_str,
            freshness="stage_fallback",
            calculation_method="District-Crop-Season Median (Stage Calibration)",
            details={
                "baseline_reason": reason_msg,
                "baseline_value": baseline_ndvi_flowering,
                "available_instantaneous_ndvi": first_obs.ndvi.mean,
                "observation_date": obs_d_str,
                "growth_stage": growth_stage,
            },
        )


class RainfallAccumulationEngine:
    """Calculates defensible rainfall accumulation across active crop cycle."""

    @classmethod
    def calculate_rainfall(
        cls,
        crop_name: str,
        sowing_date: Optional[Union[date, str]],
        baseline_rainfall: float,
        weather: Optional[CurrentWeatherResponse],
        historical_weather: Optional[List[WeatherObservationRecord]] = None,
    ) -> FeatureProvenanceItem:
        """Calculate seasonal rainfall input.

        Rules:
        1. If sowing_date is known and historical daily observations cover >= 14 days:
           accumulate recorded precipitation + project remainder of standard season.
        2. If 7-day live weather is available and crop is very young or sowing date missing:
           use baseline median to preserve seasonal scale compatibility, recording live 7d context.
        3. If no weather data: use baseline median.
        """
        crop_key = (crop_name or "").strip().lower()
        duration_days = CROP_TOTAL_DURATION_DAYS.get(crop_key, DEFAULT_CROP_DURATION_DAYS)

        sow_d: Optional[date] = None
        if isinstance(sowing_date, str) and sowing_date.strip():
            try:
                sow_d = date.fromisoformat(sowing_date.strip())
            except ValueError:
                sow_d = None
        elif isinstance(sowing_date, date):
            sow_d = sowing_date

        today = date.today()

        # Check historical recorded observations
        if sow_d and historical_weather:
            valid_recs = []
            for rec in historical_weather:
                rec_dt = None
                if rec.observation_time:
                    try:
                        rec_dt = datetime.fromisoformat(str(rec.observation_time).replace("Z", "+00:00")).date()
                    except Exception:
                        pass
                if rec_dt and rec_dt >= sow_d and rec.precipitation_mm is not None:
                    valid_recs.append((rec_dt, float(rec.precipitation_mm)))

            if len(valid_recs) >= 14:
                # Group by date to avoid duplicate hourly summing if stored hourly
                daily_map: Dict[date, float] = {}
                for d, p in valid_recs:
                    daily_map[d] = max(daily_map.get(d, 0.0), p)

                accumulated_mm = sum(daily_map.values())
                days_observed = len(daily_map)
                das = (today - sow_d).days

                # If season completed
                if das >= duration_days:
                    final_rainfall = min(max(accumulated_mm, 0.0), 1500.0)
                    return FeatureProvenanceItem(
                        feature_name="Rainfall",
                        value=round(final_rainfall, 1),
                        source_type="accumulated_weather",
                        source_reference="Supabase public.weather_observations",
                        is_live=True,
                        is_baseline=False,
                        is_derived=True,
                        observation_timestamp=today.isoformat(),
                        freshness="fresh",
                        calculation_method=f"Full-season recorded accumulation ({days_observed} days)",
                        details={
                            "rainfall_source": "weather_observations_history",
                            "rainfall_period_start": sow_d.isoformat(),
                            "rainfall_period_end": today.isoformat(),
                            "rainfall_accumulation_mm": round(accumulated_mm, 1),
                            "days_observed": days_observed,
                        },
                    )
                else:
                    # In-season projection: Observed accumulation + (Baseline Daily Rate * Remaining Days)
                    remaining_days = max(duration_days - das, 0)
                    normal_daily_rate = baseline_rainfall / duration_days
                    projected_total = accumulated_mm + (normal_daily_rate * remaining_days)
                    bounded_total = min(max(projected_total, 0.0), 1500.0)

                    return FeatureProvenanceItem(
                        feature_name="Rainfall",
                        value=round(bounded_total, 1),
                        source_type="accumulated_weather",
                        source_reference="Supabase weather_observations + Regional Normal Projection",
                        is_live=False,
                        is_baseline=False,
                        is_derived=True,
                        observation_timestamp=today.isoformat(),
                        freshness="fresh",
                        calculation_method=f"Accumulated ({accumulated_mm:.1f}mm over {das}d) + projected baseline ({normal_daily_rate * remaining_days:.1f}mm over {remaining_days}d)",
                        details={
                            "rainfall_source": "projected_accumulation",
                            "rainfall_period_start": sow_d.isoformat(),
                            "rainfall_period_end": today.isoformat(),
                            "rainfall_accumulation_mm": round(accumulated_mm, 1),
                            "das": das,
                            "remaining_days": remaining_days,
                        },
                    )

        # Fallback to historical baseline with live 7-day weather note if available
        precip_7d = weather.precipitation_sum_7d if (weather and weather.success) else None
        details_dict: Dict[str, Any] = {
            "baseline_reason": "District seasonal normal (insufficient continuous daily accumulation series)",
            "baseline_value": baseline_rainfall,
        }
        if precip_7d is not None:
            details_dict["live_7d_precipitation_mm"] = precip_7d

        return FeatureProvenanceItem(
            feature_name="Rainfall",
            value=float(baseline_rainfall),
            source_type="historical_baseline",
            source_reference="district_dataset.csv",
            is_live=False,
            is_baseline=True,
            is_derived=False,
            freshness="fallback",
            calculation_method="District-Crop-Season Median",
            details=details_dict,
        )


class FeatureAssembler:
    """Unified feature assembly layer for ML inference and SHAP explainability."""

    @classmethod
    def assemble_features(
        cls,
        farm_state: str,
        farm_district: str,
        farm_region: Optional[str] = None,
        farm_soil_type: Optional[str] = None,
        farm_irrigation_level: Optional[str] = None,
        crop_name: str = "Rice",
        crop_season: str = "Kharif",
        crop_sowing_date: Optional[Union[date, str]] = None,
        crop_growth_stage: Optional[str] = None,
        crop_soil_type: Optional[str] = None,
        crop_irrigation_level: Optional[str] = None,
        weather: Optional[CurrentWeatherResponse] = None,
        historical_weather: Optional[List[WeatherObservationRecord]] = None,
        satellite_observation: Optional[SatelliteObservationResponse] = None,
        historical_satellite: Optional[List[SatelliteObservationResponse]] = None,
        baseline_info: Optional[Dict[str, Any]] = None,
        overrides: Optional[Dict[str, float]] = None,
        bundle: Optional[dict] = None,
    ) -> FeatureAssemblyResult:
        """Construct the exact 16 model features with complete provenance."""
        # 1. District baselines
        if not baseline_info:
            from src.live_prediction import get_district_baseline
            baseline_info = get_district_baseline(district=farm_district, crop=crop_name, season=crop_season)

        feature_baselines = baseline_info.get("feature_baselines", {})

        features: Dict[str, Any] = {}
        provenance_map: Dict[str, FeatureProvenanceItem] = {}

        # ---------------------------------------------------------------------
        # 1. Categorical Features (6) - Live from Farm & Crop Records
        # ---------------------------------------------------------------------
        # State
        norm_state = normalize_state(farm_state) if farm_state else None
        state_val = norm_state or farm_state
        features["State"] = state_val
        provenance_map["State"] = FeatureProvenanceItem(
            feature_name="State",
            value=state_val,
            source_type="live_farm",
            source_reference=f"Farm Profile ({farm_state})" if (farm_state and farm_state != state_val) else "Farm Profile",
            is_live=True,
            is_baseline=False,
            is_derived=False,
            freshness="static",
            calculation_method="Direct farm state selection (canonical normalized)",
        )

        # Region (Derived from district geographical mapping)
        region_val = farm_region or baseline_info.get("region") or f"{state_val}-Region"
        features["Region"] = region_val
        provenance_map["Region"] = FeatureProvenanceItem(
            feature_name="Region",
            value=region_val,
            source_type="live_farm",
            source_reference="District Agro-Climatic Mapping",
            is_live=False,
            is_baseline=False,
            is_derived=True,
            freshness="static",
            calculation_method="District agro-climatic zone resolution",
        )

        # Season
        features["Season"] = crop_season
        provenance_map["Season"] = FeatureProvenanceItem(
            feature_name="Season",
            value=crop_season,
            source_type="live_farm",
            source_reference="Active Crop Cycle",
            is_live=True,
            is_baseline=False,
            is_derived=False,
            freshness="current",
            calculation_method="Crop cycle season",
        )

        # Crop
        features["Crop"] = crop_name
        provenance_map["Crop"] = FeatureProvenanceItem(
            feature_name="Crop",
            value=crop_name,
            source_type="live_farm",
            source_reference="Active Crop Cycle",
            is_live=True,
            is_baseline=False,
            is_derived=False,
            freshness="current",
            calculation_method="Crop species selection",
        )

        # SoilType
        raw_soil = crop_soil_type or farm_soil_type
        norm_soil = normalize_soil_type(raw_soil) if raw_soil else None
        soil = norm_soil or feature_baselines.get("SoilType", "Medium Black")
        has_soil = bool(raw_soil)
        features["SoilType"] = soil
        provenance_map["SoilType"] = FeatureProvenanceItem(
            feature_name="SoilType",
            value=soil,
            source_type="live_farm" if has_soil else "historical_baseline",
            source_reference=f"Farm/Crop Profile ({raw_soil})" if (has_soil and raw_soil != soil) else ("Farm/Crop Profile" if has_soil else "district_dataset.csv"),
            is_live=has_soil,
            is_baseline=not has_soil,
            is_derived=False,
            freshness="current" if has_soil else "fallback",
            calculation_method="User soil type profile" if has_soil else "District-Crop-Season Median",
        )

        # IrrigationLevel
        irrigation = crop_irrigation_level or farm_irrigation_level or feature_baselines.get("IrrigationLevel", "Medium")
        has_irr = bool(crop_irrigation_level or farm_irrigation_level)
        features["IrrigationLevel"] = irrigation
        provenance_map["IrrigationLevel"] = FeatureProvenanceItem(
            feature_name="IrrigationLevel",
            value=irrigation,
            source_type="live_farm" if has_irr else "historical_baseline",
            source_reference="Farm/Crop Profile" if has_irr else "district_dataset.csv",
            is_live=has_irr,
            is_baseline=not has_irr,
            is_derived=False,
            freshness="current" if has_irr else "fallback",
            calculation_method="User irrigation accessibility profile" if has_irr else "District-Crop-Season Median",
        )

        # ---------------------------------------------------------------------
        # 2. Numerical Features (10)
        # ---------------------------------------------------------------------
        # Year
        curr_year = datetime.now().year
        features["Year"] = curr_year
        provenance_map["Year"] = FeatureProvenanceItem(
            feature_name="Year",
            value=curr_year,
            source_type="live_farm",
            source_reference="System Clock",
            is_live=True,
            is_baseline=False,
            is_derived=False,
            freshness="current",
            calculation_method="Current calendar year",
        )

        # Check weather freshness (24h validity rule)
        is_fallback_weather = True
        is_stale_weather = False
        weather_time_str = None

        if weather and weather.success and weather.temperature is not None:
            # Check timestamp if available
            if weather.timestamp:
                weather_time_str = str(weather.timestamp)
                try:
                    cleaned_ts = weather_time_str.replace("Z", "+00:00").strip()
                    try:
                        w_dt = datetime.fromisoformat(cleaned_ts)
                    except ValueError:
                        w_dt = datetime.strptime(cleaned_ts, "%Y-%m-%d %H:%M")
                    
                    if w_dt.tzinfo is not None:
                        now_dt = datetime.now(timezone.utc)
                    else:
                        now_dt = datetime.now()
                    
                    age_hours = (now_dt - w_dt).total_seconds() / 3600.0
                    if age_hours > 24.0:
                        is_stale_weather = True
                except Exception as ex:
                    logger.debug("Weather timestamp check exception: %s", str(ex))

            if not is_stale_weather:
                is_fallback_weather = False

        # Temperature
        if not is_fallback_weather and weather and weather.temperature is not None:
            temp_val = float(weather.temperature)
            features["Temperature"] = temp_val
            provenance_map["Temperature"] = FeatureProvenanceItem(
                feature_name="Temperature",
                value=temp_val,
                source_type="live_weather",
                source_reference=weather.source,
                is_live=True,
                is_baseline=False,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="fresh",
                calculation_method="Live dry-bulb temperature (2m)",
                details={"timestamp": weather.timestamp},
            )
        else:
            base_temp = float(feature_baselines.get("Temperature", 28.0))
            features["Temperature"] = base_temp
            provenance_map["Temperature"] = FeatureProvenanceItem(
                feature_name="Temperature",
                value=base_temp,
                source_type="historical_baseline",
                source_reference="district_dataset.csv",
                is_live=False,
                is_baseline=True,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="stale_fallback" if is_stale_weather else "fallback",
                calculation_method="District-Crop-Season Median" if not is_stale_weather else "District-Crop-Season Median (Telemetry older than 24h)",
                details={"baseline_reason": "Live weather stale (>24h)" if is_stale_weather else "Live weather unavailable"},
            )

        # Humidity
        if not is_fallback_weather and weather and weather.relative_humidity is not None:
            hum_val = float(weather.relative_humidity)
            features["Humidity"] = hum_val
            provenance_map["Humidity"] = FeatureProvenanceItem(
                feature_name="Humidity",
                value=hum_val,
                source_type="live_weather",
                source_reference=weather.source,
                is_live=True,
                is_baseline=False,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="fresh",
                calculation_method="Live relative humidity (2m)",
                details={"timestamp": weather.timestamp},
            )
        else:
            base_hum = float(feature_baselines.get("Humidity", 65.0))
            features["Humidity"] = base_hum
            provenance_map["Humidity"] = FeatureProvenanceItem(
                feature_name="Humidity",
                value=base_hum,
                source_type="historical_baseline",
                source_reference="district_dataset.csv",
                is_live=False,
                is_baseline=True,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="stale_fallback" if is_stale_weather else "fallback",
                calculation_method="District-Crop-Season Median" if not is_stale_weather else "District-Crop-Season Median (Telemetry older than 24h)",
                details={"baseline_reason": "Live weather stale (>24h)" if is_stale_weather else "Live weather unavailable"},
            )

        # SoilMoisture
        if not is_fallback_weather and weather and weather.soil_moisture_percentage is not None:
            sm_val = float(weather.soil_moisture_percentage)
            features["SoilMoisture"] = sm_val
            provenance_map["SoilMoisture"] = FeatureProvenanceItem(
                feature_name="SoilMoisture",
                value=sm_val,
                source_type="live_weather",
                source_reference=f"{weather.source} (0-27cm)",
                is_live=True,
                is_baseline=False,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="fresh",
                calculation_method="Multi-layer root-zone relative moisture saturation (0-27cm)",
                details={"volumetric_m3m3": weather.soil_moisture_m3m3},
            )
        else:
            base_sm = float(feature_baselines.get("SoilMoisture", 45.0))
            features["SoilMoisture"] = base_sm
            provenance_map["SoilMoisture"] = FeatureProvenanceItem(
                feature_name="SoilMoisture",
                value=base_sm,
                source_type="historical_baseline",
                source_reference="district_dataset.csv",
                is_live=False,
                is_baseline=True,
                is_derived=False,
                observation_timestamp=weather_time_str,
                freshness="stale_fallback" if is_stale_weather else "fallback",
                calculation_method="District-Crop-Season Median" if not is_stale_weather else "District-Crop-Season Median (Telemetry older than 24h)",
                details={"baseline_reason": "Live weather stale (>24h)" if is_stale_weather else "Live weather unavailable"},
            )

        # Rainfall
        base_rainfall = float(feature_baselines.get("Rainfall", 650.0))
        rainfall_prov = RainfallAccumulationEngine.calculate_rainfall(
            crop_name=crop_name,
            sowing_date=crop_sowing_date,
            baseline_rainfall=base_rainfall,
            weather=weather,
            historical_weather=historical_weather,
        )
        features["Rainfall"] = rainfall_prov.value
        provenance_map["Rainfall"] = rainfall_prov

        # NDVI_Flowering (Stage-Aware)
        base_ndvi = float(feature_baselines.get("NDVI_Flowering", 0.55))
        ndvi_prov = StageAwareNDVIEngine.derive_ndvi_flowering(
            crop_name=crop_name,
            growth_stage=crop_growth_stage,
            sowing_date=crop_sowing_date,
            baseline_ndvi_flowering=base_ndvi,
            satellite_observation=satellite_observation,
            historical_observations=historical_satellite,
        )
        features["NDVI_Flowering"] = ndvi_prov.value
        provenance_map["NDVI_Flowering"] = ndvi_prov
        is_fallback_satellite = ndvi_prov.is_baseline

        # WaterStress (Derived Feature)
        base_ws = float(feature_baselines.get("WaterStress", 0.40))
        if not is_fallback_weather and weather and weather.soil_moisture_percentage is not None:
            derived_ws = round(min(max(1.0 - (float(weather.soil_moisture_percentage) / 100.0), 0.05), 0.95), 3)
            features["WaterStress"] = derived_ws
            provenance_map["WaterStress"] = FeatureProvenanceItem(
                feature_name="WaterStress",
                value=derived_ws,
                source_type="derived",
                source_reference="Live Soil Moisture Deficit",
                is_live=False,
                is_baseline=False,
                is_derived=True,
                observation_timestamp=weather_time_str,
                freshness="fresh",
                calculation_method="Derived crop water stress index from live root-zone saturation",
                details={"soil_moisture_pct": weather.soil_moisture_percentage},
            )
        else:
            features["WaterStress"] = base_ws
            provenance_map["WaterStress"] = FeatureProvenanceItem(
                feature_name="WaterStress",
                value=base_ws,
                source_type="historical_baseline",
                source_reference="district_dataset.csv",
                is_live=False,
                is_baseline=True,
                is_derived=False,
                freshness="fallback",
                calculation_method="District-Crop-Season Median",
            )

        # PestRisk (Baseline)
        base_pr = float(feature_baselines.get("PestRisk", 0.35))
        features["PestRisk"] = base_pr
        provenance_map["PestRisk"] = FeatureProvenanceItem(
            feature_name="PestRisk",
            value=base_pr,
            source_type="historical_baseline",
            source_reference="district_dataset.csv",
            is_live=False,
            is_baseline=True,
            is_derived=False,
            freshness="fallback",
            calculation_method="District-Crop-Season Median",
        )

        # SuitabilityScore (Baseline)
        base_ss = float(feature_baselines.get("SuitabilityScore", 0.70))
        features["SuitabilityScore"] = base_ss
        provenance_map["SuitabilityScore"] = FeatureProvenanceItem(
            feature_name="SuitabilityScore",
            value=base_ss,
            source_type="historical_baseline",
            source_reference="district_dataset.csv",
            is_live=False,
            is_baseline=True,
            is_derived=False,
            freshness="fallback",
            calculation_method="District-Crop Agro-Ecological Suitability Score",
        )

        # YieldIndex (Baseline)
        base_yi = float(feature_baselines.get("YieldIndex", 100.0))
        features["YieldIndex"] = base_yi
        provenance_map["YieldIndex"] = FeatureProvenanceItem(
            feature_name="YieldIndex",
            value=base_yi,
            source_type="historical_baseline",
            source_reference="district_dataset.csv",
            is_live=False,
            is_baseline=True,
            is_derived=False,
            freshness="fallback",
            calculation_method="District-Crop Historical Productivity Index",
        )

        # ---------------------------------------------------------------------
        # 3. Apply Manual Expert Overrides (if supplied)
        # ---------------------------------------------------------------------
        if overrides:
            mapping = {
                "rainfall_override": "Rainfall",
                "temperature_override": "Temperature",
                "humidity_override": "Humidity",
                "soil_moisture_override": "SoilMoisture",
                "ndvi_override": "NDVI_Flowering",
                "water_stress_override": "WaterStress",
                "pest_risk_override": "PestRisk",
                "suitability_score_override": "SuitabilityScore",
                "yield_index_override": "YieldIndex",
            }
            for override_key, feat_name in mapping.items():
                val = overrides.get(override_key)
                if val is not None:
                    features[feat_name] = float(val)
                    provenance_map[feat_name] = FeatureProvenanceItem(
                        feature_name=feat_name,
                        value=float(val),
                        source_type="expert_override",
                        source_reference="Advanced Inputs",
                        is_live=False,
                        is_baseline=False,
                        is_derived=False,
                        freshness="override",
                        calculation_method="Manual expert parameter override",
                        details={"override_field": override_key},
                    )

        # ---------------------------------------------------------------------
        # 4. Data Quality & Freshness Coverage Summary
        # ---------------------------------------------------------------------
        live_count = sum(1 for p in provenance_map.values() if p.is_live and not p.is_derived)
        derived_count = sum(1 for p in provenance_map.values() if p.is_derived)
        baseline_count = sum(1 for p in provenance_map.values() if p.is_baseline)
        total_count = len(provenance_map)  # Exactly 16
        live_pct = round((live_count / float(total_count)) * 100.0, 1)

        # Satellite status determination
        if ndvi_prov.is_live:
            satellite_status = "live_fresh"
        elif ndvi_prov.freshness == "stage_fallback":
            satellite_status = "stage_deferred"
        elif ndvi_prov.freshness == "stale_fallback":
            satellite_status = "stale_fallback"
        else:
            satellite_status = "baseline"

        # Weather status determination
        if is_fallback_weather:
            weather_status = "stale_fallback" if is_stale_weather else "baseline"
        elif weather and getattr(weather, "is_cached", False):
            weather_status = "live_cached"
        else:
            weather_status = "live_fresh"

        # Summary label
        if satellite_status == "live_fresh" and weather_status in ("live_fresh", "live_cached"):
            summary_label = "Prediction based on live weather + satellite telemetry"
        elif satellite_status == "stage_deferred" and weather_status in ("live_fresh", "live_cached"):
            summary_label = "Prediction based on live weather + stage-calibrated crop baseline"
        elif live_count >= 8:
            summary_label = "Prediction based on live weather + regional crop baselines"
        else:
            summary_label = "Some model inputs use historical baseline data"

        data_quality = {
            "live_feature_count": live_count,
            "baseline_feature_count": baseline_count,
            "derived_feature_count": derived_count,
            "total_feature_count": total_count,
            "live_feature_percentage": live_pct,
            "satellite_status": satellite_status,
            "weather_status": weather_status,
            "summary_label": summary_label,
        }

        # ---------------------------------------------------------------------
        # 5. Schema & Bounds Validation
        # ---------------------------------------------------------------------
        is_valid, val_err = validate_prediction_input(features, bundle=bundle)

        # Human-readable summary map
        summary_provenance: Dict[str, str] = {
            k: v.to_summary_string() for k, v in provenance_map.items()
        }

        return FeatureAssemblyResult(
            features=features,
            provenance=summary_provenance,
            feature_provenance=provenance_map,
            is_valid=is_valid,
            validation_error=val_err,
            is_fallback_weather=is_fallback_weather,
            is_fallback_satellite=is_fallback_satellite,
            rainfall_metadata=rainfall_prov.details,
            satellite_metadata=ndvi_prov.details,
            data_quality=data_quality,
        )
