"""Normalized Pydantic schemas for Weather data provider abstraction."""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CurrentWeatherResponse(BaseModel):
    """Normalized live/current meteorological observation response."""

    success: bool = True
    farm_id: Optional[str] = None
    latitude: float
    longitude: float
    timestamp: str
    timezone: str = "Asia/Kolkata"
    temperature: Optional[float] = Field(None, description="Air temperature at 2m in Celsius")
    relative_humidity: Optional[float] = Field(None, description="Relative humidity percentage at 2m")
    precipitation: Optional[float] = Field(None, description="Current precipitation in mm")
    wind_speed_10m: Optional[float] = Field(None, description="Wind speed at 10m in km/h")
    soil_moisture_m3m3: Optional[float] = Field(None, description="Root-zone volumetric soil moisture in m3/m3")
    soil_moisture_percentage: Optional[float] = Field(None, description="Calculated relative soil saturation percentage (5-95%)")
    weather_code: Optional[int] = Field(None, description="WMO weather interpretation code")
    source: str = "Open-Meteo (Meteorological Model Estimate)"
    is_forecast: bool = False
    is_estimate: bool = True
    is_cached: bool = False
    precipitation_sum_7d: Optional[float] = Field(None, description="7-day cumulative precipitation sum in mm")
    error: Optional[str] = None


class DailyForecastItem(BaseModel):
    """Single daily meteorological forecast projection."""

    date: str
    temperature_max: Optional[float] = None
    temperature_min: Optional[float] = None
    precipitation_sum: Optional[float] = None
    precipitation_probability_max: Optional[int] = None
    weather_code: Optional[int] = None
    soil_moisture_mean: Optional[float] = None


class WeatherForecastResponse(BaseModel):
    """Normalized multi-day meteorological forecast projection response."""

    success: bool = True
    farm_id: Optional[str] = None
    latitude: float
    longitude: float
    timezone: str = "Asia/Kolkata"
    source: str = "Open-Meteo"
    is_forecast: bool = True
    is_cached: bool = False
    forecast_days: int = 7
    daily: List[DailyForecastItem] = Field(default_factory=list)
    disclaimer: str = (
        "This is numerical meteorological forecast data provided for agronomic planning "
        "and is not a crop-failure risk assessment."
    )
    error: Optional[str] = None


class WeatherObservationRecord(BaseModel):
    """Persisted weather observation stored in database."""

    id: str
    farm_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    observation_time: str
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    precipitation_mm: Optional[float] = None
    soil_moisture_pct: Optional[float] = None
    soil_moisture_m3m3: Optional[float] = None
    weather_code: Optional[int] = None
    source: str = "Open-Meteo"
    is_forecast: bool = False
    created_at: str
