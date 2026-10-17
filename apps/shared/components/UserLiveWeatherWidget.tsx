"use client";

import React, { useState } from "react";
import { useUserLocation } from "@shared/context/UserLocationContext";
import { useAuth } from "@shared/context/AuthContext";
import { t } from "@shared/translations";

const PRESET_LOCALITIES = [
  { name: "Pune, Maharashtra", lat: 18.5204, lon: 73.8567 },
  { name: "Amritsar, Punjab", lat: 31.634, lon: 74.8723 },
  { name: "Indore, Madhya Pradesh", lat: 22.7196, lon: 75.8577 },
  { name: "Varanasi, Uttar Pradesh", lat: 25.3176, lon: 82.9739 },
  { name: "Coimbatore, Tamil Nadu", lat: 11.0168, lon: 76.9558 },
  { name: "Bengaluru, Karnataka", lat: 12.9716, lon: 77.5946 },
  { name: "Kolkata, West Bengal", lat: 22.5726, lon: 88.3639 },
  { name: "Ahmedabad, Gujarat", lat: 23.0225, lon: 72.5714 },
];

export const UserLiveWeatherWidget: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { language } = useAuth();
  const {
    location,
    weather,
    forecast,
    forecastHorizon,
    isWeatherLoading,
    isForecastLoading,
    isGeocodingLoading,
    weatherError,
    forecastError,
    requestLocation,
    setManualLocation,
    setForecastHorizon,
    refreshWeather,
  } = useUserLocation();

  const [isManualSelectorOpen, setIsManualSelectorOpen] = useState(false);
  const [customLat, setCustomLat] = useState("");
  const [customLon, setCustomLon] = useState("");

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const lat = parseFloat(customLat);
    const lon = parseFloat(customLon);
    if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      setManualLocation(lat, lon, `Custom (${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E)`);
      setIsManualSelectorOpen(false);
    }
  };

  return (
    <div
      className={`rounded-2xl border transition shadow-sm overflow-hidden ${
        compact
          ? "bg-[#14231a] border-[#294332] p-3 text-xs"
          : "bg-gradient-to-br from-[#132219] to-[#0e1712] border-emerald-800/40 p-4 sm:p-5"
      }`}
    >
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[#243d2e]">
        <div className="flex items-center gap-2">
          <span className="text-lg">📍</span>
          <div>
            <h3 className="font-bold text-white text-sm">
              {t("user_location_title", language)}
            </h3>
            <p className="text-[11px] text-gray-400">
              {t("user_location_caption", language)}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={requestLocation}
            disabled={location.status === "detecting"}
            className="px-2.5 py-1 bg-emerald-800/80 hover:bg-emerald-700 text-white text-[11px] font-semibold rounded-lg border border-emerald-600/40 transition flex items-center gap-1 disabled:opacity-50"
            title={t("use_my_gps", language)}
          >
            <span>🎯</span>
            <span>{location.status === "detecting" ? t("loading", language) : t("use_my_gps", language)}</span>
          </button>

          <button
            onClick={() => setIsManualSelectorOpen((v) => !v)}
            className="px-2.5 py-1 bg-[#1a2f23] hover:bg-[#233f30] text-emerald-300 text-[11px] font-semibold rounded-lg border border-emerald-900/60 transition"
          >
            ✏️ {t("select_manually", language)}
          </button>

          <button
            onClick={refreshWeather}
            disabled={isWeatherLoading}
            className="p-1.5 bg-[#1a2f23] hover:bg-[#233f30] text-gray-300 hover:text-white rounded-lg transition disabled:opacity-50"
            title={t("retry_weather", language)}
          >
            🔄
          </button>
        </div>
      </div>

      {/* Manual Selection Dropdown Panel */}
      {isManualSelectorOpen && (
        <div className="my-3 p-3 bg-[#182a20] rounded-xl border border-emerald-800/50 space-y-3">
          <div className="text-[11px] text-gray-300 font-semibold">
            {t("select_manually", language)}:
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
            {PRESET_LOCALITIES.map((p) => (
              <button
                key={p.name}
                onClick={() => {
                  setManualLocation(p.lat, p.lon, p.name);
                  setIsManualSelectorOpen(false);
                }}
                className="text-left px-2 py-1.5 bg-[#121f18] hover:bg-emerald-900/60 text-white text-[11px] rounded border border-emerald-900/40 truncate"
              >
                {p.name.split(",")[0]}
              </button>
            ))}
          </div>

          <form onSubmit={handleManualSubmit} className="flex flex-wrap items-center gap-2 pt-2 border-t border-[#243d2e]">
            <input
              type="number"
              step="0.0001"
              placeholder="Lat (-90 to 90)"
              value={customLat}
              onChange={(e) => setCustomLat(e.target.value)}
              className="px-2 py-1 bg-[#101b15] border border-[#2d4d38] text-white text-xs rounded w-28"
            />
            <input
              type="number"
              step="0.0001"
              placeholder="Lon (-180 to 180)"
              value={customLon}
              onChange={(e) => setCustomLon(e.target.value)}
              className="px-2 py-1 bg-[#101b15] border border-[#2d4d38] text-white text-xs rounded w-28"
            />
            <button
              type="submit"
              className="px-3 py-1 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold rounded"
            >
              {t("save", language)}
            </button>
          </form>
        </div>
      )}

      {/* Status & Locality Banner */}
      <div className="pt-3 pb-2 flex flex-wrap items-start justify-between gap-2 text-xs">
        <div className="flex flex-col gap-0.5">
          {/* Prominent Place Name */}
          <div className="flex items-center gap-2">
            {location.status === "detecting" ? (
              <span className="flex items-center gap-1.5 text-amber-300 font-medium">
                <span className="animate-spin text-sm">⏳</span>
                <span>{t("detecting_location", language)}</span>
              </span>
            ) : isGeocodingLoading ? (
              <span className="flex items-center gap-1.5 text-amber-300 font-medium">
                <span className="animate-spin text-xs">⏳</span>
                <span>{t("finding_place_name", language)}</span>
              </span>
            ) : location.placeName ? (
              <span className="text-white font-bold text-sm tracking-tight text-emerald-200">
                {location.placeName}
              </span>
            ) : location.locality ? (
              <span className="text-white font-bold text-sm tracking-tight text-emerald-200">
                {location.locality}
              </span>
            ) : location.latitude !== null && location.longitude !== null ? (
              <span className="text-amber-200/90 font-medium text-xs tracking-tight italic">
                {language === "hi" ? "स्थान का नाम अनुपलब्ध (निर्देशांक सक्रिय)" : "Place name unavailable"}
              </span>
            ) : (
              <span className="text-gray-400 font-medium text-xs tracking-tight">
                {t("location_unavailable", language)}
              </span>
            )}

            {/* Verification Status Badge */}
            {location.status === "granted" && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-600/50 text-[10px] text-emerald-300 font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>GPS Verified</span>
              </span>
            )}
            {location.status === "manual" && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-950/80 border border-sky-600/50 text-[10px] text-sky-300 font-medium">
                <span>📌</span>
                <span>{t("manual_location", language)}</span>
              </span>
            )}
            {(location.status === "denied" || location.status === "unavailable") && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/80 border border-amber-600/50 text-[10px] text-amber-300">
                <span>⚠️</span>
                <span>{location.errorMessage || t("location_unavailable", language)}</span>
              </span>
            )}
          </div>

          {/* Coordinates Underneath in Smaller Text */}
          {location.latitude !== null && location.longitude !== null && (
            <div className="text-[11px] text-gray-400 font-mono flex items-center gap-2">
              <span>
                {location.latitude.toFixed(4)}°N, {location.longitude.toFixed(4)}°E
              </span>
              {location.state && (
                <span className="text-gray-500 font-sans">
                  · {location.state}{location.country ? `, ${location.country}` : ""}
                </span>
              )}
            </div>
          )}
        </div>

        {weather && (
          <div className="text-[10px] text-gray-400 text-right">
            {weather.is_estimate && <span>ℹ️ Model estimate · </span>}
            <span>Updated: {weather.timestamp}</span>
          </div>
        )}
      </div>

      {/* Weather Content */}
      {isWeatherLoading ? (
        <div className="py-6 flex flex-col items-center justify-center text-gray-400 text-xs">
          <div className="animate-spin text-2xl mb-1">⏳</div>
          <span>{t("loading", language)}</span>
        </div>
      ) : weatherError ? (
        <div className="my-2 p-3 bg-red-950/40 border border-red-800/60 rounded-xl text-red-300 text-xs flex items-center justify-between">
          <span>⚠️ {weatherError}</span>
          <button
            onClick={refreshWeather}
            className="px-2.5 py-1 bg-red-900/60 hover:bg-red-800 text-white rounded text-[11px]"
          >
            {t("retry_weather", language)}
          </button>
        </div>
      ) : weather && weather.success ? (
        <div className="space-y-3 pt-1">
          {/* Metrics grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            <div className="p-2.5 bg-[#17271e] border border-[#2b4735] rounded-xl text-center">
              <span className="text-[10px] text-gray-400 uppercase tracking-wide block">
                {t("temperature", language)}
              </span>
              <span className="text-base font-bold text-white">
                {weather.temperature !== null ? `${weather.temperature} °C` : "--"}
              </span>
            </div>

            <div className="p-2.5 bg-[#17271e] border border-[#2b4735] rounded-xl text-center">
              <span className="text-[10px] text-gray-400 uppercase tracking-wide block">
                {t("humidity", language)}
              </span>
              <span className="text-base font-bold text-white">
                {weather.relative_humidity !== null ? `${weather.relative_humidity} %` : "--"}
              </span>
            </div>

            <div className="p-2.5 bg-[#17271e] border border-[#2b4735] rounded-xl text-center">
              <span className="text-[10px] text-gray-400 uppercase tracking-wide block">
                {t("rainfall", language)}
              </span>
              <span className="text-base font-bold text-white">
                {weather.precipitation !== null ? `${weather.precipitation} mm` : "0.0 mm"}
              </span>
            </div>

            <div className="p-2.5 bg-[#17271e] border border-[#2b4735] rounded-xl text-center">
              <span className="text-[10px] text-gray-400 uppercase tracking-wide block">
                {t("wind_speed", language)}
              </span>
              <span className="text-base font-bold text-white">
                {weather.wind_speed_10m !== null && weather.wind_speed_10m !== undefined
                  ? `${weather.wind_speed_10m} km/h`
                  : "--"}
              </span>
            </div>

            <div className="p-2.5 bg-[#17271e] border border-[#2b4735] rounded-xl text-center">
              <span className="text-[10px] text-gray-400 uppercase tracking-wide block">
                {t("soil_moisture", language)}
              </span>
              <span className="text-base font-bold text-emerald-400">
                {weather.soil_moisture_percentage !== null && weather.soil_moisture_percentage !== undefined
                  ? `${weather.soil_moisture_percentage} %`
                  : "--"}
              </span>
            </div>
          </div>

          {/* Local User Forecast (7/14 Days) */}
          <div className="pt-2 border-t border-[#243d2e]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-white">
                📅 Local User Forecast
              </span>
              <div className="flex items-center gap-1 text-[11px] bg-[#17271e] p-0.5 rounded-lg border border-[#2b4735]">
                <button
                  onClick={() => setForecastHorizon(7)}
                  className={`px-2 py-0.5 rounded ${
                    forecastHorizon === 7 ? "bg-emerald-700 text-white font-bold" : "text-gray-400 hover:text-white"
                  }`}
                >
                  7-Day
                </button>
                <button
                  onClick={() => setForecastHorizon(14)}
                  className={`px-2 py-0.5 rounded ${
                    forecastHorizon === 14 ? "bg-emerald-700 text-white font-bold" : "text-gray-400 hover:text-white"
                  }`}
                >
                  14-Day
                </button>
              </div>
            </div>

            {isForecastLoading ? (
              <div className="text-[11px] text-gray-400 py-2">Loading forecast...</div>
            ) : forecastError ? (
              <div className="text-[11px] text-amber-400 py-1">⚠️ {forecastError}</div>
            ) : forecast && forecast.daily && forecast.daily.length > 0 ? (
              <div>
                {forecast.forecast_days < forecastHorizon && (
                  <div className="text-[10px] text-amber-300 bg-amber-950/40 p-1.5 rounded mb-1.5 border border-amber-900/50">
                    ℹ️ Provider returned {forecast.forecast_days} days. 14-day projection data is partially unavailable upstream; displaying available horizon without fabrication.
                  </div>
                )}
                <div className="grid grid-cols-2 sm:grid-cols-7 gap-1 text-center">
                  {forecast.daily.slice(0, forecastHorizon).map((d) => (
                    <div
                      key={d.date}
                      className="p-1.5 bg-[#121f18] border border-emerald-950/60 rounded-lg text-[10px]"
                    >
                      <div className="font-semibold text-gray-300">
                        {new Date(d.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}
                      </div>
                      <div className="text-white font-bold text-[11px] mt-0.5">
                        {d.temperature_max}° / {d.temperature_min}°
                      </div>
                      <div className="text-emerald-400">
                        🌧️ {d.precipitation_sum ?? 0} mm
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="py-2 text-xs text-gray-400">
          Select or detect your location to retrieve live local weather.
        </div>
      )}
    </div>
  );
};
