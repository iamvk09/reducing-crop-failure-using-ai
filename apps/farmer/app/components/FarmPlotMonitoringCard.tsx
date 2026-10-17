"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Farm, FarmCrop, CurrentWeatherResponse, FarmVegetationSummary, FarmMonitoringResponse, PredictionResponse } from "@shared/types";
import { listFarmCrops } from "@shared/api/crops";
import { listFarmPredictions, predictForFarm } from "@shared/api/predictions";
import { getCurrentWeather } from "@shared/api/weather";
import { getFarmVegetationSummary } from "@shared/api/satellite";
import { getFarmMonitoring } from "@shared/api/monitoring";
import { t, localize_value } from "@shared/translations";

interface FarmPlotMonitoringCardProps {
  farm: Farm;
  isSelected: boolean;
  onSelect: (farm: Farm) => void;
  token: string | null;
  language: string;
  externalPrediction?: PredictionResponse | null;
  isParentEvaluating?: boolean;
  onPredictionSuccess?: (prediction: PredictionResponse) => void;
}

export const FarmPlotMonitoringCard: React.FC<FarmPlotMonitoringCardProps> = ({
  farm,
  isSelected,
  onSelect,
  token,
  language,
  externalPrediction,
  isParentEvaluating = false,
  onPredictionSuccess,
}) => {
  const [activeCrop, setActiveCrop] = useState<FarmCrop | null>(null);
  const [latestPrediction, setLatestPrediction] = useState<PredictionResponse | null>(null);
  const [weather, setWeather] = useState<CurrentWeatherResponse | null>(null);
  const [vegetation, setVegetation] = useState<FarmVegetationSummary | null>(null);
  const [monitoring, setMonitoring] = useState<FarmMonitoringResponse | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isPredLoading, setIsPredLoading] = useState<boolean>(true);
  const [predError, setPredError] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [evalNotice, setEvalNotice] = useState<string | null>(null);

  // Synchronize external prediction updates from dashboard when targeted to this farm
  useEffect(() => {
    if (externalPrediction !== undefined) {
      if (externalPrediction && (!externalPrediction.farm_id || externalPrediction.farm_id === farm.id)) {
        setLatestPrediction(externalPrediction);
        setPredError(null);
      }
    }
  }, [externalPrediction, farm.id]);

  const fetchFarmPrediction = useCallback(async () => {
    if (!token || !farm?.id) return;
    setIsPredLoading(true);
    setPredError(null);
    try {
      const preds = await listFarmPredictions(farm.id, token);
      if (preds && preds.length > 0) {
        setLatestPrediction(preds[0]);
      } else {
        setLatestPrediction(null);
      }
    } catch (err: any) {
      const msg = err?.message || "Failed to load prediction";
      setPredError(msg);
    } finally {
      setIsPredLoading(false);
    }
  }, [farm.id, token]);

  const loadCardData = useCallback(async () => {
    if (!token || !farm?.id) return;
    setIsLoading(true);
    setError(null);
    setIsPredLoading(true);
    setPredError(null);

    try {
      const [cropsRes, predsRes, weatherRes, vegRes, monRes] = await Promise.allSettled([
        listFarmCrops(farm.id, token),
        listFarmPredictions(farm.id, token),
        getCurrentWeather(farm.id, token),
        getFarmVegetationSummary(farm.id, token),
        getFarmMonitoring(farm.id, token),
      ]);

      if (cropsRes.status === "fulfilled") {
        const cropList = cropsRes.value || [];
        setActiveCrop(cropList.find((c) => c.is_active) || cropList[0] || null);
      }

      if (predsRes.status === "fulfilled") {
        if (predsRes.value && predsRes.value.length > 0) {
          setLatestPrediction(predsRes.value[0]);
        } else {
          setLatestPrediction(null);
        }
        setPredError(null);
      } else {
        const reasonMsg = (predsRes as PromiseRejectedResult).reason?.message || "Network request timed out";
        setPredError(reasonMsg);
      }
      setIsPredLoading(false);

      if (weatherRes.status === "fulfilled") {
        setWeather(weatherRes.value);
      }

      if (vegRes.status === "fulfilled") {
        setVegetation(vegRes.value);
      }

      if (monRes.status === "fulfilled") {
        setMonitoring(monRes.value);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load telemetry for this farm.");
    } finally {
      setIsLoading(false);
    }
  }, [farm.id, token]);

  useEffect(() => {
    loadCardData();
  }, [loadCardData]);

  const handleEvaluate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token || !farm?.id || isEvaluating || isParentEvaluating) return;
    setIsEvaluating(true);
    setEvalNotice(null);
    setPredError(null);
    try {
      const pred = await predictForFarm(farm.id, {}, token);
      // Validate prediction response
      if (!pred || typeof pred.risk_probability !== "number" || isNaN(pred.risk_probability) || pred.risk_probability < 0 || pred.risk_probability > 1) {
        throw new Error("Invalid risk score received from server. Expected a finite probability between 0 and 1.");
      }
      setLatestPrediction(pred);
      setEvalNotice("Live risk re-evaluated!");
      onPredictionSuccess?.(pred);

      const mon = await getFarmMonitoring(farm.id, token).catch(() => null);
      if (mon) setMonitoring(mon);
    } catch (err: any) {
      const msg = err?.message || "Assessment failed";
      setPredError(msg);
      setEvalNotice(msg.toLowerCase().includes("crop") ? "Please register an active crop first." : msg);
    } finally {
      setIsEvaluating(false);
    }
  };

  const isCurrentEvaluating = isEvaluating || isParentEvaluating;

  return (
    <div
      onClick={() => onSelect(farm)}
      className={`rounded-2xl border transition-all duration-200 p-5 space-y-4 cursor-pointer ${
        isSelected
          ? "bg-[#16271e] border-emerald-500/80 shadow-lg ring-1 ring-emerald-500/50"
          : "bg-[#142018] border-[#23352a] hover:border-emerald-700/60 hover:bg-[#17251c]"
      }`}
    >
      {/* Farm Meta Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#24392c] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-white text-base tracking-tight">{farm.name}</h3>
            {isSelected ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-700/60 text-[10px] font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Active Plot
              </span>
            ) : (
              <span className="text-[10px] text-gray-500 hover:text-gray-300 font-medium">Click to select</span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            {farm.district}, {farm.state} · {t("area_hectares", language)}: {farm.area_hectares || "Not specified"} ha
            {farm.latitude !== undefined && farm.longitude !== undefined && (
              <span className="ml-2 font-mono text-[11px] text-gray-500">
                ({farm.latitude.toFixed(4)}°N, {farm.longitude.toFixed(4)}°E)
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs" onClick={(e) => e.stopPropagation()}>
          <span className="text-gray-400">{t("current_crop", language)}:</span>
          <span className="font-bold text-white bg-[#1e2c23] px-2.5 py-1 rounded border border-[#2d4034]">
            {activeCrop
              ? `${localize_value(activeCrop.crop, language)} (${localize_value(activeCrop.season, language)})`
              : t("no_crops_yet", language)}
          </span>
          {!activeCrop && (
            <Link
              href={`/farmer/farms/${farm.id}/crop`}
              className="text-xs font-bold bg-emerald-700 hover:bg-emerald-600 text-white px-2.5 py-1 rounded-lg"
            >
              ➕ {t("add_crop", language)}
            </Link>
          )}
          <Link
            href={`/farmer/farms/${farm.id}`}
            className="text-emerald-400 hover:text-emerald-300 font-bold ml-2 text-xs"
          >
            {language === "hi" ? "सीमा संपादित करें ➔" : "Edit Boundary ➔"}
          </Link>
          <button
            onClick={handleEvaluate}
            disabled={isCurrentEvaluating}
            className="ml-2 px-3 py-1 bg-emerald-800/80 hover:bg-emerald-700 disabled:bg-gray-700 text-white text-[11px] font-bold rounded-lg transition"
          >
            {isCurrentEvaluating ? "..." : `🔍 ${t("predict_risk_btn", language)}`}
          </button>
        </div>
      </div>

      {evalNotice && (
        <div className="text-[11px] px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-300">
          {evalNotice}
        </div>
      )}

      {isLoading ? (
        <div className="py-6 flex items-center justify-center text-xs text-gray-400">
          <span className="animate-spin mr-2">⏳</span>
          {language === "hi" ? "टेलीमेट्री लोड हो रही है..." : "Loading plot telemetry & sensors..."}
        </div>
      ) : error ? (
        <div className="py-4 text-xs text-rose-300 bg-rose-950/40 border border-rose-800/60 rounded-xl px-4 flex items-center justify-between">
          <span>⚠️ {error}</span>
          <button onClick={loadCardData} className="underline text-[11px] text-white ml-2">Retry</button>
        </div>
      ) : (
        /* Telemetry Cards Grid */
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-[#121c16] border border-[#23352a] rounded-xl p-3.5 flex flex-col justify-between">
            <div>
              <p className="text-[11px] text-gray-400 uppercase font-semibold">{t("crop_risk", language)}</p>

              {/* 5 Distinct Lifecycle States */}
              {isPredLoading || isCurrentEvaluating ? (
                /* State 2: Evaluating */
                <div className="flex items-center gap-1.5 mt-2 text-xs text-amber-300">
                  <span className="animate-spin text-sm">⏳</span>
                  <span>{language === "hi" ? "फसल जोखिम का मूल्यांकन जारी..." : "Evaluating crop risk…"}</span>
                </div>
              ) : predError ? (
                /* State 5: Error */
                <div className="mt-1 space-y-1">
                  <p className="text-xs font-bold text-rose-400 flex items-center gap-1">
                    <span>⚠️</span>
                    <span className="truncate" title={predError}>
                      {predError.toLowerCase().includes("soil") || predError.toLowerCase().includes("soiltype")
                        ? (language === "hi" ? "मिट्टी के प्रकार की त्रुटि" : "Soil type error")
                        : predError.toLowerCase().includes("timed out")
                        ? (language === "hi" ? "अनुरोध समय समाप्त (Timed out)" : "Prediction timed out")
                        : (language === "hi" ? "पूर्वानुमान विफल" : "Prediction failed")}
                    </span>
                  </p>
                  <p className="text-[10px] text-gray-400">
                    {predError.toLowerCase().includes("timed out")
                      ? (language === "hi" ? "सर्वर रिस्पॉन्स में देरी हुई।" : "Server took too long to respond.")
                      : predError}
                  </p>
                </div>
              ) : latestPrediction ? (
                /* State 3: Success */
                <div className="mt-1">
                  <p className="text-xl font-black text-white">{latestPrediction.risk_percentage}</p>
                  <p className="text-[10px] text-emerald-400 font-medium">
                    {latestPrediction.risk_level} {language === "hi" ? "जोखिम" : "Risk"}
                  </p>
                  {latestPrediction.created_at && (
                    <p className="text-[9px] text-gray-500 mt-1">
                      {new Date(latestPrediction.created_at).toLocaleDateString([], {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  )}
                </div>
              ) : (
                /* State 1 & 4: Idle / No prediction yet */
                <div className="mt-1">
                  <p className="text-sm font-semibold text-gray-300">
                    {language === "hi" ? "कोई भविष्यवाणी नहीं" : "No prediction yet"}
                  </p>
                  <p className="text-[10px] text-gray-500">
                    {language === "hi" ? "मूल्यांकन के लिए तैयार" : "Ready for risk evaluation"}
                  </p>
                </div>
              )}
            </div>

            {/* Per-Farm Action / Retry */}
            <div className="mt-3 pt-2 border-t border-[#1e2f24] flex items-center justify-between text-[11px]">
              {predError ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      fetchFarmPrediction();
                    }}
                    disabled={isPredLoading || isCurrentEvaluating}
                    className="px-2.5 py-1 bg-rose-900/40 hover:bg-rose-800/60 border border-rose-700/60 text-rose-200 rounded-lg font-bold transition flex items-center gap-1"
                  >
                    <span>🔄</span> {language === "hi" ? "पुनः प्रयास (Retry)" : "Retry Prediction"}
                  </button>
                  {(predError.toLowerCase().includes("soil") || predError.toLowerCase().includes("crop")) && (
                    <Link
                      href={`/farmer/farms/${farm.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="px-2.5 py-1 bg-emerald-900/60 hover:bg-emerald-800 border border-emerald-700/60 text-emerald-200 rounded-lg font-bold transition"
                    >
                      ✏️ {language === "hi" ? "संपादित करें" : "Edit Profile"}
                    </Link>
                  )}
                </div>
              ) : !latestPrediction && !isPredLoading ? (
                <button
                  onClick={handleEvaluate}
                  disabled={isCurrentEvaluating}
                  className="text-emerald-400 hover:text-emerald-300 font-bold flex items-center gap-1 text-[11px] disabled:opacity-50"
                >
                  <span>🔍</span> {language === "hi" ? "जोखिम जांचें" : "Assess Risk"}
                </button>
              ) : null}
            </div>
          </div>

          <div className="bg-[#121c16] border border-[#23352a] rounded-xl p-3.5">
            <p className="text-[11px] text-gray-400 uppercase font-semibold">{t("live_weather", language)}</p>
            <p className="text-sm font-bold text-white mt-1">
              {weather && weather.temperature !== null && weather.temperature !== undefined
                ? `${weather.temperature} °C · ${weather.relative_humidity}% RH`
                : (language === "hi" ? "डेटा अनुपलब्ध" : "Data unavailable")}
            </p>
            {weather?.wind_speed_10m !== undefined && weather?.wind_speed_10m !== null && (
              <p className="text-[10px] text-gray-500 mt-0.5">Wind: {weather.wind_speed_10m} km/h</p>
            )}
          </div>

          <div className="bg-[#121c16] border border-[#23352a] rounded-xl p-3.5">
            <p className="text-[11px] text-gray-400 uppercase font-semibold">Sentinel-2 NDVI</p>
            <p className="text-sm font-bold text-white mt-1">
              {vegetation?.latest_ndvi !== null && vegetation?.latest_ndvi !== undefined
                ? Number(vegetation.latest_ndvi).toFixed(3)
                : (language === "hi" ? "कोई उपग्रह डेटा नहीं" : "No satellite pass")}
            </p>
            {vegetation?.vegetation_health && (
              <p className="text-[10px] text-emerald-400 mt-0.5">{vegetation.vegetation_health}</p>
            )}
          </div>

          <div className="bg-[#121c16] border border-[#23352a] rounded-xl p-3.5">
            <p className="text-[11px] text-gray-400 uppercase font-semibold">{t("risk_trend_title", language)}</p>
            <p className="text-sm font-bold text-white mt-1">
              {monitoring?.risk_trend?.trend_direction === "increasing"
                ? (language === "hi" ? "📈 बढ़ रहा है" : "📈 Increasing")
                : monitoring?.risk_trend?.trend_direction === "decreasing"
                ? (language === "hi" ? "📉 घट रहा है" : "📉 Decreasing")
                : (language === "hi" ? "⚖️ स्थिर" : "⚖️ Stable")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
