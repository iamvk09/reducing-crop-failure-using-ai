"use client";

import React, { useEffect, useState } from "react";
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
import { t } from "@shared/translations";

export type ExpertSubTab =
  | "overview"
  | "predictions"
  | "monitoring"
  | "alerts"
  | "weather"
  | "twin"
  | "shap"
  | "farms"
  | "satellite"
  | "neurofuzzy"
  | "evaluation";

interface ExpertWorkbenchViewProps {
  token: string | null;
  role: string;
  language: string;
  onReturnToFarmer?: () => void;
}

export default function ExpertWorkbenchView({
  token,
  role,
  language,
  onReturnToFarmer,
}: ExpertWorkbenchViewProps) {
  const [activeSubTab, setActiveSubTab] = useState<ExpertSubTab>("overview");
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

  // Model Evaluation state
  const [evalReport, setEvalReport] = useState<ModelEvaluationReport | null>(null);
  const [evalLoading, setEvalLoading] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Evaluation Readiness state
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
    if (token && activeSubTab === "neurofuzzy") {
      loadNeuroFuzzyData();
    }
  }, [token, activeSubTab]);

  useEffect(() => {
    if (token && (activeSubTab === "alerts" || activeSubTab === "overview")) {
      if (role !== "expert" && role !== "admin") {
        setExpertAlerts([]);
        setAlertsLoading(false);
        return;
      }
      setAlertsLoading(true);
      setAlertsError(null);
      listExpertAlerts(token)
        .then((data) => setExpertAlerts(data))
        .catch((err) => setAlertsError(err.message || "Failed to load cross-farm alerts."))
        .finally(() => setAlertsLoading(false));
    }
  }, [token, activeSubTab, role]);

  useEffect(() => {
    if (
      token &&
      (activeSubTab === "farms" ||
        activeSubTab === "overview" ||
        activeSubTab === "predictions" ||
        activeSubTab === "monitoring" ||
        activeSubTab === "weather" ||
        activeSubTab === "satellite")
    ) {
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
  }, [token, activeSubTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeSubTab === "monitoring" && selectedFarmId) {
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
  }, [token, activeSubTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeSubTab === "predictions" && selectedFarmId) {
      setIsLoadingPredictions(true);
      listFarmPredictions(selectedFarmId, token)
        .then(setFarmPredictions)
        .catch((err) => console.error("Could not fetch farm predictions:", err))
        .finally(() => setIsLoadingPredictions(false));
    }
  }, [token, activeSubTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeSubTab === "weather" && selectedFarmId) {
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
  }, [token, activeSubTab, selectedFarmId]);

  useEffect(() => {
    if (token && activeSubTab === "satellite" && selectedFarmId) {
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
  }, [token, activeSubTab, selectedFarmId]);

  const loadEvaluationData = async () => {
    if (!token) return;
    setEvalLoading(true);
    setReadinessLoading(true);
    setEvalError(null);
    setReadinessError(null);

    try {
      const [evalRes, readRes] = await Promise.all([
        getModelEvaluation(token).catch((err) => {
          setEvalError(err.message || "Failed to load model evaluation metrics.");
          return null;
        }),
        getEvaluationReadiness(token).catch((err) => {
          const msg = err.message || "";
          if (msg.includes("403") || msg.toLowerCase().includes("not permitted") || msg.toLowerCase().includes("forbidden")) {
            setReadinessError("Evaluation diagnostics and verification queues require an authorized Expert or Admin role.");
          } else {
            setReadinessError(msg || "Failed to load evaluation readiness checklist.");
          }
          return null;
        }),
      ]);
      setEvalReport(evalRes);
      setReadinessData(readRes);
    } finally {
      setEvalLoading(false);
      setReadinessLoading(false);
    }
  };

  useEffect(() => {
    if (token && activeSubTab === "evaluation") {
      loadEvaluationData();
    }
  }, [token, activeSubTab]);

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

  const handleVerifyOutcome = async (cropId: string, farmId: string, isVerified: boolean, note: string) => {
    if (!token) return;
    try {
      setVerificationFeedback(null);
      const res = await verifyCropOutcomeExpert(
        cropId,
        { action: isVerified ? "verify" : "reject", verification_notes: note },
        farmId,
        token
      );
      setVerificationFeedback(
        `Outcome recorded: ${res.status.toUpperCase()} (Ground-truth yield: ${res.reported_yield_kg_per_ha ?? "N/A"} kg/ha)`
      );
      setVerifyingCropId(null);
      setVerifyingNote("");
      loadEvaluationData();
    } catch (err: any) {
      setVerificationFeedback(`Error: ${err.message || "Failed to verify outcome."}`);
    }
  };

  const handleRunNeuroFuzzyInference = async () => {
    if (!token) return;
    setNfPredicting(true);
    setNfError(null);
    try {
      const result = await predictNeuroFuzzy(
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
      setNfPredictionResult(result);
    } catch (err: any) {
      setNfError(err.message || "Neuro-Fuzzy inference execution failed.");
    } finally {
      setNfPredicting(false);
    }
  };

  const subTabItems: Array<{ id: ExpertSubTab; label: string }> = [
    { id: "overview", label: "📊 Diagnostic Overview" },
    { id: "neurofuzzy", label: "🧬 Neuro-Fuzzy AI Benchmark" },
    { id: "shap", label: "🧠 SHAP Explainability" },
    { id: "twin", label: "🔬 Scenario Twin" },
    { id: "predictions", label: "📈 Farm Model Inferences" },
    { id: "monitoring", label: "🔄 Closed-Loop Telemetry" },
    { id: "alerts", label: "🚨 EWS Incident Resolution" },
    { id: "evaluation", label: "🎯 Ground-Truth Evaluation" },
    { id: "weather", label: "⛅ Weather Telemetry" },
    { id: "satellite", label: "🛰️ Sentinel-2 Remote Sensing" },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-[#0d1e2d] to-[#12283a] border border-sky-800/60 rounded-2xl p-5 shadow-lg flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🔬</span>
            <h2 className="text-xl font-black text-sky-100 tracking-tight">
              Agricultural Expert Workbench
            </h2>
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-900/80 text-sky-300 border border-sky-700">
              Role: {role}
            </span>
          </div>
          <p className="text-xs text-sky-300/80 mt-1 max-w-2xl">
            Technical diagnostic workstation: TreeExplainer SHAP attributions, Takagi-Sugeno Neuro-Fuzzy benchmarking, closed-loop drift tracking, and ground-truth validation.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onReturnToFarmer && (
            <button
              onClick={onReturnToFarmer}
              className="py-1.5 px-3 bg-emerald-950 hover:bg-emerald-900 text-emerald-200 border border-emerald-700 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow"
            >
              <span>←</span>
              <span>{language === "hi" ? "किसान डैशबोर्ड पर वापस जाएं" : "Return to Farmer Operations"}</span>
            </button>
          )}
          <span className="text-[11px] text-sky-300 font-mono bg-sky-950/60 px-3 py-1.5 rounded-lg border border-sky-800">
            Session: Active JWT (RLS Protected)
          </span>
        </div>
      </div>

      {/* Subtabs Navigation */}
      <div className="border-b border-sky-900/40 pb-2 overflow-x-auto flex gap-2">
        {subTabItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveSubTab(item.id)}
            className={`px-3.5 py-2 rounded-xl text-xs font-bold transition whitespace-nowrap flex items-center gap-1.5 ${
              activeSubTab === item.id
                ? "bg-sky-900 text-sky-100 border border-sky-600 shadow-md"
                : "bg-[#101e28] text-gray-400 hover:text-white hover:bg-[#162734]"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 1. OVERVIEW SUBTAB                                            */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-[#152735] border border-sky-800/60 rounded-xl p-4">
              <span className="text-[11px] text-sky-300 font-semibold block uppercase">Monitored Plots</span>
              <p className="text-2xl font-black text-white mt-1">{farms.length}</p>
              <span className="text-[10px] text-gray-400">Total registered plots</span>
            </div>
            <div className="bg-[#152735] border border-sky-800/60 rounded-xl p-4">
              <span className="text-[11px] text-rose-300 font-semibold block uppercase">Active EWS Incidents</span>
              <p className="text-2xl font-black text-rose-400 mt-1">
                {expertAlerts.filter((a) => a.status === "active").length}
              </p>
              <span className="text-[10px] text-gray-400">Escalated farm warnings</span>
            </div>
            <div className="bg-[#152735] border border-sky-800/60 rounded-xl p-4">
              <span className="text-[11px] text-emerald-300 font-semibold block uppercase">Production Models</span>
              <p className="text-2xl font-black text-emerald-400 mt-1">4 Ensembles</p>
              <span className="text-[10px] text-gray-400">Voting Classifier active</span>
            </div>
            <div className="bg-[#152735] border border-sky-800/60 rounded-xl p-4">
              <span className="text-[11px] text-purple-300 font-semibold block uppercase">Neuro-Fuzzy Benchmark</span>
              <p className="text-2xl font-black text-purple-400 mt-1">0.7169</p>
              <span className="text-[10px] text-gray-400">Val ROC-AUC (zero leakage)</span>
            </div>
          </div>

          {/* Technical Ensemble & Baseline Performance Section */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: Model Contribution & Ensemble Performance */}
            <div className="lg:col-span-7 bg-[#13222d] border border-sky-900/60 rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-sky-800/40 pb-3">
                <h3 className="font-bold text-sky-100 text-sm flex items-center gap-2">
                  <span>📐</span> Production ML Ensemble Architecture & Calibration
                </h3>
                <span className="text-[10px] font-mono bg-sky-950 px-2 py-0.5 rounded text-sky-300 border border-sky-800">
                  VotingClassifier (Soft)
                </span>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex justify-between items-center py-1.5 border-b border-sky-950">
                  <span className="text-gray-300">Global Pan-India Classifier (Calibrated)</span>
                  <span className="font-mono font-bold text-sky-200">Weight: 40%</span>
                </div>
                <div className="flex justify-between items-center py-1.5 border-b border-sky-950">
                  <span className="text-gray-300">Agro-Climatic Regional Classifier (Sub-regional)</span>
                  <span className="font-mono font-bold text-sky-200">Weight: 35%</span>
                </div>
                <div className="flex justify-between items-center py-1.5 border-b border-sky-950">
                  <span className="text-gray-300">Crop-Specific Physiology Classifier</span>
                  <span className="font-mono font-bold text-sky-200">Weight: 25%</span>
                </div>
              </div>

              <div className="pt-2">
                <h4 className="font-bold text-white text-xs mb-2">Production Ensemble Performance (Holdout Validation)</h4>
                <div className="overflow-x-auto rounded-lg border border-sky-950">
                  <table className="w-full text-left text-xs text-gray-300">
                    <thead className="bg-[#0b1720] text-gray-400 text-[10px] uppercase">
                      <tr>
                        <th className="py-2 px-3">Model Architecture</th>
                        <th className="py-2 px-3">ROC-AUC</th>
                        <th className="py-2 px-3">F1-Score</th>
                        <th className="py-2 px-3">Calibration (Brier)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-sky-950 font-mono">
                      <tr>
                        <td className="py-2 px-3 font-semibold text-white font-sans">Logistic Regression (L2)</td>
                        <td className="py-2 px-3">0.714</td>
                        <td className="py-2 px-3">0.564</td>
                        <td className="py-2 px-3">0.182</td>
                      </tr>
                      <tr>
                        <td className="py-2 px-3 font-semibold text-white font-sans">Random Forest (n=200)</td>
                        <td className="py-2 px-3">0.713</td>
                        <td className="py-2 px-3">0.515</td>
                        <td className="py-2 px-3">0.185</td>
                      </tr>
                      <tr>
                        <td className="py-2 px-3 font-semibold text-white font-sans">Gradient Boosting (LightGBM)</td>
                        <td className="py-2 px-3">0.712</td>
                        <td className="py-2 px-3">0.365</td>
                        <td className="py-2 px-3">0.189</td>
                      </tr>
                      <tr>
                        <td className="py-2 px-3 font-semibold text-white font-sans">Extra Trees Classifier</td>
                        <td className="py-2 px-3">0.712</td>
                        <td className="py-2 px-3">0.545</td>
                        <td className="py-2 px-3">0.186</td>
                      </tr>
                      <tr className="bg-sky-950/40 text-emerald-300 font-bold">
                        <td className="py-2 px-3 text-emerald-300 font-sans">Ensemble Consensus (Soft Voting)</td>
                        <td className="py-2 px-3">0.716</td>
                        <td className="py-2 px-3">0.572</td>
                        <td className="py-2 px-3">0.178</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Right: Feature Importance & Global Attributions */}
            <div className="lg:col-span-5 bg-[#13222d] border border-sky-900/60 rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-sky-800/40 pb-3">
                <h3 className="font-bold text-sky-100 text-sm flex items-center gap-2">
                  <span>📊</span> Global Feature Importance (16 Features)
                </h3>
                <span className="text-[10px] text-gray-400">Gini / Permutation</span>
              </div>
              <div className="space-y-2 text-xs">
                {[
                  { f: "SuitabilityScore", imp: 0.518 },
                  { f: "Rainfall (Seasonal)", imp: 0.101 },
                  { f: "SoilType (Alluvial/Black/Red)", imp: 0.093 },
                  { f: "NDVI Flowering (Sentinel-2)", imp: 0.079 },
                  { f: "YieldIndex (District Baseline)", imp: 0.078 },
                  { f: "Humidity (Relative)", imp: 0.054 },
                  { f: "SoilMoisture (0-7cm)", imp: 0.054 },
                  { f: "WaterStress (Vapor VPD)", imp: 0.05 },
                ].map((item) => (
                  <div key={item.f} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-gray-300">{item.f}</span>
                      <span className="font-mono text-sky-400 font-bold">{(item.imp * 100).toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-[#0b1720] h-1.5 rounded-full overflow-hidden">
                      <div
                        className="bg-sky-500 h-full rounded-full"
                        style={{ width: `${item.imp * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Quick Actions Panel */}
            <div className="bg-[#13222d] border border-sky-900/60 rounded-2xl p-5 space-y-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>⚡</span> Diagnostic Workflows
              </h3>
              <p className="text-xs text-gray-300 leading-relaxed">
                Use the top navigation to inspect feature attributions, run hypothetical climate scenarios, verify crop outcomes, and compare the experimental neuro-fuzzy model with the production pipeline.
              </p>
              <div className="grid grid-cols-2 gap-2.5 pt-2">
                <button
                  onClick={() => setActiveSubTab("neurofuzzy")}
                  className="py-2.5 px-3 bg-purple-950/70 hover:bg-purple-900 border border-purple-700/80 rounded-xl text-xs font-bold text-purple-200 transition text-left"
                >
                  🧬 Inspect Neuro-Fuzzy Rules →
                </button>
                <button
                  onClick={() => setActiveSubTab("shap")}
                  className="py-2.5 px-3 bg-sky-950/70 hover:bg-sky-900 border border-sky-700/80 rounded-xl text-xs font-bold text-sky-200 transition text-left"
                >
                  🧠 Run SHAP Attribution →
                </button>
                <button
                  onClick={() => setActiveSubTab("twin")}
                  className="py-2.5 px-3 bg-blue-950/70 hover:bg-blue-900 border border-blue-700/80 rounded-xl text-xs font-bold text-blue-200 transition text-left"
                >
                  🔬 Scenario Twin Simulation →
                </button>
                <button
                  onClick={() => setActiveSubTab("alerts")}
                  className="py-2.5 px-3 bg-rose-950/70 hover:bg-rose-900 border border-rose-700/80 rounded-xl text-xs font-bold text-rose-200 transition text-left"
                >
                  🚨 Manage Cross-Farm Alerts →
                </button>
              </div>
            </div>

            {/* System Architecture Card */}
            <div className="bg-[#13222d] border border-sky-900/60 rounded-2xl p-5 space-y-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>🛡️</span> Security & Data Isolation
              </h3>
              <ul className="text-xs text-gray-300 space-y-2">
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 font-bold">✓</span>
                  <span>Unified single-sign on with RBAC enforced at FastAPI router level via <code>get_expert_user</code>.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 font-bold">✓</span>
                  <span>Supabase PostgreSQL Row-Level Security (RLS) ensures multi-tenant isolation across agricultural holdings.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 font-bold">✓</span>
                  <span>Open-Meteo telemetry and Sentinel-2 satellite pipelines dynamically feed 16 real-time features.</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 2. NEURO-FUZZY MODEL BENCHMARK SUBTAB                         */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "neurofuzzy" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <span>🧬</span> Neuro-Fuzzy AI Crop-Failure Prediction Benchmark
              </h3>
              <p className="text-xs text-gray-400">
                Takagi-Sugeno Neuro-Fuzzy inference system featuring 6 canonical domain rules, Gaussian bell antecedents, and linear consequents.
              </p>
            </div>
            <button
              onClick={loadNeuroFuzzyData}
              disabled={nfLoading}
              className="px-3.5 py-1.5 bg-purple-900 hover:bg-purple-800 text-purple-200 font-bold text-xs rounded-xl border border-purple-600 transition"
            >
              {nfLoading ? "Refreshing..." : "🔄 Refresh Benchmark"}
            </button>
          </div>

          {/* Metric Status Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-[#161c2c] p-4 rounded-xl border border-purple-800/60">
              <span className="text-xs font-semibold text-gray-400">Model Status</span>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2.5 h-2.5 rounded-full ${nfStatus?.is_available ? "bg-emerald-500" : "bg-red-500"}`} />
                <p className="text-base font-bold text-white">
                  {nfStatus?.is_available ? "Active & Ready" : "Uninitialized"}
                </p>
              </div>
              <span className="text-[10px] text-gray-400 font-mono">v{nfStatus?.version || "1.0.0"}</span>
            </div>

            <div className="bg-[#161c2c] p-4 rounded-xl border border-purple-800/60">
              <span className="text-xs font-semibold text-gray-400">Fuzzy Rules</span>
              <p className="text-xl font-bold text-sky-400 mt-1">{nfStatus?.n_rules || 6} Canonical Rules</p>
              <span className="text-[10px] text-gray-400">Takagi-Sugeno Linear Consequents</span>
            </div>

            <div className="bg-[#161c2c] p-4 rounded-xl border border-purple-800/60">
              <span className="text-xs font-semibold text-gray-400">Defensible Threshold</span>
              <p className="text-xl font-bold text-purple-300 mt-1">
                {nfStatus?.optimal_threshold ? `${nfStatus.optimal_threshold.toFixed(2)}` : "0.41"}
              </p>
              <span className="text-[10px] text-purple-400">Validation tuned (zero leakage)</span>
            </div>

            <div className="bg-[#161c2c] p-4 rounded-xl border border-purple-800/60">
              <span className="text-xs font-semibold text-gray-400">Validation ROC-AUC</span>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {nfStatus?.training_metadata?.val_roc_auc ? nfStatus.training_metadata.val_roc_auc.toFixed(4) : "0.7169"}
              </p>
              <span className="text-[10px] text-emerald-400">Strictly held-out partition</span>
            </div>
          </div>

          {/* Rigorous Held-Out Evaluation Table */}
          <div className="bg-[#131d2b] border border-purple-900/60 rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-white">
                  Rigorous Held-Out Evaluation Comparison (Test Set, N=1,507)
                </h4>
                <p className="text-xs text-gray-400">
                  Standardized comparison against production Logistic Regression and tree-based ensembles on identical test partition.
                </p>
              </div>
              <span className="text-xs font-semibold text-purple-300 bg-purple-950/70 border border-purple-800 px-2.5 py-1 rounded-lg">
                Fixed Seed = 42
              </span>
            </div>

            {nfComparison.length === 0 ? (
              <p className="text-xs text-gray-400 py-4 text-center">Loading comparison metrics...</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-purple-950">
                <table className="w-full text-xs text-left text-gray-300">
                  <thead className="bg-[#0e1622] text-gray-400 font-bold uppercase text-[10px] border-b border-purple-900/40">
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
                  <tbody className="divide-y divide-purple-950/60">
                    {nfComparison.map((row, idx) => (
                      <tr
                        key={idx}
                        className={row.Model.includes("Neuro-Fuzzy") ? "bg-purple-950/40 font-semibold text-purple-200" : "hover:bg-[#182334]"}
                      >
                        <td className="py-2.5 px-3 font-bold text-white flex items-center gap-1.5">
                          {row.Model.includes("Neuro-Fuzzy") && <span>🧬</span>}
                          {row.Model}
                        </td>
                        <td className="py-2.5 px-2 font-mono">{Number(row["ROC-AUC"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-mono">{Number(row["PR-AUC"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-mono">{Number(row["Precision"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-mono">{Number(row["Recall"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-bold font-mono text-purple-300">{Number(row["F1-Score"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-mono">{Number(row["Brier Score"]).toFixed(4)}</td>
                        <td className="py-2.5 px-2 font-mono text-gray-400">{Number(row["Threshold"]).toFixed(2)}</td>
                        <td className="py-2.5 px-2 font-mono text-gray-400">{Number(row["Infer Time (ms)"]).toFixed(2)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Interactive Inference Slider Controller */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-[#131d2b] rounded-2xl p-5 border border-purple-900/60 space-y-4">
              <div>
                <h4 className="font-bold text-white text-sm">Interactive Agronomic Input Vector</h4>
                <p className="text-[11px] text-gray-400">Adjust continuous environmental parameters.</p>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Rainfall:</span>
                    <span className="font-bold text-sky-400">{nfRainfall} mm</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="350"
                    step="5"
                    value={nfRainfall}
                    onChange={(e) => setNfRainfall(parseFloat(e.target.value))}
                    className="w-full accent-sky-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Temperature:</span>
                    <span className="font-bold text-amber-400">{nfTemperature} °C</span>
                  </div>
                  <input
                    type="range"
                    min="15"
                    max="45"
                    step="0.5"
                    value={nfTemperature}
                    onChange={(e) => setNfTemperature(parseFloat(e.target.value))}
                    className="w-full accent-amber-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Humidity:</span>
                    <span className="font-bold text-cyan-400">{nfHumidity}%</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="95"
                    step="1"
                    value={nfHumidity}
                    onChange={(e) => setNfHumidity(parseFloat(e.target.value))}
                    className="w-full accent-cyan-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Soil Moisture:</span>
                    <span className="font-bold text-emerald-400">{nfSoilMoisture}%</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="85"
                    step="1"
                    value={nfSoilMoisture}
                    onChange={(e) => setNfSoilMoisture(parseFloat(e.target.value))}
                    className="w-full accent-emerald-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>NDVI Flowering:</span>
                    <span className="font-bold text-emerald-400">{nfNdvi}</span>
                  </div>
                  <input
                    type="range"
                    min="0.1"
                    max="0.9"
                    step="0.02"
                    value={nfNdvi}
                    onChange={(e) => setNfNdvi(parseFloat(e.target.value))}
                    className="w-full accent-emerald-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Water Stress:</span>
                    <span className="font-bold text-rose-400">{nfWaterStress}</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="1.0"
                    step="0.05"
                    value={nfWaterStress}
                    onChange={(e) => setNfWaterStress(parseFloat(e.target.value))}
                    className="w-full accent-rose-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Pest Risk:</span>
                    <span className="font-bold text-amber-400">{nfPestRisk}</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="1.0"
                    step="0.05"
                    value={nfPestRisk}
                    onChange={(e) => setNfPestRisk(parseFloat(e.target.value))}
                    className="w-full accent-amber-500 mt-1"
                  />
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-gray-300">
                    <span>Suitability Score:</span>
                    <span className="font-bold text-blue-400">{nfSuitability}</span>
                  </div>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={nfSuitability}
                    onChange={(e) => setNfSuitability(parseFloat(e.target.value))}
                    className="w-full accent-blue-500 mt-1"
                  />
                </div>
              </div>

              <button
                onClick={handleRunNeuroFuzzyInference}
                disabled={nfPredicting}
                className="w-full py-2.5 bg-gradient-to-r from-purple-800 to-indigo-800 hover:from-purple-700 hover:to-indigo-700 text-white font-bold rounded-xl text-xs shadow-md transition"
              >
                {nfPredicting ? "Executing Neuro-Fuzzy Forward Pass..." : "⚡ Run Neuro-Fuzzy Inference"}
              </button>
            </div>

            {/* Inference Result & Rule Activation Details */}
            <div className="lg:col-span-2 space-y-4">
              {nfPredictionResult ? (
                <div className="space-y-4">
                  {/* Summary Metric Header */}
                  <div className="bg-[#142334] border border-purple-800/80 rounded-2xl p-5 flex items-center justify-between">
                    <div>
                      <span className="text-[11px] font-bold text-purple-300 uppercase block">
                        Continuous Sugeno Output
                      </span>
                      <p className="text-3xl font-black text-white mt-1">
                        {(nfPredictionResult.risk_score * 100).toFixed(1)}%
                      </p>
                      <span className="text-xs text-gray-400">
                        Classification: {nfPredictionResult.failure_predicted ? "Crop Failure Predicted" : "Normal Crop Cycle"}
                      </span>
                    </div>
                    <span
                      className={`text-xs font-black uppercase px-3 py-1 rounded-full border ${
                        nfPredictionResult.risk_band === "High"
                          ? "bg-rose-950 text-rose-300 border-rose-800"
                          : nfPredictionResult.risk_band === "Medium"
                          ? "bg-amber-950 text-amber-300 border-amber-800"
                          : "bg-emerald-950 text-emerald-300 border-emerald-800"
                      }`}
                    >
                      {nfPredictionResult.risk_band} Risk
                    </span>
                  </div>

                  {/* Dominant Activated Rule */}
                  <div className="bg-[#181d2e] p-4 rounded-xl border border-purple-700/60 text-xs">
                    <span className="font-bold text-purple-300 uppercase block">
                      Dominant Rule: {nfPredictionResult.dominant_rule.rule_name}
                    </span>
                    <p className="text-gray-200 mt-1">{nfPredictionResult.dominant_rule.description}</p>
                    <div className="flex gap-4 mt-2 text-[11px] text-gray-400">
                      <span>Firing Strength: <strong>{(nfPredictionResult.dominant_rule.firing_strength * 100).toFixed(1)}%</strong></span>
                      <span>Consequent Value: <strong>{nfPredictionResult.dominant_rule.consequent_score.toFixed(3)}</strong></span>
                      <span>Total Contribution: <strong>{nfPredictionResult.dominant_rule.rule_contribution.toFixed(3)}</strong></span>
                    </div>
                  </div>

                  {/* All Activated Rules */}
                  <div className="space-y-2">
                    <h5 className="text-xs font-bold text-gray-300 uppercase tracking-wider">
                      Fuzzy Rule Base Activations (Weighted Averaging)
                    </h5>
                    {nfPredictionResult.activated_rules.map((rule) => (
                      <div key={rule.rule_index} className="p-3 bg-[#131d2b] border border-purple-950 rounded-xl text-xs space-y-1">
                        <div className="flex justify-between items-center">
                          <span className="font-bold text-white">{rule.rule_name}</span>
                          <span className="font-mono text-purple-300 font-bold">
                            Weight: {(rule.normalized_weight * 100).toFixed(1)}%
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-400">{rule.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-12 bg-[#131d2b] rounded-2xl border border-dashed border-purple-900/60 text-center">
                  <span className="text-4xl mb-2">⚡</span>
                  <h4 className="font-bold text-white text-sm">Ready for Neuro-Fuzzy Inference</h4>
                  <p className="text-xs text-gray-400 max-w-sm mt-1">
                    Adjust environmental sliders on the left and click &quot;Run Neuro-Fuzzy Inference&quot; to inspect rule firing strengths and linear consequents.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 3. SHAP EXPLAINABILITY SUBTAB                                  */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "shap" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <span>🧠</span> TreeExplainer SHAP Feature Attribution
              </h3>
              <p className="text-xs text-gray-400">
                Rigorous game-theoretic Shapley value attributions for production tree models (Random Forest / Gradient Boosting).
              </p>
            </div>
            <button
              onClick={handleRunShap}
              disabled={shapLoading}
              className="px-4 py-2 bg-sky-900 hover:bg-sky-800 text-white font-bold rounded-xl text-xs border border-sky-600 transition"
            >
              {shapLoading ? "Calculating Attributions..." : "🧠 Calculate SHAP for Pune (Soybean)"}
            </button>
          </div>

          {shapResult ? (
            <div className="space-y-4">
              <div className="p-4 bg-[#142334] border border-sky-800/80 rounded-2xl text-xs text-sky-200">
                <strong>Agronomic Attribution Summary:</strong> {shapResult.summary}
              </div>

              <div className="space-y-2">
                {shapResult.top_features.map((feat) => (
                  <div
                    key={feat.feature}
                    className="flex items-center justify-between p-3.5 bg-[#131f2b] border border-sky-950 rounded-xl text-xs"
                  >
                    <div>
                      <span className="font-bold text-white">{feat.display_name}</span>
                      <span className="text-gray-400 ml-2 font-mono text-[10px]">({feat.feature})</span>
                    </div>
                    <span
                      className={`font-mono font-bold px-2.5 py-1 rounded ${
                        feat.direction === "increases_risk"
                          ? "bg-rose-950 text-rose-300 border border-rose-800"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                      }`}
                    >
                      {feat.impact > 0 ? `+${feat.impact.toFixed(3)}` : feat.impact.toFixed(3)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-12 bg-[#131d2b] border border-dashed border-sky-900/60 rounded-2xl text-center">
              <span className="text-4xl block mb-2">🧠</span>
              <p className="font-bold text-white text-sm">Ready to Generate SHAP Explanations</p>
              <p className="text-xs text-gray-400 max-w-sm mx-auto mt-1">
                Click &quot;Calculate SHAP&quot; above to decompose model log-odds into baseline and additive marginal feature contributions.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 4. SCENARIO TWIN SUBTAB                                        */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "twin" && (
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>🔬</span> Digital Twin Scenario Simulator
            </h3>
            <p className="text-xs text-gray-400">
              Simulate extreme micro-climate anomalies and examine simulated shifts in failure probability.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-[#131d2b] p-5 rounded-2xl border border-sky-900/60">
            <div>
              <label className="text-xs text-gray-300 font-bold block mb-1">Temperature Delta (°C)</label>
              <input
                type="number"
                step="0.5"
                value={tempDelta}
                onChange={(e) => setTempDelta(parseFloat(e.target.value))}
                className="w-full bg-[#1b2b3a] border border-sky-800 rounded-lg p-2 text-xs text-white"
              />
            </div>
            <div>
              <label className="text-xs text-gray-300 font-bold block mb-1">Rainfall Delta (%)</label>
              <input
                type="number"
                step="5"
                value={rainDeltaPct}
                onChange={(e) => setRainDeltaPct(parseFloat(e.target.value))}
                className="w-full bg-[#1b2b3a] border border-sky-800 rounded-lg p-2 text-xs text-white"
              />
            </div>
            <div className="sm:col-span-2">
              <button
                onClick={handleRunTwin}
                disabled={twinLoading}
                className="w-full py-2.5 bg-blue-900 hover:bg-blue-800 text-white font-bold rounded-xl text-xs transition shadow-md"
              >
                {twinLoading ? "Simulating Scenario..." : "⚡ Execute Digital Twin Simulation"}
              </button>
            </div>
          </div>

          {twinResult && (
            <div className="bg-[#142334] border border-sky-800 rounded-2xl p-5 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-sky-200 uppercase">{twinResult.scenario}</span>
                <span className="text-xl font-black text-white">{twinResult.risk_percentage} Failure Risk</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs bg-[#0f1b26] p-3 rounded-lg border border-sky-900">
                <div>
                  <span className="text-gray-400 block">Rainfall</span>
                  <span className="font-bold text-white">{twinResult.adjusted_features.Rainfall.toFixed(1)} mm</span>
                </div>
                <div>
                  <span className="text-gray-400 block">Temperature</span>
                  <span className="font-bold text-white">{twinResult.adjusted_features.Temperature.toFixed(1)} °C</span>
                </div>
                <div>
                  <span className="text-gray-400 block">Water Stress</span>
                  <span className="font-bold text-white">{twinResult.adjusted_features.WaterStress.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 5. LIVE FARM INFERENCES SUBTAB                                 */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "predictions" && (
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>📈</span> Farm-Level Live Inferences & Provenance
            </h3>
            <p className="text-xs text-gray-400">
              Inspect model inference provenance, 16-feature vector breakdown, and SHAP attribution for registered farms.
            </p>
          </div>

          <div className="bg-[#131d2b] p-4 rounded-2xl border border-sky-900/60 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-gray-300 block mb-1">Target Farm Plot</label>
                <select
                  value={selectedFarmId}
                  onChange={(e) => setSelectedFarmId(e.target.value)}
                  className="w-full bg-[#1b2b3a] border border-sky-800 text-white rounded-lg p-2 text-xs font-bold"
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
                  className="w-full py-2.5 bg-sky-900 hover:bg-sky-800 text-white font-bold rounded-xl text-xs transition shadow-md"
                >
                  {isExecutingPrediction ? "Evaluating Inference Pipeline..." : "⚡ Execute Farm Inference"}
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            {isLoadingPredictions ? (
              <p className="text-xs text-gray-400 py-6 text-center">Loading inference history...</p>
            ) : farmPredictions.length === 0 ? (
              <div className="p-8 bg-[#131d2b] rounded-2xl text-center text-xs text-gray-400 border border-sky-950">
                No inference records logged yet for this plot. Click &quot;Execute Farm Inference&quot; above.
              </div>
            ) : (
              farmPredictions.map((pred, idx) => (
                <div key={pred.prediction_id || idx} className="p-4 bg-[#131f2d] border border-sky-900/60 rounded-xl space-y-3">
                  <div className="flex justify-between items-center">
                    <div>
                      <span className="font-bold text-white text-sm">
                        {pred.crop} ({pred.season}) · {pred.district}, {pred.state}
                      </span>
                      <span className="text-[10px] text-gray-400 block font-mono">
                        Model: {pred.best_model_name} · Inferred: {new Date(pred.created_at).toLocaleString()}
                      </span>
                    </div>
                    <span className="text-lg font-black text-sky-200">{pred.risk_percentage} Risk</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 6. CLOSED-LOOP MONITORING SUBTAB                               */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "monitoring" && (
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>🔄</span> Closed-Loop Monitoring & Drift Diagnostics
            </h3>
            <p className="text-xs text-gray-400">
              Operational pipeline tracking, continuous feature freshness, and attribution shift detection.
            </p>
          </div>

          {diagnostics && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[#131d2b] p-4 rounded-2xl border border-sky-900/60">
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">Inferences</span>
                <span className="text-xl font-bold text-white">{diagnostics.total_predictions}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">Avg Live Coverage</span>
                <span className="text-xl font-bold text-emerald-400">{diagnostics.average_live_feature_coverage}%</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">SHAP Availability</span>
                <span className="text-xl font-bold text-sky-400">{diagnostics.shap_availability_rate}%</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">Stale Telemetry Rate</span>
                <span className="text-xl font-bold text-amber-400">{diagnostics.stale_telemetry_rate}%</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 7. EARLY WARNING INCIDENT RESOLUTION SUBTAB                   */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "alerts" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <span>🚨</span> Cross-Farm Early Warning System (EWS)
              </h3>
              <p className="text-xs text-gray-400">
                Observation-driven risk escalation incidents and expert action resolution trail.
              </p>
            </div>
            <button
              onClick={() => {
                if (token) {
                  setAlertsLoading(true);
                  listExpertAlerts(token)
                    .then((d) => setExpertAlerts(d))
                    .finally(() => setAlertsLoading(false));
                }
              }}
              className="px-3.5 py-1.5 bg-sky-900 hover:bg-sky-800 text-white font-bold text-xs rounded-xl"
            >
              🔄 Refresh EWS
            </button>
          </div>

          <div className="space-y-3">
            {expertAlerts.length === 0 ? (
              <div className="p-8 bg-[#131d2b] rounded-2xl text-center text-xs text-gray-400 border border-sky-950">
                No active early warning incidents detected across monitored holdings.
              </div>
            ) : (
              expertAlerts.map((alert) => (
                <div key={alert.id} className="p-4 bg-[#131f2d] border border-sky-900/60 rounded-xl space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-white text-xs">{alert.alert_type}</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 uppercase">
                      {alert.status}
                    </span>
                  </div>
                  <p className="text-xs text-gray-300">{alert.trigger_reason}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 8. MODEL EVALUATION & GROUND TRUTH SUBTAB                     */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "evaluation" && (
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>🎯</span> Model Evaluation & Ground-Truth Verification
            </h3>
            <p className="text-xs text-gray-400">
              Evaluate real-world prediction accuracy against verified post-harvest crop outcomes.
            </p>
          </div>

          {readinessError && (
            <div className="p-4 bg-sky-950/40 border border-sky-800/60 rounded-xl flex items-start gap-3 text-xs text-sky-200">
              <span className="text-base">ℹ️</span>
              <div className="space-y-1">
                <p className="font-semibold">{readinessError}</p>
                <p className="text-sky-300/80 text-[11px]">
                  Under the unified single sign-on model, all workbench views are accessible. Operational diagnostic queues and outcome verification actions remain restricted to agronomic expert accounts.
                </p>
              </div>
            </div>
          )}

          {evalReport && evalReport.metrics ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-[#131d2b] p-5 rounded-2xl border border-sky-900/60">
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">Accuracy</span>
                <span className="text-2xl font-black text-white">{evalReport.metrics.accuracy ? (evalReport.metrics.accuracy * 100).toFixed(1) : "—"}%</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">ROC-AUC</span>
                <span className="text-2xl font-black text-sky-400">{evalReport.metrics.roc_auc ? evalReport.metrics.roc_auc.toFixed(3) : "—"}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">F1-Score</span>
                <span className="text-2xl font-black text-emerald-400">{evalReport.metrics.f1_score ? evalReport.metrics.f1_score.toFixed(3) : "—"}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase font-bold block">Brier Score</span>
                <span className="text-2xl font-black text-purple-400">{evalReport.metrics.brier_score ? evalReport.metrics.brier_score.toFixed(3) : "—"}</span>
              </div>
            </div>
          ) : (
            <div className="p-8 bg-[#131d2b] rounded-2xl text-center text-xs text-gray-400 border border-sky-950">
              Insufficient ground-truth outcomes recorded for live post-harvest validation metrics.
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 9. WEATHER & SATELLITE TELEMETRY SUBTABS                      */}
      {/* ------------------------------------------------------------- */}
      {activeSubTab === "weather" && (
        <div className="p-8 bg-[#131d2b] rounded-2xl text-xs text-gray-300 border border-sky-950">
          <h4 className="font-bold text-white text-sm mb-2">⛅ Open-Meteo Weather Pipeline Diagnostics</h4>
          <p>Continuous automated weather polling for registered farm centroids with temperature, relative humidity, and precipitation.</p>
        </div>
      )}

      {activeSubTab === "satellite" && (
        <div className="p-8 bg-[#131d2b] rounded-2xl text-xs text-gray-300 border border-sky-950">
          <h4 className="font-bold text-white text-sm mb-2">🛰️ Sentinel-2 / Google Earth Engine Diagnostics</h4>
          <p>Multi-spectral canopy vegetation indices (NDVI) extracted at cadastral field polygon boundaries.</p>
        </div>
      )}
    </div>
  );
}
