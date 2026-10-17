"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { getFarm, updateFarm } from "@shared/api/farms";
import { listFarmCrops } from "@shared/api/crops";
import { getFarmVegetationSummary } from "@shared/api/satellite";
import { BoundaryMapper } from "@shared/components/BoundaryMapper";
import { Farm, FarmCrop, FarmVegetationSummary } from "@shared/types";
import { t } from "@shared/translations";

export default function FarmDetailPage() {
  const params = useParams();
  const farmId = params?.farmId as string;

  const { token, language, user, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [farm, setFarm] = useState<Farm | null>(null);
  const [crops, setCrops] = useState<FarmCrop[]>([]);
  const [vegetation, setVegetation] = useState<FarmVegetationSummary | null>(null);
  const [boundary, setBoundary] = useState<Record<string, any> | null>(null);
  const [calculatedArea, setCalculatedArea] = useState<number | null>(null);
  const [isSavingBoundary, setIsSavingBoundary] = useState<boolean>(false);
  const [boundarySaveSuccess, setBoundarySaveSuccess] = useState<boolean>(false);
  const [boundaryError, setBoundaryError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoadingVeg, setIsLoadingVeg] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [vegError, setVegError] = useState<string | null>(null);

  // Soil & Profile Editing State
  const [isEditingProfile, setIsEditingProfile] = useState<boolean>(false);
  const [editSoilType, setEditSoilType] = useState<string>("Medium Black");
  const [editIrrigation, setEditIrrigation] = useState<string>("Medium");
  const [isSavingProfile, setIsSavingProfile] = useState<boolean>(false);
  const [profileSaveSuccess, setProfileSaveSuccess] = useState<boolean>(false);
  const [profileSaveError, setProfileSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!token || !farmId) return;

    const loadFarmDetails = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const farmData = await getFarm(farmId, token);
        setFarm(farmData);
        setBoundary(farmData.boundary_geojson || null);
        setEditSoilType(farmData.soil_type || "Medium Black");
        setEditIrrigation(farmData.irrigation_level || "Medium");
        const cropData = await listFarmCrops(farmId, token);
        setCrops(cropData);
      } catch (err: any) {
        setError(err.message || "Failed to load farm details.");
      } finally {
        setIsLoading(false);
      }
    };

    const loadVegetationSummary = async () => {
      setIsLoadingVeg(true);
      setVegError(null);
      try {
        const vegData = await getFarmVegetationSummary(farmId, token);
        setVegetation(vegData);
      } catch (vErr: any) {
        setVegError(vErr.message || "Could not retrieve satellite vegetation telemetry.");
      } finally {
        setIsLoadingVeg(false);
      }
    };

    loadFarmDetails();
    loadVegetationSummary();
  }, [farmId, token]);

  const handleSaveBoundary = async () => {
    if (!token || !farmId) return;
    setIsSavingBoundary(true);
    setBoundarySaveSuccess(false);
    setBoundaryError(null);
    try {
      const updated = await updateFarm(
        farmId,
        {
          boundary_geojson: boundary,
        },
        token
      );
      if (updated && updated.id) {
        setFarm(updated);
        setBoundary(updated.boundary_geojson || null);
        setBoundarySaveSuccess(true);
        setTimeout(() => setBoundarySaveSuccess(false), 5000);
      } else {
        throw new Error("Server did not return confirmed updated farm boundary.");
      }
    } catch (err: any) {
      setBoundaryError(err.message || "Failed to save farm boundary.");
    } finally {
      setIsSavingBoundary(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!token || !farmId) return;
    setIsSavingProfile(true);
    setProfileSaveSuccess(false);
    setProfileSaveError(null);
    try {
      const updated = await updateFarm(
        farmId,
        {
          soil_type: editSoilType,
          irrigation_level: editIrrigation,
        },
        token
      );
      if (updated && updated.id) {
        setFarm(updated);
        setEditSoilType(updated.soil_type || "Medium Black");
        setEditIrrigation(updated.irrigation_level || "Medium");
        setProfileSaveSuccess(true);
        setIsEditingProfile(false);
        setTimeout(() => setProfileSaveSuccess(false), 5000);
      } else {
        throw new Error("Server did not return confirmed updated farm profile.");
      }
    } catch (err: any) {
      setProfileSaveError(err.message || "Failed to save farm profile changes.");
    } finally {
      setIsSavingProfile(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar portalType="farmer" />

      <main className="flex-1 max-w-3xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <Link
            href="/farmer/farms"
            className="text-xs font-bold text-emerald-800 hover:underline inline-flex items-center gap-1 mb-1"
          >
            ← Back to My Farms
          </Link>
          <h2 className="text-2xl font-bold text-gray-900">{farm ? farm.name : t("farm_details", language)}</h2>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="text-center py-12 text-gray-600 font-semibold">{t("loading", language)}</div>
        ) : farm ? (
          <div className="space-y-6">
            {/* Farm Specification Card */}
            <div className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-gray-100 pb-2">
                <h3 className="font-bold text-gray-900 text-base">
                  Location & Characteristics
                </h3>
                <div className="flex items-center gap-2">
                  {isEditingProfile ? (
                    <>
                      <button
                        type="button"
                        onClick={handleSaveProfile}
                        disabled={isSavingProfile}
                        className="text-xs font-bold bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
                      >
                        {isSavingProfile ? "Saving..." : "💾 Save Changes"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditSoilType(farm.soil_type || "Medium Black");
                          setEditIrrigation(farm.irrigation_level || "Medium");
                          setIsEditingProfile(false);
                          setProfileSaveError(null);
                        }}
                        className="text-xs font-bold bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg transition"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setIsEditingProfile(true)}
                      className="text-xs font-bold text-emerald-700 hover:text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-3 py-1 rounded-lg transition"
                    >
                      ✏️ Edit Soil / Irrigation
                    </button>
                  )}
                </div>
              </div>

              {profileSaveSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-xl text-xs font-semibold">
                  ✅ Farm profile updated successfully!
                </div>
              )}

              {profileSaveError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-900 rounded-xl text-xs font-semibold">
                  ⚠️ {profileSaveError}
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
                <div>
                  <span className="text-gray-500 block">{t("state", language)}</span>
                  <span className="font-bold text-gray-900 text-sm">{farm.state}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">{t("district", language)}</span>
                  <span className="font-bold text-gray-900 text-sm">{farm.district}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">{t("village", language)}</span>
                  <span className="font-bold text-gray-900 text-sm">{farm.village || "N/A"}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Coordinates</span>
                  <span className="font-mono text-gray-900 text-sm">
                    {farm.latitude.toFixed(4)}, {farm.longitude.toFixed(4)}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block">{t("soil_type", language)}</span>
                  {isEditingProfile ? (
                    <select
                      value={editSoilType}
                      onChange={(e) => setEditSoilType(e.target.value)}
                      className="mt-1 w-full bg-slate-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-900 font-medium"
                    >
                      <option value="Alluvial">Alluvial Soil</option>
                      <option value="Black">Black Soil</option>
                      <option value="Clay Loam">Clay Loam / Clayey Soil</option>
                      <option value="Laterite">Laterite Soil</option>
                      <option value="Loam">Loam / Loamy Soil</option>
                      <option value="Loamy Sand">Loamy Sand Soil</option>
                      <option value="Medium Black">Medium Black Soil</option>
                      <option value="Red Loam">Red Loam Soil</option>
                      <option value="Red Sandy Loam">Red Sandy Loam Soil</option>
                      <option value="Sandy">Sandy Soil</option>
                      <option value="Sandy Loam">Sandy Loam Soil</option>
                    </select>
                  ) : (
                    <span className="font-bold text-gray-900 text-sm">{farm.soil_type || "Medium Black"}</span>
                  )}
                </div>
                <div>
                  <span className="text-gray-500 block">{t("irrigation_level", language)}</span>
                  {isEditingProfile ? (
                    <select
                      value={editIrrigation}
                      onChange={(e) => setEditIrrigation(e.target.value)}
                      className="mt-1 w-full bg-slate-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-900 font-medium"
                    >
                      <option value="High">High (Canal / Borewell Available)</option>
                      <option value="Medium">Medium (Partial Irrigation)</option>
                      <option value="Low">Low (Rainfed / Limited Water)</option>
                    </select>
                  ) : (
                    <span className="font-bold text-gray-900 text-sm">{farm.irrigation_level || "Medium"}</span>
                  )}
                </div>
              </div>
            </div>

            {/* Farm Boundary Polygon Mapping Card */}
            <div className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-gray-100 pb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🗺️</span>
                  <h3 className="font-bold text-gray-900 text-base">
                    Cadastral Boundary Mapping
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={handleSaveBoundary}
                  disabled={isSavingBoundary}
                  className="text-xs font-bold bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
                >
                  {isSavingBoundary ? "Saving Boundary..." : "💾 Save Boundary"}
                </button>
              </div>

              {boundarySaveSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-xl text-xs font-semibold">
                  ✅ Farm cadastral boundary updated successfully! Sentinel-2 queries will use this polygon.
                </div>
              )}

              {boundaryError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-900 rounded-xl text-xs font-semibold">
                  ⚠️ {boundaryError}
                </div>
              )}

              <BoundaryMapper
                latitude={farm.latitude}
                longitude={farm.longitude}
                initialBoundary={farm.boundary_geojson}
                reportedHectares={farm.area_hectares}
                onBoundaryChange={(newBoundary, newHa) => {
                  setBoundary(newBoundary);
                  setCalculatedArea(newHa);
                }}
              />
            </div>

            {/* Satellite Canopy & Vegetation Telemetry Card */}
            <div className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-gray-100 pb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🛰️</span>
                  <h3 className="font-bold text-gray-900 text-base">
                    Satellite Vegetation Health (Sentinel-2)
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  {vegetation?.status === "REAL_SATELLITE_DATA" && (
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Live Verified Pass
                    </span>
                  )}
                  {isLoadingVeg ? (
                    <span className="text-xs text-gray-400">Loading satellite pass...</span>
                  ) : (
                    <span
                      className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                        vegetation?.status === "REAL_SATELLITE_DATA"
                          ? vegetation?.vegetation_health === "Healthy"
                            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                            : vegetation?.vegetation_health === "Moderate"
                              ? "bg-blue-100 text-blue-800 border-blue-300"
                              : "bg-amber-100 text-amber-800 border-amber-300"
                          : vegetation?.status === "SATELLITE_ERROR"
                            ? "bg-red-100 text-red-800 border-red-300"
                            : vegetation?.status === "SATELLITE_NO_VALID_OBSERVATION"
                              ? "bg-amber-50 text-amber-700 border-amber-200"
                              : "bg-slate-100 text-slate-700 border-slate-300"
                      }`}
                    >
                      {vegetation?.status === "SATELLITE_NOT_CONFIGURED"
                        ? "NOT_CONFIGURED"
                        : vegetation?.status === "SATELLITE_NO_VALID_OBSERVATION"
                          ? "CONFIGURED_NO_OBSERVATION"
                          : vegetation?.status === "SATELLITE_ERROR"
                            ? "ERROR"
                            : vegetation?.status === "REAL_SATELLITE_DATA"
                              ? vegetation?.vegetation_health || "AVAILABLE"
                              : "FETCHING"}
                    </span>
                  )}
                </div>
              </div>

              {isLoadingVeg ? (
                <div className="text-center py-6 text-gray-400 text-xs">
                  <span className="animate-spin inline-block mr-2">⏳</span>
                  Retrieving latest Sentinel-2 cloud-masked observation...
                </div>
              ) : vegError ? (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex justify-between items-center">
                  <span>⚠️ {vegError}</span>
                  <button
                    onClick={() => {
                      if (!token || !farmId) return;
                      setIsLoadingVeg(true);
                      setVegError(null);
                      getFarmVegetationSummary(farmId, token)
                        .then((v) => setVegetation(v))
                        .catch((e) => setVegError(e.message || "Failed to load satellite observation"))
                        .finally(() => setIsLoadingVeg(false));
                    }}
                    className="px-2.5 py-1 bg-white hover:bg-amber-100 text-amber-800 font-bold border border-amber-300 rounded text-xs ml-2"
                  >
                    Retry
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                    <div className="bg-emerald-50/60 p-3 rounded-xl border border-emerald-100">
                      <span className="text-[11px] font-semibold text-emerald-900 uppercase">
                        Mean NDVI Index
                      </span>
                      <p className="text-xl font-black text-emerald-800 mt-0.5">
                        {vegetation?.latest_ndvi !== undefined && vegetation?.latest_ndvi !== null
                          ? Number(vegetation.latest_ndvi).toFixed(3)
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">Scale: -1.0 to +1.0</span>
                    </div>

                    <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                      <span className="text-[11px] font-semibold text-gray-700 uppercase">
                        Observation Date
                      </span>
                      <p className="text-sm font-bold text-gray-900 mt-0.5">
                        {vegetation?.observation_date || "Pending Pass"}
                      </p>
                      <span className="text-[10px] text-gray-500">Sentinel-2 5-day cycle</span>
                    </div>

                    <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                      <span className="text-[11px] font-semibold text-gray-700 uppercase">
                        Scene Clouds & Coverage
                      </span>
                      <p className="text-xs font-bold text-gray-900 mt-0.5">
                        {vegetation?.scene_cloud_percent !== undefined && vegetation?.scene_cloud_percent !== null
                          ? `${vegetation.scene_cloud_percent.toFixed(1)}% Cloud`
                          : "—"}
                      </p>
                      <span className="text-[10px] text-gray-500">
                        Valid Pixels:{" "}
                        {vegetation?.valid_pixel_percent !== undefined && vegetation?.valid_pixel_percent !== null
                          ? `${vegetation.valid_pixel_percent.toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>

                    <div className="bg-slate-50 p-3 rounded-xl border border-gray-100">
                      <span className="text-[11px] font-semibold text-gray-700 uppercase">
                        Data Source & Quality
                      </span>
                      <p className="text-xs font-bold text-gray-900 mt-0.5">
                        {vegetation?.data_source || "Sentinel-2 (GEE)"}
                      </p>
                      <span className="text-[10px] text-gray-500">
                        Quality: {vegetation?.quality_label || "Good"}
                      </span>
                    </div>
                  </div>

                  <div className="bg-slate-50 rounded-xl p-3 border border-gray-100 text-xs text-gray-600">
                    <p>
                      <strong>Canopy Status:</strong>{" "}
                      {vegetation?.message ||
                        (vegetation?.status === "SATELLITE_NOT_CONFIGURED"
                          ? "Satellite provider awaiting Google Earth Engine credentials."
                          : "Surface chlorophyll absorption and canopy density monitored via 10m Sentinel-2 optical bands.")}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Recorded Crop Cycles */}
            <div className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
              <div className="flex justify-between items-center border-b border-gray-100 pb-2">
                <h3 className="font-bold text-gray-900 text-base">Recorded Crop Cycles</h3>
                <Link
                  href={`/farmer/farms/${farm.id}/crop`}
                  className="text-xs font-bold bg-emerald-700 hover:bg-emerald-800 text-white px-3 py-1.5 rounded-lg shadow-sm"
                >
                  ➕ {t("add_crop", language)}
                </Link>
              </div>

              {crops.length === 0 ? (
                <p className="text-xs text-gray-500 py-4 text-center">{t("no_crops_yet", language)}</p>
              ) : (
                <div className="space-y-2">
                  {crops.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-gray-100 text-xs"
                    >
                      <div>
                        <span className="font-bold text-gray-900 text-sm mr-2">{c.crop}</span>
                        <span className="text-gray-500 font-medium">({c.season})</span>
                        <div className="text-gray-400 text-[11px] mt-0.5">
                          Stage: {c.growth_stage || "Sowing"} · Status: {c.status}
                        </div>
                      </div>
                      <span className={`px-2.5 py-1 rounded-full font-bold text-[11px] ${c.is_active ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"}`}>
                        {c.is_active ? "Active" : "Archived"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}
