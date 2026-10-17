"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { getFarm } from "@shared/api/farms";
import { registerCrop } from "@shared/api/crops";
import { Farm } from "@shared/types";
import { t } from "@shared/translations";

export default function RegisterCropPage() {
  const params = useParams();
  const farmId = params?.farmId as string;

  const { token, language, user, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [farm, setFarm] = useState<Farm | null>(null);
  const [crop, setCrop] = useState("Rice");
  const [season, setSeason] = useState("Kharif");
  const [sowingDate, setSowingDate] = useState(new Date().toISOString().split("T")[0]);
  const [growthStage, setGrowthStage] = useState("Sowing");
  const [status, setStatus] = useState("active");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!token || !farmId) return;
    getFarm(farmId, token)
      .then(setFarm)
      .catch((err) => setError(err.message || "Could not load farm."));
  }, [farmId, token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !farmId) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await registerCrop(
        farmId,
        {
          crop: crop.trim(),
          season,
          sowing_date: sowingDate || undefined,
          growth_stage: growthStage,
          status,
        },
        token
      );
      router.push("/farmer");
    } catch (err: any) {
      setError(err.message || "Failed to register crop cycle.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar portalType="farmer" />

      <main className="flex-1 max-w-xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <Link
            href={`/farmer/farms/${farmId}`}
            className="text-xs font-bold text-emerald-800 hover:underline inline-flex items-center gap-1 mb-1"
          >
            ← Back to Farm
          </Link>
          <h2 className="text-2xl font-bold text-gray-900">{t("add_crop", language)}</h2>
          <p className="text-xs text-gray-600 mt-0.5">
            Plot: <strong>{farm?.name || "Loading..."}</strong> ({farm?.district}, {farm?.state})
          </p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
              {t("crop", language)} *
            </label>
            <select
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
              className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-bold"
            >
              <option value="Rice">Rice (Paddy)</option>
              <option value="Wheat">Wheat</option>
              <option value="Maize">Maize</option>
              <option value="Cotton">Cotton</option>
              <option value="Soybean">Soybean</option>
              <option value="Sugarcane">Sugarcane</option>
              <option value="Groundnut">Groundnut</option>
              <option value="Chickpea">Chickpea (Gram)</option>
              <option value="Mustard">Mustard</option>
              <option value="Pigeonpea">Pigeonpea (Arhar/Tur)</option>
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("season", language)} *
              </label>
              <select
                value={season}
                onChange={(e) => setSeason(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              >
                <option value="Kharif">Kharif (Monsoon)</option>
                <option value="Rabi">Rabi (Winter)</option>
                <option value="Zaid">Zaid (Summer)</option>
                <option value="Whole Year">Whole Year</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("growth_stage", language)}
              </label>
              <select
                value={growthStage}
                onChange={(e) => setGrowthStage(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              >
                <option value="Sowing">Sowing / Germination</option>
                <option value="Vegetative">Vegetative Growth</option>
                <option value="Flowering">Flowering / Grain Formation</option>
                <option value="Maturity">Maturity / Ripening</option>
                <option value="Harvest Ready">Ready for Harvest</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("sowing_date", language)}
              </label>
              <input
                type="date"
                value={sowingDate}
                onChange={(e) => setSowingDate(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("status", language)}
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              >
                <option value="active">Active (Currently in Field)</option>
                <option value="harvested">Harvested</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          <div className="pt-3 flex gap-3">
            <Link
              href="/farmer"
              className="w-1/3 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-xl text-center text-sm transition"
            >
              {t("cancel", language)}
            </Link>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-2/3 py-3 px-4 bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-xl shadow-md text-sm transition active:scale-[0.99]"
            >
              {isSubmitting ? "Recording..." : t("save", language)}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
