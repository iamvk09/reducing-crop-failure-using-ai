"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { Navbar } from "@shared/components/Navbar";
import { BoundaryMapper } from "@shared/components/BoundaryMapper";
import { createFarm } from "@shared/api/farms";
import { t } from "@shared/translations";

export default function NewFarmPage() {
  const { token, language } = useAuth();
  const router = useRouter();

  const [name, setName] = useState("");
  const [state, setState] = useState("Maharashtra");
  const [district, setDistrict] = useState("Pune");
  const [village, setVillage] = useState("");
  const [latitude, setLatitude] = useState("18.5204");
  const [longitude, setLongitude] = useState("73.8567");
  const [areaHectares, setAreaHectares] = useState("2.5");
  const [soilType, setSoilType] = useState("Black");
  const [irrigationLevel, setIrrigationLevel] = useState("Medium");
  const [boundary, setBoundary] = useState<Record<string, any> | null>(null);
  const [calculatedArea, setCalculatedArea] = useState<number | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setGpsError("Geolocation is not supported by your browser.");
      return;
    }
    setGpsLoading(true);
    setGpsError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(5));
        setLongitude(position.coords.longitude.toFixed(5));
        setGpsLoading(false);
      },
      (err) => {
        setGpsError(`GPS Permission/Error: ${err.message}`);
        setGpsLoading(false);
      },
      { timeout: 10000 }
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    if (!token) {
      setError("You must be logged in to register a farm. Please log in or refresh your session.");
      return;
    }

    const errors: Record<string, string> = {};

    if (!name.trim() || name.trim().length < 2) {
      errors.name = "Farm name must be at least 2 characters.";
    }
    if (!state.trim() || state.trim().length < 2) {
      errors.state = "State is required.";
    }
    if (!district.trim() || district.trim().length < 2) {
      errors.district = "District is required.";
    }

    const latNum = parseFloat(latitude);
    const lonNum = parseFloat(longitude);
    const areaNum = areaHectares ? parseFloat(areaHectares) : undefined;

    if (isNaN(latNum) || latNum < -90 || latNum > 90) {
      errors.latitude = "Please enter a valid Latitude between -90 and 90.";
    }
    if (isNaN(lonNum) || lonNum < -180 || lonNum > 180) {
      errors.longitude = "Please enter a valid Longitude between -180 and 180.";
    }
    if (areaNum !== undefined && (isNaN(areaNum) || areaNum <= 0)) {
      errors.areaHectares = "Farm area must be greater than 0 hectares.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError("Please correct the errors highlighted below.");
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    setError(null);

    try {
      const created = await createFarm(
        {
          name: name.trim(),
          state: state.trim(),
          district: district.trim(),
          village: village.trim() || undefined,
          latitude: latNum,
          longitude: lonNum,
          area_hectares: areaNum,
          soil_type: soilType,
          irrigation_level: irrigationLevel,
          boundary_geojson: boundary || undefined,
        },
        token
      );
      if (created && created.id) {
        if (typeof window !== "undefined") {
          try {
            sessionStorage.setItem("crop_ai_farms_updated", Date.now().toString());
            window.dispatchEvent(new Event("storage"));
          } catch {}
        }
        router.push("/dashboard");
      } else {
        throw new Error("Farm creation was not acknowledged by the backend.");
      }
    } catch (err: any) {
      let actionMsg = err.message || "Failed to register farm.";
      if (err.statusCode === 401 || err.statusCode === 403) {
        actionMsg = "Authentication or permissions error: You are not authorized to create farms. Please log in with a farmer account.";
      } else if (err.statusCode === 0) {
        actionMsg = `Network error: ${err.message || "Unable to reach the backend API. Please check your connection."}`;
      } else if (err.statusCode === 422 && err.details?.errors) {
        const pydanticErrors = Array.isArray(err.details.errors)
          ? err.details.errors.map((e: any) => `${e.loc?.join(".")}: ${e.msg}`).join("; ")
          : "";
        actionMsg = `Validation error: ${pydanticErrors || err.message}`;
      }
      setError(actionMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar portalType="farmer" />

      <main className="flex-1 max-w-2xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <Link
            href="/dashboard"
            className="text-xs font-bold text-emerald-800 hover:underline inline-flex items-center gap-1 mb-1"
          >
            ← Back to Unified Dashboard
          </Link>
          <h2 className="text-2xl font-bold text-gray-900">{t("add_farm", language)}</h2>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl p-6 border border-emerald-100 shadow-sm space-y-4">
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
              Farm Name / Plot Identifier *
            </label>
            <input
              type="text"
              required
              minLength={2}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: "" }));
              }}
              placeholder="e.g. North Plot 1"
              className={`w-full bg-slate-50 border rounded-xl px-4 py-3 text-sm text-gray-900 focus:ring-2 focus:ring-emerald-500 font-medium ${
                fieldErrors.name ? "border-red-400 bg-red-50/30" : "border-gray-300"
              }`}
            />
            {fieldErrors.name && (
              <p className="text-xs text-red-600 mt-1">{fieldErrors.name}</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("state", language)} *
              </label>
              <input
                type="text"
                required
                value={state}
                onChange={(e) => {
                  setState(e.target.value);
                  if (fieldErrors.state) setFieldErrors((prev) => ({ ...prev, state: "" }));
                }}
                placeholder="e.g. Maharashtra"
                className={`w-full bg-slate-50 border rounded-xl px-4 py-3 text-sm text-gray-900 font-medium ${
                  fieldErrors.state ? "border-red-400 bg-red-50/30" : "border-gray-300"
                }`}
              />
              {fieldErrors.state && (
                <p className="text-xs text-red-600 mt-1">{fieldErrors.state}</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("district", language)} *
              </label>
              <input
                type="text"
                required
                value={district}
                onChange={(e) => {
                  setDistrict(e.target.value);
                  if (fieldErrors.district) setFieldErrors((prev) => ({ ...prev, district: "" }));
                }}
                placeholder="e.g. Pune"
                className={`w-full bg-slate-50 border rounded-xl px-4 py-3 text-sm text-gray-900 font-medium ${
                  fieldErrors.district ? "border-red-400 bg-red-50/30" : "border-gray-300"
                }`}
              />
              {fieldErrors.district && (
                <p className="text-xs text-red-600 mt-1">{fieldErrors.district}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("village", language)} (Optional)
              </label>
              <input
                type="text"
                value={village}
                onChange={(e) => setVillage(e.target.value)}
                placeholder="e.g. Haveli"
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("area_hectares", language)}
              </label>
              <input
                type="number"
                step="0.1"
                min="0.01"
                value={areaHectares}
                onChange={(e) => {
                  setAreaHectares(e.target.value);
                  if (fieldErrors.areaHectares) setFieldErrors((prev) => ({ ...prev, areaHectares: "" }));
                }}
                placeholder="e.g. 2.5"
                className={`w-full bg-slate-50 border rounded-xl px-4 py-3 text-sm text-gray-900 font-medium ${
                  fieldErrors.areaHectares ? "border-red-400 bg-red-50/30" : "border-gray-300"
                }`}
              />
              {fieldErrors.areaHectares && (
                <p className="text-xs text-red-600 mt-1">{fieldErrors.areaHectares}</p>
              )}
            </div>
          </div>

          {/* GPS Coordinates Section */}
          <div className="bg-emerald-50/50 p-4 rounded-xl border border-emerald-100 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-900 uppercase">
                Geo-Coordinates (For Live Open-Meteo Weather)
              </span>
              <button
                type="button"
                onClick={handleUseCurrentLocation}
                disabled={gpsLoading}
                className="text-xs font-bold bg-emerald-700 hover:bg-emerald-800 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
              >
                {gpsLoading ? "Getting GPS..." : t("use_my_location", language)}
              </button>
            </div>

            {gpsError && (
              <p className="text-xs text-amber-800 font-medium">{gpsError}</p>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                  Latitude (-90 to 90) *
                </label>
                <input
                  type="number"
                  step="0.0001"
                  required
                  value={latitude}
                  onChange={(e) => setLatitude(e.target.value)}
                  className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 font-medium"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                  Longitude (-180 to 180) *
                </label>
                <input
                  type="number"
                  step="0.0001"
                  required
                  value={longitude}
                  onChange={(e) => setLongitude(e.target.value)}
                  className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 font-medium"
                />
              </div>
            </div>
          </div>

          {/* Farm Boundary Polygon Mapping */}
          <div className="bg-emerald-50/50 p-4 rounded-xl border border-emerald-100 space-y-3">
            <BoundaryMapper
              latitude={parseFloat(latitude) || 18.5204}
              longitude={parseFloat(longitude) || 73.8567}
              reportedHectares={parseFloat(areaHectares) || null}
              onBoundaryChange={(newBoundary, newHa) => {
                setBoundary(newBoundary);
                setCalculatedArea(newHa);
              }}
            />
          </div>

          {/* Soil & Irrigation */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("soil_type", language)}
              </label>
              <select
                value={soilType}
                onChange={(e) => setSoilType(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
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
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-700 uppercase mb-1">
                {t("irrigation_level", language)}
              </label>
              <select
                value={irrigationLevel}
                onChange={(e) => setIrrigationLevel(e.target.value)}
                className="w-full bg-slate-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-900 font-medium"
              >
                <option value="High">High (Canal / Borewell Available)</option>
                <option value="Medium">Medium (Partial Irrigation)</option>
                <option value="Low">Low (Rainfed / Limited Water)</option>
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
              {isSubmitting ? "Registering..." : t("save", language)}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
