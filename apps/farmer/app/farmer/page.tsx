"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { RiskBadge } from "@shared/components/RiskBadge";
import { listFarms } from "@shared/api/farms";
import { listFarmCrops } from "@shared/api/crops";
import { listFarmPredictions, predictForFarm } from "@shared/api/predictions";
import { getCurrentWeather } from "@shared/api/weather";
import { getFarmVegetationSummary } from "@shared/api/satellite";
import {
  getFarmMonitoring,
  logFarmFeedback,
  recordCropOutcome,
} from "@shared/api/monitoring";
import { listFarmAlerts, acknowledgeFarmAlert } from "@shared/api/alerts";
import {
  CurrentWeatherResponse,
  Farm,
  FarmAlert,
  FarmCrop,
  FarmFeedbackResponse,
  FarmMonitoringResponse,
  FarmVegetationSummary,
  PredictionResponse,
} from "@shared/types";
import { t } from "@shared/translations";

export default function FarmerDashboard() {
  const { user, profile, token, language, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [farms, setFarms] = useState<Farm[]>([]);
  const [selectedFarm, setSelectedFarm] = useState<Farm | null>(null);
  const [crops, setCrops] = useState<FarmCrop[]>([]);
  const [activeCrop, setActiveCrop] = useState<FarmCrop | null>(null);
  const [latestPrediction, setLatestPrediction] = useState<PredictionResponse | null>(null);
  const [monitoringSummary, setMonitoringSummary] = useState<FarmMonitoringResponse | null>(null);
  const [currentWeather, setCurrentWeather] = useState<CurrentWeatherResponse | null>(null);
  const [vegetationSummary, setVegetationSummary] = useState<FarmVegetationSummary | null>(null);
  const [isLoadingData, setIsLoadingData] = useState<boolean>(true);
  const [isEvaluatingRisk, setIsEvaluatingRisk] = useState<boolean>(false);
  const [isLoggingFeedback, setIsLoggingFeedback] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [predictionNotice, setPredictionNotice] = useState<string | null>(null);

  // Early Warning & Alert Engine state
  const [alerts, setAlerts] = useState<FarmAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState<boolean>(false);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [acknowledgingAlertId, setAcknowledgingAlertId] = useState<string | null>(null);

  // Quick feedback & outcome state
  const [feedbackNote, setFeedbackNote] = useState<string>("");
  const [selectedActionType, setSelectedActionType] = useState<string | null>(null);
  const [showOutcomeModal, setShowOutcomeModal] = useState<boolean>(false);
  const [outcomeStatus, setOutcomeStatus] = useState<string>("harvested");
  const [reportedYield, setReportedYield] = useState<string>("");
  const [outcomeNotes, setOutcomeNotes] = useState<string>("");

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!token) return;

    const loadData = async () => {
      setIsLoadingData(true);
      setErrorMessage(null);
      try {
        const farmList = await listFarms(token);
        setFarms(farmList);
        if (farmList.length > 0) {
          const current = farmList[0];
          setSelectedFarm(current);
          const cropList = await listFarmCrops(current.id, token);
          setCrops(cropList);
          const active = cropList.find((c) => c.is_active) || cropList[0] || null;
          setActiveCrop(active);

          // Fetch latest past prediction if exists
          try {
            const pastPredictions = await listFarmPredictions(current.id, token);
            if (pastPredictions && pastPredictions.length > 0) {
              setLatestPrediction(pastPredictions[0]);
            } else {
              setLatestPrediction(null);
            }
          } catch {
            setLatestPrediction(null);
          }

          // Fetch closed-loop monitoring summary
          try {
            const mon = await getFarmMonitoring(current.id, token);
            setMonitoringSummary(mon);
          } catch {
            setMonitoringSummary(null);
          }

          // Fetch live farm weather
          try {
            const weather = await getCurrentWeather(current.id, token);
            setCurrentWeather(weather);
          } catch {
            setCurrentWeather(null);
          }

          // Fetch satellite vegetation summary
          try {
            const veg = await getFarmVegetationSummary(current.id, token);
            setVegetationSummary(veg);
          } catch {
            setVegetationSummary(null);
          }

          // Fetch early warning alerts
          try {
            setAlertsLoading(true);
            setAlertsError(null);
            const farmAlerts = await listFarmAlerts(current.id, token);
            setAlerts(farmAlerts);
          } catch (err: any) {
            setAlertsError(err.message || "Failed to load early warning alerts.");
            setAlerts([]);
          } finally {
            setAlertsLoading(false);
          }
        }
      } catch (err: any) {
        setErrorMessage(err.message || t("error_network", language));
      } finally {
        setIsLoadingData(false);
      }
    };

    loadData();
  }, [token, language]);

  const handleFarmChange = async (farmId: string) => {
    const farm = farms.find((f) => f.id === farmId);
    if (farm && token) {
      setSelectedFarm(farm);
      setLatestPrediction(null);
      setMonitoringSummary(null);
      setCurrentWeather(null);
      setVegetationSummary(null);
      setPredictionNotice(null);
      try {
        const cropList = await listFarmCrops(farm.id, token);
        setCrops(cropList);
        setActiveCrop(cropList.find((c) => c.is_active) || cropList[0] || null);

        const pastPredictions = await listFarmPredictions(farm.id, token);
        if (pastPredictions && pastPredictions.length > 0) {
          setLatestPrediction(pastPredictions[0]);
        }

        try {
          const mon = await getFarmMonitoring(farm.id, token);
          setMonitoringSummary(mon);
        } catch {
          setMonitoringSummary(null);
        }

        const weather = await getCurrentWeather(farm.id, token);
        setCurrentWeather(weather);

        const veg = await getFarmVegetationSummary(farm.id, token);
        setVegetationSummary(veg);

        try {
          setAlertsLoading(true);
          setAlertsError(null);
          const farmAlerts = await listFarmAlerts(farm.id, token);
          setAlerts(farmAlerts);
        } catch (err: any) {
          setAlertsError(err.message || "Failed to load early warning alerts.");
          setAlerts([]);
        } finally {
          setAlertsLoading(false);
        }
      } catch {
        setCrops([]);
        setActiveCrop(null);
      }
    }
  };

  const handleEvaluateRisk = async () => {
    if (!selectedFarm || !token) return;
    setIsEvaluatingRisk(true);
    setErrorMessage(null);
    setPredictionNotice(null);
    try {
      const pred = await predictForFarm(selectedFarm.id, {}, token);
      setLatestPrediction(pred);
      setPredictionNotice("Live crop risk analysis updated using real-time Open-Meteo weather.");

      // Refresh monitoring state
      try {
        const mon = await getFarmMonitoring(selectedFarm.id, token);
        setMonitoringSummary(mon);
      } catch (e) {
        console.error("Could not refresh monitoring state:", e);
      }

      // Refresh current weather
      const weather = await getCurrentWeather(selectedFarm.id, token);
      setCurrentWeather(weather);

      // Refresh alerts
      try {
        const farmAlerts = await listFarmAlerts(selectedFarm.id, token);
        setAlerts(farmAlerts);
      } catch (e) {
        console.error("Could not refresh alerts:", e);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to evaluate crop failure risk.");
    } finally {
      setIsEvaluatingRisk(false);
    }
  };

  const handleAcknowledgeAlert = async (alertId: string) => {
    if (!token || !selectedFarm) return;
    setAcknowledgingAlertId(alertId);
    try {
      const updated = await acknowledgeFarmAlert(selectedFarm.id, alertId, token);
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId
            ? { ...a, status: "acknowledged", acknowledged_at: updated.acknowledged_at }
            : a
        )
      );
      setPredictionNotice("Early warning advisory acknowledged successfully.");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to acknowledge alert.");
    } finally {
      setAcknowledgingAlertId(null);
    }
  };

  const handleQuickFeedback = async (
    actionType: "irrigation_applied" | "fertilizer_applied" | "pest_control_applied" | "farmer_note",
    notes: string
  ) => {
    if (!selectedFarm || !token) return;
    setIsLoggingFeedback(true);
    try {
      await logFarmFeedback(
        selectedFarm.id,
        {
          action_type: actionType,
          prediction_id: latestPrediction?.prediction_id || null,
          notes: notes || undefined,
        },
        token
      );
      setPredictionNotice(`Logged: ${actionType.replace(/_/g, " ")}`);
      setSelectedActionType(null);
      setFeedbackNote("");
      const mon = await getFarmMonitoring(selectedFarm.id, token);
      setMonitoringSummary(mon);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to record management action.");
    } finally {
      setIsLoggingFeedback(false);
    }
  };

  const handleRecordCropOutcome = async () => {
    if (!selectedFarm || !activeCrop || !token) return;
    setIsLoggingFeedback(true);
    try {
      await recordCropOutcome(
        selectedFarm.id,
        activeCrop.id,
        {
          crop_status: outcomeStatus as "active" | "harvested" | "failed",
          actual_harvest_date: new Date().toISOString().split("T")[0],
          reported_yield_kg_per_ha: reportedYield ? parseFloat(reportedYield) : undefined,
          outcome_notes: outcomeNotes || undefined,
        },
        token
      );
      setPredictionNotice(`Season outcome recorded as '${outcomeStatus}'.`);
      setShowOutcomeModal(false);
      const mon = await getFarmMonitoring(selectedFarm.id, token);
      setMonitoringSummary(mon);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to record crop outcome.");
    } finally {
      setIsLoggingFeedback(false);
    }
  };

  if (authLoading || (!user && !errorMessage)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="text-center">
          <div className="text-3xl animate-bounce mb-2">🌾</div>
          <p className="font-semibold text-gray-700">{t("loading", language)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar portalType="farmer" />

      <main className="flex-1 max-w-4xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* Farmer Header Greeting */}
        <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-bold text-emerald-800 uppercase tracking-wider bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              {t("welcome_farmer", language)}
            </span>
            <h2 className="text-2xl font-bold text-gray-900 mt-2">
              {t("welcome_user", language)}, {profile?.full_name || "Farmer"}!
            </h2>
            <p className="text-sm text-gray-600">
              {selectedFarm
                ? `${selectedFarm.name} · ${selectedFarm.village ? selectedFarm.village + ", " : ""}${selectedFarm.district}, ${selectedFarm.state}`
                : t("register_farm_first", language)}
            </p>
          </div>

          <div className="flex gap-2 w-full sm:w-auto">
            <Link
              href="/farmer/farms"
              className="flex-1 sm:flex-none text-center px-4 py-2.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 font-bold rounded-xl border border-emerald-300 text-sm transition"
            >
              📋 {t("my_farms", language)}
            </Link>
            <Link
              href="/farmer/farms/new"
              className="flex-1 sm:flex-none text-center px-4 py-2.5 bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-xl shadow text-sm transition"
            >
              ➕ {t("add_farm", language)}
            </Link>
          </div>
        </section>

        {/* Error Alert if any */}
        {errorMessage && (
          <div className="bg-amber-50 border-2 border-amber-400 rounded-xl p-4 text-amber-900 text-sm flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <p>{errorMessage}</p>
          </div>
        )}

        {/* Success Notice if any */}
        {predictionNotice && (
          <div className="bg-emerald-50 border border-emerald-300 rounded-xl p-3 text-emerald-900 text-xs flex items-center justify-between">
            <span>✅ {predictionNotice}</span>
            <button onClick={() => setPredictionNotice(null)} className="text-emerald-700 font-bold ml-2">✕</button>
          </div>
        )}

        {/* If no farms registered yet */}
        {farms.length === 0 && !isLoadingData && (
          <section className="bg-white rounded-2xl border-2 border-dashed border-emerald-300 p-8 text-center space-y-4">
            <div className="text-4xl">📍</div>
            <h3 className="text-lg font-bold text-gray-900">{t("no_farms_yet", language)}</h3>
            <p className="text-sm text-gray-600 max-w-md mx-auto">
              {t("register_farm_first", language)}
            </p>
            <Link
              href="/farmer/farms/new"
              className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-xl shadow-md text-base transition"
            >
              ➕ {t("add_farm", language)}
            </Link>
          </section>
        )}

        {/* Active Farm & Crop Details */}
        {selectedFarm && (
          <>
            {/* Farm Selector & Live Trigger Toolbar */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-gray-200">
              <div className="flex items-center gap-3 flex-1">
                <label htmlFor="farm-select" className="text-xs font-bold text-gray-700 whitespace-nowrap">
                  {t("choose_field", language)}:
                </label>
                <select
                  id="farm-select"
                  value={selectedFarm.id}
                  onChange={(e) => handleFarmChange(e.target.value)}
                  className="bg-slate-50 border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-semibold text-gray-900 w-full"
                >
                  {farms.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} ({f.district}, {f.state})
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleEvaluateRisk}
                disabled={isEvaluatingRisk || !activeCrop}
                className="px-4 py-2 bg-emerald-800 hover:bg-emerald-900 disabled:bg-gray-400 text-white font-bold rounded-xl text-xs shadow transition flex items-center justify-center gap-2"
              >
                {isEvaluatingRisk ? (
                  <>
                    <span className="animate-spin text-sm">⏳</span> Evaluating Risk...
                  </>
                ) : (
                  <>
                    <span>🔍</span> Check Crop Risk
                  </>
                )}
              </button>
            </div>

            {/* Early Warning Alerts Section */}
            <section className="bg-white rounded-2xl shadow-sm border border-amber-200 p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">🚨</span>
                  <div>
                    <h3 className="font-bold text-gray-900 text-base">
                      Early Warning Alerts & Field Advisories
                    </h3>
                    <p className="text-xs text-gray-500">
                      Observation-driven alerts for risk transitions, significant trends, and telemetry quality.
                    </p>
                  </div>
                </div>
                {alerts.filter((a) => a.status === "active").length > 0 ? (
                  <span className="text-xs font-bold px-3 py-1 rounded-full bg-rose-100 text-rose-800 border border-rose-300 self-start sm:self-auto">
                    {alerts.filter((a) => a.status === "active").length} Active Alert{alerts.filter((a) => a.status === "active").length > 1 ? "s" : ""}
                  </span>
                ) : (
                  <span className="text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 self-start sm:self-auto">
                    0 Active Alerts
                  </span>
                )}
              </div>

              {alertsLoading ? (
                <div className="py-6 text-center text-xs text-gray-500 flex items-center justify-center gap-2">
                  <span className="animate-spin">⏳</span> Checking for early warnings...
                </div>
              ) : alertsError ? (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                  ⚠️ Error loading early warning alerts: {alertsError}
                </div>
              ) : alerts.length === 0 ? (
                <div className="p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl text-emerald-900 text-xs flex items-center gap-3">
                  <span className="text-lg">✅</span>
                  <div>
                    <p className="font-bold">No active early warning alerts</p>
                    <p className="text-gray-600">Model risk estimate and sensor telemetries are within normal operating ranges.</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {alerts.map((alert) => {
                    const isCritical = alert.severity === "critical";
                    const isWarning = alert.severity === "warning";
                    const badgeBg = isCritical
                      ? "bg-rose-100 text-rose-800 border-rose-300"
                      : isWarning
                      ? "bg-amber-100 text-amber-800 border-amber-300"
                      : "bg-blue-100 text-blue-800 border-blue-300";

                    return (
                      <div
                        key={alert.id}
                        className={`p-4 rounded-xl border ${
                          isCritical
                            ? "bg-rose-50/40 border-rose-200"
                            : isWarning
                            ? "bg-amber-50/40 border-amber-200"
                            : "bg-blue-50/40 border-blue-200"
                        } space-y-2`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-bold px-2 py-0.5 rounded border ${badgeBg} uppercase tracking-wider`}>
                              {alert.severity}
                            </span>
                            <span className="text-xs font-bold text-gray-900">{alert.trigger_reason}</span>
                          </div>
                          <span className="text-xs text-gray-500 whitespace-nowrap">
                            {new Date(alert.created_at).toLocaleDateString()}
                          </span>
                        </div>

                        <div className="text-xs text-gray-700 space-y-1">
                          <p>
                            <span className="font-semibold text-gray-900">Current Model Risk:</span>{" "}
                            {alert.risk_percentage || `${(alert.risk_probability * 100).toFixed(1)}%`}
                            {alert.risk_delta_pp !== null && alert.risk_delta_pp !== undefined && (
                              <span className="ml-2 font-medium text-gray-600">
                                ({alert.risk_delta_pp > 0 ? `+${alert.risk_delta_pp}` : alert.risk_delta_pp} pp)
                              </span>
                            )}
                          </p>

                          {alert.shap_context?.summary && (
                            <p className="bg-white/80 p-2 rounded border border-gray-200 text-gray-800">
                              <span className="font-semibold">Model Contributing Factors:</span>{" "}
                              {alert.shap_context.summary}
                            </p>
                          )}

                          {alert.recommended_action && (
                            <p className="bg-white/80 p-2 rounded border border-gray-200 text-emerald-900">
                              <span className="font-semibold">Recommended Action:</span>{" "}
                              {alert.recommended_action.title}
                              {alert.recommended_action.action_items && alert.recommended_action.action_items.length > 0 && (
                                <span className="block mt-0.5 text-gray-600">
                                  • {alert.recommended_action.action_items.join(" • ")}
                                </span>
                              )}
                            </p>
                          )}
                        </div>

                        <div className="pt-2 flex justify-end items-center gap-2 border-t border-gray-200/60">
                          {alert.status === "active" ? (
                            <button
                              onClick={() => handleAcknowledgeAlert(alert.id)}
                              disabled={acknowledgingAlertId === alert.id}
                              className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-800 disabled:bg-gray-400 text-white font-bold text-xs rounded-lg transition shadow-sm"
                            >
                              {acknowledgingAlertId === alert.id ? "Acknowledging..." : "Acknowledge Advisory"}
                            </button>
                          ) : alert.status === "acknowledged" ? (
                            <span className="text-xs font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                              ✓ Acknowledged
                            </span>
                          ) : (
                            <span className="text-xs font-semibold text-slate-800 bg-slate-100 px-2.5 py-1 rounded border border-slate-300">
                              ✓ Resolved by Expert
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Main Risk & Current Crop Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Card 1: Risk Overview */}
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                    <span>🛡️</span> {t("crop_risk", language)}
                  </h3>
                  <RiskBadge level={latestPrediction?.risk_level || "Low"} language={language} />
                </div>

                <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-4">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs font-semibold text-emerald-900 uppercase">
                      {t("current_risk", language)}
                    </span>
                    <span className="text-2xl font-black text-emerald-800">
                      {latestPrediction ? latestPrediction.risk_percentage : "Ready for Analysis"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 mt-2">
                    {latestPrediction?.recommendations?.advisory_summary ||
                      (latestPrediction?.risk_level === "High"
                        ? t("advice_high", language)
                        : latestPrediction?.risk_level === "Medium"
                        ? t("advice_medium", language)
                        : t("advice_low", language))}
                  </p>
                </div>

                {/* Data freshness & model input transparency banner */}
                {latestPrediction && (
                  <div className="flex items-center gap-2 text-[11px] text-emerald-800 bg-emerald-50/80 px-3 py-1.5 rounded-xl border border-emerald-100">
                    <span className="text-sm">
                      {latestPrediction.data_quality?.satellite_status === "live_fresh" ? "🛰️" : "🌱"}
                    </span>
                    <span className="font-medium">
                      {latestPrediction.data_quality?.summary_label ||
                        (latestPrediction.data_quality?.live_feature_percentage && latestPrediction.data_quality.live_feature_percentage >= 50
                          ? "Prediction based on live weather + regional crop baselines"
                          : "Some model inputs use historical baseline data")}
                    </span>
                  </div>
                )}

                <div className="text-xs text-gray-500 flex justify-between items-center pt-1 border-t border-gray-100">
                  <span>
                    {t("safer_options", language)}:{" "}
                    <strong>
                      {latestPrediction?.recommendations?.top_options &&
                      latestPrediction.recommendations.top_options.length > 0
                        ? latestPrediction.recommendations.top_options.map((o) => o.crop).join(", ")
                        : "Soybean, Maize"}
                    </strong>
                  </span>
                  <span className="text-emerald-700 font-semibold">
                    {latestPrediction ? latestPrediction.best_model_name : "Verified AI Pipeline"}
                  </span>
                </div>
              </section>

              {/* Card 2: Current Crop Cycle */}
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                    <span>🌾</span> {t("current_crop", language)}
                  </h3>
                  <Link
                    href={`/farmer/farms/${selectedFarm.id}/crop`}
                    className="text-xs font-bold text-emerald-700 hover:text-emerald-800 underline"
                  >
                    {activeCrop ? t("edit", language) : t("add_crop", language)}
                  </Link>
                </div>

                {activeCrop ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-600">{t("crop", language)}:</span>
                      <span className="font-bold text-gray-900">{activeCrop.crop}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-600">{t("season", language)}:</span>
                      <span className="font-medium text-gray-900">{activeCrop.season}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-600">{t("growth_stage", language)}:</span>
                      <span className="font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded">
                        {activeCrop.growth_stage || "Flowering"}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gray-600">{t("soil_type", language)}:</span>
                      <span className="font-medium text-gray-900">{selectedFarm.soil_type || "Medium Black"}</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 bg-gray-50 rounded-xl">
                    <p className="text-xs text-gray-500 mb-2">{t("no_crops_yet", language)}</p>
                    <Link
                      href={`/farmer/farms/${selectedFarm.id}/crop`}
                      className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-bold rounded-lg"
                    >
                      ➕ {t("add_crop", language)}
                    </Link>
                  </div>
                )}
              </section>
            </div>

            {/* Farm Monitoring & Risk Trend Section */}
            {monitoringSummary && (
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🔄</span>
                    <div>
                      <h3 className="font-bold text-gray-900 text-base">
                        Farm Monitoring & Temporal Risk Progression
                      </h3>
                      <p className="text-xs text-gray-500">
                        Sequential observation lifecycle tracking real-time telemetry shifts and risk delta.
                      </p>
                    </div>
                  </div>
                  <span
                    className={`text-xs font-bold px-3 py-1 rounded-full border self-start sm:self-auto ${
                      monitoringSummary.monitoring_status === "optimal"
                        ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                        : monitoringSummary.monitoring_status === "attention_needed"
                        ? "bg-rose-50 text-rose-800 border-rose-300"
                        : monitoringSummary.monitoring_status === "insufficient_history"
                        ? "bg-slate-100 text-slate-700 border-slate-300"
                        : "bg-blue-50 text-blue-800 border-blue-300"
                    }`}
                  >
                    {monitoringSummary.monitoring_status === "optimal" && "🟢 Optimal Conditions"}
                    {monitoringSummary.monitoring_status === "attention_needed" && "⚠️ Attention Needed"}
                    {monitoringSummary.monitoring_status === "insufficient_history" && "ℹ️ Initial Baseline"}
                    {monitoringSummary.monitoring_status === "active" && "🔵 Active Monitoring"}
                  </span>
                </div>

                {monitoringSummary.status_reason && (
                  <p className="text-xs text-gray-600 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                    {monitoringSummary.status_reason}
                  </p>
                )}

                {/* Consecutive Risk Assessment Progression Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                    <span className="text-[11px] font-semibold text-gray-500 uppercase">
                      Current Failure Risk
                    </span>
                    <p className="text-2xl font-black text-gray-900 mt-1">
                      {(monitoringSummary.risk_trend.current_risk_probability * 100).toFixed(1)}%
                    </p>
                    <span className="text-[10px] text-gray-400">
                      {monitoringSummary.risk_trend.current_prediction_timestamp
                        ? new Date(monitoringSummary.risk_trend.current_prediction_timestamp).toLocaleDateString()
                        : "Latest Run"}
                    </span>
                  </div>

                  <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                    <span className="text-[11px] font-semibold text-gray-500 uppercase">
                      Previous Assessment
                    </span>
                    <p className="text-2xl font-black text-gray-600 mt-1">
                      {monitoringSummary.risk_trend.previous_risk_probability !== null &&
                      monitoringSummary.risk_trend.previous_risk_probability !== undefined
                        ? `${(monitoringSummary.risk_trend.previous_risk_probability * 100).toFixed(1)}%`
                        : "—"}
                    </p>
                    <span className="text-[10px] text-gray-400">
                      {monitoringSummary.risk_trend.previous_prediction_timestamp
                        ? new Date(monitoringSummary.risk_trend.previous_prediction_timestamp).toLocaleDateString()
                        : "Baseline Run"}
                    </span>
                  </div>

                  <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                    <span className="text-[11px] font-semibold text-gray-500 uppercase">
                      Risk Delta & Direction
                    </span>
                    <div className="flex items-center gap-2 mt-1">
                      <p
                        className={`text-2xl font-black ${
                          monitoringSummary.risk_trend.trend_direction === "increasing"
                            ? "text-rose-700"
                            : monitoringSummary.risk_trend.trend_direction === "decreasing"
                            ? "text-emerald-700"
                            : "text-blue-800"
                        }`}
                      >
                        {monitoringSummary.risk_trend.risk_delta_percentage_points !== null &&
                        monitoringSummary.risk_trend.risk_delta_percentage_points !== undefined
                          ? `${monitoringSummary.risk_trend.risk_delta_percentage_points > 0 ? "+" : ""}${monitoringSummary.risk_trend.risk_delta_percentage_points.toFixed(1)} pp`
                          : "Baseline"}
                      </p>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          monitoringSummary.risk_trend.trend_direction === "increasing"
                            ? "bg-rose-100 text-rose-800"
                            : monitoringSummary.risk_trend.trend_direction === "decreasing"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {monitoringSummary.risk_trend.trend_label}
                      </span>
                    </div>
                    <span className="text-[10px] text-gray-400">
                      Evaluated on {monitoringSummary.risk_trend.assessment_count} cycle(s)
                    </span>
                  </div>
                </div>

                <div className="text-xs text-gray-700 bg-emerald-50/40 p-3 rounded-xl border border-emerald-100 leading-relaxed">
                  <strong>Risk Progression Context:</strong> {monitoringSummary.risk_trend.trend_description}
                </div>

                {/* Why the risk changed (Telemetry evolution) */}
                {monitoringSummary.telemetry_changes && monitoringSummary.telemetry_changes.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold text-gray-900 uppercase flex items-center gap-1.5">
                      <span>🔍</span> Why the risk changed (Consecutive Telemetry Deltas)
                    </h4>
                    <div className="space-y-1.5">
                      {monitoringSummary.telemetry_changes.slice(0, 4).map((change, idx) => (
                        <div
                          key={idx}
                          className="bg-slate-50 p-2.5 rounded-lg border border-slate-200 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-1"
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                                change.change_type === "DIRECT_LIVE_CHANGE"
                                  ? "bg-blue-100 text-blue-800"
                                  : change.change_type === "DERIVED_CHANGE"
                                  ? "bg-purple-100 text-purple-800"
                                  : "bg-gray-100 text-gray-600"
                              }`}
                            >
                              {change.change_type.replace(/_/g, " ")}
                            </span>
                            <span className="font-semibold text-gray-800">{change.statement || change.description}</span>
                          </div>
                          <span className="text-[11px] font-mono font-medium text-gray-500">
                            {change.formatted_previous} → {change.formatted_current}
                          </span>
                        </div>
                      ))}
                    </div>
                    <p className="text-[11px] text-gray-400 italic">
                      Attributions describe statistical feature deltas between sequential monitoring cycles, not definitive agronomic causation.
                    </p>
                  </div>
                )}

                {/* Log Field Management Action */}
                <div className="pt-2 border-t border-gray-100 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-gray-900 uppercase flex items-center gap-1.5">
                      <span>⚡</span> Log Farmer Action Taken on Field
                    </h4>
                    <span className="text-[11px] text-gray-500">Tracks closed-loop management response</span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => setSelectedActionType("irrigation_applied")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition ${
                        selectedActionType === "irrigation_applied"
                          ? "bg-blue-600 text-white border-blue-700 shadow"
                          : "bg-white hover:bg-slate-50 text-gray-700 border-gray-300"
                      }`}
                    >
                      💧 Irrigation Applied
                    </button>
                    <button
                      onClick={() => setSelectedActionType("fertilizer_applied")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition ${
                        selectedActionType === "fertilizer_applied"
                          ? "bg-emerald-600 text-white border-emerald-700 shadow"
                          : "bg-white hover:bg-slate-50 text-gray-700 border-gray-300"
                      }`}
                    >
                      🌱 Nutrient / Fertilizer Added
                    </button>
                    <button
                      onClick={() => setSelectedActionType("pest_control_applied")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition ${
                        selectedActionType === "pest_control_applied"
                          ? "bg-amber-600 text-white border-amber-700 shadow"
                          : "bg-white hover:bg-slate-50 text-gray-700 border-gray-300"
                      }`}
                    >
                      🛡️ Pest Control Applied
                    </button>
                    <button
                      onClick={() => setSelectedActionType("farmer_note")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition ${
                        selectedActionType === "farmer_note"
                          ? "bg-purple-600 text-white border-purple-700 shadow"
                          : "bg-white hover:bg-slate-50 text-gray-700 border-gray-300"
                      }`}
                    >
                      📝 Farmer Field Note
                    </button>
                    <button
                      onClick={() => setShowOutcomeModal(!showOutcomeModal)}
                      className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-100 hover:bg-slate-200 text-gray-800 border border-slate-300 ml-auto"
                    >
                      🌾 Record Harvest Outcome
                    </button>
                  </div>

                  {selectedActionType && (
                    <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-2">
                      <label className="text-xs font-semibold text-gray-700 block">
                        Add Field Note for: <strong>{selectedActionType.replace(/_/g, " ")}</strong>
                      </label>
                      <input
                        type="text"
                        value={feedbackNote}
                        onChange={(e) => setFeedbackNote(e.target.value)}
                        placeholder="e.g. Applied 30mm supplemental irrigation across Block A"
                        className="w-full text-xs p-2 rounded-lg border border-gray-300 bg-white"
                      />
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => setSelectedActionType(null)}
                          className="px-3 py-1 text-xs text-gray-600 hover:text-gray-900"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handleQuickFeedback(selectedActionType as any, feedbackNote)}
                          disabled={isLoggingFeedback}
                          className="px-4 py-1 bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold rounded-lg shadow"
                        >
                          {isLoggingFeedback ? "Saving..." : "Confirm Action"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Outcome Recording Expander */}
                  {showOutcomeModal && (
                    <div className="bg-amber-50/60 p-4 rounded-xl border border-amber-200 space-y-3">
                      <div className="flex justify-between items-center">
                        <h5 className="text-xs font-bold text-amber-900 uppercase">
                          Record Field Outcome for {activeCrop?.crop || "Current Crop"}
                        </h5>
                        <span className="text-[10px] bg-amber-200/70 text-amber-900 px-2 py-0.5 rounded font-bold">
                          Farmer-Reported
                        </span>
                      </div>
                      <p className="text-[11px] text-amber-800">
                        This records a real-world harvest or failure observation for your farm. It will be stored as farmer-reported pending agricultural expert verification for AI model evaluation.
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="text-[11px] font-semibold text-gray-700 block mb-1">
                            Harvest Status
                          </label>
                          <select
                            value={outcomeStatus}
                            onChange={(e) => setOutcomeStatus(e.target.value)}
                            className="w-full text-xs p-2 rounded-lg border border-gray-300 bg-white"
                          >
                            <option value="harvested">Harvested Successfully</option>
                            <option value="failed">Crop Failed / Substantial Loss</option>
                            <option value="active">Still Growing (Active)</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-[11px] font-semibold text-gray-700 block mb-1">
                            Reported Yield (kg/ha)
                          </label>
                          <input
                            type="number"
                            value={reportedYield}
                            onChange={(e) => setReportedYield(e.target.value)}
                            placeholder="e.g. 2400"
                            className="w-full text-xs p-2 rounded-lg border border-gray-300 bg-white"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-semibold text-gray-700 block mb-1">
                            Field Observations
                          </label>
                          <input
                            type="text"
                            value={outcomeNotes}
                            onChange={(e) => setOutcomeNotes(e.target.value)}
                            placeholder="Weather impact, pest damage notes"
                            className="w-full text-xs p-2 rounded-lg border border-gray-300 bg-white"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setShowOutcomeModal(false)}
                          className="px-3 py-1 text-xs text-gray-600"
                        >
                          Close
                        </button>
                        <button
                          onClick={handleRecordCropOutcome}
                          disabled={isLoggingFeedback}
                          className="px-4 py-1.5 bg-amber-700 hover:bg-amber-800 text-white text-xs font-bold rounded-lg shadow"
                        >
                          {isLoggingFeedback ? "Saving..." : "Submit Field Outcome"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Recent Action Trail */}
                  {monitoringSummary.recent_actions && monitoringSummary.recent_actions.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase text-gray-400">
                        Recent Field Actions ({monitoringSummary.recent_actions.length})
                      </span>
                      <div className="flex flex-wrap gap-2 pt-1">
                        {monitoringSummary.recent_actions.map((act) => (
                          <span
                            key={act.id}
                            className="text-[11px] bg-slate-100 text-gray-700 px-2.5 py-1 rounded-md border border-slate-200 flex items-center gap-1"
                          >
                            <span>✓</span>
                            <strong>{act.action_label}</strong>
                            {act.notes && <span className="text-gray-500">· {act.notes}</span>}
                            <span className="text-[9px] text-gray-400 ml-1">
                              ({new Date(act.created_at).toLocaleDateString()})
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Why This Prediction? (SHAP Explainability) Section */}
            {latestPrediction?.explanation && (
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🧠</span>
                    <div>
                      <h3 className="font-bold text-gray-900 text-base">
                        Why this prediction? (Model Feature Breakdown)
                      </h3>
                      <p className="text-xs text-gray-500">
                        Statistical feature contributions evaluating field, weather, and satellite metrics.
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-bold bg-slate-100 text-slate-700 px-2.5 py-1 rounded-full border border-slate-200 self-start sm:self-auto">
                    {latestPrediction.explanation.explainer_type} (SHAP)
                  </span>
                </div>

                {latestPrediction.explanation.summary_narrative && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-xs text-gray-800 leading-relaxed">
                    <strong className="text-emerald-900 font-bold block mb-1">Assessment Summary:</strong>
                    {latestPrediction.explanation.summary_narrative}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Mitigating Factors (Green) */}
                  <div className="bg-emerald-50/50 border border-emerald-200 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-emerald-900 uppercase flex items-center gap-1.5">
                        <span>🛡️</span> Risk-Reducing Factors
                      </h4>
                      <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded">
                        Mitigating
                      </span>
                    </div>

                    {latestPrediction.explanation.top_risk_reducing && latestPrediction.explanation.top_risk_reducing.length > 0 ? (
                      <div className="space-y-2.5">
                        {latestPrediction.explanation.top_risk_reducing.map((item, idx) => (
                          <div key={idx} className="bg-white p-2.5 rounded-lg border border-emerald-100 text-xs space-y-1">
                            <div className="flex justify-between items-center">
                              <span className="font-bold text-gray-900">{item.display_name}</span>
                              <span className="font-black text-emerald-700">{item.formatted_value}</span>
                            </div>
                            <p className="text-[11px] text-gray-600">{item.farmer_text}</p>
                            {item.provenance_source && (
                              <div className="text-[10px] text-gray-400 flex items-center gap-1">
                                <span>Source:</span>
                                <span className="font-medium text-gray-600">{item.provenance_source}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-500 italic">No significant mitigating factors detected.</p>
                    )}
                  </div>

                  {/* Escalating Factors (Amber/Rose) */}
                  <div className="bg-rose-50/50 border border-rose-200 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-rose-900 uppercase flex items-center gap-1.5">
                        <span>⚠️</span> Risk-Elevating Factors
                      </h4>
                      <span className="text-[10px] font-bold text-rose-800 bg-rose-100 px-2 py-0.5 rounded">
                        Escalating
                      </span>
                    </div>

                    {latestPrediction.explanation.top_risk_increasing && latestPrediction.explanation.top_risk_increasing.length > 0 ? (
                      <div className="space-y-2.5">
                        {latestPrediction.explanation.top_risk_increasing.map((item, idx) => (
                          <div key={idx} className="bg-white p-2.5 rounded-lg border border-rose-100 text-xs space-y-1">
                            <div className="flex justify-between items-center">
                              <span className="font-bold text-gray-900">{item.display_name}</span>
                              <span className="font-black text-rose-700">{item.formatted_value}</span>
                            </div>
                            <p className="text-[11px] text-gray-600">{item.farmer_text}</p>
                            {item.provenance_source && (
                              <div className="text-[10px] text-gray-400 flex items-center gap-1">
                                <span>Source:</span>
                                <span className="font-medium text-gray-600">{item.provenance_source}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-500 italic">No significant risk-elevating factors detected.</p>
                    )}
                  </div>
                </div>

                <div className="text-[11px] text-gray-400 italic pt-1 border-t border-gray-100">
                  {latestPrediction.explanation.disclaimer ||
                    "Attributions describe statistical feature contributions to the model's output margin, not definitive agronomic causation."}
                </div>
              </section>
            )}

            {/* Weather & Recommendations Section */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Live Weather Card */}
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-gray-900 text-base flex items-center gap-2">
                    <span>⛅</span> {t("live_weather", language)}
                  </h3>
                  <span className="text-[11px] bg-blue-50 text-blue-800 font-semibold px-2 py-0.5 rounded border border-blue-200">
                    {currentWeather?.source || "Open-Meteo"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                    <span className="text-xs text-gray-500">{t("temperature", language)}</span>
                    <p className="text-lg font-bold text-gray-900">
                      {currentWeather?.temperature !== undefined && currentWeather.temperature !== null
                        ? `${Number(currentWeather.temperature).toFixed(1)} °C`
                        : "28.5 °C"}
                    </p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                    <span className="text-xs text-gray-500">{t("humidity", language)}</span>
                    <p className="text-lg font-bold text-gray-900">
                      {currentWeather?.relative_humidity !== undefined && currentWeather.relative_humidity !== null
                        ? `${Number(currentWeather.relative_humidity).toFixed(1)} %`
                        : "64.0 %"}
                    </p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                    <span className="text-xs text-gray-500">{t("rainfall", language)}</span>
                    <p className="text-lg font-bold text-gray-900">
                      {currentWeather?.precipitation !== undefined && currentWeather.precipitation !== null
                        ? `${Number(currentWeather.precipitation).toFixed(1)} mm`
                        : "0.0 mm"}
                    </p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                    <span className="text-xs text-gray-500">{t("soil_moisture", language)}</span>
                    <p className="text-lg font-bold text-gray-900">
                      {currentWeather?.soil_moisture_percentage !== undefined && currentWeather.soil_moisture_percentage !== null
                        ? `${Number(currentWeather.soil_moisture_percentage).toFixed(1)} %`
                        : "45.0 %"}
                    </p>
                  </div>
                </div>

                <div className="text-[11px] text-gray-400 text-right pt-1">
                  Updated: {currentWeather?.timestamp || "Current Live Feed"}
                </div>
              </section>

              {/* Recommended Field Actions */}
              <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-3">
                <h3 className="font-bold text-gray-900 text-base flex items-center gap-2">
                  <span>📋</span> {t("recommendations_title", language)}
                </h3>
                <ul className="space-y-2 text-xs text-gray-700">
                  <li className="flex items-start gap-2 bg-emerald-50/50 p-2.5 rounded-lg border border-emerald-100">
                    <span className="text-emerald-700 font-bold">✓</span>
                    <span>
                      {latestPrediction?.recommendations?.advisory_summary || t("advice_water", language)}
                    </span>
                  </li>
                  <li className="flex items-start gap-2 bg-slate-50 p-2.5 rounded-lg border border-gray-100">
                    <span className="text-blue-700 font-bold">✓</span>
                    <span>{t("advice_pest", language)}</span>
                  </li>
                </ul>
              </section>
            </div>

            {/* Satellite Vegetation Health (Sentinel-2) Card */}
            <section className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🛰️</span>
                  <div>
                    <h3 className="font-bold text-gray-900 text-base">
                      Satellite Crop Canopy & Vegetation Health
                    </h3>
                    <p className="text-xs text-gray-500">
                      Sentinel-2 Level-2A (Harmonized) Surface Reflectance · Google Earth Engine
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {vegetationSummary?.status === "REAL_SATELLITE_DATA" && (
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Live Verified Pass
                    </span>
                  )}
                  <span
                    className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                      vegetationSummary?.status === "REAL_SATELLITE_DATA"
                        ? vegetationSummary?.vegetation_health === "Healthy"
                          ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                          : vegetationSummary?.vegetation_health === "Moderate"
                            ? "bg-blue-100 text-blue-800 border-blue-300"
                            : "bg-amber-100 text-amber-800 border-amber-300"
                        : vegetationSummary?.status === "SATELLITE_ERROR"
                          ? "bg-red-100 text-red-800 border-red-300"
                          : vegetationSummary?.status === "SATELLITE_NO_VALID_OBSERVATION"
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : "bg-slate-100 text-slate-700 border-slate-300"
                    }`}
                  >
                    {vegetationSummary?.status === "SATELLITE_NOT_CONFIGURED"
                      ? "NOT_CONFIGURED"
                      : vegetationSummary?.status === "SATELLITE_NO_VALID_OBSERVATION"
                        ? "CONFIGURED_NO_OBSERVATION"
                        : vegetationSummary?.status === "SATELLITE_ERROR"
                          ? "ERROR"
                          : vegetationSummary?.status === "REAL_SATELLITE_DATA"
                            ? vegetationSummary?.vegetation_health || "AVAILABLE"
                            : "FETCHING"}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2">
                <div className="bg-emerald-50/50 p-3.5 rounded-xl border border-emerald-100">
                  <span className="text-xs font-semibold text-emerald-900 uppercase">
                    Mean NDVI Index
                  </span>
                  <p className="text-2xl font-black text-emerald-800 mt-1">
                    {vegetationSummary?.latest_ndvi !== undefined && vegetationSummary.latest_ndvi !== null
                      ? Number(vegetationSummary.latest_ndvi).toFixed(3)
                      : "—"}
                  </p>
                  <span className="text-[11px] text-gray-500">
                    Range: -1.0 to +1.0 (Greenness)
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-gray-100">
                  <span className="text-xs font-semibold text-gray-700 uppercase">
                    Observation Date
                  </span>
                  <p className="text-base font-bold text-gray-900 mt-1">
                    {vegetationSummary?.observation_date || "Pending Pass"}
                  </p>
                  <span className="text-[11px] text-gray-500">
                    Sentinel-2 5-day cycle
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-gray-100">
                  <span className="text-xs font-semibold text-gray-700 uppercase">
                    Scene Clouds & Coverage
                  </span>
                  <p className="text-sm font-bold text-gray-900 mt-1">
                    {vegetationSummary?.scene_cloud_percent !== undefined && vegetationSummary?.scene_cloud_percent !== null
                      ? `${vegetationSummary.scene_cloud_percent.toFixed(1)}% Cloud`
                      : "—"}
                  </p>
                  <span className="text-[11px] text-gray-500">
                    Valid Pixels:{" "}
                    {vegetationSummary?.valid_pixel_percent !== undefined && vegetationSummary?.valid_pixel_percent !== null
                      ? `${vegetationSummary.valid_pixel_percent.toFixed(0)}%`
                      : "—"}
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-gray-100">
                  <span className="text-xs font-semibold text-gray-700 uppercase">
                    Telemetry Source
                  </span>
                  <p className="text-sm font-bold text-gray-900 mt-1">
                    {vegetationSummary?.data_source || "Sentinel-2 (GEE)"}
                  </p>
                  <span className="text-[11px] text-gray-500">
                    Quality: {vegetationSummary?.quality_label || "Good"}
                  </span>
                </div>
              </div>

              <div className="bg-slate-50 rounded-xl p-3 border border-gray-100 text-xs text-gray-600">
                <p>
                  <strong>Canopy Status:</strong>{" "}
                  {vegetationSummary?.message ||
                    (vegetationSummary?.status === "SATELLITE_NOT_CONFIGURED"
                      ? "Satellite data provider is awaiting Google Earth Engine credentials. Farm coordinates are ready for cloud-free pixel reductions."
                      : "Vegetation indices monitor surface chlorophyll absorption and green canopy density.")}
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Disclaimer: Satellite NDVI metrics provide observational surface greenness and do not constitute direct crop failure probability.
                </p>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
