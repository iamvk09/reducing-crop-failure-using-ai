"use client";

import React, { useEffect, useState } from "react";
import { PredictionResponse } from "@shared/types";
import { listMyPredictions } from "@shared/api/predictions";
import { RiskBadge } from "@shared/components/RiskBadge";
import { localize_value, localize_feature } from "@shared/translations";

interface PredictionHistoryViewProps {
  token: string | null;
  language: string;
}

export default function PredictionHistoryView({
  token,
  language,
}: PredictionHistoryViewProps) {
  const [predictions, setPredictions] = useState<PredictionResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPrediction, setSelectedPrediction] = useState<PredictionResponse | null>(null);

  const fetchHistory = async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const records = await listMyPredictions(token, 50, 0);
      setPredictions(records);
      if (records.length > 0 && !selectedPrediction) {
        setSelectedPrediction(records[0]);
      }
    } catch (err: any) {
      const errMsg = err?.message || "Failed to load prediction history.";
      setError(errMsg);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [token]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white flex items-center gap-2">
            <span>📜</span> {language === "hi" ? "मेरा भविष्यवाणी इतिहास" : "My Prediction History"}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {language === "hi"
              ? "डेटाबेस में सुरक्षित वास्तविक फसल विफलता जोखिम पूर्वानुमान और कृषि सलाहकार रिकॉर्ड।"
              : "Real persisted crop failure risk inferences and agronomic advisory records."}
          </p>
        </div>
        <button
          onClick={fetchHistory}
          disabled={isLoading}
          className="px-4 py-2 bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs rounded-xl transition shadow flex items-center gap-2 self-start sm:self-auto"
        >
          <span>🔄</span> {language === "hi" ? "रीफ्रेश करें" : "Refresh Records"}
        </button>
      </div>

      {isLoading ? (
        <div className="py-12 text-center bg-[#17221b] border border-[#23352a] rounded-2xl">
          <div className="inline-block animate-spin text-3xl mb-2">⏳</div>
          <p className="text-xs text-gray-400">
            {language === "hi" ? "भविष्यवाणी रिकॉर्ड लोड हो रहे हैं..." : "Loading persisted prediction records..."}
          </p>
        </div>
      ) : error ? (
        <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-xl text-rose-200 text-xs">
          ⚠️ {error}
        </div>
      ) : predictions.length === 0 ? (
        <div className="text-center py-12 bg-[#17221b] rounded-2xl border border-[#23352a] space-y-3">
          <span className="text-4xl block">🌱</span>
          <h3 className="text-base font-bold text-white">
            {language === "hi" ? "कोई सहेजी गई भविष्यवाणी नहीं मिली" : "No Persisted Predictions Found"}
          </h3>
          <p className="text-xs text-gray-400 max-w-md mx-auto">
            {language === "hi"
              ? "आपके खाते के लिए कोई पिछला पूर्वानुमान नहीं है। अपने खेत या लाइव प्रेडिक्शन टैब पर जाकर नया पूर्वानुमान लगाएं।"
              : "You haven't run any farm predictions yet. Use the Live Prediction or My Farms tab to run an inference."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* History List */}
          <div className="lg:col-span-5 space-y-3 max-h-[750px] overflow-y-auto pr-1">
            {predictions.map((pred) => {
              const isSelected = selectedPrediction?.prediction_id === pred.prediction_id;
              const dateStr = pred.created_at ? new Date(pred.created_at).toLocaleDateString() : "Recent";
              const timeStr = pred.created_at ? new Date(pred.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

              return (
                <div
                  key={pred.prediction_id || Math.random()}
                  onClick={() => setSelectedPrediction(pred)}
                  className={`p-4 rounded-xl border cursor-pointer transition space-y-2 ${
                    isSelected
                      ? "bg-[#1f3b2b] border-emerald-500 shadow-md"
                      : "bg-[#152119] border-[#23352a] hover:bg-[#1a2b20]"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-bold text-white text-sm">
                        {localize_value(pred.crop, language)} ({localize_value(pred.season, language)})
                      </h4>
                      <p className="text-[11px] text-gray-400">
                        {pred.district}, {pred.state}
                      </p>
                    </div>
                    <RiskBadge level={pred.risk_level} />
                  </div>

                  <div className="flex justify-between items-center text-[10px] text-gray-400 pt-1 border-t border-[#23352a]/60">
                    <span>
                      {dateStr} {timeStr}
                    </span>
                    <span className="font-mono text-emerald-400 font-bold">{pred.risk_percentage} Risk</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Details Panel */}
          <div className="lg:col-span-7 bg-[#17221b] border border-[#23352a] rounded-2xl p-6 space-y-6">
            {selectedPrediction ? (
              <>
                <div className="flex flex-wrap justify-between items-start gap-4 pb-4 border-b border-[#23352a]">
                  <div>
                    <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-wider block">
                      ID: {selectedPrediction.prediction_id?.slice(0, 16) || "Persisted"}...
                    </span>
                    <h3 className="text-xl font-black text-white mt-0.5">
                      {localize_value(selectedPrediction.crop, language)} · {localize_value(selectedPrediction.season, language)}
                    </h3>
                    <p className="text-xs text-gray-400">
                      {selectedPrediction.district}, {selectedPrediction.state} · Model: {selectedPrediction.best_model_name}
                    </p>
                  </div>
                  <div className="text-right">
                    <RiskBadge level={selectedPrediction.risk_level} />
                    <p className="text-2xl font-black text-white mt-1">{selectedPrediction.risk_percentage}</p>
                    <span className="text-[10px] text-gray-400">Calculated Failure Risk</span>
                  </div>
                </div>

                {/* Input Telemetry Used */}
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">
                    {language === "hi" ? "पूर्वानुमान में प्रयुक्त टेलीमेट्री इनपुट" : "Weather & Soil Telemetry Inputs Used"}
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <div className="bg-[#121c15] p-3 rounded-xl border border-[#23352a]">
                      <span className="text-[10px] text-gray-400 block">{localize_feature("Rainfall", language)}</span>
                      <span className="font-bold text-white text-sm">
                        {selectedPrediction.input_features?.Rainfall !== undefined
                          ? `${Number(selectedPrediction.input_features.Rainfall).toFixed(1)} mm`
                          : "—"}
                      </span>
                    </div>
                    <div className="bg-[#121c15] p-3 rounded-xl border border-[#23352a]">
                      <span className="text-[10px] text-gray-400 block">{localize_feature("Temperature", language)}</span>
                      <span className="font-bold text-white text-sm">
                        {selectedPrediction.input_features?.Temperature !== undefined
                          ? `${Number(selectedPrediction.input_features.Temperature).toFixed(1)} °C`
                          : "—"}
                      </span>
                    </div>
                    <div className="bg-[#121c15] p-3 rounded-xl border border-[#23352a]">
                      <span className="text-[10px] text-gray-400 block">{localize_feature("Humidity", language)}</span>
                      <span className="font-bold text-white text-sm">
                        {selectedPrediction.input_features?.Humidity !== undefined
                          ? `${Number(selectedPrediction.input_features.Humidity).toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>
                    <div className="bg-[#121c15] p-3 rounded-xl border border-[#23352a]">
                      <span className="text-[10px] text-gray-400 block">{localize_feature("SoilMoisture", language)}</span>
                      <span className="font-bold text-white text-sm">
                        {selectedPrediction.input_features?.SoilMoisture !== undefined
                          ? `${Number(selectedPrediction.input_features.SoilMoisture).toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Satellite Observation if recorded */}
                {(selectedPrediction.input_features?.NDVI_Flowering !== undefined ||
                  Boolean(selectedPrediction.provenance?.NDVI_Flowering)) && (
                  <div className="bg-[#121c15] p-4 rounded-xl border border-[#23352a] space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">🛰️</span>
                      <h4 className="text-xs font-bold text-white">
                        {language === "hi" ? "उपग्रह रिमोट सेंसिंग प्रेक्षण" : "Sentinel-2 Satellite Observation"}
                      </h4>
                    </div>
                    <p className="text-xs text-gray-300">
                      NDVI Flowering:{" "}
                      <span className="font-bold text-emerald-400">
                        {selectedPrediction.input_features?.NDVI_Flowering !== undefined
                          ? Number(selectedPrediction.input_features.NDVI_Flowering).toFixed(3)
                          : "Derived"}
                      </span>
                    </p>
                  </div>
                )}

                {/* Advisory Recommendations */}
                {selectedPrediction.recommendations && (
                  <div className="bg-[#121c15] p-4 rounded-xl border border-emerald-900/60 space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">💡</span>
                      <h4 className="text-xs font-bold text-emerald-300 uppercase tracking-wider">
                        {language === "hi" ? "कृषि सलाहकार एवं अनुशंसित विकल्प" : "Agronomic Advisory & Alternatives"}
                      </h4>
                    </div>
                    {selectedPrediction.recommendations.recommended_crop && (
                      <p className="text-xs text-white">
                        <span className="text-gray-400">
                          {language === "hi" ? "अनुशंसित सुरक्षित फसल:" : "Recommended Resilient Crop:"}
                        </span>{" "}
                        <strong className="text-emerald-400">
                          {localize_value(selectedPrediction.recommendations.recommended_crop, language)}
                        </strong>
                      </p>
                    )}
                    {selectedPrediction.recommendations.advisory_summary && (
                      <p className="text-xs text-gray-300 leading-relaxed bg-[#0d1610] p-3 rounded-lg border border-[#1b2b20]">
                        {selectedPrediction.recommendations.advisory_summary}
                      </p>
                    )}
                  </div>
                )}

                {/* Disclaimer */}
                <p className="text-[10px] text-gray-500 pt-2 border-t border-[#23352a]">
                  {selectedPrediction.disclaimer ||
                    "Advisory prediction derived using Machine Learning and Agro-Climatic baselines. Consult local agricultural extension officers before major planting decisions."}
                </p>
              </>
            ) : (
              <p className="text-xs text-gray-400 text-center py-10">Select a record to inspect full telemetry.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
