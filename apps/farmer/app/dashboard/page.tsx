"use client";

import React, { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { LanguageSelector } from "@shared/components/LanguageSelector";
import { RiskBadge } from "@shared/components/RiskBadge";
import { listFarms } from "@shared/api/farms";
import { listFarmCrops } from "@shared/api/crops";
import { listFarmPredictions, predictForFarm } from "@shared/api/predictions";
import { getCurrentWeather, getForecast } from "@shared/api/weather";
import { getFarmVegetationSummary } from "@shared/api/satellite";
import { getFarmMonitoring } from "@shared/api/monitoring";
import { listFarmAlerts, acknowledgeFarmAlert, resolveFarmAlert } from "@shared/api/alerts";
import { UserLiveWeatherWidget } from "@shared/components/UserLiveWeatherWidget";
import { FarmPlotMonitoringCard } from "../components/FarmPlotMonitoringCard";
import {
  CurrentWeatherResponse,
  DailyForecastItem,
  Farm,
  FarmAlert,
  FarmCrop,
  FarmMonitoringResponse,
  FarmVegetationSummary,
  PredictionResponse,
  WeatherForecastResponse,
} from "@shared/types";
import { t, localize_value, localize_feature } from "@shared/translations";

import dynamic from "next/dynamic";
import districtMetadataRaw from "@shared/data/district_metadata.json";

// Lazy-loaded secondary dashboard components for bundle optimization
const DistrictRiskMap = dynamic(() => import("../components/DistrictRiskMap"), {
  loading: () => (
    <div className="h-96 flex items-center justify-center bg-[#131d16] border border-[#23352a] rounded-2xl text-xs text-gray-400">
      <span className="animate-pulse">🗺️ Loading Interactive District Risk Map...</span>
    </div>
  ),
  ssr: false,
});

const ExpertWorkbenchView = dynamic(() => import("../components/ExpertWorkbenchView"), {
  loading: () => (
    <div className="p-12 text-center bg-[#101b26] border border-sky-950 rounded-2xl text-xs text-sky-400">
      <span className="animate-pulse">🔬 Loading Diagnostic Expert Workbench...</span>
    </div>
  ),
  ssr: false,
});

const PredictionHistoryView = dynamic(() => import("../components/PredictionHistoryView"), {
  loading: () => (
    <div className="p-12 text-center bg-[#152119] border border-[#23352a] rounded-2xl text-xs text-emerald-400">
      <span className="animate-pulse">📜 Loading Inferred Prediction History...</span>
    </div>
  ),
  ssr: false,
});

const UserProfileView = dynamic(() => import("../components/UserProfileView"), {
  loading: () => (
    <div className="p-12 text-center bg-[#152119] border border-[#23352a] rounded-2xl text-xs text-emerald-400">
      <span className="animate-pulse">👤 Loading User Profile Settings...</span>
    </div>
  ),
  ssr: false,
});

const VoiceAssistantPanel = dynamic(
  () => import("../components/VoiceAssistantPanel").then((mod) => mod.VoiceAssistantPanel),
  { ssr: false }
);

interface DistrictRecord {
  district: string;
  state: string;
  region: string;
  year: number;
  season: string;
  crop: string;
  soil_type: string;
  irrigation_level: string;
  rainfall: number;
  temperature: number;
  humidity: number;
  soil_moisture: number;
  ndvi_flowering: number;
  water_stress: number;
  pest_risk: number;
  suitability_score: number;
  yield_index: number;
  consensus_risk: number;
  risk_level: string;
  recommended_crop: string;
  recommendation_summary: string;
  top_options: Array<{ crop: string; percentage: string }>;
}

interface ObservedRecord {
  state: string;
  district: string;
  year: number;
  production: number | null;
  yield_tonnes_per_ha: number | null;
  rainfall: number | null;
  temperature: number | null;
  observation_status: string;
  crop_data_source: string;
  weather_data_source: string;
}

interface DistrictMeta {
  district: string;
  state: string;
  has_verified: boolean;
  latitude?: number | null;
  longitude?: number | null;
  consensus_risk?: number | null;
  risk_level?: string;
  current_crop?: string;
  recommended_crop?: string;
  top_options?: string;
}

// Initial fallback records for instant initial dashboard render without 6.2 MB bundle bloat
const DEFAULT_DISTRICT_RECORD: DistrictRecord = {
  district: "Amritsar",
  state: "Punjab",
  region: "Northwest Irrigated",
  year: 2022,
  season: "Kharif",
  crop: "Rice",
  soil_type: "Loam",
  irrigation_level: "High",
  rainfall: 117.7,
  temperature: 29.8,
  humidity: 62.6,
  soil_moisture: 61.7,
  ndvi_flowering: 0.684,
  water_stress: 0.617,
  pest_risk: 0.446,
  suitability_score: 0.729,
  yield_index: 63.2,
  consensus_risk: 0.6836,
  risk_level: "Medium",
  recommended_crop: "Maize",
  recommendation_summary: "Moderate alert: monitor the field closely and prepare contingency inputs. Increase irrigation scheduling or moisture conservation practices. Better fit detected: consider Maize for this district-season profile.",
  top_options: [
    { crop: "Maize", percentage: "48.3%" },
    { crop: "Soybean", percentage: "43.7%" },
    { crop: "Cotton", percentage: "3.2%" }
  ]
};

const DEFAULT_OBSERVED_RECORD: ObservedRecord = {
  state: "Punjab",
  district: "Amritsar",
  year: 2022,
  production: 644000.0,
  yield_tonnes_per_ha: 3.5580110497237567,
  rainfall: 839.5,
  temperature: 23.18,
  observation_status: "Observed DES production + historical weather API",
  crop_data_source: "DES, Ministry of Agriculture & Farmers Welfare",
  weather_data_source: "Open-Meteo Historical Weather API"
};

const districtMetadata = districtMetadataRaw as DistrictMeta[];

// Module-level cached promise to prevent duplicate dynamic imports
let cachedGuideDataPromise: Promise<{
  records: Record<string, DistrictRecord>;
  observed: Record<string, ObservedRecord>;
}> | null = null;

function loadGuideRecordsAsync() {
  if (!cachedGuideDataPromise) {
    cachedGuideDataPromise = import("@shared/data/district_guide_data.json").then((mod) => ({
      records: ((mod as any).default?.records || (mod as any).records) as Record<string, DistrictRecord>,
      observed: ((mod as any).default?.observed || (mod as any).observed) as Record<string, ObservedRecord>,
    }));
  }
  return cachedGuideDataPromise;
}

// Controls for custom scenario simulator matching DIGITAL_TWIN_CONTROLS from dashboard_app.py
const DIGITAL_TWIN_CONTROLS = [
  { key: "Rainfall", label: "Rainfall change (mm)", min: -80, max: 80, step: 1 },
  { key: "Temperature", label: "Temperature change (°C)", min: -8, max: 8, step: 0.5 },
  { key: "Humidity", label: "Humidity change (%)", min: -30, max: 30, step: 1 },
  { key: "SoilMoisture", label: "Soil moisture change (%)", min: -30, max: 30, step: 1 },
  { key: "NDVI_Flowering", label: "Crop greenness change", min: -0.3, max: 0.3, step: 0.01 },
  { key: "WaterStress", label: "Water shortage change", min: -0.4, max: 0.4, step: 0.01 },
];

export default function UnifiedDashboard() {
  const { user, profile, token, role, isLoading: authLoading, signOut, language, setLanguage } = useAuth();
  const router = useRouter();

  // Role validation
  const isExpertAuthorized = role === "expert" || role === "admin";

  // Sidebar Controls
  const [districtScope, setDistrictScope] = useState<"all" | "verified">("all");
  const [selectedDistrict, setSelectedDistrict] = useState<string>("Amritsar");
  const [selectedYear, setSelectedYear] = useState<number>(2022);
  const [selectedSeason, setSelectedSeason] = useState<string>("Kharif");
  const [selectedCrop, setSelectedCrop] = useState<string>("Rice");
  const [showExpertTools, setShowExpertTools] = useState<boolean>(false);

  // Tabs: live, field, compare, weather, map, alerts, farms, history, expert, profile
  const [activeTab, setActiveTab] = useState<"live" | "field" | "compare" | "weather" | "map" | "alerts" | "farms" | "history" | "expert" | "profile">("field");

  // Live Prediction Tab State
  const [liveDistrict, setLiveDistrict] = useState<string>("Amritsar");
  const [liveCrop, setLiveCrop] = useState<string>("Rice");
  const [liveSeason, setLiveSeason] = useState<string>("Kharif");
  const [liveSoil, setLiveSoil] = useState<string>("Alluvial");
  const [liveIrrigation, setLiveIrrigation] = useState<string>("Medium");
  const [liveWeatherTemp, setLiveWeatherTemp] = useState<number | null>(null);
  const [liveWeatherHum, setLiveWeatherHum] = useState<number | null>(null);
  const [liveWeatherPrecip, setLiveWeatherPrecip] = useState<number | null>(null);
  const [liveWeatherSoilMoisture, setLiveWeatherSoilMoisture] = useState<number | null>(null);
  const [isFetchingWeather, setIsFetchingWeather] = useState<boolean>(false);
  const [hasRunLivePrediction, setHasRunLivePrediction] = useState<boolean>(false);
  const [livePredictionResult, setLivePredictionResult] = useState<{
    risk_probability: number;
    risk_level: "High" | "Medium" | "Low";
    recommended_crop: string;
    top_options: Array<{ crop: string; percentage: string }>;
  } | null>(null);

  // Digital Twin Simulator State
  const [simName, setSimName] = useState<string>("My field change");
  const [simRainfallDelta, setSimRainfallDelta] = useState<number>(0);
  const [simTempDelta, setSimTempDelta] = useState<number>(0);
  const [simHumidityDelta, setSimHumidityDelta] = useState<number>(0);
  const [simSoilMoistureDelta, setSimSoilMoistureDelta] = useState<number>(0);
  const [simNDVIDelta, setSimNDVIDelta] = useState<number>(0);
  const [simWaterStressDelta, setSimWaterStressDelta] = useState<number>(0);

  // Farm Telemetry State
  const [farms, setFarms] = useState<Farm[]>([]);
  const [selectedFarm, setSelectedFarm] = useState<Farm | null>(null);
  const [isFarmsLoading, setIsFarmsLoading] = useState<boolean>(true);
  const [farmsError, setFarmsError] = useState<string | null>(null);
  const [crops, setCrops] = useState<FarmCrop[]>([]);
  const [activeCrop, setActiveCrop] = useState<FarmCrop | null>(null);
  const [latestFarmPrediction, setLatestFarmPrediction] = useState<PredictionResponse | null>(null);
  const [farmWeather, setFarmWeather] = useState<CurrentWeatherResponse | null>(null);
  const [farmVegetation, setFarmVegetation] = useState<FarmVegetationSummary | null>(null);
  const [farmMonitoring, setFarmMonitoring] = useState<FarmMonitoringResponse | null>(null);
  const [farmAlerts, setFarmAlerts] = useState<FarmAlert[]>([]);
  const [isEvaluatingFarm, setIsEvaluatingFarm] = useState<boolean>(false);
  const [isAcknowledgingAlert, setIsAcknowledgingAlert] = useState<string | null>(null);
  const [isResolvingAlert, setIsResolvingAlert] = useState<string | null>(null);

  // Weather Forecasting State
  const [farmForecast, setFarmForecast] = useState<WeatherForecastResponse | null>(null);
  const [forecastHorizon, setForecastHorizon] = useState<7 | 14>(7);
  const [isFetchingForecast, setIsFetchingForecast] = useState<boolean>(false);

  // Voice Assistant Panel Visibility
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);

  // Status notifications
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Lazy-loaded district guide records & observed data
  const [guideRecords, setGuideRecords] = useState<Record<string, DistrictRecord> | null>(null);
  const [guideObserved, setGuideObserved] = useState<Record<string, ObservedRecord> | null>(null);
  const [isGuideLoading, setIsGuideLoading] = useState<boolean>(false);
  const [guideLoadError, setGuideLoadError] = useState<string | null>(null);

  // Load heavy district scenario records dynamically in background without blocking initial render
  useEffect(() => {
    let isSubscribed = true;
    setIsGuideLoading(true);
    loadGuideRecordsAsync()
      .then((data) => {
        if (isSubscribed) {
          setGuideRecords(data.records);
          setGuideObserved(data.observed);
          setIsGuideLoading(false);
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          console.warn("Failed to dynamically load district scenario guide data:", err);
          setGuideLoadError("Detailed scenario guide could not be loaded; using cached district benchmarks.");
          setIsGuideLoading(false);
        }
      });
    return () => {
      isSubscribed = false;
    };
  }, []);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);

  // Load farms when authenticated
  const refreshFarms = useCallback(async () => {
    if (!token) return;
    setIsFarmsLoading(true);
    setFarmsError(null);
    try {
      const farmList = await listFarms(token);
      setFarms(farmList);
      if (farmList.length > 0) {
        setSelectedFarm((prev) => {
          if (!prev) return farmList[0];
          const exists = farmList.find((f) => f.id === prev.id);
          return exists || farmList[0];
        });
      } else {
        setSelectedFarm(null);
      }
    } catch (e: any) {
      console.error("Error loading farms:", e);
      setFarmsError(e?.message || "Failed to load registered farms.");
    } finally {
      setIsFarmsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refreshFarms();

    const handleWindowFocus = () => {
      refreshFarms();
    };

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === "crop_ai_farms_updated") {
        refreshFarms();
      }
    };

    if (typeof window !== "undefined") {
      window.addEventListener("focus", handleWindowFocus);
      window.addEventListener("storage", handleStorageChange);
    }

    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("focus", handleWindowFocus);
        window.removeEventListener("storage", handleStorageChange);
      }
    };
  }, [refreshFarms]);

  // Load farm details when selectedFarm changes
  useEffect(() => {
    if (!token || !selectedFarm) return;
    const farmId = selectedFarm.id;

    listFarmCrops(farmId, token)
      .then((cropList) => {
        setCrops(cropList);
        setActiveCrop(cropList.find((c) => c.is_active) || cropList[0] || null);
      })
      .catch(() => setCrops([]));

    listFarmPredictions(farmId, token)
      .then((preds) => {
        if (preds && preds.length > 0) setLatestFarmPrediction(preds[0]);
        else setLatestFarmPrediction(null);
      })
      .catch(() => setLatestFarmPrediction(null));

    getCurrentWeather(farmId, token)
      .then(setFarmWeather)
      .catch(() => setFarmWeather(null));

    getFarmVegetationSummary(farmId, token)
      .then(setFarmVegetation)
      .catch(() => setFarmVegetation(null));

    getFarmMonitoring(farmId, token)
      .then(setFarmMonitoring)
      .catch(() => setFarmMonitoring(null));

    listFarmAlerts(farmId, token)
      .then(setFarmAlerts)
      .catch(() => setFarmAlerts([]));

    setIsFetchingForecast(true);
    getForecast(farmId, token, forecastHorizon)
      .then(setFarmForecast)
      .catch(() => setFarmForecast(null))
      .finally(() => setIsFetchingForecast(false));
  }, [token, selectedFarm, forecastHorizon]);


  // Filtered district list based on scope (verified vs all) using lightweight districtMetadata
  const districtOptions = useMemo(() => {
    if (districtScope === "verified") {
      return districtMetadata.filter((d) => d.has_verified);
    }
    return districtMetadata;
  }, [districtScope]);

  // Selected district meta
  const currentDistrictMeta = useMemo(() => {
    return (
      districtMetadata.find(
        (d) => d.district.toLowerCase() === selectedDistrict.toLowerCase()
      ) || districtMetadata[0]
    );
  }, [selectedDistrict]);

  // Active District Record Key with fallback to default Amritsar record while loading or if missing
  const currentDistrictRecord = useMemo<DistrictRecord>(() => {
    if (!guideRecords) {
      if (selectedDistrict.toLowerCase() === "amritsar" && selectedCrop.toLowerCase() === "rice") {
        return DEFAULT_DISTRICT_RECORD;
      }
      return {
        ...DEFAULT_DISTRICT_RECORD,
        district: selectedDistrict,
        crop: selectedCrop,
        season: selectedSeason,
        year: selectedYear,
        state: currentDistrictMeta?.state || DEFAULT_DISTRICT_RECORD.state,
      };
    }

    const key = `${selectedDistrict.toLowerCase()}_${selectedYear}_${selectedSeason.toLowerCase()}_${selectedCrop.toLowerCase()}`;
    return (
      guideRecords[key] ||
      // Fallback matching district and season
      Object.values(guideRecords).find(
        (r) =>
          r.district.toLowerCase() === selectedDistrict.toLowerCase() &&
          r.season.toLowerCase() === selectedSeason.toLowerCase()
      ) ||
      Object.values(guideRecords)[0] ||
      DEFAULT_DISTRICT_RECORD
    );
  }, [guideRecords, selectedDistrict, selectedYear, selectedSeason, selectedCrop, currentDistrictMeta]);

  // Matched observed historical record from DES
  const currentObservedRecord = useMemo<ObservedRecord | null>(() => {
    if (!guideObserved) {
      if (selectedDistrict.toLowerCase() === "amritsar" && selectedYear === 2022) {
        return DEFAULT_OBSERVED_RECORD;
      }
      return null;
    }
    const key = `${selectedDistrict.toLowerCase()}_${selectedYear}`;
    return guideObserved[key] || null;
  }, [guideObserved, selectedDistrict, selectedYear]);

  // Crop Comparison Table rows: all available crops for the selected district and season
  const comparisonCrops = useMemo<DistrictRecord[]>(() => {
    if (!guideRecords) {
      // Fallback preview crop while records are loading
      return [DEFAULT_DISTRICT_RECORD];
    }

    const prefix = `${selectedDistrict.toLowerCase()}_${selectedYear}_${selectedSeason.toLowerCase()}_`;
    const matched = Object.entries(guideRecords)
      .filter(([k]) => k.startsWith(prefix))
      .map(([_, r]) => r);

    if (matched.length === 0) {
      const fallback = Object.values(guideRecords).filter(
        (r) =>
          r.district.toLowerCase() === selectedDistrict.toLowerCase() &&
          r.season.toLowerCase() === selectedSeason.toLowerCase()
      );
      const seen = new Set<string>();
      return fallback
        .filter((r) => {
          if (seen.has(r.crop)) return false;
          seen.add(r.crop);
          return true;
        })
        .sort((a, b) => a.consensus_risk - b.consensus_risk);
    }

    return matched.sort((a, b) => a.consensus_risk - b.consensus_risk);
  }, [guideRecords, selectedDistrict, selectedYear, selectedSeason]);

  // Digital Twin Presets
  const presetScenarios = useMemo(() => {
    const baseRisk = currentDistrictRecord.consensus_risk;
    return [
      {
        name: "Baseline",
        risk: baseRisk,
        rainfall: currentDistrictRecord.rainfall,
        temp: currentDistrictRecord.temperature,
        sm: currentDistrictRecord.soil_moisture,
        notes: "Historical observed / baseline regional climate",
      },
      {
        name: "Drought Stress",
        risk: Math.min(1.0, baseRisk + 0.28),
        rainfall: Math.max(0, currentDistrictRecord.rainfall - 35),
        temp: currentDistrictRecord.temperature + 2.5,
        sm: Math.max(5, currentDistrictRecord.soil_moisture - 18),
        notes: "-35mm rain, -18% soil moisture, +2.5°C temp",
      },
      {
        name: "Heatwave",
        risk: Math.min(1.0, baseRisk + 0.19),
        rainfall: currentDistrictRecord.rainfall,
        temp: currentDistrictRecord.temperature + 4.0,
        sm: Math.max(5, currentDistrictRecord.soil_moisture - 8),
        notes: "+4.0°C temp, adverse evaporative demand",
      },
      {
        name: "Irrigation Support",
        risk: Math.max(0.02, baseRisk - 0.24),
        rainfall: currentDistrictRecord.rainfall,
        temp: currentDistrictRecord.temperature,
        sm: Math.min(100, currentDistrictRecord.soil_moisture + 14),
        notes: "+14% soil moisture, mitigating moisture deficit",
      },
    ];
  }, [currentDistrictRecord]);

  // Digital Twin Custom Interactive Scenario projection
  const customScenarioResult = useMemo(() => {
    const baseRisk = currentDistrictRecord.consensus_risk;
    const riskShift =
      simTempDelta * 0.042 -
      simRainfallDelta * 0.0028 -
      simSoilMoistureDelta * 0.0065 -
      simHumidityDelta * 0.0022 -
      simNDVIDelta * 0.25 +
      simWaterStressDelta * 0.35;

    const simulatedRisk = Math.min(0.99, Math.max(0.01, baseRisk + riskShift));
    return {
      baseRisk,
      simulatedRisk,
      deltaPts: (simulatedRisk - baseRisk) * 100,
      adjustedRainfall: Math.max(0, currentDistrictRecord.rainfall + simRainfallDelta),
      adjustedTemp: currentDistrictRecord.temperature + simTempDelta,
      adjustedHumidity: Math.max(10, Math.min(100, currentDistrictRecord.humidity + simHumidityDelta)),
      adjustedSoilMoisture: Math.max(5, Math.min(100, currentDistrictRecord.soil_moisture + simSoilMoistureDelta)),
      adjustedNDVI: Math.max(0.05, Math.min(0.95, currentDistrictRecord.ndvi_flowering + simNDVIDelta)),
      adjustedWaterStress: Math.max(0.01, Math.min(0.99, currentDistrictRecord.water_stress + simWaterStressDelta)),
    };
  }, [
    currentDistrictRecord,
    simRainfallDelta,
    simTempDelta,
    simHumidityDelta,
    simSoilMoistureDelta,
    simNDVIDelta,
    simWaterStressDelta,
  ]);

  // Fetch live weather for live tab
  useEffect(() => {
    if (activeTab === "live" && currentDistrictMeta.latitude && currentDistrictMeta.longitude) {
      setIsFetchingWeather(true);
      fetch(
        `https://api.open-meteo.com/v1/forecast?latitude=${currentDistrictMeta.latitude}&longitude=${currentDistrictMeta.longitude}&current=temperature_2m,relative_humidity_2m,precipitation,soil_moisture_0_to_1cm&timezone=Asia%2FKolkata`
      )
        .then((res) => res.json())
        .then((data) => {
          if (data && data.current) {
            setLiveWeatherTemp(data.current.temperature_2m);
            setLiveWeatherHum(data.current.relative_humidity_2m);
            setLiveWeatherPrecip(data.current.precipitation);
            setLiveWeatherSoilMoisture(
              data.current.soil_moisture_0_to_1cm !== undefined
                ? Math.round(data.current.soil_moisture_0_to_1cm * 100)
                : 38
            );
          }
        })
        .catch(() => {
          setLiveWeatherTemp(currentDistrictRecord.temperature);
          setLiveWeatherHum(currentDistrictRecord.humidity);
          setLiveWeatherPrecip(0);
          setLiveWeatherSoilMoisture(currentDistrictRecord.soil_moisture);
        })
        .finally(() => setIsFetchingWeather(false));
    }
  }, [activeTab, currentDistrictMeta, currentDistrictRecord]);

  // Execute Live Case Prediction
  const handleRunLivePrediction = () => {
    setHasRunLivePrediction(true);
    const risk = currentDistrictRecord.consensus_risk;
    const level = currentDistrictRecord.risk_level as "High" | "Medium" | "Low";
    setLivePredictionResult({
      risk_probability: risk,
      risk_level: level,
      recommended_crop: currentDistrictRecord.recommended_crop,
      top_options: currentDistrictRecord.top_options,
    });
  };

  // Farm live evaluation trigger
  const handleEvaluateFarmRisk = async () => {
    if (!selectedFarm || !token) return;
    setIsEvaluatingFarm(true);
    setStatusNotice(null);
    try {
      const pred = await predictForFarm(selectedFarm.id, {}, token);
      setLatestFarmPrediction(pred);
      setStatusNotice("Live farm risk evaluated using real-time Open-Meteo weather and crop phenology.");

      const [mon, alerts] = await Promise.all([
        getFarmMonitoring(selectedFarm.id, token).catch(() => null),
        listFarmAlerts(selectedFarm.id, token).catch(() => []),
      ]);
      if (mon) setFarmMonitoring(mon);
      setFarmAlerts(alerts);
    } catch (err: any) {
      const isMissingCrop = !activeCrop || (err.message && err.message.toLowerCase().includes("crop"));
      if (isMissingCrop) {
        setStatusNotice(
          "Live Risk Assessment failed: Please register an active crop cycle for this farm before running an assessment."
        );
      } else {
        setStatusNotice(`Live Risk Assessment failed: ${err.message}`);
      }
    } finally {
      setIsEvaluatingFarm(false);
    }
  };

  // Acknowledge Alert (Farmer & Expert)
  const handleAcknowledgeAlert = async (alertId: string) => {
    if (!token || !selectedFarm) return;
    setIsAcknowledgingAlert(alertId);
    try {
      const updated = await acknowledgeFarmAlert(selectedFarm.id, alertId, token);
      setFarmAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId ? { ...a, status: "acknowledged", acknowledged_at: updated.acknowledged_at } : a
        )
      );
      setStatusNotice("Early warning advisory acknowledged.");
    } catch (err: any) {
      setStatusNotice(`Alert update error: ${err.message}`);
    } finally {
      setIsAcknowledgingAlert(null);
    }
  };

  // Resolve Alert (Authorized Expert & Admin)
  const handleResolveAlert = async (alertId: string, resolutionNotes?: string) => {
    if (!token || !selectedFarm) return;
    if (!isExpertAuthorized) {
      setStatusNotice("Permission denied: Only agricultural experts and administrators can resolve early warning alerts.");
      return;
    }
    setIsResolvingAlert(alertId);
    try {
      const updated = await resolveFarmAlert(selectedFarm.id, alertId, token, resolutionNotes || "Resolved by agricultural expert via Crop Safety Guide");
      setFarmAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId ? { ...a, status: "resolved", resolved_at: updated.resolved_at, resolution_notes: updated.resolution_notes } : a
        )
      );
      setStatusNotice("Early warning alert resolved by expert.");
    } catch (err: any) {
      setStatusNotice(`Alert resolution error: ${err.message}`);
    } finally {
      setIsResolvingAlert(null);
    }
  };


  if (authLoading || (!user && !statusNotice)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#121815] text-white">
        <div className="text-center space-y-3">
          <div className="text-4xl animate-bounce">🌾</div>
          <p className="text-emerald-400 font-semibold tracking-wide">Loading Crop Safety Guide...</p>
        </div>
      </div>
    );
  }

  // Formatting helpers matching dashboard_app.py
  const riskColor =
    currentDistrictRecord.risk_level === "High"
      ? "#c53030"
      : currentDistrictRecord.risk_level === "Medium"
      ? "#dd6b20"
      : "#2f855a";

  const farmerAdviceList = [
    currentDistrictRecord.risk_level === "High"
      ? t("advice_high", language)
      : currentDistrictRecord.risk_level === "Medium"
      ? t("advice_medium", language)
      : t("advice_low", language),
  ];
  if (currentDistrictRecord.water_stress >= 0.55 || currentDistrictRecord.soil_moisture < 35) {
    farmerAdviceList.push(t("advice_water", language));
  }
  if (currentDistrictRecord.pest_risk >= 0.55) {
    farmerAdviceList.push(t("advice_pest", language));
  }
  if (currentDistrictRecord.recommended_crop !== currentDistrictRecord.crop) {
    farmerAdviceList.push(`For the next planting decision, ${currentDistrictRecord.recommended_crop} may be a better fit.`);
  }

  return (
    <div className="min-h-screen bg-[#121815] text-gray-100 flex flex-col md:flex-row antialiased font-sans">
      {/* ------------------------------------------------------------- */}
      {/* 1. RESTORE ORIGINAL LEFT SIDEBAR                               */}
      {/* ------------------------------------------------------------- */}
      <aside className="w-full md:w-80 bg-[#111914] border-r border-[#294332] flex flex-col p-4 md:p-5 space-y-5 shrink-0 md:min-h-screen">
        {/* Top: Language & Session */}
        <div className="flex items-center justify-between border-b border-[#1f2d25] pb-3">
          <div className="space-y-0.5">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              {t("language", language)}
            </span>
            <LanguageSelector />
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
              {role}
            </span>
            <button
              onClick={() => signOut()}
              className="block text-[11px] text-gray-400 hover:text-white underline mt-1"
            >
              {t("sign_out", language)}
            </button>
          </div>
        </div>

        {/* Top-Left User Profile Quick Access */}
        <div className="bg-[#15231a] border border-[#243d2e] rounded-xl p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="w-7 h-7 rounded-full bg-emerald-900 border border-emerald-500/80 flex items-center justify-center text-xs text-white shrink-0">
              {role === "expert" ? "🔬" : "👨‍🌾"}
            </div>
            <div className="truncate">
              <span className="block text-xs font-bold text-white truncate">
                {profile?.full_name || user?.email?.split("@")[0] || "My Account"}
              </span>
              <span className="block text-[10px] text-gray-400 truncate">
                {user?.email || "Authenticated User"}
              </span>
            </div>
          </div>
          <button
            onClick={() => setActiveTab("profile")}
            className={`px-2 py-1 rounded text-[11px] font-bold transition shrink-0 ${
              activeTab === "profile"
                ? "bg-emerald-700 text-white"
                : "bg-[#1c3024] hover:bg-[#254231] text-emerald-300 border border-[#2d4d38]"
            }`}
          >
            {language === "hi" ? "प्रोफ़ाइल" : "Profile"}
          </button>
        </div>

        {/* Header: Choose your field */}
        <div className="space-y-1">
          <h2 className="text-base font-bold text-white tracking-tight">
            {t("choose_field", language)}
          </h2>
          <p className="text-xs text-gray-400">
            {t("choose_caption", language)}
          </p>
        </div>

        {/* District Data Scope Radio */}
        <div className="space-y-1.5">
          <label className="text-xs text-gray-400 font-semibold">{t("district_data", language)}</label>
          <div className="bg-[#18231c] p-1.5 rounded-lg border border-[#42664b] flex text-xs">
            <button
              onClick={() => setDistrictScope("all")}
              className={`flex-1 py-1.5 rounded text-center font-medium transition ${
                districtScope === "all"
                  ? "bg-emerald-800 text-white font-bold shadow-sm"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {t("all_districts", language)}
            </button>
            <button
              onClick={() => setDistrictScope("verified")}
              className={`flex-1 py-1.5 rounded text-center font-medium transition ${
                districtScope === "verified"
                  ? "bg-emerald-800 text-white font-bold shadow-sm"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {t("verified_districts", language)}
            </button>
          </div>
          <p className="text-[10px] text-gray-500">
            {districtOptions.length} {t("districts_available_caption", language)}
          </p>
        </div>

        {/* District Selector */}
        <div className="space-y-1">
          <label htmlFor="sb-district" className="text-xs text-gray-300 font-medium">
            {t("district", language)}
          </label>
          <select
            id="sb-district"
            value={selectedDistrict}
            onChange={(e) => {
              setSelectedDistrict(e.target.value);
              setLiveDistrict(e.target.value);
            }}
            className="w-full bg-[#18231c] border border-[#42664b] text-white text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-emerald-500"
          >
            {districtOptions.map((d) => (
              <option key={d.district} value={d.district}>
                {d.district} ({d.state}) {d.has_verified ? "★" : ""}
              </option>
            ))}
          </select>
        </div>

        {/* Year Selector */}
        <div className="space-y-1">
          <label htmlFor="sb-year" className="text-xs text-gray-300 font-medium">
            {t("year", language)}
          </label>
          <select
            id="sb-year"
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="w-full bg-[#18231c] border border-[#42664b] text-white text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-emerald-500"
          >
            {[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018].map((yr) => (
              <option key={yr} value={yr}>
                {yr}
              </option>
            ))}
          </select>
        </div>

        {/* Season Selector */}
        <div className="space-y-1">
          <label htmlFor="sb-season" className="text-xs text-gray-300 font-medium">
            {t("season", language)}
          </label>
          <select
            id="sb-season"
            value={selectedSeason}
            onChange={(e) => {
              setSelectedSeason(e.target.value);
              setLiveSeason(e.target.value);
            }}
            className="w-full bg-[#18231c] border border-[#42664b] text-white text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-emerald-500"
          >
            {["Kharif", "Rabi", "Zaid"].map((sz) => (
              <option key={sz} value={sz}>
                {localize_value(sz, language)} ({sz})
              </option>
            ))}
          </select>
        </div>

        {/* Crop Selector */}
        <div className="space-y-1">
          <label htmlFor="sb-crop" className="text-xs text-gray-300 font-medium">
            {t("crop", language)}
          </label>
          <select
            id="sb-crop"
            value={selectedCrop}
            onChange={(e) => {
              setSelectedCrop(e.target.value);
              setLiveCrop(e.target.value);
            }}
            className="w-full bg-[#18231c] border border-[#42664b] text-white text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-emerald-500"
          >
            {[
              "Chickpea",
              "Cotton",
              "Groundnut",
              "Maize",
              "Millet",
              "Mustard",
              "Rice",
              "Soybean",
              "Wheat",
            ].map((cr) => (
              <option key={cr} value={cr}>
                {localize_value(cr, language)} ({cr})
              </option>
            ))}
          </select>
        </div>

        {/* Agriculture Experts Workbench Section */}
        <div className="pt-3 border-t border-[#294332] space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-200">
              {t("expert_heading", language)}
            </h3>
            <span className="text-[10px] text-sky-400 font-mono">V2 Diagnostics</span>
          </div>
          <p className="text-[11px] text-gray-400 leading-snug">
            {t("expert_caption", language)}
          </p>

          {/* Expert Workbench Navigation Button */}
          <button
            onClick={() => setActiveTab("expert")}
            className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition shadow ${
              activeTab === "expert"
                ? "bg-sky-900 border border-sky-400 text-white ring-1 ring-sky-500"
                : "bg-gradient-to-r from-[#122330] to-[#152735] hover:from-[#172c3d] hover:to-[#1a3244] border border-sky-800 text-sky-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="text-sm">🔬</span>
              <span>{t("open_expert_workbench", language)}</span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-sky-950 text-sky-300 border border-sky-700">
              {role === "expert" ? "Expert" : "Full Access"}
            </span>
          </button>
        </div>

        {/* AI Crop Assistant Button */}
        <div className="pt-2 border-t border-[#294332]">
          <button
            onClick={() => setIsAssistantOpen(true)}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-3 bg-gradient-to-r from-emerald-800 to-teal-800 hover:from-emerald-700 hover:to-teal-700 border border-emerald-500/40 text-white rounded-xl text-xs font-bold transition shadow-lg"
          >
            <span className="text-sm">🎙️</span>
            <span>{t("ask_crop_assistant", language)}</span>
          </button>
        </div>

        {/* Plot and Farm Management Entry */}
        <div className="pt-2 border-t border-[#294332] flex flex-col gap-2">
          <button
            onClick={() => setActiveTab("farms")}
            className={`w-full py-2 px-3 text-left rounded-lg text-xs font-semibold flex items-center justify-between border transition ${
              activeTab === "farms"
                ? "bg-emerald-900/60 border-emerald-500 text-white"
                : "bg-[#14231a] border-[#243d2e] text-emerald-300 hover:bg-[#1b3124]"
            }`}
          >
            <span>🚜 {t("farm_monitoring_title", language)}</span>
            <span className="text-[10px] bg-emerald-950 px-1.5 py-0.5 rounded text-emerald-400">
              {farms.length}
            </span>
          </button>
        </div>

        {/* Footer info */}
        <div className="mt-auto pt-3 border-t border-[#294332] text-[10px] text-gray-500">
          Reducing Crop Failure Using AI · 16-feature ML with Open-Meteo & Sentinel-2.
        </div>
      </aside>

      {/* ------------------------------------------------------------- */}
      {/* 2. MAIN DASHBOARD CONTENT AREA                                 */}
      {/* ------------------------------------------------------------- */}
      <main className="flex-1 bg-[#121815] p-4 md:p-8 overflow-y-auto max-w-7xl mx-auto space-y-6">
        {/* Status Notice */}
        {statusNotice && (
          <div className="bg-[#183d27] border border-[#55b879] text-[#f2fff5] px-4 py-2.5 rounded-xl text-xs flex items-center justify-between shadow">
            <span>ℹ️ {statusNotice}</span>
            <button onClick={() => setStatusNotice(null)} className="font-bold ml-3 text-emerald-300">
              ✕
            </button>
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* ORIGINAL HEADER: Heading & Subtitle                         */}
        {/* ----------------------------------------------------------- */}
        <div>
          <h1 className="text-3xl font-black text-white tracking-tight">
            {t("app_title", language)}
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            {t("app_caption", language)}
          </p>
        </div>

        {/* ----------------------------------------------------------- */}
        {/* AUTOMATIC USER LOCATION & LIVE WEATHER WIDGET               */}
        {/* ----------------------------------------------------------- */}
        <UserLiveWeatherWidget />

        {/* ----------------------------------------------------------- */}
        {/* ORIGINAL HERO: Two columns (hero_left [1.35], hero_right [1])*/}
        {/* ----------------------------------------------------------- */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: District, Badge, Risk, Farmer-Note, Metrics, Observed */}
          <div className="lg:col-span-7 space-y-4">
            {/* Selected district, state, season and year */}
            <h2 className="text-xl font-bold text-white tracking-tight">
              {selectedDistrict}, {currentDistrictRecord.state} | {selectedSeason} {selectedYear}
            </h2>

            {/* Verified historical weather and DES data indicator */}
            {currentObservedRecord ? (
              <div>
                <span className="data-badge verified-badge">
                  {t("verified_badge_text", language)}
                </span>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {t("verified_badge_desc", language)}
                </p>
              </div>
            ) : (
              <div>
                <span className="data-badge modelled-badge">
                  {t("modelled_badge_text", language)}
                </span>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {t("modelled_badge_desc", language)}
                </p>
              </div>
            )}

            {/* Soil and Irrigation subtitle */}
            <p className="text-xs text-gray-300">
              {t("soil_label", language)}: <strong className="text-white">{localize_value(currentDistrictRecord.soil_type, language)}</strong> · {t("irrigation_label", language)}: <strong className="text-white">{localize_value(currentDistrictRecord.irrigation_level, language)}</strong>
            </p>

            {/* Primary crop-failure risk percentage and styled badge */}
            <div className="flex items-center gap-3">
              <div
                style={{ backgroundColor: riskColor }}
                className="px-3.5 py-1.5 rounded-full text-white font-bold text-sm shadow-sm inline-block"
              >
                {currentDistrictRecord.risk_level === "High"
                  ? t("high_risk", language)
                  : currentDistrictRecord.risk_level === "Medium"
                  ? t("medium_risk", language)
                  : t("low_risk", language)}
              </div>
            </div>

            {/* Green "What this means" advisory panel (.farmer-note style) */}
            <div className="farmer-note">
              <strong>{t("what_means", language)}</strong> {farmerAdviceList.join(" ")}
            </div>

            {/* Compact Metric Summary Row (4 columns) */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-[#18231c] border border-[#2b4434] rounded-xl p-3">
                <p className="text-[10px] text-gray-400 uppercase font-semibold">{t("crop_risk", language)}</p>
                <p className="text-xl font-black text-white mt-1">
                  {(currentDistrictRecord.consensus_risk * 100).toFixed(1)}%
                </p>
              </div>
              <div className="bg-[#18231c] border border-[#2b4434] rounded-xl p-3">
                <p className="text-[10px] text-gray-400 uppercase font-semibold">{t("your_crop", language)}</p>
                <p className="text-base font-bold text-white mt-1 truncate">
                  {localize_value(currentDistrictRecord.crop, language)}
                </p>
              </div>
              <div className="bg-[#18231c] border border-[#2b4434] rounded-xl p-3">
                <p className="text-[10px] text-gray-400 uppercase font-semibold">{t("better_crop_option", language)}</p>
                <p className="text-base font-bold text-emerald-400 mt-1 truncate">
                  {localize_value(currentDistrictRecord.recommended_crop, language)}
                </p>
              </div>
              <div className="bg-[#18231c] border border-[#2b4434] rounded-xl p-3">
                <p className="text-[10px] text-gray-400 uppercase font-semibold">{t("expected_yield_index", language)}</p>
                <p className="text-xl font-black text-white mt-1">
                  {currentDistrictRecord.yield_index.toFixed(1)}
                </p>
              </div>
            </div>

            {/* Verified Historical Record Metrics below (when available) */}
            {currentObservedRecord && (
              <div className="bg-[#15231a] border border-[#294332] rounded-xl p-4 space-y-3">
                <p className="text-xs font-bold text-white">{t("verified_historical_record", language)}</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <p className="text-gray-400 text-[10px]">{t("des_production", language)}</p>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {currentObservedRecord.production !== null
                        ? `${currentObservedRecord.production.toLocaleString()} MT`
                        : "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-[10px]">{t("des_yield", language)}</p>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {currentObservedRecord.yield_tonnes_per_ha !== null
                        ? currentObservedRecord.yield_tonnes_per_ha.toFixed(2)
                        : "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-[10px]">{t("observed_rainfall", language)}</p>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {currentObservedRecord.rainfall !== null
                        ? `${currentObservedRecord.rainfall.toFixed(0)} mm`
                        : "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-[10px]">{t("observed_temperature", language)}</p>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {currentObservedRecord.temperature !== null
                        ? `${currentObservedRecord.temperature.toFixed(1)} °C`
                        : "N/A"}
                    </p>
                  </div>
                </div>
                <p className="text-[10px] text-gray-500">
                  {t("weather_centroid_desc", language)}
                </p>
              </div>
            )}
          </div>

          {/* Right Column: Safer Crop Options Table beside main risk section */}
          <div className="lg:col-span-5 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-4">
            <div>
              <h3 className="font-bold text-white text-base">
                {t("safer_options", language)}
              </h3>
              <p className="text-xs text-gray-400 mt-1">
                {t("safer_options_caption", language)}
              </p>
            </div>

            {/* Table */}
            <div className="overflow-x-auto rounded-xl border border-[#2b3e32]">
              <table className="w-full text-left text-xs text-gray-300">
                <thead className="bg-[#121c16] text-gray-400 uppercase text-[10px] border-b border-[#2b3e32]">
                  <tr>
                    <th className="py-2.5 px-3">{t("crop", language)}</th>
                    <th className="py-2.5 px-3">{t("crop_risk", language)}</th>
                    <th className="py-2.5 px-3">{t("risk_level", language)}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#23352a]">
                  {comparisonCrops.slice(0, 4).map((c) => (
                    <tr key={c.crop} className="hover:bg-[#1a2b21] transition">
                      <td className="py-2.5 px-3 font-bold text-white flex items-center gap-1.5">
                        <span>{localize_value(c.crop, language)}</span>
                        {c.crop === currentDistrictRecord.recommended_crop && (
                          <span className="text-[10px] text-amber-400">⭐</span>
                        )}
                        {c.crop.toLowerCase() === selectedCrop.toLowerCase() && (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                            {t("your_crop", language)}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 font-mono font-semibold">
                        {(c.consensus_risk * 100).toFixed(1)}%
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            c.risk_level === "High"
                              ? "bg-rose-950 text-rose-300 border border-rose-800"
                              : c.risk_level === "Medium"
                              ? "bg-amber-950 text-amber-300 border border-amber-800"
                              : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          }`}
                        >
                          {c.risk_level === "High"
                            ? t("high_risk", language)
                            : c.risk_level === "Medium"
                            ? t("medium_risk", language)
                            : t("low_risk", language)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pt-2 flex justify-between items-center text-xs">
              <button
                onClick={() => setActiveTab("compare")}
                className="text-emerald-400 hover:text-emerald-300 font-bold underline"
              >
                {t("view_full_crop_table", language)}
              </button>
              <button
                onClick={() => setActiveTab("map")}
                className="text-gray-400 hover:text-white"
              >
                {t("view_on_district_map", language)}
              </button>
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------- */}
        {/* 3. ORIGINAL NAVIGATION TABS                                  */}
        {/* ----------------------------------------------------------- */}
        <div className="border-t border-[#1f2d25] pt-4">
          <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-[#1f2d25]">
            <button
              onClick={() => setActiveTab("live")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "live"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>🔮</span>
              <span>{t("tab_live", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("field")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "field"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>🌱</span>
              <span>{t("tab_field", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("compare")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "compare"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>⚖️</span>
              <span>{t("tab_compare", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("weather")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "weather"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>⛅</span>
              <span>{t("tab_weather", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("map")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "map"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>🗺️</span>
              <span>{t("tab_map", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("alerts")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "alerts"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>🚨</span>
              <span>{t("tab_alerts", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("farms")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "farms"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>🚜</span>
              <span>{t("tab_farms", language)}</span>
            </button>

            <button
              onClick={() => setActiveTab("history")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
                activeTab === "history"
                  ? "bg-[#1f3b2b] text-white border border-emerald-500/60 shadow-sm"
                  : "bg-[#152119] text-gray-400 hover:text-white hover:bg-[#1a2b20]"
              }`}
            >
              <span>📜</span>
              <span>{language === "hi" ? "पूर्वानुमान इतिहास" : "Prediction History"}</span>
            </button>
          </div>
        </div>

        {/* ----------------------------------------------------------- */}
        {/* TAB 1: 🔮 LIVE CROP RISK PREDICTION                         */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "live" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-black text-white tracking-tight">
                {t("live_prediction_heading", language)}
              </h2>
              <p className="text-xs text-gray-400 mt-1">
                {t("live_prediction_caption", language)}
              </p>
            </div>

            {/* Field Selection Row */}
            <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-4">
              <h3 className="font-bold text-white text-sm">{t("choose_field", language)}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-gray-400">{t("state", language)}</label>
                  <p className="font-bold text-white text-sm mt-0.5">{currentDistrictRecord.state}</p>
                </div>
                <div>
                  <label className="text-xs text-gray-400">{t("district", language)}</label>
                  <select
                    value={liveDistrict}
                    onChange={(e) => {
                      setLiveDistrict(e.target.value);
                      setSelectedDistrict(e.target.value);
                    }}
                    className="w-full bg-[#121c16] border border-[#2b4434] text-white text-xs rounded-lg px-2.5 py-1.5 mt-0.5"
                  >
                    {districtOptions.map((d) => (
                      <option key={d.district} value={d.district}>
                        {d.district}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400">{t("crop", language)}</label>
                  <select
                    value={liveCrop}
                    onChange={(e) => {
                      setLiveCrop(e.target.value);
                      setSelectedCrop(e.target.value);
                    }}
                    className="w-full bg-[#121c16] border border-[#2b4434] text-white text-xs rounded-lg px-2.5 py-1.5 mt-0.5"
                  >
                    {[
                      "Chickpea",
                      "Cotton",
                      "Groundnut",
                      "Maize",
                      "Millet",
                      "Mustard",
                      "Rice",
                      "Soybean",
                      "Wheat",
                    ].map((cr) => (
                      <option key={cr} value={cr}>
                        {localize_value(cr, language)} ({cr})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-[#23352a]">
                <div>
                  <label className="text-xs text-gray-400">{t("season", language)}</label>
                  <select
                    value={liveSeason}
                    onChange={(e) => {
                      setLiveSeason(e.target.value);
                      setSelectedSeason(e.target.value);
                    }}
                    className="w-full bg-[#121c16] border border-[#2b4434] text-white text-xs rounded-lg px-2.5 py-1.5 mt-0.5"
                  >
                    {["Kharif", "Rabi", "Zaid"].map((s) => (
                      <option key={s} value={s}>
                        {localize_value(s, language)} ({s})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400">{t("soil_type", language)}</label>
                  <select
                    value={liveSoil}
                    onChange={(e) => setLiveSoil(e.target.value)}
                    className="w-full bg-[#121c16] border border-[#2b4434] text-white text-xs rounded-lg px-2.5 py-1.5 mt-0.5"
                  >
                    {[
                      "Alluvial",
                      "Black",
                      "Clay Loam",
                      "Laterite",
                      "Loam",
                      "Medium Black",
                      "Red Loam",
                      "Sandy Loam",
                    ].map((st) => (
                      <option key={st} value={st}>
                        {localize_value(st, language)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400">{t("irrigation_level", language)}</label>
                  <select
                    value={liveIrrigation}
                    onChange={(e) => setLiveIrrigation(e.target.value)}
                    className="w-full bg-[#121c16] border border-[#2b4434] text-white text-xs rounded-lg px-2.5 py-1.5 mt-0.5"
                  >
                    {["Low", "Medium", "High"].map((ir) => (
                      <option key={ir} value={ir}>
                        {localize_value(ir, language)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Live Weather Section */}
            <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-white text-sm">{t("live_weather", language)}</h3>
                <span className="text-[10px] text-emerald-400 font-semibold bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  {t("source_open_meteo", language)}
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                  <p className="text-gray-400 text-[10px]">{t("temperature", language)}</p>
                  <p className="text-lg font-bold text-white mt-0.5">
                    {liveWeatherTemp !== null ? `${liveWeatherTemp} °C` : "..."}
                  </p>
                </div>
                <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                  <p className="text-gray-400 text-[10px]">{t("humidity", language)}</p>
                  <p className="text-lg font-bold text-white mt-0.5">
                    {liveWeatherHum !== null ? `${liveWeatherHum} %` : "..."}
                  </p>
                </div>
                <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                  <p className="text-gray-400 text-[10px]">{t("rainfall", language)}</p>
                  <p className="text-lg font-bold text-white mt-0.5">
                    {liveWeatherPrecip !== null ? `${liveWeatherPrecip} mm` : "0.0 mm"}
                  </p>
                </div>
                <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                  <p className="text-gray-400 text-[10px]">{t("soil_moisture", language)}</p>
                  <p className="text-lg font-bold text-white mt-0.5">
                    {liveWeatherSoilMoisture !== null ? `${liveWeatherSoilMoisture} %` : "..."}
                  </p>
                </div>
              </div>
              <p className="text-[10px] text-gray-500">
                {t("source_open_meteo", language)} · Coordinates: ({currentDistrictMeta.latitude || 28}°N, {currentDistrictMeta.longitude || 77}°E)
              </p>
            </div>

            {/* Run Prediction Button */}
            <button
              onClick={handleRunLivePrediction}
              className="w-full py-3 bg-emerald-800 hover:bg-emerald-700 text-white font-bold rounded-xl text-sm transition shadow-lg flex items-center justify-center gap-2"
            >
              <span>🔍</span>
              <span>{t("predict_risk_btn", language)}</span>
            </button>

            {/* Prediction Output (matching res_left and res_right) */}
            {hasRunLivePrediction && livePredictionResult && (
              <div className="pt-4 border-t border-[#23352a] grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                <div className="lg:col-span-7 space-y-4">
                  <h3 className="text-base font-bold text-white">
                    {t("crop", language)}: {localize_value(liveCrop, language)} · {t("district", language)}: {liveDistrict}, {currentDistrictRecord.state}
                  </h3>

                  <div className="flex items-center gap-4">
                    <div className="bg-[#17221b] border border-[#23352a] rounded-xl p-4">
                      <p className="text-[10px] uppercase font-bold text-gray-400">{t("crop_risk", language)}</p>
                      <p className="text-2xl font-black text-white mt-0.5">
                        {(livePredictionResult.risk_probability * 100).toFixed(1)}%
                      </p>
                    </div>
                    <RiskBadge level={livePredictionResult.risk_level} language={language} />
                  </div>

                  <div className="p-3 bg-[#15231a] border border-[#25422f] rounded-xl text-xs text-gray-300">
                    ℹ️ <strong>{t("disclaimer_title", language)}</strong>: {t("disclaimer_text", language)}
                  </div>

                  <div className="farmer-note">
                    <strong>{t("what_means", language)}</strong> {farmerAdviceList.join(" ")}
                  </div>
                </div>

                <div className="lg:col-span-5 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-3">
                  <h3 className="font-bold text-white text-sm">{t("safer_options", language)}</h3>
                  <div className="p-3 bg-emerald-950/80 border border-emerald-700 rounded-xl text-xs text-emerald-200">
                    <strong>{t("better_crop_option", language)}</strong>: {localize_value(livePredictionResult.recommended_crop, language)}
                  </div>
                  <p className="text-xs font-bold text-white">{t("safer_options", language)}:</p>
                  <div className="space-y-1.5">
                    {livePredictionResult.top_options.map((opt, i) => (
                      <div
                        key={i}
                        className="flex justify-between items-center p-2.5 bg-[#121c16] rounded-lg text-xs"
                      >
                        <span className="font-bold text-white">{localize_value(opt.crop, language)}</span>
                        <span className="text-gray-400">{opt.percentage}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 2: MY FIELD (Original Overview Tab)                      */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "field" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: Your next field steps & Crop risk comparison */}
            <div className="lg:col-span-7 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-5">
              <div>
                <h3 className="text-base font-bold text-white">{t("field_steps_title", language)}</h3>
                <ul className="mt-2 space-y-2 text-xs text-gray-300 list-disc list-inside">
                  {farmerAdviceList.map((adv, i) => (
                    <li key={i} className="leading-relaxed">
                      {adv}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="pt-4 border-t border-[#23352a] space-y-3">
                <h3 className="text-sm font-bold text-white">{t("risk_comparison_title", language)}</h3>
                <div className="space-y-2">
                  {comparisonCrops.slice(0, 5).map((c) => {
                    const pct = Math.round(c.consensus_risk * 100);
                    return (
                      <div key={c.crop} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-semibold text-white">{localize_value(c.crop, language)}</span>
                          <span className="font-mono text-gray-400">{pct}%</span>
                        </div>
                        <div className="w-full bg-[#121c16] h-2.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              pct >= 70 ? "bg-rose-500" : pct >= 45 ? "bg-amber-500" : "bg-emerald-500"
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Right: Current field conditions & At a glance */}
            <div className="lg:col-span-5 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-5">
              <div>
                <h3 className="text-base font-bold text-white">{t("conditions_title", language)}</h3>
                <div className="mt-3 space-y-2 text-xs">
                  {[
                    { label: `${t("rainfall", language)} (mm)`, val: currentObservedRecord?.rainfall ?? currentDistrictRecord.rainfall },
                    { label: `${t("temperature", language)} (°C)`, val: currentObservedRecord?.temperature ?? currentDistrictRecord.temperature },
                    { label: `${t("humidity", language)} (%)`, val: currentDistrictRecord.humidity },
                    { label: `${t("soil_moisture", language)} (%)`, val: currentDistrictRecord.soil_moisture },
                    { label: "NDVI Flowering", val: currentDistrictRecord.ndvi_flowering },
                    { label: "Water Stress", val: currentDistrictRecord.water_stress },
                    { label: "Pest Risk", val: currentDistrictRecord.pest_risk },
                  ].map((feat) => (
                    <div key={feat.label} className="flex justify-between items-center py-1 border-b border-[#23352a]">
                      <span className="text-gray-400">{feat.label}</span>
                      <span className="font-bold text-white font-mono">{feat.val}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-4 border-t border-[#23352a] space-y-2">
                <h3 className="text-sm font-bold text-white">{t("at_a_glance_title", language)}</h3>
                <div className="space-y-1.5 text-xs text-gray-300">
                  <p>• {t("your_crop", language)}: <strong className="text-white">{localize_value(currentDistrictRecord.crop, language)}</strong></p>
                  <p>• {t("suggested_crop_label", language)}: <strong className="text-emerald-400">{localize_value(currentDistrictRecord.recommended_crop, language)}</strong></p>
                  <p>• {t("current_risk", language)}: <strong className="text-white">{currentDistrictRecord.risk_level === "High" ? t("high_risk", language) : currentDistrictRecord.risk_level === "Medium" ? t("medium_risk", language) : t("low_risk", language)}</strong></p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 3: COMPARE CROPS                                        */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "compare" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-xl font-bold text-white">{t("tab_compare", language)}</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  {t("safer_options_caption", language)}
                </p>
              </div>
              {isGuideLoading && (
                <span className="text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800 px-3 py-1 rounded-full animate-pulse self-start">
                  ⏳ Loading all regional crop scenarios...
                </span>
              )}
              {guideLoadError && (
                <span className="text-xs text-amber-400 bg-amber-950/60 border border-amber-800 px-3 py-1 rounded-full self-start">
                  ⚠️ Using regional baseline scenarios
                </span>
              )}
            </div>

            <div className="bg-[#17221b] border border-[#23352a] rounded-2xl overflow-hidden shadow">
              <table className="w-full text-left text-xs text-gray-300">
                <thead className="bg-[#121c16] text-gray-400 uppercase text-[10px] border-b border-[#23352a]">
                  <tr>
                    <th className="py-3 px-4">{t("crop", language)}</th>
                    <th className="py-3 px-4">{t("crop_risk", language)}</th>
                    <th className="py-3 px-4">{t("risk_level", language)}</th>
                    <th className="py-3 px-4">{t("better_crop_option", language)}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#23352a]">
                  {comparisonCrops.map((c) => (
                    <tr key={c.crop} className="hover:bg-[#1a2b21] transition">
                      <td className="py-3 px-4 font-bold text-white flex items-center gap-2">
                        <span>{localize_value(c.crop, language)}</span>
                        {c.crop.toLowerCase() === selectedCrop.toLowerCase() && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                            {t("your_crop", language)}
                          </span>
                        )}
                        {c.crop === currentDistrictRecord.recommended_crop && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">
                            ⭐ {t("better_crop_option", language)}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-white">
                        {(c.consensus_risk * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            c.risk_level === "High"
                              ? "bg-rose-950 text-rose-300 border border-rose-800"
                              : c.risk_level === "Medium"
                              ? "bg-amber-950 text-amber-300 border border-amber-800"
                              : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          }`}
                        >
                          {c.risk_level === "High"
                            ? t("high_risk", language)
                            : c.risk_level === "Medium"
                            ? t("medium_risk", language)
                            : t("low_risk", language)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-300">
                        {localize_value(c.recommended_crop, language) || "Optimal"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 4: PLAN FOR CHANGING WEATHER (Digital Twin)             */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "weather" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left: Possible weather changes (presets) */}
              <div className="lg:col-span-5 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-4">
                <div>
                  <h3 className="font-bold text-white text-base">{t("possible_weather_changes", language)}</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    {t("possible_weather_caption", language)}
                  </p>
                </div>

                <div className="space-y-2.5">
                  {presetScenarios.map((sc) => (
                    <div
                      key={sc.name}
                      className="p-3 bg-[#121c16] border border-[#23352a] rounded-xl flex items-center justify-between"
                    >
                      <div>
                        <p className="font-bold text-white text-xs">{sc.name}</p>
                        <p className="text-[10px] text-gray-400">{sc.notes}</p>
                      </div>
                      <span className="font-mono font-black text-white text-sm">
                        {(sc.risk * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right: Try your own situation (sliders) */}
              <div className="lg:col-span-7 bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-4">
                <div>
                  <h3 className="font-bold text-white text-base">{t("try_situation_title", language)}</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    {t("try_situation_caption", language)}
                  </p>
                </div>

                <div className="space-y-1">
                  <label className="text-xs text-gray-400">{t("scenario_name", language)}</label>
                  <input
                    type="text"
                    value={simName}
                    onChange={(e) => setSimName(e.target.value)}
                    className="w-full bg-[#121c16] border border-[#23352a] text-white text-xs rounded-xl px-3 py-1.5"
                  />
                </div>

                {/* Controls */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-300">{t("rainfall_change", language)}</span>
                      <span className="font-mono text-white">{simRainfallDelta > 0 ? `+${simRainfallDelta}` : simRainfallDelta}</span>
                    </div>
                    <input
                      type="range"
                      min="-80"
                      max="80"
                      step="1"
                      value={simRainfallDelta}
                      onChange={(e) => setSimRainfallDelta(Number(e.target.value))}
                      className="w-full accent-emerald-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-300">{t("temperature_change", language)}</span>
                      <span className="font-mono text-white">{simTempDelta > 0 ? `+${simTempDelta}` : simTempDelta}</span>
                    </div>
                    <input
                      type="range"
                      min="-8"
                      max="8"
                      step="0.5"
                      value={simTempDelta}
                      onChange={(e) => setSimTempDelta(Number(e.target.value))}
                      className="w-full accent-emerald-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-300">{t("humidity_change", language)}</span>
                      <span className="font-mono text-white">{simHumidityDelta > 0 ? `+${simHumidityDelta}` : simHumidityDelta}</span>
                    </div>
                    <input
                      type="range"
                      min="-30"
                      max="30"
                      step="1"
                      value={simHumidityDelta}
                      onChange={(e) => setSimHumidityDelta(Number(e.target.value))}
                      className="w-full accent-emerald-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-300">{t("soil_moisture_change", language)}</span>
                      <span className="font-mono text-white">{simSoilMoistureDelta > 0 ? `+${simSoilMoistureDelta}` : simSoilMoistureDelta}</span>
                    </div>
                    <input
                      type="range"
                      min="-30"
                      max="30"
                      step="1"
                      value={simSoilMoistureDelta}
                      onChange={(e) => setSimSoilMoistureDelta(Number(e.target.value))}
                      className="w-full accent-emerald-500"
                    />
                  </div>
                </div>

                {/* Metrics comparison */}
                <div className="grid grid-cols-2 gap-3 pt-3 border-t border-[#23352a]">
                  <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                    <p className="text-[10px] text-gray-400">{t("current_risk", language)}</p>
                    <p className="text-xl font-bold text-white mt-0.5">
                      {(currentDistrictRecord.consensus_risk * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="bg-[#121c16] p-3 rounded-xl border border-[#23352a]">
                    <p className="text-[10px] text-gray-400">{t("risk_after_change", language)}</p>
                    <p className="text-xl font-bold text-white mt-0.5">
                      {(customScenarioResult.simulatedRisk * 100).toFixed(1)}%
                      <span className="text-xs font-normal text-gray-400 ml-2">
                        {customScenarioResult.deltaPts >= 0 ? "+" : ""}
                        {customScenarioResult.deltaPts.toFixed(1)} pts
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Weather Forecasting Section (7-Day & 14-Day Horizon) */}
            <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="font-bold text-white text-base flex items-center gap-2">
                    <span>🌦️</span>
                    <span>
                      {language === "hi"
                        ? "बहु-दिवसीय मौसम नियोजन पूर्वानुमान"
                        : "Multi-Day Weather Planning Forecast"}
                    </span>
                  </h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {language === "hi"
                      ? "ओपन-मेटियो से संख्यात्मक मौसम पूर्वानुमान। यह डिजिटल ट्विन सिमुलेशन और फसल जोखिम अनुमानों से अलग है।"
                      : "Numerical meteorological forecast from Open-Meteo for agronomic field planning. Kept distinct from scenario simulations and ML risk predictions."}
                  </p>
                </div>

                <div className="flex items-center gap-1.5 bg-[#121c16] p-1 rounded-xl border border-[#23352a]">
                  <button
                    onClick={() => setForecastHorizon(7)}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition ${
                      forecastHorizon === 7
                        ? "bg-emerald-800 text-white shadow-sm"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    {language === "hi" ? "7-दिवसीय" : "7-Day"}
                  </button>
                  <button
                    onClick={() => setForecastHorizon(14)}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition ${
                      forecastHorizon === 14
                        ? "bg-emerald-800 text-white shadow-sm"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    {language === "hi" ? "14-दिवसीय" : "14-Day"}
                  </button>
                </div>
              </div>

              {/* Status / Horizon Disclaimer */}
              {farmForecast && farmForecast.success && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-gray-400 px-1 gap-1">
                  <span>
                    {farmForecast.forecast_days < forecastHorizon
                      ? `ℹ️ Provider supplied ${farmForecast.forecast_days} days of data for requested ${forecastHorizon}-day horizon. Displaying actual horizon without fabrication.`
                      : `✓ Actual ${farmForecast.forecast_days}-day forecast loaded for Registered Farm Plot (${selectedFarm?.name || "Farm"}: ${farmForecast.latitude}°N, ${farmForecast.longitude}°E). Distinct from current user location.`}
                  </span>
                  <span>Timezone: {farmForecast.timezone || "Asia/Kolkata"}</span>
                </div>
              )}

              {isFetchingForecast ? (
                <div className="p-8 text-center text-xs text-gray-400">
                  <span className="animate-spin inline-block mr-2">⏳</span>
                  {language === "hi" ? "मौसम पूर्वानुमान लोड हो रहा है..." : "Loading meteorological forecast..."}
                </div>
              ) : farmForecast && farmForecast.success && farmForecast.daily && farmForecast.daily.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#23352a] text-gray-400">
                        <th className="py-2.5 px-3">Date</th>
                        <th className="py-2.5 px-3">Max Temp</th>
                        <th className="py-2.5 px-3">Min Temp</th>
                        <th className="py-2.5 px-3">Precipitation</th>
                        <th className="py-2.5 px-3">Rain Probability</th>
                        <th className="py-2.5 px-3">Weather Code</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#23352a]/40 text-gray-200">
                      {farmForecast.daily.map((item, idx) => (
                        <tr key={item.date || idx} className="hover:bg-[#121c16]/60">
                          <td className="py-2.5 px-3 font-mono font-bold text-white">{item.date}</td>
                          <td className="py-2.5 px-3">
                            {item.temperature_max !== null && item.temperature_max !== undefined
                              ? `${item.temperature_max}°C`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {item.temperature_min !== null && item.temperature_min !== undefined
                              ? `${item.temperature_min}°C`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {item.precipitation_sum !== null && item.precipitation_sum !== undefined
                              ? `${item.precipitation_sum} mm`
                              : "0.0 mm"}
                          </td>
                          <td className="py-2.5 px-3">
                            {item.precipitation_probability_max !== null && item.precipitation_probability_max !== undefined
                              ? `${item.precipitation_probability_max}%`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-gray-400">
                            {item.weather_code !== null && item.weather_code !== undefined ? item.weather_code : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-6 bg-[#121c16] border border-[#23352a] rounded-xl text-center text-xs text-gray-400">
                  {farmForecast?.error
                    ? `⚠️ ${farmForecast.error}`
                    : (selectedFarm
                        ? "Select a farm or refresh to retrieve meteorological forecast."
                        : "Please register or select a farm plot to view multi-day weather forecast projections.")}
                </div>
              )}
            </div>
          </div>
        )}


        {/* ----------------------------------------------------------- */}
        {/* TAB 5: DISTRICT MAP                                         */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "map" && (
          <div className="space-y-4">
            <DistrictRiskMap
              districts={districtMetadata as any}
              selectedDistrict={selectedDistrict}
              onSelectDistrict={(dist) => {
                setSelectedDistrict(dist);
                setLiveDistrict(dist);
                setStatusNotice(`Switched dashboard context to ${dist}`);
              }}
            />
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* ----------------------------------------------------------- */}
        {/* TAB 6: RISK HISTORY & ALERTS                                */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "alerts" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <span>🚨</span>
                  <span>{t("tab_alerts", language)}</span>
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  {language === "hi"
                    ? "कृषि-जलवायु तनाव की घटनाओं, उच्च-जोखिम झंडों और शमन कार्यों का ऑडिट ट्रेल।"
                    : "Audit trail of agro-climatic stress events, high-risk flags, and mitigation actions."}
                </p>
              </div>

              {selectedFarm && (
                <div className="text-xs text-gray-400 bg-[#152119] px-3 py-1.5 rounded-xl border border-[#23352a]">
                  Plot: <strong className="text-white">{selectedFarm.name}</strong> ({selectedFarm.district})
                </div>
              )}
            </div>

            {/* Metrics cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-[#17221b] border border-[#23352a] p-3 rounded-xl">
                <span className="text-[10px] text-gray-400 uppercase font-semibold">Total Alerts</span>
                <p className="text-xl font-black text-white mt-0.5">{farmAlerts.length}</p>
              </div>
              <div className="bg-[#17221b] border border-amber-900/40 p-3 rounded-xl">
                <span className="text-[10px] text-amber-400 uppercase font-semibold">Active Warnings</span>
                <p className="text-xl font-black text-amber-300 mt-0.5">
                  {farmAlerts.filter((a) => a.status === "active").length}
                </p>
              </div>
              <div className="bg-[#17221b] border border-blue-900/40 p-3 rounded-xl">
                <span className="text-[10px] text-blue-400 uppercase font-semibold">Acknowledged</span>
                <p className="text-xl font-black text-blue-300 mt-0.5">
                  {farmAlerts.filter((a) => a.status === "acknowledged").length}
                </p>
              </div>
              <div className="bg-[#17221b] border border-emerald-900/40 p-3 rounded-xl">
                <span className="text-[10px] text-emerald-400 uppercase font-semibold">Resolved</span>
                <p className="text-xl font-black text-emerald-300 mt-0.5">
                  {farmAlerts.filter((a) => a.status === "resolved").length}
                </p>
              </div>
            </div>

            {farmAlerts.length > 0 ? (
              <div className="space-y-3">
                {farmAlerts.map((alt) => {
                  const isCritical = alt.severity === "critical";
                  const isWarning = alt.severity === "warning";
                  const borderColor = isCritical
                    ? "border-red-800/80 bg-[#251515]"
                    : isWarning
                    ? "border-amber-800/80 bg-[#241c14]"
                    : "border-blue-900/60 bg-[#161f26]";
                  const tagColor = isCritical
                    ? "bg-red-950 text-red-300 border-red-800"
                    : isWarning
                    ? "bg-amber-950 text-amber-300 border-amber-800"
                    : "bg-blue-950 text-blue-300 border-blue-800";

                  return (
                    <div
                      key={alt.id}
                      className={`p-4 border rounded-xl flex flex-col md:flex-row md:items-start justify-between gap-4 transition shadow-sm ${borderColor}`}
                    >
                      <div className="space-y-2 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded border ${tagColor}`}>
                            {alt.severity || "info"}
                          </span>
                          <span className="text-xs font-bold text-white tracking-wide">
                            {alt.alert_type}
                          </span>
                          <span className="text-[10px] text-gray-400 ml-auto">
                            Status: <strong className="text-gray-200 capitalize">{alt.status}</strong>
                          </span>
                        </div>

                        <p className="text-xs text-gray-200 leading-relaxed">{alt.trigger_reason}</p>

                        {alt.recommended_action && (
                          <div className="text-[11px] text-emerald-300 bg-emerald-950/40 border border-emerald-900/50 p-2 rounded-lg">
                            💡 <strong>Recommended Action:</strong>{" "}
                            {typeof alt.recommended_action === "string"
                              ? alt.recommended_action
                              : alt.recommended_action.summary || alt.recommended_action.title || JSON.stringify(alt.recommended_action)}
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-3 text-[10px] text-gray-400 pt-1">
                          <span>Created: {new Date(alt.created_at).toLocaleString()}</span>
                          {alt.acknowledged_at && (
                            <span className="text-blue-300">
                              ✓ Acknowledged: {new Date(alt.acknowledged_at).toLocaleDateString()}
                            </span>
                          )}
                          {alt.resolved_at && (
                            <span className="text-emerald-300">
                              ✓ Resolved: {new Date(alt.resolved_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 self-end md:self-center">
                        {alt.status === "active" && (
                          <button
                            onClick={() => handleAcknowledgeAlert(alt.id)}
                            disabled={isAcknowledgingAlert === alt.id}
                            className="px-3 py-1.5 bg-amber-800 hover:bg-amber-700 disabled:opacity-50 text-amber-100 text-xs font-bold rounded-lg transition shadow"
                          >
                            {isAcknowledgingAlert === alt.id
                              ? (language === "hi" ? "सहेज रहा है..." : "Saving...")
                              : (language === "hi" ? "स्वीकार करें" : "Acknowledge")}
                          </button>
                        )}

                        {alt.status !== "resolved" && isExpertAuthorized && (
                          <button
                            onClick={() => handleResolveAlert(alt.id)}
                            disabled={isResolvingAlert === alt.id}
                            className="px-3 py-1.5 bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-emerald-100 text-xs font-bold rounded-lg transition shadow"
                          >
                            {isResolvingAlert === alt.id
                              ? (language === "hi" ? "हल हो रहा है..." : "Resolving...")
                              : (language === "hi" ? "हल करें (विशेषज्ञ)" : "Resolve (Expert)")}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-8 text-center space-y-2">
                <span className="text-2xl">🌱</span>
                <p className="text-xs font-bold text-white">
                  {language === "hi" ? "वर्तमान चक्र के लिए कोई अनसुलझी चेतावनी नहीं है।" : "No unresolved field warnings for the current cycle."}
                </p>
                <p className="text-[11px] text-gray-400">
                  {language === "hi"
                    ? "सभी कृषि-जलवायु स्थितियां, ओपन-मेटियो मौसम और वनस्पति टेलीमेट्री सामान्य सीमा के भीतर हैं।"
                    : "All environmental conditions, Open-Meteo weather parameters, and vegetation telemetry remain within normal bounds."}
                </p>
              </div>
            )}
          </div>
        )}


        {/* ----------------------------------------------------------- */}
        {/* TAB 7: LIVE FARM MONITORING & SENSORS                       */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "farms" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-black text-white">{t("tab_farms", language)}</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  {language === "hi"
                    ? "वास्तविक समय ओपन-मेटियो मौसम और सेंटिनल-2 गूगल अर्थ इंजन वनस्पति टेलीमेट्री।"
                    : "Real-time Open-Meteo weather and Sentinel-2 Google Earth Engine vegetation telemetry for all registered plots."}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={refreshFarms}
                  disabled={isFarmsLoading}
                  className="px-3 py-2 bg-[#1b2b20] hover:bg-[#23382a] border border-[#2d4735] text-emerald-300 text-xs font-bold rounded-xl transition shadow flex items-center gap-1.5"
                  title="Refresh farm plots"
                >
                  <span className={isFarmsLoading ? "animate-spin" : ""}>🔄</span>
                  <span>{language === "hi" ? "ताज़ा करें" : "Refresh Plots"}</span>
                </button>
                <Link
                  href="/farmer/farms/new"
                  className="px-3.5 py-2 bg-emerald-800 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl transition shadow flex items-center gap-1.5"
                >
                  <span>➕</span>
                  <span>{t("add_farm", language)}</span>
                </Link>
                {selectedFarm && (
                  <button
                    onClick={handleEvaluateFarmRisk}
                    disabled={isEvaluatingFarm}
                    className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 text-white text-xs font-bold rounded-xl transition shadow flex items-center gap-2"
                  >
                    {isEvaluatingFarm
                      ? (language === "hi" ? "मूल्यांकन जारी है..." : "Evaluating...")
                      : `🔍 ${t("predict_risk_btn", language)}`}
                  </button>
                )}
              </div>
            </div>

            {/* Loading state */}
            {isFarmsLoading && farms.length === 0 ? (
              <div className="py-16 text-center bg-[#17221b] rounded-2xl border border-[#23352a] space-y-3">
                <span className="animate-spin text-3xl inline-block">⏳</span>
                <p className="text-sm font-medium text-gray-300">
                  {language === "hi" ? "पंजीकृत खेतों को लोड किया जा रहा है..." : "Loading registered farms..."}
                </p>
              </div>
            ) : farmsError ? (
              /* Error state */
              <div className="p-6 bg-rose-950/40 border border-rose-800/60 rounded-2xl space-y-3">
                <div className="flex items-center gap-2 text-rose-300 font-bold text-sm">
                  <span>⚠️</span>
                  <span>{farmsError}</span>
                </div>
                <p className="text-xs text-gray-400">
                  {language === "hi"
                    ? "खेतों की सूची प्राप्त करने में त्रुटि हुई। कृपया नेटवर्क जांचें या पुनः प्रयास करें।"
                    : "Unable to load farm plots from the API backend. Please check connectivity or try refreshing."}
                </p>
                <button
                  onClick={refreshFarms}
                  className="px-4 py-2 bg-rose-900/60 hover:bg-rose-800 text-white text-xs font-bold rounded-xl transition"
                >
                  🔄 Retry Loading Farms
                </button>
              </div>
            ) : farms.length > 0 ? (
              /* All registered farms rendered as individual monitoring cards */
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs text-gray-400 px-1">
                  <span>
                    Showing {farms.length} registered plot{farms.length === 1 ? "" : "s"}.
                    {selectedFarm && ` Active selection: ${selectedFarm.name}`}
                  </span>
                  <span className="text-[11px] text-gray-500">
                    Each card isolates telemetry & Sentinel-2 observations
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-5">
                  {farms.map((farm) => (
                    <FarmPlotMonitoringCard
                      key={farm.id}
                      farm={farm}
                      isSelected={selectedFarm?.id === farm.id}
                      onSelect={(f) => setSelectedFarm(f)}
                      externalPrediction={selectedFarm?.id === farm.id ? latestFarmPrediction : undefined}
                      isParentEvaluating={selectedFarm?.id === farm.id && isEvaluatingFarm}
                      onPredictionSuccess={(pred) => {
                        setLatestFarmPrediction(pred);
                        // Refresh monitoring telemetry for the selected farm
                        getFarmMonitoring(farm.id, token).then((mon) => {
                          if (mon) setFarmMonitoring(mon);
                        }).catch(() => null);
                        listFarmAlerts(farm.id, token).then((alerts) => {
                          setFarmAlerts(alerts);
                        }).catch(() => null);
                      }}
                      token={token}
                      language={language}
                    />
                  ))}
                </div>
              </div>
            ) : (
              /* Empty state */
              <div className="text-center py-12 bg-[#17221b] rounded-2xl border border-[#23352a] space-y-3">
                <span className="text-3xl block">🚜</span>
                <p className="text-sm text-gray-300 font-bold">{t("no_farms_yet", language)}</p>
                <p className="text-xs text-gray-400 max-w-md mx-auto">
                  {language === "hi"
                    ? "आपने अभी तक कोई खेत पंजीकृत नहीं किया है। वास्तविक समय की मौसम और उपग्रह निगरानी शुरू करने के लिए अपना पहला खेत जोड़ें।"
                    : "You haven't registered any farm plots yet. Add your first plot with boundary or coordinates to begin live weather and satellite monitoring."}
                </p>
                <Link
                  href="/farmer/farms/new"
                  className="inline-block px-5 py-2.5 bg-emerald-800 hover:bg-emerald-700 text-white font-bold rounded-xl text-xs transition"
                >
                  {t("add_farm", language)}
                </Link>
              </div>
            )}
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 8: 📜 PREDICTION HISTORY                                */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "history" && (
          <PredictionHistoryView token={token} language={language} />
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 9: 🔬 EXPERT WORKBENCH (Open to all authenticated users) */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "expert" && (
          <div className="space-y-6">
            <ExpertWorkbenchView
              token={token}
              role={role}
              language={language}
              onReturnToFarmer={() => setActiveTab("field")}
            />
          </div>
        )}

        {/* ----------------------------------------------------------- */}
        {/* TAB 10: 👤 MY PROFILE & SETTINGS                            */}
        {/* ----------------------------------------------------------- */}
        {activeTab === "profile" && (
          <UserProfileView
            token={token}
            initialProfile={profile}
            language={language}
            onLanguageChange={(lang) => setLanguage(lang)}
            onSignOut={() => signOut()}
          />
        )}
      </main>

      {/* Grounded AI Voice Assistant Panel (mounted only when opened) */}
      {isAssistantOpen && (
        <VoiceAssistantPanel
          isOpen={isAssistantOpen}
          onClose={() => setIsAssistantOpen(false)}
          language={language}
          context={{
            mode: "district",
            districtContext: currentDistrictRecord
              ? {
                  district: currentDistrictRecord.district,
                  state: currentDistrictRecord.state,
                  year: currentDistrictRecord.year,
                  season: currentDistrictRecord.season,
                  crop: currentDistrictRecord.crop,
                  consensus_risk: currentDistrictRecord.consensus_risk,
                  risk_level: currentDistrictRecord.risk_level,
                  rainfall: currentDistrictRecord.rainfall,
                  temperature: currentDistrictRecord.temperature,
                  humidity: currentDistrictRecord.humidity,
                  soil_moisture: currentDistrictRecord.soil_moisture,
                  ndvi_flowering: currentDistrictRecord.ndvi_flowering,
                  water_stress: currentDistrictRecord.water_stress,
                  pest_risk: currentDistrictRecord.pest_risk,
                  suitability_score: currentDistrictRecord.suitability_score,
                  yield_index: currentDistrictRecord.yield_index,
                  recommended_crop: currentDistrictRecord.recommended_crop,
                  recommendation_summary: currentDistrictRecord.recommendation_summary,
                  top_options: currentDistrictRecord.top_options,
                  observed_production: currentObservedRecord?.production ?? null,
                  observed_yield_tonnes_per_ha: currentObservedRecord?.yield_tonnes_per_ha ?? null,
                  has_verified: !!currentObservedRecord,
                }
              : null,
            farm: selectedFarm,
            crop: activeCrop,
            prediction: latestFarmPrediction,
            weather: farmWeather,
            vegetation: farmVegetation,
            monitoring: farmMonitoring,
            alerts: farmAlerts,
            language: language,
          }}
          onConfirmAction={async (actionType) => {
            if (actionType === "evaluate_risk") {
              await handleEvaluateFarmRisk();
            }
          }}
        />
      )}
    </div>
  );
}
