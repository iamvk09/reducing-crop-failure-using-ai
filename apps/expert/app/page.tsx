"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { RiskBadge } from "@shared/components/RiskBadge";
import { listFarms } from "@shared/api/farms";
import { simulateScenario, explainPrediction } from "@shared/api/experts";
import { listFarmPredictions, predictForFarm } from "@shared/api/predictions";
import { getCurrentWeather, getWeatherForecast, getWeatherHistory } from "@shared/api/weather";
import { getLatestSatelliteObservation, getSatelliteHistory } from "@shared/api/satellite";
import { getFarmMonitoring, getMonitoringDiagnostics } from "@shared/api/monitoring";
import { listExpertAlerts, acknowledgeFarmAlert, resolveFarmAlert } from "@shared/api/alerts";
import { getModelEvaluation, getEvaluationReadiness, verifyCropOutcomeExpert } from "@shared/api/evaluation";
import {
  getNeuroFuzzyStatus,
  predictNeuroFuzzy,
  getNeuroFuzzyComparison,
  NeuroFuzzyStatusResponse,
  NeuroFuzzyPredictionResponse,
} from "@shared/api/neuro_fuzzy";
import {
  CurrentWeatherResponse,
  EvaluationReadinessResponse,
  Farm,
  FarmAlert,
  FarmMonitoringResponse,
  ModelEvaluationReport,
  MonitoringDiagnosticsResponse,
  PredictionResponse,
  SatelliteObservationResponse,
  ScenarioSimulationResponse,
  ShapExplanationResponse,
  WeatherForecastResponse,
  WeatherObservationRecord,
} from "@shared/types";

type TabKey =
  | "overview"
  | "predictions"
  | "monitoring"
  | "alerts"
  | "weather"
  | "twin"
  | "shap"
  | "farms"
  | "performance"
  | "models"
  | "satellite"
  | "evaluation"
  | "neurofuzzy";

export default function ExpertDashboard() {
  const { user, profile, token, role, isLoading: authLoading, signInWithDevRole } = useAuth();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [farms, setFarms] = useState<Farm[]>([]);
  const [selectedFarmId, setSelectedFarmId] = useState<string>("");
  const [farmPredictions, setFarmPredictions] = useState<PredictionResponse[]>([]);
  const [isLoadingFarms, setIsLoadingFarms] = useState(false);
  const [isLoadingPredictions, setIsLoadingPredictions] = useState(false);
  const [isExecutingPrediction, setIsExecutingPrediction] = useState(false);

  // Closed-Loop Monitoring state
  const [monitoringSummary, setMonitoringSummary] = useState<FarmMonitoringResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<MonitoringDiagnosticsResponse | null>(null);
  const [isLoadingMonitoring, setIsLoadingMonitoring] = useState(false);

  // Weather Telemetry state
  const [currentWeather, setCurrentWeather] = useState<CurrentWeatherResponse | null>(null);
  const [forecastWeather, setForecastWeather] = useState<WeatherForecastResponse | null>(null);
  const [weatherHistory, setWeatherHistory] = useState<WeatherObservationRecord[]>([]);
  const [isLoadingWeather, setIsLoadingWeather] = useState<boolean>(false);

  // Satellite Telemetry state
  const [latestSatellite, setLatestSatellite] = useState<SatelliteObservationResponse | null>(null);
  const [satelliteHistory, setSatelliteHistory] = useState<SatelliteObservationResponse[]>([]);
  const [isLoadingSatellite, setIsLoadingSatellite] = useState<boolean>(false);

  // Digital Twin state
  const [twinCrop, setTwinCrop] = useState("Soybean");
  const [twinDistrict, setTwinDistrict] = useState("Pune");
  const [twinSeason, setTwinSeason] = useState("Kharif");
  const [tempDelta, setTempDelta] = useState(2.0);
  const [rainDeltaPct, setRainDeltaPct] = useState(-20.0);
  const [twinResult, setTwinResult] = useState<ScenarioSimulationResponse | null>(null);
  const [twinLoading, setTwinLoading] = useState(false);

  // SHAP state
  const [shapResult, setShapResult] = useState<ShapExplanationResponse | null>(null);
  const [shapLoading, setShapLoading] = useState(false);

  // Prediction Overrides state
  const [tempOverride, setTempOverride] = useState<string>("");
  const [rainOverride, setRainOverride] = useState<string>("");
  const [ndviOverride, setNdviOverride] = useState<string>("");

  // Early Warning & Alert Engine state
  const [expertAlerts, setExpertAlerts] = useState<FarmAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState<boolean>(false);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertFilter, setAlertFilter] = useState<string>("all");
  const [resolutionNotes, setResolutionNotes] = useState<Record<string, string>>({});
  const [actionAlertId, setActionAlertId] = useState<string | null>(null);

  // Model Evaluation state (Expert/Admin only — never for farmers)
  const [evalReport, setEvalReport] = useState<ModelEvaluationReport | null>(null);
  const [evalLoading, setEvalLoading] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Evaluation Readiness state (Milestone 12)
  const [readinessData, setReadinessData] = useState<EvaluationReadinessResponse | null>(null);
  const [readinessLoading, setReadinessLoading] = useState<boolean>(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [verifyingCropId, setVerifyingCropId] = useState<string | null>(null);
  const [verifyingAction, setVerifyingAction] = useState<"verify" | "reject">("verify");
  const [verifyingNote, setVerifyingNote] = useState<string>("");
  const [verificationFeedback, setVerificationFeedback] = useState<string | null>(null);

  // Experimental Neuro-Fuzzy state
  const [nfStatus, setNfStatus] = useState<NeuroFuzzyStatusResponse | null>(null);
  const [nfComparison, setNfComparison] = useState<Array<Record<string, any>>>([]);
  const [nfLoading, setNfLoading] = useState<boolean>(false);
  const [nfError, setNfError] = useState<string | null>(null);
  const [nfPredictionResult, setNfPredictionResult] = useState<NeuroFuzzyPredictionResponse | null>(null);
  const [nfPredicting, setNfPredicting] = useState<boolean>(false);

  // Neuro-Fuzzy Test Inputs
  const [nfRainfall, setNfRainfall] = useState<number>(115.0);
  const [nfTemperature, setNfTemperature] = useState<number>(29.5);
  const [nfHumidity, setNfHumidity] = useState<number>(58.0);
  const [nfSoilMoisture, setNfSoilMoisture] = useState<number>(38.0);
  const [nfNdvi, setNfNdvi] = useState<number>(0.62);
  const [nfWaterStress, setNfWaterStress] = useState<number>(0.35);
  const [nfPestRisk, setNfPestRisk] = useState<number>(0.42);
  const [nfSuitability, setNfSuitability] = useState<number>(0.75);

  const loadNeuroFuzzyData = async () => {
    if (!token) return;
    setNfLoading(true);
    setNfError(null);
    try {
      const [statusRes, compRes] = await Promise.all([
        getNeuroFuzzyStatus(token).catch(() => null),
        getNeuroFuzzyComparison(token).catch(() => []),
      ]);
      if (statusRes) setNfStatus(statusRes);
      if (compRes) setNfComparison(compRes);
    } catch (err: any) {
      setNfError(err.message || "Failed to load Neuro-Fuzzy model state.");
    } finally {
      setNfLoading(false);
    }
  };

  useEffect(() => {
    if (token && activeTab === "neurofuzzy") {
      loadNeuroFuzzyData();
    }
  }, [token, activeTab]);

  useEffect(() => {
    if (!authLoading && !user) {
      signInWithDevRole("expert");
    }
  }, [user, authLoading, signInWithDevRole]);

  useEffect(() => {
    if (token && (activeTab === "alerts" || activeTab === "overview")) {
      setAlertsLoading(true);
      setAlertsError(null);
      listExpertAlerts(token)
        .then((data) => setExpertAlerts(data))
        .catch((err) => setAlertsError(err.message || "Failed to load cross-farm alerts."))
        .finally(() => setAlertsLoading(false));
    }
  }, [token, activeTab]);

  useEffect(() => {
    if (token && (activeTab === "farms" || activeTab === "overview" || activeTab === "predictions" || activeTab === "monitoring" || activeTab === "weather" || activeTab === "satellite")) {
      setIsLoadingFarms(true);
      listFarms(token)
        .then((data) => {
          setFarms(data);
          if (data.length > 0 && !selectedFarmId) {
            setSelectedFarmId(data[0].id);
          }
        })
        .catch((err) => console.error("Could not fetch expert farms:", err))
        .finally(() => setIsLoadingFarms(false));
    }
  }, [token, activeTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeTab === "monitoring" && selectedFarmId) {
      setIsLoadingMonitoring(true);
      Promise.all([
        getFarmMonitoring(selectedFarmId, token).catch(() => null),
        getMonitoringDiagnostics(selectedFarmId, token).catch(() => null),
      ])
        .then(([mon, diag]) => {
          setMonitoringSummary(mon);
          setDiagnostics(diag);
        })
        .finally(() => setIsLoadingMonitoring(false));
    }
  }, [token, activeTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeTab === "predictions" && selectedFarmId) {
      setIsLoadingPredictions(true);
      listFarmPredictions(selectedFarmId, token)
        .then(setFarmPredictions)
        .catch((err) => console.error("Could not fetch farm predictions:", err))
        .finally(() => setIsLoadingPredictions(false));
    }
  }, [token, activeTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeTab === "weather" && selectedFarmId) {
      setIsLoadingWeather(true);
      Promise.all([
        getCurrentWeather(selectedFarmId, token).catch(() => null),
        getWeatherForecast(selectedFarmId, token, 7).catch(() => null),
        getWeatherHistory(selectedFarmId, token, 10).catch(() => []),
      ])
        .then(([current, forecast, history]) => {
          setCurrentWeather(current);
          setForecastWeather(forecast);
          setWeatherHistory(history);
        })
        .finally(() => setIsLoadingWeather(false));
    }
  }, [token, activeTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeTab === "satellite" && selectedFarmId) {
      setIsLoadingSatellite(true);
      Promise.all([
        getLatestSatelliteObservation(selectedFarmId, token).catch(() => null),
        getSatelliteHistory(selectedFarmId, token, 20).catch(() => []),
      ])
        .then(([latest, history]) => {
          setLatestSatellite(latest);
          setSatelliteHistory(history);
        })
        .finally(() => setIsLoadingSatellite(false));
    }
  }, [token, activeTab, selectedFarmId]);

  const loadEvaluationData = () => {
    if (!token) return;
    setEvalLoading(true);
    setEvalError(null);
    setReadinessLoading(true);
    setReadinessError(null);
    Promise.all([
      getModelEvaluation(token).catch((err) => {
        setEvalError(err.message || "Failed to load model evaluation report.");
        return null;
      }),
      getEvaluationReadiness(token).catch((err) => {
        setReadinessError(err.message || "Failed to load evaluation readiness queue.");
        return null;
      }),
    ])
      .then(([evaluation, readiness]) => {
        if (evaluation) setEvalReport(evaluation);
        if (readiness) setReadinessData(readiness);
      })
      .finally(() => {
        setEvalLoading(false);
        setReadinessLoading(false);
      });
  };

  useEffect(() => {
    if (token && activeTab === "evaluation") {
      loadEvaluationData();
    }
  }, [token, activeTab]);

  const handleVerifyCropOutcome = async (cropId: string, farmId?: string) => {
    if (!token) return;
    setVerificationFeedback(null);
    try {
      await verifyCropOutcomeExpert(
        cropId,
        {
          action: verifyingAction,
          verification_notes: verifyingNote || undefined,
        },
        farmId,
        token
      );
      setVerificationFeedback(
        `Successfully ${verifyingAction === "verify" ? "verified" : "marked invalid"} crop outcome!`
      );
      setVerifyingCropId(null);
      setVerifyingNote("");
      // Reload both evaluation and readiness reports
      loadEvaluationData();
    } catch (err: any) {
      setVerificationFeedback(`Error: ${err.message || "Failed to verify outcome."}`);
    }
  };

  const handleRunTwin = async () => {
    if (!token) return;
    setTwinLoading(true);
    try {
      const res = await simulateScenario(
        {
          scenario_name: `Stress Test: ${tempDelta > 0 ? "+" : ""}${tempDelta}°C, ${rainDeltaPct}% Rain`,
          updates: {
            Temperature: 28.5 + tempDelta,
            Rainfall: Math.max(0, 150.0 * (1 + rainDeltaPct / 100)),
          },
        },
        { district: twinDistrict, crop: twinCrop, season: twinSeason },
        token
      );
      setTwinResult(res);
    } catch (err: any) {
      alert(`Simulation Error: ${err.message}`);
    } finally {
      setTwinLoading(false);
    }
  };

  const handleRunShap = async () => {
    if (!token) return;
    setShapLoading(true);
    try {
      const res = await explainPrediction(
        { district: twinDistrict, crop: twinCrop, season: twinSeason },
        token
      );
      setShapResult(res);
    } catch (err: any) {
      alert(`SHAP Error: ${err.message}`);
    } finally {
      setShapLoading(false);
    }
  };

  const handleExecuteFarmPrediction = async () => {
    if (!selectedFarmId || !token) return;
    setIsExecutingPrediction(true);
    try {
      const overrides: Record<string, number> = {};
      if (tempOverride !== "") overrides.temperature_override = parseFloat(tempOverride);
      if (rainOverride !== "") overrides.rainfall_override = parseFloat(rainOverride);
      if (ndviOverride !== "") overrides.ndvi_override = parseFloat(ndviOverride);

      const res = await predictForFarm(selectedFarmId, overrides, token);
      setFarmPredictions((prev) => [res, ...prev]);
    } catch (err: any) {
      alert(`Prediction Error: ${err.message}`);
    } finally {
      setIsExecutingPrediction(false);
    }
  };

  const handleExpertAcknowledge = async (alertId: string, farmId: string) => {
    if (!token) return;
    setActionAlertId(alertId);
    try {
      const updated = await acknowledgeFarmAlert(farmId, alertId, token);
      setExpertAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId
            ? { ...a, status: "acknowledged", acknowledged_at: updated.acknowledged_at }
            : a
        )
      );
    } catch (err: any) {
      alert(`Acknowledge failed: ${err.message}`);
    } finally {
      setActionAlertId(null);
    }
  };

  const handleExpertResolve = async (alertId: string, farmId: string) => {
    if (!token) return;
    setActionAlertId(alertId);
    try {
      const note = resolutionNotes[alertId];
      const updated = await resolveFarmAlert(farmId, alertId, token, note);
      setExpertAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId
            ? { ...a, status: "resolved", resolved_at: updated.resolved_at }
            : a
        )
      );
    } catch (err: any) {
      alert(`Resolve failed: ${err.message}`);
    } finally {
      setActionAlertId(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <Navbar portalType="expert" />

      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 flex flex-col md:flex-row gap-6">
        {/* Sidebar Navigation */}
        <aside className="w-full md:w-64 bg-white rounded-2xl p-4 shadow-sm border border-slate-200 shrink-0">
          <div className="mb-4 pb-3 border-b border-gray-100">
            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-800 bg-blue-50 px-2.5 py-1 rounded-full">
              Agronomy Workbench
            </span>
            <h2 className="text-sm font-bold text-gray-900 mt-2">Expert Controls</h2>
            <p className="text-xs text-gray-500">{profile?.full_name || "Expert User"}</p>
          </div>

          <nav className="space-y-1">
            {[
              { id: "overview", label: "📊 Overview", active: true },
              { id: "predictions", label: "📈 Live Farm Inference", active: true },
              { id: "monitoring", label: "🔄 Closed-Loop Monitoring", active: true },
              { id: "alerts", label: "🚨 Early Warnings", active: true },
              { id: "weather", label: "⛅ Weather & Telemetry", active: true },
              { id: "twin", label: "🔬 Digital Twin", active: true },
              { id: "shap", label: "🧠 SHAP Explainability", active: true },
              { id: "farms", label: "🗺️ Monitored Farms", active: true },
              { id: "satellite", label: "🛰️ Satellite (Sentinel-2)", active: true },
              { id: "neurofuzzy", label: "🧬 Neuro-Fuzzy Model", active: true },
              { id: "evaluation", label: "🎯 Model Evaluation", active: true },
              { id: "performance", label: "📊 Model Validation (v2)", active: false },
              { id: "models", label: "📦 Model Versions", active: false },
            ].map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id as TabKey)}
                className={`w-full text-left px-3 py-2 rounded-xl text-xs font-bold transition flex items-center justify-between ${
                  activeTab === item.id
                    ? "bg-blue-900 text-white shadow-sm"
                    : "text-gray-700 hover:bg-slate-100"
                }`}
              >
                <span>{item.label}</span>
                {!item.active && (
                  <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                    Planned
                  </span>
                )}
              </button>
            ))}
          </nav>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Expert System Status & Telemetry</h2>
                <p className="text-xs text-gray-500">Live indicators from authenticated backend services.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Monitored Farms</span>
                  <p className="text-2xl font-black text-blue-900 mt-1">{farms.length}</p>
                  <span className="text-[11px] text-gray-400">Queried via GET /api/v1/farms</span>
                </div>
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Active ML Model</span>
                  <p className="text-lg font-bold text-emerald-800 mt-1">agri_ai_runtime_bundle</p>
                  <span className="text-[11px] text-emerald-600 font-medium">CalibratedClassifierCV / RF</span>
                </div>
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Weather Gateway</span>
                  <p className="text-lg font-bold text-blue-800 mt-1">Open-Meteo REST</p>
                  <span className="text-[11px] text-blue-600 font-medium">Real-time hourly/daily feed</span>
                </div>
              </div>

              <div className="border-t border-gray-100 pt-4">
                <h3 className="text-sm font-bold text-gray-800 mb-2">Verified Architectural Capabilities</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 bg-blue-50 rounded-xl border border-blue-200 text-blue-900">
                    <strong>✅ Live ML Inference:</strong> Full 16-feature vector evaluation with provenance and agronomic recommendations.
                  </div>
                  <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-emerald-900">
                    <strong>✅ Live Parametric Digital Twin:</strong> Stress-test temperature, rainfall, and soil moisture variations.
                  </div>
                  <div className="p-3 bg-purple-50 rounded-xl border border-purple-200 text-purple-900">
                    <strong>✅ Explainable AI (SHAP):</strong> TreeExplainer feature importance attributions calculated on demand.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB: LIVE FARM PREDICTIONS */}
          {activeTab === "predictions" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Live Farm Risk Inference Engine</h2>
                <p className="text-xs text-gray-500">
                  Evaluate registered farm plots using real-time Open-Meteo weather and trained ML pipelines.
                </p>
              </div>

              {/* Farm Selector & Overrides Panel */}
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                      Select Target Farm
                    </label>
                    <select
                      value={selectedFarmId}
                      onChange={(e) => setSelectedFarmId(e.target.value)}
                      className="w-full bg-white border border-gray-300 rounded-lg p-2 text-xs font-bold"
                    >
                      {farms.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name} — {f.district}, {f.state}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-end">
                    <button
                      onClick={handleExecuteFarmPrediction}
                      disabled={isExecutingPrediction || !selectedFarmId}
                      className="w-full py-2.5 bg-blue-900 hover:bg-blue-950 disabled:bg-gray-400 text-white font-bold rounded-xl text-xs shadow transition flex items-center justify-center gap-2"
                    >
                      {isExecutingPrediction ? "Evaluating Risk Pipeline..." : "⚡ Execute Live Inference"}
                    </button>
                  </div>
                </div>

                {/* Optional Overrides */}
                <div className="pt-3 border-t border-gray-200">
                  <span className="text-[11px] font-bold text-gray-600 uppercase block mb-2">
                    Optional Agronomic Overrides (Expert Sensitivity Test)
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    <div>
                      <label className="text-gray-500 block">Temperature Override (°C)</label>
                      <input
                        type="number"
                        placeholder="e.g. 36.5"
                        value={tempOverride}
                        onChange={(e) => setTempOverride(e.target.value)}
                        className="w-full bg-white border border-gray-300 rounded-lg p-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-gray-500 block">Rainfall Override (mm)</label>
                      <input
                        type="number"
                        placeholder="e.g. 15.0"
                        value={rainOverride}
                        onChange={(e) => setRainOverride(e.target.value)}
                        className="w-full bg-white border border-gray-300 rounded-lg p-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-gray-500 block">NDVI Override (0.0 - 1.0)</label>
                      <input
                        type="number"
                        step="0.05"
                        placeholder="e.g. 0.45"
                        value={ndviOverride}
                        onChange={(e) => setNdviOverride(e.target.value)}
                        className="w-full bg-white border border-gray-300 rounded-lg p-1.5 text-xs"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Prediction Results History */}
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-gray-900">Inference History for Selected Farm</h3>

                {isLoadingPredictions ? (
                  <p className="text-xs text-gray-500 py-6 text-center">Loading inference records...</p>
                ) : farmPredictions.length === 0 ? (
                  <div className="p-6 bg-slate-50 rounded-xl text-center text-xs text-gray-500 border border-slate-200">
                    No predictions recorded yet for this farm. Click &quot;Execute Live Inference&quot; above to run the ML model.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {farmPredictions.map((pred, idx) => (
                      <div
                        key={pred.prediction_id || idx}
                        className="p-4 bg-white border border-gray-200 rounded-xl shadow-sm space-y-3"
                      >
                        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                          <div className="flex items-center gap-3">
                            <RiskBadge level={pred.risk_level} />
                            <div>
                              <span className="font-bold text-gray-900 text-sm">
                                {pred.crop} ({pred.season}) · {pred.district}, {pred.state}
                              </span>
                              <span className="text-[11px] text-gray-400 block">
                                Inferred: {new Date(pred.created_at).toLocaleString()} · Model: {pred.best_model_name}
                              </span>
                            </div>
                          </div>
                          <div className="text-right">
                            <span className="text-lg font-black text-gray-900">{pred.risk_percentage}</span>
                            <span className="text-[11px] text-gray-500 block">Failure Risk</span>
                          </div>
                        </div>

                        {/* Advisory text */}
                        {pred.recommendations?.advisory_summary && (
                          <div className="p-2.5 bg-emerald-50 rounded-lg border border-emerald-100 text-xs text-emerald-900">
                            <strong>Agronomic Advisory:</strong> {pred.recommendations.advisory_summary}
                          </div>
                        )}

                        {/* Data Freshness & Quality Coverage Header */}
                        <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex flex-wrap items-center justify-between gap-2 text-[11px]">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-gray-700">Data Freshness:</span>
                            <span className="px-2 py-0.5 rounded font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                              LIVE: {pred.data_quality?.live_feature_count ?? 9}/16
                            </span>
                            <span className="px-2 py-0.5 rounded font-bold bg-blue-100 text-blue-800 border border-blue-200">
                              DERIVED: {pred.data_quality?.derived_feature_count ?? 2}/16
                            </span>
                            <span className="px-2 py-0.5 rounded font-bold bg-amber-100 text-amber-800 border border-amber-200">
                              BASELINE: {pred.data_quality?.baseline_feature_count ?? 5}/16
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-gray-500">
                            <span>Weather: <strong className="text-gray-800">{pred.data_quality?.weather_status ?? "live_fresh"}</strong></span>
                            <span>·</span>
                            <span>Satellite: <strong className="text-gray-800">{pred.data_quality?.satellite_status ?? "baseline"}</strong></span>
                          </div>
                        </div>

                        {/* Input Features & Provenance Grid with Visual Source Tags */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-gray-100 text-[11px]">
                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Temperature</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                                LIVE
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.Temperature !== undefined
                                ? `${Number(pred.input_features.Temperature).toFixed(1)} °C`
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.Temperature}>
                              {pred.provenance?.Temperature || "Live weather"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Humidity</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                                LIVE
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.Humidity !== undefined
                                ? `${Number(pred.input_features.Humidity).toFixed(1)} %`
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.Humidity}>
                              {pred.provenance?.Humidity || "Live relative humidity"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Rainfall</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-blue-100 text-blue-800">
                                DERIVED
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.Rainfall !== undefined
                                ? `${Number(pred.input_features.Rainfall).toFixed(1)} mm`
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.Rainfall}>
                              {pred.provenance?.Rainfall || "Accumulated / Seasonal baseline"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Soil Moisture</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                                LIVE
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.SoilMoisture !== undefined
                                ? `${Number(pred.input_features.SoilMoisture).toFixed(1)} %`
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.SoilMoisture}>
                              {pred.provenance?.SoilMoisture || "Root-zone saturation (0-27cm)"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">NDVI (Flowering)</span>
                              <span className={`text-[9px] font-black px-1.5 py-0.2 rounded ${
                                pred.data_quality?.satellite_status === "live_fresh"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-amber-100 text-amber-800"
                              }`}>
                                {pred.data_quality?.satellite_status === "live_fresh" ? "LIVE" : "BASELINE"}
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.NDVI_Flowering !== undefined
                                ? Number(pred.input_features.NDVI_Flowering).toFixed(3)
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.NDVI_Flowering}>
                              {pred.provenance?.NDVI_Flowering || "Stage-calibrated canopy baseline"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Water Stress</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-blue-100 text-blue-800">
                                DERIVED
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.WaterStress !== undefined
                                ? Number(pred.input_features.WaterStress).toFixed(3)
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.WaterStress}>
                              {pred.provenance?.WaterStress || "Moisture deficit model"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Pest Risk</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
                                BASELINE
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.PestRisk !== undefined
                                ? Number(pred.input_features.PestRisk).toFixed(2)
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.PestRisk}>
                              {pred.provenance?.PestRisk || "Regional baseline"}
                            </span>
                          </div>

                          <div className="bg-slate-50 p-2 rounded relative">
                            <div className="flex justify-between items-center mb-0.5">
                              <span className="text-gray-500">Suitability</span>
                              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
                                BASELINE
                              </span>
                            </div>
                            <span className="font-bold text-gray-900">
                              {pred.input_features?.SuitabilityScore !== undefined
                                ? Number(pred.input_features.SuitabilityScore).toFixed(2)
                                : "N/A"}
                            </span>
                            <span className="text-[10px] text-gray-400 block truncate" title={pred.provenance?.SuitabilityScore}>
                              {pred.provenance?.SuitabilityScore || "Agro-ecological score"}
                            </span>
                          </div>
                        </div>

                        {/* SHAP Feature Attributions & Decision Margin */}
                        {pred.explanation && (
                          <div className="mt-3 pt-3 border-t border-gray-100 bg-slate-50/50 p-3 rounded-xl space-y-3">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <span className="text-sm">🧠</span>
                                <span className="text-xs font-bold text-gray-900">
                                  SHAP Feature Attribution Breakdown ({pred.explanation.explainer_type})
                                </span>
                              </div>
                              <div className="flex items-center gap-3 text-[11px] font-mono text-gray-600">
                                <span>Base: <strong>{pred.explanation.base_value >= 0 ? `+${pred.explanation.base_value.toFixed(4)}` : pred.explanation.base_value.toFixed(4)}</strong></span>
                                <span>Σ SHAP: <strong>{pred.explanation.sum_shap >= 0 ? `+${pred.explanation.sum_shap.toFixed(4)}` : pred.explanation.sum_shap.toFixed(4)}</strong></span>
                                <span>Margin: <strong className="text-blue-900">{pred.explanation.margin_value >= 0 ? `+${pred.explanation.margin_value.toFixed(4)}` : pred.explanation.margin_value.toFixed(4)}</strong></span>
                              </div>
                            </div>

                            {pred.explanation.summary_narrative && (
                              <p className="text-xs text-gray-700 bg-white p-2.5 rounded-lg border border-gray-200">
                                {pred.explanation.summary_narrative}
                              </p>
                            )}

                            {/* Top 3 Mitigating vs Escalating Horizontal Impact Chart */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              <div className="bg-emerald-50/70 border border-emerald-200 rounded-lg p-2.5 space-y-1.5">
                                <span className="text-[10px] font-bold text-emerald-900 uppercase block">
                                  🛡️ Top Risk-Reducing Contributors (φ &lt; 0)
                                </span>
                                {pred.explanation.top_risk_reducing.map((f, i) => (
                                  <div key={i} className="flex justify-between items-center text-xs bg-white p-1.5 rounded border border-emerald-100">
                                    <span className="font-semibold text-gray-800 truncate max-w-[150px]">{f.display_name}</span>
                                    <span className="font-bold text-emerald-700 font-mono text-[11px]">
                                      {f.attribution_value.toFixed(4)} ({f.formatted_value})
                                    </span>
                                  </div>
                                ))}
                              </div>

                              <div className="bg-rose-50/70 border border-rose-200 rounded-lg p-2.5 space-y-1.5">
                                <span className="text-[10px] font-bold text-rose-900 uppercase block">
                                  ⚠️ Top Risk-Elevating Contributors (φ &gt; 0)
                                </span>
                                {pred.explanation.top_risk_increasing.map((f, i) => (
                                  <div key={i} className="flex justify-between items-center text-xs bg-white p-1.5 rounded border border-rose-100">
                                    <span className="font-semibold text-gray-800 truncate max-w-[150px]">{f.display_name}</span>
                                    <span className="font-bold text-rose-700 font-mono text-[11px]">
                                      +{f.attribution_value.toFixed(4)} ({f.formatted_value})
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>

                            {/* Full 16-feature table details */}
                            <details className="text-xs">
                              <summary className="font-bold text-blue-900 cursor-pointer hover:underline py-1">
                                📊 View Complete 16-Feature Attribution Table ({pred.explanation.all_features?.length || 16} features)
                              </summary>
                              <div className="mt-2 overflow-x-auto border border-gray-200 rounded-lg bg-white">
                                <table className="min-w-full divide-y divide-gray-200 text-left text-[11px]">
                                  <thead className="bg-slate-100 font-bold text-gray-700">
                                    <tr>
                                      <th className="p-2">Feature Name</th>
                                      <th className="p-2">Input Value</th>
                                      <th className="p-2">Provenance Source</th>
                                      <th className="p-2">SHAP (φ)</th>
                                      <th className="p-2">Direction</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-gray-100">
                                    {pred.explanation.all_features.map((f, i) => (
                                      <tr key={i} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium text-gray-900">
                                          {f.display_name} <span className="text-gray-400">({f.feature_name})</span>
                                        </td>
                                        <td className="p-2 font-semibold text-gray-800">{f.formatted_value}</td>
                                        <td className="p-2 text-gray-500">{f.provenance_source || "Empirical Baseline"}</td>
                                        <td className="p-2 font-mono font-bold">
                                          <span className={f.attribution_value > 0 ? "text-rose-700" : f.attribution_value < 0 ? "text-emerald-700" : "text-gray-500"}>
                                            {f.attribution_value > 0 ? `+${f.attribution_value.toFixed(4)}` : f.attribution_value.toFixed(4)}
                                          </span>
                                        </td>
                                        <td className="p-2">
                                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                            f.direction === "increases_risk" ? "bg-rose-100 text-rose-800" :
                                            f.direction === "reduces_risk" ? "bg-emerald-100 text-emerald-800" :
                                            "bg-gray-100 text-gray-700"
                                          }`}>
                                            {f.direction_label}
                                          </span>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </details>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB: CLOSED-LOOP MONITORING */}
          {activeTab === "monitoring" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Closed-Loop Risk Intelligence & Monitoring</h2>
                  <p className="text-xs text-gray-500">
                    Continuous observation-prediction-feedback tracking, telemetry deltas, SHAP attribution shifts, and operational diagnostics.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <div className="w-56">
                    <label className="block text-[10px] font-bold text-gray-500 uppercase mb-0.5">Select Farm</label>
                    <select
                      value={selectedFarmId}
                      onChange={(e) => setSelectedFarmId(e.target.value)}
                      className="w-full bg-slate-50 border border-gray-300 rounded-lg p-2 text-xs font-bold text-gray-800"
                    >
                      {farms.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name} ({f.district})
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={() => {
                      if (token && selectedFarmId) {
                        setIsLoadingMonitoring(true);
                        Promise.all([
                          getFarmMonitoring(selectedFarmId, token).catch(() => null),
                          getMonitoringDiagnostics(selectedFarmId, token).catch(() => null),
                        ])
                          .then(([mon, diag]) => {
                            setMonitoringSummary(mon);
                            setDiagnostics(diag);
                          })
                          .finally(() => setIsLoadingMonitoring(false));
                      }
                    }}
                    className="mt-4 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-gray-700 text-xs font-bold rounded-lg transition"
                  >
                    🔄 Refresh
                  </button>
                </div>
              </div>

              {isLoadingMonitoring ? (
                <div className="py-16 text-center text-gray-400">
                  <div className="inline-block animate-spin text-2xl mb-2">🔄</div>
                  <p className="text-xs font-semibold">Aggregating closed-loop monitoring telemetry & SHAP progression...</p>
                </div>
              ) : !monitoringSummary ? (
                <div className="p-8 text-center bg-slate-50 border border-dashed border-gray-200 rounded-xl">
                  <p className="text-sm font-semibold text-gray-600">No monitoring telemetry available for this farm.</p>
                  <p className="text-xs text-gray-400 mt-1">Run an inference under Live Farm Inference to initiate closed-loop tracking.</p>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Status & Farm Overview Banner */}
                  <div className="bg-gradient-to-r from-slate-900 to-blue-950 text-white p-5 rounded-2xl shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold text-blue-300 uppercase tracking-wider">
                          {monitoringSummary.farm_name} • {monitoringSummary.district}, {monitoringSummary.state}
                        </span>
                        {monitoringSummary.active_crop && (
                          <span className="text-[10px] bg-emerald-900/60 border border-emerald-500/40 text-emerald-300 px-2 py-0.5 rounded-full font-bold">
                            🌱 {monitoringSummary.active_crop} ({monitoringSummary.growth_stage || "Active Stage"})
                          </span>
                        )}
                      </div>
                      <h3 className="text-lg font-bold">Closed-Loop Farm Telemetry Loop</h3>
                      <p className="text-xs text-slate-300 mt-1 max-w-xl">
                        {monitoringSummary.status_reason}
                      </p>
                    </div>

                    <div className="flex flex-col sm:items-end gap-1">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Monitoring Status</span>
                      <span className={`px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider ${
                        monitoringSummary.monitoring_status === "optimal"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/50"
                          : monitoringSummary.monitoring_status === "attention_needed"
                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/50"
                          : monitoringSummary.monitoring_status === "active"
                          ? "bg-blue-500/20 text-blue-300 border border-blue-500/50"
                          : "bg-slate-700 text-slate-300"
                      }`}>
                        {monitoringSummary.monitoring_status.replace("_", " ")}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1">
                        Evaluated: {new Date(monitoringSummary.last_evaluated_at).toLocaleString()}
                      </span>
                    </div>
                  </div>

                  {/* 4 Risk KPI Progression Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl">
                      <span className="text-[11px] font-bold text-gray-500 uppercase block mb-1">Current Risk</span>
                      <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-black text-gray-900">
                          {(monitoringSummary.risk_trend.current_risk_probability * 100).toFixed(1)}%
                        </span>
                        {monitoringSummary.latest_prediction && (
                          <RiskBadge level={monitoringSummary.latest_prediction.risk_level} />
                        )}
                      </div>
                      <span className="text-[10px] text-gray-400 block mt-1">Latest inference probability</span>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl">
                      <span className="text-[11px] font-bold text-gray-500 uppercase block mb-1">Previous Risk</span>
                      <div className="text-2xl font-black text-gray-700">
                        {monitoringSummary.risk_trend.previous_risk_probability !== null && monitoringSummary.risk_trend.previous_risk_probability !== undefined
                          ? `${(monitoringSummary.risk_trend.previous_risk_probability * 100).toFixed(1)}%`
                          : "—"}
                      </div>
                      <span className="text-[10px] text-gray-400 block mt-1">
                        {monitoringSummary.risk_trend.previous_prediction_timestamp
                          ? new Date(monitoringSummary.risk_trend.previous_prediction_timestamp).toLocaleDateString()
                          : "Prior assessment"}
                      </span>
                    </div>

                    <div className={`p-4 rounded-xl border ${
                      monitoringSummary.risk_trend.trend_direction === "increasing"
                        ? "bg-rose-50 border-rose-200"
                        : monitoringSummary.risk_trend.trend_direction === "decreasing"
                        ? "bg-emerald-50 border-emerald-200"
                        : "bg-blue-50 border-blue-200"
                    }`}>
                      <span className="text-[11px] font-bold text-gray-500 uppercase block mb-1">Consecutive Delta</span>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-2xl font-black ${
                          monitoringSummary.risk_trend.trend_direction === "increasing"
                            ? "text-rose-700"
                            : monitoringSummary.risk_trend.trend_direction === "decreasing"
                            ? "text-emerald-700"
                            : "text-blue-700"
                        }`}>
                          {monitoringSummary.risk_trend.risk_delta_percentage_points !== null && monitoringSummary.risk_trend.risk_delta_percentage_points !== undefined
                            ? `${monitoringSummary.risk_trend.risk_delta_percentage_points > 0 ? "+" : ""}${monitoringSummary.risk_trend.risk_delta_percentage_points.toFixed(1)} pp`
                            : "Baseline"}
                        </span>
                      </div>
                      <span className="text-[10px] font-bold text-gray-600 uppercase block mt-1">
                        {monitoringSummary.risk_trend.trend_label}
                      </span>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl">
                      <span className="text-[11px] font-bold text-gray-500 uppercase block mb-1">Assessment Depth</span>
                      <div className="text-2xl font-black text-gray-900">
                        {monitoringSummary.risk_trend.assessment_count}
                      </div>
                      <span className="text-[10px] text-gray-400 block mt-1">Total recorded evaluations</span>
                    </div>
                  </div>

                  {/* Non-causal Trend Description Narrative */}
                  <div className="bg-white border-l-4 border-blue-600 p-4 rounded-r-xl shadow-xs space-y-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-blue-900">Observation-Driven Narrative</span>
                    <p className="text-xs text-gray-800 font-medium leading-relaxed">
                      {monitoringSummary.risk_trend.trend_description}
                    </p>
                  </div>

                  {/* Consecutive Telemetry Deltas Section */}
                  <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-xs space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                        📡 Telemetry Shift Analysis (Consecutive Assessments)
                      </h4>
                      <span className="text-[11px] text-gray-500">
                        Live Weather, Satellite & Soil Trajectory
                      </span>
                    </div>

                    {monitoringSummary.telemetry_changes.length === 0 ? (
                      <p className="text-xs text-gray-400 py-3">No telemetry changes recorded between assessments.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-left text-xs">
                          <thead className="bg-slate-50 font-bold text-gray-600">
                            <tr>
                              <th className="p-2.5">Telemetry Parameter</th>
                              <th className="p-2.5">Previous Value</th>
                              <th className="p-2.5">Current Value</th>
                              <th className="p-2.5">Delta</th>
                              <th className="p-2.5">Classification</th>
                              <th className="p-2.5">Non-Causal Observation Statement</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {monitoringSummary.telemetry_changes.map((item, idx) => (
                              <tr key={idx} className="hover:bg-slate-50">
                                <td className="p-2.5 font-bold text-gray-900">
                                  {item.display_name} <span className="text-gray-400 font-normal">({item.feature_name})</span>
                                </td>
                                <td className="p-2.5 text-gray-600 font-mono">
                                  {item.formatted_previous || String(item.previous_value ?? "—")}
                                </td>
                                <td className="p-2.5 font-bold text-gray-900 font-mono">
                                  {item.formatted_current || String(item.current_value ?? "—")}
                                </td>
                                <td className="p-2.5 font-mono font-bold">
                                  {item.delta !== null && item.delta !== undefined ? (
                                    <span className={item.delta > 0 ? "text-amber-700" : item.delta < 0 ? "text-blue-700" : "text-gray-500"}>
                                      {item.delta > 0 ? `+${item.delta.toFixed(2)}` : item.delta.toFixed(2)} {item.unit || ""}
                                    </span>
                                  ) : (
                                    <span className="text-gray-400">—</span>
                                  )}
                                </td>
                                <td className="p-2.5">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    item.change_type === "DIRECT_LIVE_CHANGE"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : item.change_type === "DERIVED_CHANGE"
                                      ? "bg-blue-100 text-blue-800"
                                      : "bg-slate-100 text-slate-700"
                                  }`}>
                                    {item.change_type}
                                  </span>
                                </td>
                                <td className="p-2.5 text-gray-700 text-[11px] leading-tight max-w-sm">
                                  {item.statement || item.description}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* SHAP Attribution Shifts Section */}
                  {monitoringSummary.shap_comparison && (
                    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-xs space-y-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                        <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                          🧠 Consecutive SHAP Attribution Shifts (Δφ = φ_current − φ_prev)
                        </h4>
                        <span className="text-[11px] text-gray-500">
                          Identifies emerging agronomic stress drivers
                        </span>
                      </div>

                      {monitoringSummary.shap_comparison.summary && (
                        <p className="text-xs text-gray-700 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                          {monitoringSummary.shap_comparison.summary}
                        </p>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Newly Increasing */}
                        <div className="bg-rose-50/70 border border-rose-200 rounded-xl p-3 space-y-2">
                          <span className="text-[11px] font-bold text-rose-900 uppercase block">
                            ⚠️ Newly Escalating Risk Contributors (Δφ &gt; 0)
                          </span>
                          {monitoringSummary.shap_comparison.newly_increasing.length === 0 ? (
                            <p className="text-xs text-gray-500 italic py-2">No newly escalating features detected.</p>
                          ) : (
                            monitoringSummary.shap_comparison.newly_increasing.map((s, idx) => (
                              <div key={idx} className="bg-white p-2.5 rounded-lg border border-rose-100 text-xs flex justify-between items-center">
                                <div>
                                  <span className="font-bold text-gray-900">{s.display_name}</span>
                                  <p className="text-[11px] text-gray-500 mt-0.5">{s.farmer_text}</p>
                                </div>
                                <span className="font-bold text-rose-700 font-mono text-xs">
                                  +{s.delta_attribution.toFixed(4)}
                                </span>
                              </div>
                            ))
                          )}
                        </div>

                        {/* Newly Reducing */}
                        <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-3 space-y-2">
                          <span className="text-[11px] font-bold text-emerald-900 uppercase block">
                            🛡️ Newly Mitigating Risk Contributors (Δφ &lt; 0)
                          </span>
                          {monitoringSummary.shap_comparison.newly_reducing.length === 0 ? (
                            <p className="text-xs text-gray-500 italic py-2">No newly mitigating features detected.</p>
                          ) : (
                            monitoringSummary.shap_comparison.newly_reducing.map((s, idx) => (
                              <div key={idx} className="bg-white p-2.5 rounded-lg border border-emerald-100 text-xs flex justify-between items-center">
                                <div>
                                  <span className="font-bold text-gray-900">{s.display_name}</span>
                                  <p className="text-[11px] text-gray-500 mt-0.5">{s.farmer_text}</p>
                                </div>
                                <span className="font-bold text-emerald-700 font-mono text-xs">
                                  {s.delta_attribution.toFixed(4)}
                                </span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>

                      {/* Complete SHAP Shifts Table */}
                      <details className="text-xs">
                        <summary className="font-bold text-blue-900 cursor-pointer hover:underline py-1">
                          📊 View All SHAP Attribution Shifts ({monitoringSummary.shap_comparison.all_shifts.length} features)
                        </summary>
                        <div className="mt-2 overflow-x-auto border border-gray-200 rounded-lg">
                          <table className="min-w-full divide-y divide-gray-200 text-left text-[11px]">
                            <thead className="bg-slate-100 font-bold text-gray-700">
                              <tr>
                                <th className="p-2">Feature</th>
                                <th className="p-2">Previous φ</th>
                                <th className="p-2">Current φ</th>
                                <th className="p-2">Δ Attribution (Δφ)</th>
                                <th className="p-2">Shift Direction</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {monitoringSummary.shap_comparison.all_shifts.map((s, idx) => (
                                <tr key={idx} className="hover:bg-slate-50">
                                  <td className="p-2 font-medium text-gray-900">{s.display_name}</td>
                                  <td className="p-2 font-mono text-gray-600">{s.previous_attribution.toFixed(4)}</td>
                                  <td className="p-2 font-mono text-gray-900 font-bold">{s.current_attribution.toFixed(4)}</td>
                                  <td className="p-2 font-mono font-bold">
                                    <span className={s.delta_attribution > 0 ? "text-rose-700" : s.delta_attribution < 0 ? "text-emerald-700" : "text-gray-500"}>
                                      {s.delta_attribution > 0 ? `+${s.delta_attribution.toFixed(4)}` : s.delta_attribution.toFixed(4)}
                                    </span>
                                  </td>
                                  <td className="p-2">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                      s.shift_direction === "increased_risk_impact"
                                        ? "bg-rose-100 text-rose-800"
                                        : s.shift_direction === "reduced_risk_impact"
                                        ? "bg-emerald-100 text-emerald-800"
                                        : "bg-gray-100 text-gray-700"
                                    }`}>
                                      {s.shift_direction.replace(/_/g, " ")}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    </div>
                  )}

                  {/* Actions & Outcomes Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Farmer Feedback & Actions Trail */}
                    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-xs space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                          📝 Farmer Interventions & Actions Trail
                        </h4>
                        <span className="text-[10px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-bold">
                          {monitoringSummary.recent_actions.length} Logged
                        </span>
                      </div>

                      {monitoringSummary.recent_actions.length === 0 ? (
                        <p className="text-xs text-gray-400 py-4 text-center italic">
                          No farmer field interventions logged yet for this farm.
                        </p>
                      ) : (
                        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                          {monitoringSummary.recent_actions.map((act) => (
                            <div key={act.id} className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-gray-800">{act.action_label}</span>
                                <span className="text-[10px] text-gray-500">
                                  {new Date(act.action_date || act.created_at).toLocaleDateString()}
                                </span>
                              </div>
                              {act.notes && (
                                <p className="text-gray-600 text-[11px] italic bg-white p-1.5 rounded border border-slate-100">
                                  "{act.notes}"
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Ground-Truth Harvest Outcome Verification */}
                    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-xs space-y-3">
                      <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                        🌾 Ground-Truth Harvest Outcome Verification
                      </h4>

                      {monitoringSummary.crop_outcome ? (
                        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 space-y-2 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-emerald-900">
                              {monitoringSummary.crop_outcome.crop} ({monitoringSummary.crop_outcome.season})
                            </span>
                            <span className="px-2 py-0.5 rounded text-[10px] font-black uppercase bg-emerald-200 text-emerald-800">
                              {monitoringSummary.crop_outcome.status}
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-[11px] pt-1 border-t border-emerald-200">
                            <div>
                              <span className="text-gray-500 block">Harvest Date:</span>
                              <span className="font-bold text-gray-800">
                                {monitoringSummary.crop_outcome.actual_harvest_date || "Not specified"}
                              </span>
                            </div>
                            <div>
                              <span className="text-gray-500 block">Reported Yield:</span>
                              <span className="font-bold text-gray-800">
                                {monitoringSummary.crop_outcome.reported_yield_kg_per_ha != null
                                  ? `${monitoringSummary.crop_outcome.reported_yield_kg_per_ha} kg/ha`
                                  : "Not specified"}
                              </span>
                            </div>
                          </div>
                          {monitoringSummary.crop_outcome.outcome_notes && (
                            <p className="text-[11px] text-gray-700 bg-white p-2 rounded border border-emerald-100">
                              "{monitoringSummary.crop_outcome.outcome_notes}"
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="p-4 bg-slate-50 border border-dashed border-gray-300 rounded-lg text-center">
                          <p className="text-xs text-gray-600 font-medium">No harvest outcome reported yet.</p>
                          <p className="text-[11px] text-gray-400 mt-1">
                            Harvest outcomes can be recorded by the farmer upon completion of the crop cycle.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Operational Model Monitoring Diagnostics */}
                  {diagnostics && (
                    <div className="bg-slate-900 text-slate-100 p-5 rounded-2xl shadow-sm space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="text-xs font-bold uppercase tracking-wider text-blue-400">
                            ⚙️ Operational Model Monitoring Diagnostics
                          </h4>
                          <p className="text-[11px] text-slate-400">Continuous telemetry pipeline integrity and inference drift tracking</p>
                        </div>
                        <span className="text-[10px] bg-slate-800 text-slate-300 px-2.5 py-1 rounded-full font-bold">
                          {diagnostics.farm_count} Farms Active
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="bg-slate-800 p-3 rounded-xl border border-slate-700">
                          <span className="text-[10px] text-slate-400 uppercase font-bold block">Total Inferences</span>
                          <span className="text-xl font-bold text-white">{diagnostics.total_predictions}</span>
                        </div>
                        <div className="bg-slate-800 p-3 rounded-xl border border-slate-700">
                          <span className="text-[10px] text-slate-400 uppercase font-bold block">Avg Live Coverage</span>
                          <span className="text-xl font-bold text-emerald-400">{diagnostics.average_live_feature_coverage}%</span>
                        </div>
                        <div className="bg-slate-800 p-3 rounded-xl border border-slate-700">
                          <span className="text-[10px] text-slate-400 uppercase font-bold block">SHAP Availability</span>
                          <span className="text-xl font-bold text-blue-400">{diagnostics.shap_availability_rate}%</span>
                        </div>
                        <div className="bg-slate-800 p-3 rounded-xl border border-slate-700">
                          <span className="text-[10px] text-slate-400 uppercase font-bold block">Stale Telemetry Rate</span>
                          <span className="text-xl font-bold text-amber-400">{diagnostics.stale_telemetry_rate}%</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-2 border-t border-slate-800">
                        <div className="bg-slate-800/60 p-2.5 rounded-lg">
                          <span className="text-[10px] font-bold uppercase text-slate-400 block mb-1">Risk Level Distribution</span>
                          <div className="flex gap-4">
                            {Object.entries(diagnostics.risk_distribution || {}).map(([lvl, count]) => (
                              <div key={lvl}>
                                <span className="font-bold text-white capitalize">{lvl}: </span>
                                <span className="text-blue-300 font-mono font-bold">{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="bg-slate-800/60 p-2.5 rounded-lg">
                          <span className="text-[10px] font-bold uppercase text-slate-400 block mb-1">Feedback & Outcomes Closed</span>
                          <div className="flex gap-4">
                            <div>
                              <span className="text-slate-400">Actions: </span>
                              <span className="text-emerald-300 font-mono font-bold">{diagnostics.feedback_count}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Harvests Recorded: </span>
                              <span className="text-emerald-300 font-mono font-bold">{diagnostics.outcomes_recorded_count}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <p className="text-[10px] text-slate-500 italic">
                        {diagnostics.disclaimer}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: DIGITAL TWIN SIMULATOR */}
          {activeTab === "twin" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Digital Twin Scenario Simulation</h2>
                <p className="text-xs text-gray-500">
                  Parametric what-if stress testing using the existing ML engine (`src/digital_twin.py`).
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                  <label className="block text-[11px] font-bold text-gray-700 uppercase mb-1">State & District</label>
                  <input
                    type="text"
                    value={twinDistrict}
                    onChange={(e) => setTwinDistrict(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded-lg p-2 text-xs font-bold"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-gray-700 uppercase mb-1">Crop</label>
                  <select
                    value={twinCrop}
                    onChange={(e) => setTwinCrop(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded-lg p-2 text-xs font-bold"
                  >
                    <option value="Soybean">Soybean</option>
                    <option value="Rice">Rice</option>
                    <option value="Wheat">Wheat</option>
                    <option value="Cotton">Cotton</option>
                    <option value="Maize">Maize</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-gray-700 uppercase mb-1">Season</label>
                  <select
                    value={twinSeason}
                    onChange={(e) => setTwinSeason(e.target.value)}
                    className="w-full bg-white border border-gray-300 rounded-lg p-2 text-xs font-bold"
                  >
                    <option value="Kharif">Kharif</option>
                    <option value="Rabi">Rabi</option>
                    <option value="Zaid">Zaid</option>
                  </select>
                </div>
              </div>

              {/* Parametric Sliders */}
              <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                  <div className="flex justify-between text-xs font-bold text-gray-800 mb-1">
                    <span>Temperature Shift: {tempDelta > 0 ? `+${tempDelta}` : tempDelta} °C</span>
                  </div>
                  <input
                    type="range"
                    min="-5.0"
                    max="5.0"
                    step="0.5"
                    value={tempDelta}
                    onChange={(e) => setTempDelta(parseFloat(e.target.value))}
                    className="w-full accent-blue-700"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs font-bold text-gray-800 mb-1">
                    <span>Rainfall Shift: {rainDeltaPct > 0 ? `+${rainDeltaPct}` : rainDeltaPct} %</span>
                  </div>
                  <input
                    type="range"
                    min="-50"
                    max="50"
                    step="5"
                    value={rainDeltaPct}
                    onChange={(e) => setRainDeltaPct(parseFloat(e.target.value))}
                    className="w-full accent-blue-700"
                  />
                </div>

                <button
                  onClick={handleRunTwin}
                  disabled={twinLoading}
                  className="w-full py-2.5 bg-blue-900 hover:bg-blue-950 text-white font-bold rounded-xl text-xs shadow transition"
                >
                  {twinLoading ? "Simulating Scenario..." : "⚡ Run Digital Twin Simulation"}
                </button>
              </div>

              {/* Simulation Result */}
              {twinResult && (
                <div className="bg-blue-50/70 border border-blue-200 rounded-xl p-5 space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-blue-950 uppercase">{twinResult.scenario}</span>
                    <span className="text-lg font-black text-blue-900">{twinResult.risk_percentage} Failure Risk</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs bg-white p-3 rounded-lg border border-blue-100">
                    <div>
                      <span className="text-gray-500 block">Rainfall</span>
                      <span className="font-bold text-gray-900">{twinResult.adjusted_features.Rainfall.toFixed(1)} mm</span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Temperature</span>
                      <span className="font-bold text-gray-900">{twinResult.adjusted_features.Temperature.toFixed(1)} °C</span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Water Stress</span>
                      <span className="font-bold text-gray-900">{twinResult.adjusted_features.WaterStress.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: SHAP EXPLAINABILITY */}
          {activeTab === "shap" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Explainable AI (SHAP Feature Attribution)</h2>
                <p className="text-xs text-gray-500">
                  Calculates TreeExplainer feature importance using `src/shap_analysis.py`.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleRunShap}
                  disabled={shapLoading}
                  className="px-5 py-2.5 bg-blue-900 hover:bg-blue-950 text-white font-bold rounded-xl text-xs shadow transition"
                >
                  {shapLoading ? "Calculating SHAP attribution..." : "🧠 Generate SHAP Attribution for Pune (Soybean)"}
                </button>
              </div>

              {shapResult && (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-gray-700">
                    <strong>Summary:</strong> {shapResult.summary}
                  </div>

                  <div className="space-y-2">
                    {shapResult.top_features.map((feat) => (
                      <div
                        key={feat.feature}
                        className="flex items-center justify-between p-3 bg-white border border-gray-200 rounded-xl text-xs"
                      >
                        <div>
                          <span className="font-bold text-gray-900">{feat.display_name}</span>
                          <span className="text-gray-400 ml-2">({feat.feature})</span>
                        </div>
                        <span
                          className={`font-bold px-2 py-0.5 rounded ${
                            feat.direction === "increases_risk"
                              ? "bg-red-100 text-red-800"
                              : "bg-emerald-100 text-emerald-800"
                          }`}
                        >
                          {feat.impact > 0 ? `+${feat.impact.toFixed(3)}` : feat.impact.toFixed(3)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB: EARLY WARNINGS & ALERTS */}
          {activeTab === "alerts" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Cross-Farm Early Warning & Alert Engine</h2>
                  <p className="text-xs text-gray-500">
                    Observation-driven risk transitions, risk trend escalation, and telemetry quality degradation across all monitored farms.
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (token) {
                      setAlertsLoading(true);
                      listExpertAlerts(token)
                        .then((data) => setExpertAlerts(data))
                        .catch((err) => setAlertsError(err.message || "Failed to refresh alerts."))
                        .finally(() => setAlertsLoading(false));
                    }
                  }}
                  disabled={alertsLoading}
                  className="px-3 py-1.5 bg-blue-900 hover:bg-blue-800 disabled:bg-gray-400 text-white font-bold text-xs rounded-xl shadow-sm transition flex items-center gap-1.5"
                >
                  <span>🔄</span> Refresh Alerts
                </button>
              </div>

              {/* Status Overview Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <span className="text-[11px] font-semibold text-gray-500">Total Alerts</span>
                  <p className="text-xl font-black text-gray-900 mt-0.5">{expertAlerts.length}</p>
                </div>
                <div className="bg-rose-50/50 p-3.5 rounded-xl border border-rose-200">
                  <span className="text-[11px] font-semibold text-rose-700">Active Critical / High</span>
                  <p className="text-xl font-black text-rose-900 mt-0.5">
                    {expertAlerts.filter((a) => a.status === "active" && a.severity === "critical").length}
                  </p>
                </div>
                <div className="bg-amber-50/50 p-3.5 rounded-xl border border-amber-200">
                  <span className="text-[11px] font-semibold text-amber-700">Active Warnings</span>
                  <p className="text-xl font-black text-amber-900 mt-0.5">
                    {expertAlerts.filter((a) => a.status === "active" && a.severity === "warning").length}
                  </p>
                </div>
                <div className="bg-emerald-50/50 p-3.5 rounded-xl border border-emerald-200">
                  <span className="text-[11px] font-semibold text-emerald-700">Resolved Alerts</span>
                  <p className="text-xl font-black text-emerald-900 mt-0.5">
                    {expertAlerts.filter((a) => a.status === "resolved").length}
                  </p>
                </div>
              </div>

              {/* Filter Tabs */}
              <div className="flex flex-wrap gap-2 border-b border-gray-200 pb-2">
                {[
                  { id: "all", label: "All Alerts", count: expertAlerts.length },
                  { id: "active", label: "Active", count: expertAlerts.filter((a) => a.status === "active").length },
                  { id: "acknowledged", label: "Acknowledged", count: expertAlerts.filter((a) => a.status === "acknowledged").length },
                  { id: "resolved", label: "Resolved", count: expertAlerts.filter((a) => a.status === "resolved").length },
                  { id: "critical", label: "Critical / High", count: expertAlerts.filter((a) => a.severity === "critical").length },
                  { id: "warning", label: "Warning / Medium", count: expertAlerts.filter((a) => a.severity === "warning").length },
                  {
                    id: "data_quality",
                    label: "Data Quality / Stale",
                    count: expertAlerts.filter((a) => ["SATELLITE_STALE", "WEATHER_STALE", "TELEMETRY_DEGRADATION", "DATA_QUALITY_DEGRADED"].includes(a.alert_type)).length,
                  },
                ].map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setAlertFilter(f.id)}
                    className={`px-3 py-1.5 text-xs font-bold rounded-lg transition flex items-center gap-1.5 ${
                      alertFilter === f.id
                        ? "bg-blue-900 text-white shadow-sm"
                        : "bg-slate-100 hover:bg-slate-200 text-gray-700"
                    }`}
                  >
                    <span>{f.label}</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                        alertFilter === f.id ? "bg-blue-800 text-white" : "bg-white text-gray-600 border border-gray-200"
                      }`}
                    >
                      {f.count}
                    </span>
                  </button>
                ))}
              </div>

              {alertsError && (
                <div className="p-3 bg-rose-50 border border-rose-300 rounded-xl text-rose-800 text-xs">
                  ⚠️ {alertsError}
                </div>
              )}

              {alertsLoading ? (
                <div className="py-12 text-center text-xs text-gray-500">
                  <span className="animate-spin inline-block mr-2">⏳</span> Loading early warning alerts...
                </div>
              ) : expertAlerts.length === 0 ? (
                <div className="py-12 text-center bg-slate-50 border border-dashed border-gray-300 rounded-2xl">
                  <span className="text-3xl block mb-2">🛡️</span>
                  <p className="font-bold text-gray-700 text-sm">No Early Warning Alerts Recorded</p>
                  <p className="text-xs text-gray-500 max-w-md mx-auto mt-1">
                    No risk thresholds or telemetry degradation triggers have fired across monitored farms.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {expertAlerts
                    .filter((a) => {
                      if (alertFilter === "active") return a.status === "active";
                      if (alertFilter === "acknowledged") return a.status === "acknowledged";
                      if (alertFilter === "resolved") return a.status === "resolved";
                      if (alertFilter === "critical") return a.severity === "critical";
                      if (alertFilter === "warning") return a.severity === "warning";
                      if (alertFilter === "data_quality")
                        return ["SATELLITE_STALE", "WEATHER_STALE", "TELEMETRY_DEGRADATION", "DATA_QUALITY_DEGRADED"].includes(a.alert_type);
                      return true;
                    })
                    .map((alert) => {
                      const matchedFarm = farms.find((f) => f.id === alert.farm_id);
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
                          className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-3 hover:border-slate-300 transition"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-100 pb-2">
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] font-black px-2 py-0.5 rounded border uppercase tracking-wider ${badgeBg}`}>
                                {alert.severity}
                              </span>
                              <span className="text-xs font-bold text-gray-900">
                                {matchedFarm ? `${matchedFarm.name} (${matchedFarm.district}, ${matchedFarm.state})` : `Farm: ${alert.farm_id.slice(0, 8)}...`}
                              </span>
                              <span className="text-[10px] font-mono text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded border">
                                {alert.alert_type}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                                  alert.status === "resolved"
                                    ? "bg-slate-100 text-slate-800 border-slate-300"
                                    : alert.status === "acknowledged"
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                                    : "bg-rose-50 text-rose-800 border-rose-300"
                                }`}
                              >
                                {alert.status.toUpperCase()}
                              </span>
                              <span className="text-[11px] text-gray-500">
                                {new Date(alert.created_at).toLocaleString()}
                              </span>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                            <div className="space-y-1">
                              <span className="text-gray-500 font-semibold block">Risk & Trigger:</span>
                              <p className="text-gray-800 font-medium">{alert.trigger_reason}</p>
                              <div className="flex items-center gap-3 pt-1">
                                <span className="font-bold text-gray-900">
                                  Risk: {alert.risk_percentage || `${(alert.risk_probability * 100).toFixed(1)}%`}
                                </span>
                                {alert.risk_delta_pp !== null && alert.risk_delta_pp !== undefined && (
                                  <span
                                    className={`font-semibold ${
                                      alert.risk_delta_pp > 0 ? "text-rose-700" : "text-emerald-700"
                                    }`}
                                  >
                                    Delta: {alert.risk_delta_pp > 0 ? `+${alert.risk_delta_pp}` : alert.risk_delta_pp} pp
                                  </span>
                                )}
                              </div>
                            </div>

                            <div className="space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                              <span className="text-gray-600 font-semibold block">SHAP Factor Attribution:</span>
                              {alert.shap_context?.summary ? (
                                <>
                                  <p className="text-gray-700 text-[11px] line-clamp-2" title={alert.shap_context.summary}>
                                    {alert.shap_context.summary}
                                  </p>
                                  {alert.shap_context.top_contributors && (
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {alert.shap_context.top_contributors.map((c, idx) => (
                                        <span
                                          key={idx}
                                          className="text-[9px] px-1.5 py-0.2 rounded bg-white text-gray-700 border font-mono"
                                        >
                                          {c.display_name || c.feature_name}: {c.shap_value > 0 ? `+${c.shap_value.toFixed(2)}` : c.shap_value.toFixed(2)}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <p className="text-gray-400 text-[11px]">No SHAP attribution context captured.</p>
                              )}
                            </div>

                            <div className="space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                              <span className="text-gray-600 font-semibold block">Recommended Action:</span>
                              {alert.recommended_action ? (
                                <>
                                  <p className="font-bold text-gray-800 text-[11px]">
                                    {alert.recommended_action.title}
                                  </p>
                                  {alert.recommended_action.action_items && alert.recommended_action.action_items.length > 0 && (
                                    <p className="text-gray-600 text-[11px] line-clamp-2">
                                      {alert.recommended_action.action_items.join("; ")}
                                    </p>
                                  )}
                                </>
                              ) : (
                                <p className="text-gray-400 text-[11px]">Standard agronomic advisory applies.</p>
                              )}
                            </div>
                          </div>

                          {/* Action Controls for Expert */}
                          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 pt-2 border-t border-gray-100">
                            <div className="flex-1">
                              {alert.status !== "resolved" && (
                                <input
                                  type="text"
                                  placeholder="Expert resolution notes or field verification comments..."
                                  value={resolutionNotes[alert.id] || ""}
                                  onChange={(e) =>
                                    setResolutionNotes((prev) => ({ ...prev, [alert.id]: e.target.value }))
                                  }
                                  className="w-full text-xs px-2.5 py-1.5 border border-gray-300 rounded-lg bg-slate-50"
                                />
                              )}
                            </div>
                            <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                              {alert.status === "active" && (
                                <button
                                  onClick={() => handleExpertAcknowledge(alert.id, alert.farm_id)}
                                  disabled={actionAlertId === alert.id}
                                  className="px-3 py-1 bg-emerald-700 hover:bg-emerald-800 disabled:bg-gray-400 text-white font-bold text-xs rounded-lg transition"
                                >
                                  {actionAlertId === alert.id ? "Saving..." : "Acknowledge"}
                                </button>
                              )}
                              {alert.status !== "resolved" && (
                                <button
                                  onClick={() => handleExpertResolve(alert.id, alert.farm_id)}
                                  disabled={actionAlertId === alert.id}
                                  className="px-3 py-1 bg-blue-900 hover:bg-blue-800 disabled:bg-gray-400 text-white font-bold text-xs rounded-lg transition"
                                >
                                  {actionAlertId === alert.id ? "Saving..." : "Resolve Alert"}
                                </button>
                              )}
                              {alert.status === "resolved" && (
                                <span className="text-[11px] font-semibold text-gray-500">
                                  Resolved by Expert {alert.resolved_at ? `(${new Date(alert.resolved_at).toLocaleDateString()})` : ""}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          )}

          {/* TAB: WEATHER & TELEMETRY */}
          {activeTab === "weather" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Weather Gateway & Agrometeorology Telemetry</h2>
                  <p className="text-xs text-gray-500">
                    Live meteorological observations and multi-day projections queried via Open-Meteo REST provider.
                  </p>
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <select
                    value={selectedFarmId}
                    onChange={(e) => setSelectedFarmId(e.target.value)}
                    className="bg-slate-50 border border-gray-300 rounded-lg px-3 py-1.5 text-xs font-bold text-gray-800"
                  >
                    {farms.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name} ({f.district}, {f.state})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {isLoadingWeather ? (
                <div className="text-center py-12 text-gray-500 text-xs">
                  <span className="text-xl animate-spin inline-block mb-2">⏳</span>
                  <p>Fetching real-time meteorological observations...</p>
                </div>
              ) : !currentWeather ? (
                <div className="p-6 bg-slate-50 rounded-xl text-center text-xs text-gray-500 border border-slate-200">
                  No weather observation currently available for this location. Select a farm above to fetch data.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Current Observation Cards */}
                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-3">
                    <div className="flex flex-wrap justify-between items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-blue-900">
                        Current Farm Meteorological State
                      </span>
                      <div className="flex items-center gap-2 text-[11px]">
                        <span className="bg-blue-100 text-blue-800 font-semibold px-2 py-0.5 rounded">
                          Provider: {currentWeather.source}
                        </span>
                        <span className="bg-gray-200 text-gray-700 px-2 py-0.5 rounded font-mono">
                          {currentWeather.latitude.toFixed(3)}°N, {currentWeather.longitude.toFixed(3)}°E
                        </span>
                        {currentWeather.is_cached && (
                          <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-semibold">
                            Cached (TTL 15m)
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Temperature</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.temperature !== undefined ? `${Number(currentWeather.temperature).toFixed(1)} °C` : "N/A"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Relative Humidity</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.relative_humidity !== undefined ? `${Number(currentWeather.relative_humidity).toFixed(1)} %` : "N/A"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Precipitation</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.precipitation !== undefined ? `${Number(currentWeather.precipitation).toFixed(1)} mm` : "0.0 mm"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Soil Moisture (Root Zone)</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.soil_moisture_percentage !== undefined
                            ? `${Number(currentWeather.soil_moisture_percentage).toFixed(1)} % (${Number(currentWeather.soil_moisture_m3m3 || 0).toFixed(3)} m³/m³)`
                            : "N/A"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">7-Day Total Precip</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.precipitation_sum_7d !== undefined && currentWeather.precipitation_sum_7d !== null
                            ? `${Number(currentWeather.precipitation_sum_7d).toFixed(1)} mm`
                            : "N/A"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Weather Code (WMO)</span>
                        <span className="text-base font-bold text-gray-900">
                          {currentWeather.weather_code !== undefined && currentWeather.weather_code !== null
                            ? `${currentWeather.weather_code}`
                            : "N/A"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Status / Mode</span>
                        <span className="text-base font-bold text-emerald-800">
                          {currentWeather.is_estimate ? "District Baseline" : "Live Sensor"}
                        </span>
                      </div>
                      <div className="bg-white p-3 rounded-lg border border-slate-200">
                        <span className="text-[11px] text-gray-500 block">Observation Time</span>
                        <span className="text-xs font-semibold text-gray-700">
                          {new Date(currentWeather.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 7-Day Agronomic Forecast Table */}
                  {forecastWeather && (
                    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
                      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-1">
                        <h3 className="text-sm font-bold text-gray-900">
                          7-Day Agronomic Meteorological Forecast ({forecastWeather.forecast_days} Days)
                        </h3>
                        <span className="text-[10px] text-gray-400">
                          Timezone: {forecastWeather.timezone || "auto"}
                        </span>
                      </div>

                      {/* Disclaimer banner */}
                      <div className="p-2.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900">
                        <strong>Agronomic Planning Notice:</strong> {forecastWeather.disclaimer}
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full text-xs text-left">
                          <thead className="bg-slate-50 text-gray-700 uppercase font-bold text-[10px] border-b border-gray-200">
                            <tr>
                              <th className="py-2 px-3">Date</th>
                              <th className="py-2 px-3">Max Temp (°C)</th>
                              <th className="py-2 px-3">Min Temp (°C)</th>
                              <th className="py-2 px-3">Precipitation (mm)</th>
                              <th className="py-2 px-3">Rain Prob (%)</th>
                              <th className="py-2 px-3">Mean Soil Moisture</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {forecastWeather.daily.map((day) => (
                              <tr key={day.date} className="hover:bg-slate-50">
                                <td className="py-2 px-3 font-semibold text-gray-900">{day.date}</td>
                                <td className="py-2 px-3 text-red-700 font-bold">{day.temperature_max?.toFixed(1) ?? "-"}</td>
                                <td className="py-2 px-3 text-blue-700 font-bold">{day.temperature_min?.toFixed(1) ?? "-"}</td>
                                <td className="py-2 px-3">{day.precipitation_sum?.toFixed(1) ?? "0.0"}</td>
                                <td className="py-2 px-3">
                                  {day.precipitation_probability_max !== null && day.precipitation_probability_max !== undefined
                                    ? `${day.precipitation_probability_max}%`
                                    : "-"}
                                </td>
                                <td className="py-2 px-3 font-mono">
                                  {day.soil_moisture_mean !== undefined && day.soil_moisture_mean !== null
                                    ? `${(day.soil_moisture_mean * 100).toFixed(1)}%`
                                    : "-"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Telemetry Observation History */}
                  <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
                    <h3 className="text-sm font-bold text-gray-900">Persisted Farm Observations Log</h3>
                    {weatherHistory.length === 0 ? (
                      <p className="text-xs text-gray-400 py-3">No persisted history records found for this farm.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs text-left">
                          <thead className="bg-slate-50 text-gray-700 uppercase font-bold text-[10px] border-b border-gray-200">
                            <tr>
                              <th className="py-2 px-3">Timestamp</th>
                              <th className="py-2 px-3">Source</th>
                              <th className="py-2 px-3">Temp (°C)</th>
                              <th className="py-2 px-3">Humidity (%)</th>
                              <th className="py-2 px-3">Precipitation (mm)</th>
                              <th className="py-2 px-3">Soil Moisture (%)</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {weatherHistory.map((rec, idx) => (
                              <tr key={rec.id || idx} className="hover:bg-slate-50">
                                <td className="py-2 px-3 font-medium text-gray-800">
                                  {new Date(rec.observation_time).toLocaleString()}
                                </td>
                                <td className="py-2 px-3 text-gray-500">{rec.source}</td>
                                <td className="py-2 px-3 font-bold">{rec.temperature_c?.toFixed(1) ?? "-"}</td>
                                <td className="py-2 px-3">{rec.humidity_pct?.toFixed(1) ?? "-"}</td>
                                <td className="py-2 px-3">{rec.precipitation_mm?.toFixed(1) ?? "0.0"}</td>
                                <td className="py-2 px-3">
                                  {rec.soil_moisture_pct?.toFixed(1) ?? "-"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: MONITORED FARMS */}
          {activeTab === "farms" && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-gray-900">All Registered Farms (District Explorer)</h2>
                <p className="text-xs text-gray-500">Expert-level visibility into plots across states and districts.</p>
              </div>

              {isLoadingFarms ? (
                <p className="text-xs text-gray-500 py-6 text-center">Loading farms...</p>
              ) : farms.length === 0 ? (
                <p className="text-xs text-gray-500 py-6 text-center">No farms registered yet.</p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {farms.map((f) => (
                    <div key={f.id} className="py-3 flex justify-between items-center text-xs">
                      <div>
                        <span className="font-bold text-gray-900 text-sm block">{f.name}</span>
                        <span className="text-gray-500">
                          {f.district}, {f.state} · Coords: {f.latitude.toFixed(3)}, {f.longitude.toFixed(3)}
                        </span>
                      </div>
                      <span className="font-mono bg-slate-100 px-2 py-1 rounded text-gray-700">
                        {f.soil_type || "Black Soil"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: SATELLITE (SENTINEL-2 & GOOGLE EARTH ENGINE) */}
          {activeTab === "satellite" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    Satellite Vegetation Telemetry (Sentinel-2 L2A)
                  </h2>
                  <p className="text-xs text-gray-500">
                    Google Earth Engine spatial reducer · Cloud-masked NDVI calculations
                  </p>
                </div>

                {/* Farm Selector */}
                {farms.length > 0 && (
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-bold text-gray-700">Farm:</label>
                    <select
                      value={selectedFarmId}
                      onChange={(e) => setSelectedFarmId(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-gray-800"
                    >
                      {farms.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name} ({f.district})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {isLoadingSatellite ? (
                <div className="text-center py-12">
                  <span className="animate-spin text-2xl">⏳</span>
                  <p className="text-xs text-gray-500 mt-2">Computing Earth Engine spatial reduction statistics...</p>
                </div>
              ) : !selectedFarmId ? (
                <p className="text-xs text-gray-400 py-6 text-center">Please select a farm to inspect satellite data.</p>
              ) : (
                <div className="space-y-5">
                  {/* Status Banner */}
                  <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl p-3.5">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">🛰️</span>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-gray-900">
                            {latestSatellite?.product || "COPERNICUS/S2_SR_HARMONIZED"}
                          </span>
                          <span
                            className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                              latestSatellite?.status === "REAL_SATELLITE_DATA"
                                ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                                : latestSatellite?.status === "MOCK_DEVELOPMENT"
                                ? "bg-purple-100 text-purple-800 border border-purple-300"
                                : "bg-amber-100 text-amber-800 border border-amber-300"
                            }`}
                          >
                            {latestSatellite?.status || "Awaiting Telemetry"}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-500 mt-0.5">
                          Provider: {latestSatellite?.provider || "GoogleEarthEngine"} · Geometry: {latestSatellite?.geometry_type || "buffered_point"} · Quality: {latestSatellite?.quality_status || "UNCONFIGURED"}
                        </p>
                      </div>
                    </div>

                    <div className="text-right text-[11px] text-gray-400">
                      <span>Obs Date: <strong>{latestSatellite?.observation_date || "N/A"}</strong></span>
                      {latestSatellite?.is_cached && <span className="block text-emerald-600 font-medium">Cached (24h TTL)</span>}
                    </div>
                  </div>

                  {/* NDVI Statistics Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-emerald-50/60 p-3.5 rounded-xl border border-emerald-200">
                      <span className="text-[11px] font-semibold text-emerald-900 uppercase">Mean NDVI</span>
                      <p className="text-2xl font-black text-emerald-800 mt-1">
                        {latestSatellite?.ndvi?.mean !== undefined && latestSatellite?.ndvi?.mean !== null
                          ? latestSatellite.ndvi.mean.toFixed(3)
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">Surface Greenness Index</span>
                    </div>

                    <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                      <span className="text-[11px] font-semibold text-gray-600 uppercase">Median NDVI</span>
                      <p className="text-2xl font-bold text-gray-800 mt-1">
                        {latestSatellite?.ndvi?.median !== undefined && latestSatellite?.ndvi?.median !== null
                          ? latestSatellite.ndvi.median.toFixed(3)
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">Robust Central Value</span>
                    </div>

                    <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                      <span className="text-[11px] font-semibold text-gray-600 uppercase">NDVI Range (Min / Max)</span>
                      <p className="text-base font-bold text-gray-800 mt-2">
                        {latestSatellite?.ndvi?.min !== undefined && latestSatellite?.ndvi?.min !== null
                          ? `${latestSatellite.ndvi.min.toFixed(2)} - ${latestSatellite?.ndvi?.max?.toFixed(2) ?? "-"}`
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">
                        Std: {latestSatellite?.ndvi?.std !== undefined && latestSatellite.ndvi.std !== null ? latestSatellite.ndvi.std.toFixed(3) : "—"}
                      </span>
                    </div>

                    <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                      <span className="text-[11px] font-semibold text-gray-600 uppercase">Farm Valid Pixels</span>
                      <p className="text-2xl font-bold text-blue-900 mt-1">
                        {latestSatellite?.ndvi?.valid_pixel_percent !== undefined && latestSatellite?.ndvi?.valid_pixel_percent !== null
                          ? `${latestSatellite.ndvi.valid_pixel_percent.toFixed(0)}%`
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">
                        Scene Cloud: {latestSatellite?.ndvi?.scene_cloud_percent !== undefined && latestSatellite?.ndvi?.scene_cloud_percent !== null
                          ? `${latestSatellite.ndvi.scene_cloud_percent.toFixed(1)}%`
                          : (latestSatellite?.ndvi?.cloud_percent !== undefined && latestSatellite?.ndvi?.cloud_percent !== null ? `${latestSatellite.ndvi.cloud_percent.toFixed(1)}%` : "0%")}
                      </span>
                    </div>
                  </div>

                  {/* Satellite Pipeline Metadata & Scientific Context */}
                  <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2 text-xs">
                    <h3 className="font-bold text-gray-900 text-sm">Spatial Reduction Architecture</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-gray-600">
                      <div>
                        <p><strong>Band Formula:</strong> NDVI = (B8 [NIR 842nm] - B4 [Red 665nm]) / (B8 + B4)</p>
                        <p><strong>Cloud Masking:</strong> SCL (Classes 3, 8, 9, 10, 11) + QA60 Opaque & Cirrus bands</p>
                        <p><strong>Spatial Resolution:</strong> 10-meter native optical resolution</p>
                      </div>
                      <div>
                        <p><strong>Server Processing:</strong> Zero raw raster download to API server; Earth Engine computes spatial reducer server-side.</p>
                        <p><strong>Quality Distinction:</strong> Farm Valid Pixels (cloud-free plot coverage) vs Scene Cloud % (full satellite tile metadata).</p>
                      </div>
                    </div>
                    <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                      {latestSatellite?.disclaimer || "Vegetation indices (NDVI) provide surface reflectance metrics for crop health monitoring and do not constitute direct crop failure probability."}
                    </p>
                  </div>

                  {/* Persisted Satellite History Table */}
                  <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
                    <h3 className="text-sm font-bold text-gray-900">Historical Satellite Observations</h3>
                    {satelliteHistory.length === 0 ? (
                      <p className="text-xs text-gray-400 py-3">No persisted satellite history records found for this farm.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs text-left">
                          <thead className="bg-slate-50 text-gray-700 uppercase font-bold text-[10px] border-b border-gray-200">
                            <tr>
                              <th className="py-2 px-3">Observation Date</th>
                              <th className="py-2 px-3">Satellite / Product</th>
                              <th className="py-2 px-3">Mean NDVI</th>
                              <th className="py-2 px-3">Median NDVI</th>
                              <th className="py-2 px-3">Farm Valid %</th>
                              <th className="py-2 px-3">Scene Cloud %</th>
                              <th className="py-2 px-3">Status</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {satelliteHistory.map((obs, idx) => (
                              <tr key={idx} className="hover:bg-slate-50">
                                <td className="py-2 px-3 font-medium text-gray-800">
                                  {obs.observation_date || "—"}
                                </td>
                                <td className="py-2 px-3 text-gray-500">{obs.product}</td>
                                <td className="py-2 px-3 font-bold text-emerald-800">
                                  {obs.ndvi?.mean !== undefined && obs.ndvi?.mean !== null ? obs.ndvi.mean.toFixed(3) : "—"}
                                </td>
                                <td className="py-2 px-3">
                                  {obs.ndvi?.median !== undefined && obs.ndvi?.median !== null ? obs.ndvi.median.toFixed(3) : "—"}
                                </td>
                                <td className="py-2 px-3">
                                  {obs.ndvi?.valid_pixel_percent !== undefined && obs.ndvi?.valid_pixel_percent !== null
                                    ? `${obs.ndvi.valid_pixel_percent.toFixed(0)}%`
                                    : "—"}
                                </td>
                                <td className="py-2 px-3">
                                  {obs.ndvi?.cloud_percent !== undefined && obs.ndvi?.cloud_percent !== null
                                    ? `${obs.ndvi.cloud_percent.toFixed(1)}%`
                                    : "—"}
                                </td>
                                <td className="py-2 px-3">
                                  <span className="bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded text-[10px] font-semibold">
                                    {obs.status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB: MODEL EVALUATION (Expert/Admin only — never for farmers) */}
          {activeTab === "evaluation" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Model Evaluation & Ground-Truth Validation</h2>
                <p className="text-xs text-gray-500">
                  Read-only report derived from real, non-synthetic, verified crop outcomes. Expert access only.
                  Do NOT retrain the model based on this report alone.
                </p>
              </div>

              {evalLoading && (
                <p className="text-xs text-gray-500 py-8 text-center">Loading model evaluation report...</p>
              )}
              {evalError && (
                <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800">
                  <strong>Error:</strong> {evalError}
                </div>
              )}

              {evalReport && (
                <div className="space-y-6">

                  {/* Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                      <span className="text-xs text-gray-500 font-semibold">Predictions in DB</span>
                      <p className="text-2xl font-black text-blue-900">{evalReport.total_predictions_in_db}</p>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                      <span className="text-xs text-gray-500 font-semibold">Crops with Outcome</span>
                      <p className="text-2xl font-black text-blue-900">{evalReport.total_crop_cycles_with_outcome}</p>
                    </div>
                    <div className="bg-emerald-50 p-4 rounded-xl border border-emerald-200">
                      <span className="text-xs text-emerald-700 font-semibold">Eligible Pairs</span>
                      <p className="text-2xl font-black text-emerald-900">{evalReport.eligible_pair_count}</p>
                    </div>
                    <div className="bg-amber-50 p-4 rounded-xl border border-amber-200">
                      <span className="text-xs text-amber-700 font-semibold">Ineligible</span>
                      <p className="text-2xl font-black text-amber-900">{evalReport.ineligible_pair_count}</p>
                    </div>
                  </div>

                  {/* Eligibility Rules */}
                  <details className="bg-white border border-slate-200 rounded-xl p-4">
                    <summary className="text-sm font-bold text-gray-800 cursor-pointer">Eligibility Filter Rules</summary>
                    <ul className="mt-3 space-y-1 list-disc list-inside text-xs text-gray-600">
                      {evalReport.eligibility_filter_rules.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </details>

                  {/* Classification Metrics */}
                  {evalReport.metrics ? (
                    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                      <h3 className="text-sm font-bold text-gray-900">
                        Classification Metrics
                        <span className="ml-2 text-[11px] font-normal text-gray-500">
                          threshold={evalReport.metrics.threshold_used} · n={evalReport.metrics.n_eligible_pairs} pairs
                        </span>
                      </h3>
                      {evalReport.metrics.notes && (
                        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 p-2 rounded">
                          ⚠️ {evalReport.metrics.notes}
                        </div>
                      )}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        {[
                          { label: "Accuracy", val: evalReport.metrics.accuracy },
                          { label: "Precision", val: evalReport.metrics.precision },
                          { label: "Recall", val: evalReport.metrics.recall },
                          { label: "F1 Score", val: evalReport.metrics.f1_score },
                          { label: "ROC-AUC", val: evalReport.metrics.roc_auc },
                          { label: "PR-AUC", val: evalReport.metrics.pr_auc },
                          { label: "Brier Score", val: evalReport.metrics.brier_score },
                          { label: "Specificity", val: evalReport.metrics.specificity },
                          { label: "FPR", val: evalReport.metrics.false_positive_rate },
                          { label: "FNR", val: evalReport.metrics.false_negative_rate },
                        ].map((m, i) => (
                          <div key={i} className="bg-slate-50 p-2 rounded border border-slate-200">
                            <span className="text-gray-500 block">{m.label}</span>
                            <span className="font-bold text-gray-900">
                              {m.val !== null && m.val !== undefined ? m.val.toFixed(4) : "—"}
                            </span>
                          </div>
                        ))}
                      </div>
                      {/* Confusion Matrix */}
                      {evalReport.metrics.confusion_matrix && (
                        <div className="mt-3">
                          <span className="text-xs font-semibold text-gray-700 block mb-2">Confusion Matrix (threshold=0.5)</span>
                          <div className="grid grid-cols-2 gap-2 max-w-xs text-xs font-mono">
                            <div className="bg-emerald-100 border border-emerald-200 p-2 rounded text-center">
                              <span className="block text-[10px] text-emerald-800 font-bold">TP</span>
                              <span className="text-lg font-black text-emerald-900">{evalReport.metrics.confusion_matrix.true_positive}</span>
                            </div>
                            <div className="bg-rose-100 border border-rose-200 p-2 rounded text-center">
                              <span className="block text-[10px] text-rose-800 font-bold">FP</span>
                              <span className="text-lg font-black text-rose-900">{evalReport.metrics.confusion_matrix.false_positive}</span>
                            </div>
                            <div className="bg-rose-100 border border-rose-200 p-2 rounded text-center">
                              <span className="block text-[10px] text-rose-800 font-bold">FN</span>
                              <span className="text-lg font-black text-rose-900">{evalReport.metrics.confusion_matrix.false_negative}</span>
                            </div>
                            <div className="bg-emerald-100 border border-emerald-200 p-2 rounded text-center">
                              <span className="block text-[10px] text-emerald-800 font-bold">TN</span>
                              <span className="text-lg font-black text-emerald-900">{evalReport.metrics.confusion_matrix.true_negative}</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-800">
                      <strong>No metrics available.</strong> Insufficient eligible prediction-outcome pairs.
                      Collect more verified ground-truth outcomes to enable classification metrics.
                    </div>
                  )}

                  {/* Calibration Table */}
                  {evalReport.calibration_bins.length > 0 && (
                    <details className="bg-white border border-slate-200 rounded-xl p-4">
                      <summary className="text-sm font-bold text-gray-800 cursor-pointer">
                        Calibration Table (Reliability Diagram)
                      </summary>
                      {evalReport.calibration_note && (
                        <p className="text-xs text-gray-500 mt-2">{evalReport.calibration_note}</p>
                      )}
                      <div className="mt-3 overflow-x-auto">
                        <table className="w-full text-xs text-left">
                          <thead className="bg-slate-50 font-bold text-gray-700 text-[10px] uppercase border-b">
                            <tr>
                              <th className="p-2">Bin</th>
                              <th className="p-2">Predicted Mean</th>
                              <th className="p-2">Actual Fraction</th>
                              <th className="p-2">N</th>
                              <th className="p-2">Gap</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {evalReport.calibration_bins.map((b, i) => (
                              <tr key={i} className="hover:bg-slate-50">
                                <td className="p-2 text-gray-600">{b.bin_lower.toFixed(1)}–{b.bin_upper.toFixed(1)}</td>
                                <td className="p-2 font-mono">{b.predicted_mean_probability.toFixed(3)}</td>
                                <td className="p-2 font-mono">{b.actual_fraction_positive.toFixed(3)}</td>
                                <td className="p-2">{b.n_samples}</td>
                                <td className={`p-2 font-bold font-mono ${b.calibration_gap > 0 ? "text-blue-700" : b.calibration_gap < 0 ? "text-rose-700" : "text-gray-500"}`}>
                                  {b.calibration_gap > 0 ? `+${b.calibration_gap.toFixed(3)}` : b.calibration_gap.toFixed(3)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}

                  {/* Subgroup Analysis */}
                  {evalReport.subgroup_analysis.length > 0 && (
                    <details className="bg-white border border-slate-200 rounded-xl p-4">
                      <summary className="text-sm font-bold text-gray-800 cursor-pointer">Subgroup Analysis</summary>
                      {evalReport.subgroup_analysis_note && (
                        <p className="text-xs text-amber-700 mt-2">{evalReport.subgroup_analysis_note}</p>
                      )}
                      <div className="mt-3 overflow-x-auto">
                        <table className="w-full text-xs text-left">
                          <thead className="bg-slate-50 font-bold text-gray-700 text-[10px] uppercase border-b">
                            <tr>
                              <th className="p-2">Group</th>
                              <th className="p-2">Value</th>
                              <th className="p-2">N</th>
                              <th className="p-2">Accuracy</th>
                              <th className="p-2">Precision</th>
                              <th className="p-2">Recall</th>
                              <th className="p-2">F1</th>
                              <th className="p-2">ROC-AUC</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {evalReport.subgroup_analysis.map((g, i) => (
                              <tr key={i} className="hover:bg-slate-50">
                                <td className="p-2 text-gray-500">{g.subgroup_key}</td>
                                <td className="p-2 font-semibold text-gray-900">{g.subgroup_value}</td>
                                <td className="p-2">{g.n_pairs}</td>
                                <td className="p-2 font-mono">{g.accuracy?.toFixed(3) ?? "—"}</td>
                                <td className="p-2 font-mono">{g.precision?.toFixed(3) ?? "—"}</td>
                                <td className="p-2 font-mono">{g.recall?.toFixed(3) ?? "—"}</td>
                                <td className="p-2 font-mono">{g.f1_score?.toFixed(3) ?? "—"}</td>
                                <td className="p-2 font-mono">{g.roc_auc?.toFixed(3) ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}

                  {/* Data Leakage Audit */}
                  <details className="bg-white border border-slate-200 rounded-xl p-4">
                    <summary className="text-sm font-bold text-gray-800 cursor-pointer">
                      Data Leakage Audit ({evalReport.leakage_audit.length} features)
                    </summary>
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-slate-50 font-bold text-gray-700 text-[10px] uppercase border-b">
                          <tr>
                            <th className="p-2">Feature</th>
                            <th className="p-2">Risk</th>
                            <th className="p-2">Reason</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {evalReport.leakage_audit.map((a, i) => (
                            <tr key={i} className="hover:bg-slate-50">
                              <td className="p-2 font-semibold text-gray-900">{a.feature_name}</td>
                              <td className="p-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  a.leakage_risk === "high" ? "bg-rose-100 text-rose-800" :
                                  a.leakage_risk === "medium" ? "bg-amber-100 text-amber-800" :
                                  a.leakage_risk === "low" ? "bg-yellow-100 text-yellow-800" :
                                  "bg-emerald-100 text-emerald-800"
                                }`}>{a.leakage_risk.toUpperCase()}</span>
                              </td>
                              <td className="p-2 text-gray-600 max-w-sm">{a.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>

                  {/* EVALUATION READINESS SECTION (Milestone 12) */}
                  <div className="bg-white border-2 border-emerald-200/80 rounded-2xl p-5 shadow-sm space-y-5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-100 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xl">📊</span>
                          <h3 className="text-base font-bold text-gray-900">Evaluation Readiness & Queues</h3>
                        </div>
                        <p className="text-xs text-gray-500">
                          Tracking predictions awaiting crop harvest, farmer-reported outcomes awaiting expert validation, and evaluation coverage.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={loadEvaluationData}
                          className="text-xs font-semibold px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg border border-slate-300 transition"
                        >
                          🔄 Refresh Queues
                        </button>
                      </div>
                    </div>

                    {verificationFeedback && (
                      <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-xl text-xs font-semibold">
                        {verificationFeedback}
                      </div>
                    )}

                    {readinessData ? (
                      <div className="space-y-5">
                        {/* Readiness Summary Metrics */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                          <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                            <span className="text-gray-500 font-medium block">Awaiting Harvest</span>
                            <span className="text-xl font-bold text-blue-900">
                              {readinessData.summary.predictions_awaiting_outcome}
                            </span>
                            <span className="text-[10px] text-gray-400 block mt-0.5">
                              Across {readinessData.summary.crop_cycles_awaiting_outcome} active cycles
                            </span>
                          </div>

                          <div className="bg-amber-50/70 p-3 rounded-xl border border-amber-200">
                            <span className="text-amber-800 font-medium block">Unverified Outcomes</span>
                            <span className="text-xl font-bold text-amber-900">
                              {readinessData.summary.unverified_outcomes}
                            </span>
                            <span className="text-[10px] text-amber-600 block mt-0.5">
                              Farmer-reported pending review
                            </span>
                          </div>

                          <div className="bg-emerald-50/70 p-3 rounded-xl border border-emerald-200">
                            <span className="text-emerald-800 font-medium block">Verified Outcomes</span>
                            <span className="text-xl font-bold text-emerald-900">
                              {readinessData.summary.verified_outcomes}
                            </span>
                            <span className="text-[10px] text-emerald-600 block mt-0.5">
                              {readinessData.summary.eligible_prediction_outcome_pairs} eligible pairs
                            </span>
                          </div>

                          <div className="bg-blue-50/70 p-3 rounded-xl border border-blue-200">
                            <span className="text-blue-800 font-medium block">Evaluation Coverage</span>
                            <span className="text-xl font-bold text-blue-900">
                              {readinessData.summary.evaluation_coverage_percentage}%
                            </span>
                            <span className="text-[10px] text-blue-600 block mt-0.5">
                              Dataset maturity (not accuracy)
                            </span>
                          </div>
                        </div>

                        {/* Outcome Verification Queue */}
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-bold uppercase text-gray-700 tracking-wider">
                              Outcome Verification Queue ({readinessData.verification_queue.length})
                            </h4>
                            <span className="text-[11px] text-gray-500">
                              Expert verification determines entry into official evaluation
                            </span>
                          </div>

                          {readinessData.verification_queue.length === 0 ? (
                            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs text-gray-500 text-center">
                              No recorded crop outcomes waiting in the verification queue.
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {readinessData.verification_queue.map((item) => (
                                <div
                                  key={item.crop_id}
                                  className="p-4 bg-white border border-gray-200 rounded-xl shadow-xs space-y-3 text-xs"
                                >
                                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-bold text-gray-900 text-sm">{item.farm_name}</span>
                                        <span className="text-gray-400">·</span>
                                        <span className="font-semibold text-emerald-800">
                                          {item.crop} ({item.season})
                                        </span>
                                      </div>
                                      <p className="text-[11px] text-gray-500 mt-0.5">
                                        Reported Status: <strong className={item.status === "failed" ? "text-rose-700" : "text-emerald-700"}>{item.status.toUpperCase()}</strong> · Harvest Date: {item.actual_harvest_date || "—"} · Yield: {item.reported_yield_kg_per_ha ? `${item.reported_yield_kg_per_ha} kg/ha` : "—"}
                                      </p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span
                                        className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${
                                          item.verification_status === "verified"
                                            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                                            : item.verification_status === "synthetic"
                                            ? "bg-purple-100 text-purple-800 border-purple-300"
                                            : item.verification_status === "invalid"
                                            ? "bg-rose-100 text-rose-800 border-rose-300"
                                            : "bg-amber-100 text-amber-800 border-amber-300"
                                        }`}
                                      >
                                        {item.verification_status.toUpperCase()}
                                      </span>
                                    </div>
                                  </div>

                                  {item.outcome_notes && (
                                    <p className="text-gray-600 bg-slate-50 p-2 rounded border border-slate-100 italic">
                                      "{item.outcome_notes}"
                                    </p>
                                  )}

                                  {/* Eligibility Preview */}
                                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-[11px]">
                                    <div>
                                      <span className="text-gray-500 block">Prediction Count:</span>
                                      <span className="font-bold text-gray-800">{item.prediction_count}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500 block">Potentially Matchable:</span>
                                      <span className="font-bold text-blue-800">{item.potential_eligible_pairs_count}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500 block">Eligible After Verification:</span>
                                      <span className="font-bold text-emerald-800">
                                        {item.potential_eligible_pairs_count}
                                      </span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500 block">Hindsight Exclusions:</span>
                                      <span className="font-bold text-gray-800">
                                        {item.prediction_count - item.potential_eligible_pairs_count}
                                      </span>
                                    </div>
                                  </div>

                                  {/* Verification Actions for Experts */}
                                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-100">
                                    <span className="text-[11px] text-gray-400">
                                      Recorded: {item.recorded_at ? new Date(item.recorded_at).toLocaleDateString() : "—"}
                                      {item.verified_by && ` · Verified by expert`}
                                    </span>

                                    {item.verification_status === "pending" && (
                                      <div className="flex items-center gap-2">
                                        {verifyingCropId === item.crop_id ? (
                                          <div className="flex items-center gap-2 bg-slate-100 p-1.5 rounded-lg border border-slate-300">
                                            <input
                                              type="text"
                                              value={verifyingNote}
                                              onChange={(e) => setVerifyingNote(e.target.value)}
                                              placeholder="Optional verification note"
                                              className="text-xs p-1 rounded border border-gray-300 bg-white"
                                            />
                                            <button
                                              onClick={() => handleVerifyCropOutcome(item.crop_id, item.farm_id)}
                                              className={`px-3 py-1 text-white text-xs font-bold rounded ${
                                                verifyingAction === "verify"
                                                  ? "bg-emerald-700 hover:bg-emerald-800"
                                                  : "bg-rose-700 hover:bg-rose-800"
                                              }`}
                                            >
                                              Confirm {verifyingAction === "verify" ? "Approval" : "Rejection"}
                                            </button>
                                            <button
                                              onClick={() => setVerifyingCropId(null)}
                                              className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
                                            >
                                              Cancel
                                            </button>
                                          </div>
                                        ) : (
                                          <>
                                            <button
                                              onClick={() => {
                                                setVerifyingCropId(item.crop_id);
                                                setVerifyingAction("verify");
                                              }}
                                              className="px-3 py-1 bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-lg text-xs transition"
                                            >
                                              ✅ Verify Outcome
                                            </button>
                                            <button
                                              onClick={() => {
                                                setVerifyingCropId(item.crop_id);
                                                setVerifyingAction("reject");
                                              }}
                                              className="px-3 py-1 bg-slate-200 hover:bg-rose-100 text-gray-700 hover:text-rose-800 font-bold rounded-lg text-xs transition"
                                            >
                                              ❌ Mark Invalid
                                            </button>
                                          </>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Pending Evaluation Queue (Active crops awaiting harvest) */}
                        <details className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                          <summary className="text-xs font-bold uppercase text-gray-700 tracking-wider cursor-pointer">
                            Active Crops Awaiting Harvest ({readinessData.pending_queue.length} cycles)
                          </summary>
                          <div className="mt-3 overflow-x-auto">
                            {readinessData.pending_queue.length === 0 ? (
                              <p className="text-xs text-gray-400 py-2">No active crop cycles awaiting outcomes.</p>
                            ) : (
                              <table className="w-full text-xs text-left">
                                <thead className="bg-white font-bold text-gray-700 text-[10px] uppercase border-b">
                                  <tr>
                                    <th className="p-2">Farm Name</th>
                                    <th className="p-2">Crop / Season</th>
                                    <th className="p-2">Predictions</th>
                                    <th className="p-2">Earliest Prediction</th>
                                    <th className="p-2">Latest Prediction</th>
                                    <th className="p-2">Expected Harvest</th>
                                    <th className="p-2">Status</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 bg-white">
                                  {readinessData.pending_queue.map((q, idx) => (
                                    <tr key={idx} className="hover:bg-slate-50">
                                      <td className="p-2 font-semibold text-gray-900">{q.farm_name}</td>
                                      <td className="p-2 font-medium text-emerald-800">{q.crop} ({q.season})</td>
                                      <td className="p-2 font-bold">{q.prediction_count}</td>
                                      <td className="p-2 text-gray-500">{q.earliest_prediction_date ? new Date(q.earliest_prediction_date).toLocaleDateString() : "—"}</td>
                                      <td className="p-2 text-gray-500">{q.latest_prediction_date ? new Date(q.latest_prediction_date).toLocaleDateString() : "—"}</td>
                                      <td className="p-2 text-gray-700">{q.expected_harvest_date || "Not set"}</td>
                                      <td className="p-2">
                                        <span className="px-1.5 py-0.5 bg-blue-100 text-blue-800 rounded text-[10px] font-bold">
                                          Awaiting Harvest
                                        </span>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </div>
                        </details>

                        {/* Exclusions Breakdown & Model Versions */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                          <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-2">
                            <span className="font-bold text-gray-800 block">Exclusion Reasons Breakdown</span>
                            <div className="space-y-1 text-[11px]">
                              {Object.entries(readinessData.exclusions_breakdown).map(([reason, count]) => (
                                <div key={reason} className="flex justify-between py-0.5 border-b border-gray-100">
                                  <span className="text-gray-600">{reason.replace(/_/g, " ")}:</span>
                                  <span className="font-bold text-gray-900">{count}</span>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-2">
                            <span className="font-bold text-gray-800 block">Lead Time & Model Versions</span>
                            <div className="space-y-1 text-[11px]">
                              <div className="flex justify-between py-0.5 border-b border-gray-100">
                                <span className="text-gray-600">Average Lead Time:</span>
                                <span className="font-bold text-gray-900">
                                  {readinessData.average_lead_time_days !== null && readinessData.average_lead_time_days !== undefined
                                    ? `${readinessData.average_lead_time_days} days`
                                    : "No verified outcomes yet"}
                                </span>
                              </div>
                              <div className="flex justify-between py-0.5 border-b border-gray-100">
                                <span className="text-gray-600">Evaluated Model Versions:</span>
                                <span className="font-bold text-gray-900">
                                  {Object.keys(readinessData.model_version_breakdown).length > 0
                                    ? Object.entries(readinessData.model_version_breakdown)
                                        .map(([k, v]) => `${k} (${v})`)
                                        .join(", ")
                                    : "None eligible"}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  {/* Train/Test Provenance */}
                  {evalReport.train_test_provenance && (
                    <details className="bg-white border border-slate-200 rounded-xl p-4">
                      <summary className="text-sm font-bold text-gray-800 cursor-pointer">Training & Test Split Provenance</summary>
                      <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                        {[
                          { label: "Dataset Rows", val: evalReport.train_test_provenance.total_rows },
                          { label: "Train Rows", val: evalReport.train_test_provenance.train_rows },
                          { label: "Test Rows", val: evalReport.train_test_provenance.test_rows },
                          { label: "Test Split", val: `${(evalReport.train_test_provenance.test_size * 100).toFixed(0)}%` },
                          { label: "Random State", val: evalReport.train_test_provenance.random_state },
                          { label: "Stratified", val: evalReport.train_test_provenance.stratified ? "Yes" : "No" },
                          { label: "Target Column", val: evalReport.train_test_provenance.target_column },
                          { label: "Best Model", val: evalReport.train_test_provenance.best_model_name },
                          { label: "Training ROC-AUC", val: evalReport.train_test_provenance.best_model_roc_auc.toFixed(4) },
                          { label: "Training F1", val: evalReport.train_test_provenance.best_model_f1.toFixed(4) },
                          { label: "Failure Rate", val: `${(evalReport.train_test_provenance.class_balance_ratio * 100).toFixed(1)}%` },
                          { label: "Selection Metric", val: evalReport.train_test_provenance.model_selection_metric },
                        ].map((item, i) => (
                          <div key={i} className="bg-slate-50 p-2 rounded border border-slate-200">
                            <span className="text-gray-500 block">{item.label}</span>
                            <span className="font-bold text-gray-900">{String(item.val)}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Disclaimer */}
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-[11px] text-blue-800">
                    <strong>⚠️ Important:</strong> {evalReport.disclaimer}
                  </div>

                  <p className="text-[11px] text-gray-400 text-right">Report generated: {new Date(evalReport.report_generated_at).toLocaleString()}</p>
                </div>
              )}
            </div>
          )}

          {/* TAB: EXPERIMENTAL NEURO-FUZZY MODEL */}
          {activeTab === "neurofuzzy" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-100 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🧬</span>
                    <h2 className="text-xl font-bold text-gray-900">Experimental Neuro-Fuzzy Model</h2>
                    <span className="text-[10px] bg-purple-100 text-purple-800 font-bold px-2 py-0.5 rounded-full border border-purple-200">
                      Experimental
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    First-Order Takagi-Sugeno-Kang (TSK) Adaptive Neuro-Fuzzy Inference System for transparent, rule-grounded crop failure risk reasoning.
                  </p>
                </div>
                <button
                  onClick={loadNeuroFuzzyData}
                  disabled={nfLoading}
                  className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold text-xs rounded-xl border border-slate-200 transition"
                >
                  {nfLoading ? "Refreshing..." : "🔄 Refresh State"}
                </button>
              </div>

              {/* Status Header Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Model Status</span>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`w-2.5 h-2.5 rounded-full ${nfStatus?.is_available ? "bg-emerald-500" : "bg-red-500"}`} />
                    <p className="text-base font-bold text-gray-900">
                      {nfStatus?.is_available ? "Active & Ready" : "Uninitialized"}
                    </p>
                  </div>
                  <span className="text-[11px] text-gray-400">Version: {nfStatus?.version || "—"}</span>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Fuzzy Rules</span>
                  <p className="text-xl font-bold text-blue-900 mt-1">
                    {nfStatus?.n_rules || 6} Canonical Rules
                  </p>
                  <span className="text-[11px] text-gray-400">Takagi-Sugeno Linear Consequents</span>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Defensible Threshold</span>
                  <p className="text-xl font-bold text-purple-900 mt-1">
                    {nfStatus?.optimal_threshold ? `${nfStatus.optimal_threshold.toFixed(2)}` : "0.41"}
                  </p>
                  <span className="text-[11px] text-purple-700 font-medium">Tuned strictly on validation partition</span>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <span className="text-xs font-semibold text-gray-500">Validation ROC-AUC</span>
                  <p className="text-xl font-bold text-emerald-800 mt-1">
                    {nfStatus?.training_metadata?.val_roc_auc ? nfStatus.training_metadata.val_roc_auc.toFixed(4) : "0.7169"}
                  </p>
                  <span className="text-[11px] text-emerald-600 font-medium">Zero Target Leakage</span>
                </div>
              </div>

              {/* Benchmarking Comparison Table */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-gray-900">
                      Rigorous Held-Out Evaluation Comparison (Test Set, N=1,507)
                    </h3>
                    <p className="text-xs text-gray-500">
                      Standardized comparison against production Logistic Regression and tree-based ensembles on identical test partition.
                    </p>
                  </div>
                  <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2.5 py-1 rounded-lg">
                    Fixed Seed = 42
                  </span>
                </div>

                {nfComparison.length === 0 ? (
                  <p className="text-xs text-gray-400 py-4 text-center">Loading comparison metrics...</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-50 border-b border-gray-200 text-gray-700 font-bold uppercase text-[10px]">
                        <tr>
                          <th className="py-2.5 px-3">Model Architecture</th>
                          <th className="py-2.5 px-2">ROC-AUC</th>
                          <th className="py-2.5 px-2">PR-AUC</th>
                          <th className="py-2.5 px-2">Precision</th>
                          <th className="py-2.5 px-2">Recall</th>
                          <th className="py-2.5 px-2">F1-Score</th>
                          <th className="py-2.5 px-2">Brier Score</th>
                          <th className="py-2.5 px-2">Threshold</th>
                          <th className="py-2.5 px-2">Infer Time</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {nfComparison.map((row, idx) => (
                          <tr
                            key={idx}
                            className={row.Model.includes("Neuro-Fuzzy") ? "bg-purple-50/60 font-semibold" : "hover:bg-slate-50"}
                          >
                            <td className="py-2.5 px-3 font-bold text-gray-900 flex items-center gap-1.5">
                              {row.Model.includes("Neuro-Fuzzy") && <span>🧬</span>}
                              {row.Model}
                            </td>
                            <td className="py-2.5 px-2">{Number(row["ROC-AUC"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2">{Number(row["PR-AUC"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2">{Number(row["Precision"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2">{Number(row["Recall"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2 font-bold text-blue-900">{Number(row["F1-Score"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2">{Number(row["Brier Score"]).toFixed(4)}</td>
                            <td className="py-2.5 px-2 text-gray-600">{Number(row["Threshold"]).toFixed(2)}</td>
                            <td className="py-2.5 px-2 text-gray-500">{Number(row["Infer Time (ms)"]).toFixed(2)} ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Interactive Neuro-Fuzzy Inference & Rule Inspection */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Input Controller */}
                <div className="bg-slate-50 rounded-2xl p-5 border border-slate-200 space-y-4">
                  <div className="border-b border-gray-200 pb-2">
                    <h3 className="font-bold text-gray-900 text-sm">Interactive Agronomic Input Vector</h3>
                    <p className="text-[11px] text-gray-500">8 pre-harvest continuous environmental variables.</p>
                  </div>

                  <div className="space-y-3 text-xs">
                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Rainfall:</span>
                        <span className="font-bold text-blue-900">{nfRainfall} mm</span>
                      </div>
                      <input
                        type="range"
                        min="10"
                        max="350"
                        step="5"
                        value={nfRainfall}
                        onChange={(e) => setNfRainfall(parseFloat(e.target.value))}
                        className="w-full accent-blue-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Temperature:</span>
                        <span className="font-bold text-amber-900">{nfTemperature} °C</span>
                      </div>
                      <input
                        type="range"
                        min="15"
                        max="45"
                        step="0.5"
                        value={nfTemperature}
                        onChange={(e) => setNfTemperature(parseFloat(e.target.value))}
                        className="w-full accent-amber-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Humidity:</span>
                        <span className="font-bold text-cyan-900">{nfHumidity}%</span>
                      </div>
                      <input
                        type="range"
                        min="20"
                        max="95"
                        step="1"
                        value={nfHumidity}
                        onChange={(e) => setNfHumidity(parseFloat(e.target.value))}
                        className="w-full accent-cyan-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Soil Moisture:</span>
                        <span className="font-bold text-emerald-900">{nfSoilMoisture}%</span>
                      </div>
                      <input
                        type="range"
                        min="10"
                        max="85"
                        step="1"
                        value={nfSoilMoisture}
                        onChange={(e) => setNfSoilMoisture(parseFloat(e.target.value))}
                        className="w-full accent-emerald-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>NDVI Flowering (Sentinel-2 proxy):</span>
                        <span className="font-bold text-emerald-800">{nfNdvi.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.2"
                        max="0.9"
                        step="0.02"
                        value={nfNdvi}
                        onChange={(e) => setNfNdvi(parseFloat(e.target.value))}
                        className="w-full accent-emerald-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Water Stress Index:</span>
                        <span className="font-bold text-red-900">{nfWaterStress.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.0"
                        max="1.0"
                        step="0.05"
                        value={nfWaterStress}
                        onChange={(e) => setNfWaterStress(parseFloat(e.target.value))}
                        className="w-full accent-red-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Pest & Pathogen Risk:</span>
                        <span className="font-bold text-orange-900">{nfPestRisk.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.1"
                        max="0.9"
                        step="0.05"
                        value={nfPestRisk}
                        onChange={(e) => setNfPestRisk(parseFloat(e.target.value))}
                        className="w-full accent-orange-600 mt-1"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>Crop Regional Suitability:</span>
                        <span className="font-bold text-indigo-900">{nfSuitability.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.2"
                        max="1.0"
                        step="0.05"
                        value={nfSuitability}
                        onChange={(e) => setNfSuitability(parseFloat(e.target.value))}
                        className="w-full accent-indigo-600 mt-1"
                      />
                    </div>
                  </div>

                  <button
                    onClick={async () => {
                      if (!token) return;
                      setNfPredicting(true);
                      try {
                        const res = await predictNeuroFuzzy(
                          {
                            rainfall: nfRainfall,
                            temperature: nfTemperature,
                            humidity: nfHumidity,
                            soil_moisture: nfSoilMoisture,
                            ndvi_flowering: nfNdvi,
                            water_stress: nfWaterStress,
                            pest_risk: nfPestRisk,
                            suitability_score: nfSuitability,
                          },
                          token
                        );
                        setNfPredictionResult(res);
                      } catch (err: any) {
                        alert(`Inference failed: ${err.message}`);
                      } finally {
                        setNfPredicting(false);
                      }
                    }}
                    disabled={nfPredicting}
                    className="w-full py-2.5 bg-purple-700 hover:bg-purple-800 text-white font-bold text-xs rounded-xl shadow transition"
                  >
                    {nfPredicting ? "Evaluating Fuzzy Rules..." : "⚡ Run Neuro-Fuzzy Inference"}
                  </button>
                </div>

                {/* Inference Results & Activated Rules */}
                <div className="lg:col-span-2 space-y-4">
                  {nfPredictionResult ? (
                    <div className="space-y-4">
                      {/* Prediction Outcome Card */}
                      <div className="bg-white p-5 rounded-2xl border border-purple-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
                        <div>
                          <span className="text-[10px] uppercase font-bold text-purple-700 tracking-wider">
                            Neuro-Fuzzy Defuzzified Output
                          </span>
                          <h3 className="text-2xl font-black text-gray-900 mt-0.5">
                            Risk: {nfPredictionResult.risk_percentage}
                          </h3>
                          <p className="text-xs text-gray-600 mt-1">
                            Decision Threshold: <span className="font-bold">{nfPredictionResult.threshold.toFixed(2)}</span> ·{" "}
                            Outcome:{" "}
                            <span
                              className={`font-bold ${
                                nfPredictionResult.failure_predicted ? "text-red-700" : "text-emerald-700"
                              }`}
                            >
                              {nfPredictionResult.failure_predicted ? "Crop Failure Alert" : "Favorable Harvest"}
                            </span>
                          </p>
                        </div>
                        <span
                          className={`text-sm font-black px-4 py-2 rounded-xl border ${
                            nfPredictionResult.risk_band === "High"
                              ? "bg-red-100 text-red-800 border-red-300"
                              : nfPredictionResult.risk_band === "Medium"
                                ? "bg-amber-100 text-amber-800 border-amber-300"
                                : "bg-emerald-100 text-emerald-800 border-emerald-300"
                          }`}
                        >
                          {nfPredictionResult.risk_band} Risk
                        </span>
                      </div>

                      {/* Dominant Activated Rule */}
                      <div className="bg-purple-50/70 p-4 rounded-xl border border-purple-200">
                        <span className="text-xs font-bold text-purple-900 uppercase">
                          Dominant Rule: {nfPredictionResult.dominant_rule.rule_name}
                        </span>
                        <p className="text-xs font-semibold text-gray-800 mt-1">
                          {nfPredictionResult.dominant_rule.description}
                        </p>
                        <div className="flex gap-4 mt-2 text-[11px] text-gray-600">
                          <span>
                            Firing Strength: <strong>{(nfPredictionResult.dominant_rule.firing_strength * 100).toFixed(1)}%</strong>
                          </span>
                          <span>
                            Consequent Value: <strong>{nfPredictionResult.dominant_rule.consequent_score.toFixed(3)}</strong>
                          </span>
                          <span>
                            Total Contribution: <strong>{nfPredictionResult.dominant_rule.rule_contribution.toFixed(3)}</strong>
                          </span>
                        </div>
                      </div>

                      {/* All Activated Rules Table */}
                      <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-3">
                        <h4 className="text-xs font-bold text-gray-900 uppercase">
                          Fuzzy Rule Base Activations (Sugeno Weighted Averaging)
                        </h4>
                        <div className="space-y-2">
                          {nfPredictionResult.activated_rules.map((rule) => (
                            <div
                              key={rule.rule_index}
                              className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs space-y-1.5"
                            >
                              <div className="flex justify-between items-center">
                                <span className="font-bold text-gray-900">{rule.rule_name}</span>
                                <span className="font-bold text-purple-800 text-[11px]">
                                  Weight: {(rule.normalized_weight * 100).toFixed(1)}%
                                </span>
                              </div>
                              <p className="text-[11px] text-gray-600">{rule.description}</p>
                              {/* Antecedent Membership Progress Bars */}
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                                {Object.entries(rule.antecedent_memberships).map(([feat, mu]) => (
                                  <div key={feat} className="bg-white p-1.5 rounded border border-gray-100">
                                    <span className="text-[10px] text-gray-500 block truncate">{feat}</span>
                                    <span className="font-bold text-[11px] text-gray-800">μ = {mu.toFixed(2)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center p-12 bg-slate-50 rounded-2xl border border-dashed border-slate-300 text-center">
                      <span className="text-3xl mb-2">⚡</span>
                      <h4 className="font-bold text-gray-800 text-sm">Ready for Neuro-Fuzzy Inference</h4>
                      <p className="text-xs text-gray-500 max-w-sm mt-1">
                        Adjust continuous environmental factors on the left and click &quot;Run Neuro-Fuzzy Inference&quot; to inspect rule activations and consequent contributions.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Research Disclaimer */}
              <div className="p-3.5 bg-purple-50/60 border border-purple-200 rounded-xl text-xs text-purple-900">
                <strong>🔬 Experimental Protocol Notice:</strong> The Neuro-Fuzzy model is strictly an experimental tool for expert inspection. Farm-level advisory recommendations continue to use the validated production model until comprehensive longitudinal field testing is complete.
              </div>
            </div>
          )}

          {/* FUTURE PLANNED TABS */}
          {["performance", "models"].includes(activeTab) && (
            <div className="text-center py-16 space-y-3">
              <div className="text-4xl">⏳</div>
              <h3 className="text-base font-bold text-gray-800">Coming in a later development phase</h3>
              <p className="text-xs text-gray-500 max-w-sm mx-auto">
                This feature module is scheduled for implementation in upcoming milestones. No mocked or fabricated data is displayed.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
