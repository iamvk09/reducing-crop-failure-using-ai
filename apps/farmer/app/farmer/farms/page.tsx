"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { listFarms, deleteFarm } from "@shared/api/farms";
import { Farm } from "@shared/types";
import { t } from "@shared/translations";

export default function FarmsListPage() {
  const { user, token, language, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [farms, setFarms] = useState<Farm[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);

  const loadFarms = async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await listFarms(token);
      setFarms(data);
    } catch (err: any) {
      setError(err.message || t("error_network", language));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadFarms();
  }, [token, language]);

  const handleDelete = async (farmId: string, name: string) => {
    if (!token) return;
    if (confirm(`Are you sure you want to delete farm "${name}"?`)) {
      try {
        await deleteFarm(farmId, token);
        await loadFarms();
      } catch (err: any) {
        alert(err.message || "Failed to delete farm.");
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar portalType="farmer" />

      <main className="flex-1 max-w-4xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Link
              href="/dashboard"
              className="text-xs font-bold text-emerald-800 hover:underline inline-flex items-center gap-1 mb-1"
            >
              ← Back to Unified Dashboard
            </Link>
            <h2 className="text-2xl font-bold text-gray-900">{t("my_farms", language)}</h2>
          </div>

          <Link
            href="/farmer/farms/new"
            className="px-4 py-2 bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-xl shadow text-sm transition"
          >
            ➕ {t("add_farm", language)}
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="text-center py-12 text-gray-600 font-semibold">{t("loading", language)}</div>
        ) : farms.length === 0 ? (
          <div className="bg-white rounded-2xl border-2 border-dashed border-emerald-200 p-8 text-center space-y-3">
            <p className="text-gray-600">{t("no_farms_yet", language)}</p>
            <Link
              href="/farmer/farms/new"
              className="inline-block px-5 py-2.5 bg-emerald-700 text-white font-bold rounded-xl text-sm shadow"
            >
              ➕ {t("add_farm", language)}
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {farms.map((farm) => (
              <div
                key={farm.id}
                className="bg-white rounded-2xl p-5 border border-emerald-100 shadow-sm space-y-3"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-bold text-gray-900 text-lg">{farm.name}</h3>
                    <p className="text-xs text-gray-500">
                      📍 {farm.village ? `${farm.village}, ` : ""}{farm.district}, {farm.state}
                    </p>
                  </div>
                  <span className="text-xs font-semibold bg-emerald-50 text-emerald-800 px-2 py-1 rounded">
                    {farm.area_hectares ? `${farm.area_hectares} Ha` : "Plot"}
                  </span>
                </div>

                <div className="text-xs text-gray-600 grid grid-cols-2 gap-2 bg-slate-50 p-2.5 rounded-lg">
                  <div>
                    <span className="text-gray-400 block">{t("soil_type", language)}</span>
                    <span className="font-semibold text-gray-800">{farm.soil_type || "Medium"}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block">{t("irrigation_level", language)}</span>
                    <span className="font-semibold text-gray-800">{farm.irrigation_level || "Medium"}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-gray-100 text-xs">
                  <div className="flex gap-3">
                    <Link
                      href={`/farmer/farms/${farm.id}`}
                      className="font-bold text-emerald-700 hover:underline"
                    >
                      {t("farm_details", language)}
                    </Link>
                    <Link
                      href={`/farmer/farms/${farm.id}/crop`}
                      className="font-bold text-blue-700 hover:underline"
                    >
                      🌾 {t("current_crop", language)}
                    </Link>
                  </div>

                  <button
                    onClick={() => handleDelete(farm.id, farm.name)}
                    className="text-red-600 font-bold hover:underline"
                  >
                    {t("delete", language)}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
