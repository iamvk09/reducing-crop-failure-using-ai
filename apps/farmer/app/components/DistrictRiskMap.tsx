"use client";

import React, { useEffect, useRef, useState } from "react";

export interface DistrictMapItem {
  district: string;
  state: string;
  has_verified?: boolean;
  latitude: number | null;
  longitude: number | null;
  consensus_risk?: number;
  risk_level?: "Low" | "Medium" | "High";
  current_crop?: string;
  recommended_crop?: string;
  top_options?: string;
}

interface DistrictRiskMapProps {
  districts: DistrictMapItem[];
  selectedDistrict: string;
  onSelectDistrict: (district: string) => void;
}

export default function DistrictRiskMap({
  districts,
  selectedDistrict,
  onSelectDistrict,
}: DistrictRiskMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersRef = useRef<{ [key: string]: any }>({});
  const [filterRisk, setFilterRisk] = useState<"ALL" | "Low" | "Medium" | "High">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLeafletLoaded, setIsLeafletLoaded] = useState(false);

  // Filter districts with valid coordinates
  const validDistricts = districts.filter(
    (d) => typeof d.latitude === "number" && typeof d.longitude === "number"
  );

  const displayedDistricts = validDistricts.filter((d) => {
    if (filterRisk !== "ALL" && d.risk_level !== filterRisk) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        d.district.toLowerCase().includes(q) ||
        d.state.toLowerCase().includes(q) ||
        (d.current_crop && d.current_crop.toLowerCase().includes(q))
      );
    }
    return true;
  });

  // Load Leaflet dynamically via CDN if not present
  useEffect(() => {
    if (typeof window === "undefined") return;

    if ((window as any).L) {
      setIsLeafletLoaded(true);
      return;
    }

    // Leaflet CSS
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);

    // Leaflet JS
    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.async = true;
    script.onload = () => {
      setIsLeafletLoaded(true);
    };
    document.body.appendChild(script);

    return () => {
      // Keep script in DOM for hot reloads
    };
  }, []);

  // Initialize Map
  useEffect(() => {
    if (!isLeafletLoaded || !mapContainerRef.current) return;
    const L = (window as any).L;
    if (!L) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [22.8, 79.8],
        zoom: 5,
        zoomControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(map);

      mapInstanceRef.current = map;
    }

    const map = mapInstanceRef.current;

    // Clear existing markers
    Object.values(markersRef.current).forEach((m) => m.remove());
    markersRef.current = {};

    // Marker styling helper
    const getMarkerColor = (risk?: string) => {
      if (risk === "High") return "#ef4444";
      if (risk === "Medium") return "#f59e0b";
      return "#10b981";
    };

    validDistricts.forEach((d) => {
      const isSelected = d.district.toLowerCase() === selectedDistrict.toLowerCase();
      const color = getMarkerColor(d.risk_level);

      const marker = L.circleMarker([d.latitude!, d.longitude!], {
        radius: isSelected ? 12 : 7,
        fillColor: color,
        color: isSelected ? "#ffffff" : color,
        weight: isSelected ? 3 : 1.5,
        opacity: 1,
        fillOpacity: 0.85,
      });

      const popupHtml = `
        <div style="font-family: sans-serif; min-width: 180px; color: #111;">
          <h4 style="margin: 0 0 4px 0; font-size: 14px; font-weight: bold;">
            ${d.district}, ${d.state}
          </h4>
          <div style="font-size: 11px; margin-bottom: 3px;">
            <strong>Risk Level:</strong> <span style="color: ${color}; font-weight: bold;">${d.risk_level || "Unknown"}</span> 
            ${d.consensus_risk !== undefined ? `(${(d.consensus_risk * 100).toFixed(1)}%)` : ""}
          </div>
          <div style="font-size: 11px; margin-bottom: 2px;">
            <strong>Crop:</strong> ${d.current_crop || "Standard"}
          </div>
          ${d.recommended_crop ? `<div style="font-size: 11px; margin-bottom: 2px;"><strong>Recommended:</strong> ${d.recommended_crop}</div>` : ""}
          <div style="font-size: 10px; color: #666; margin-top: 4px;">
            Source: ${d.has_verified ? "Verified Historical DES" : "Regional Model Estimate"}
          </div>
          <button id="btn-select-${d.district.replace(/\s+/g, "_")}" style="margin-top: 8px; width: 100%; background: #047857; color: white; border: none; padding: 4px 8px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: bold;">
            Select District in Guide →
          </button>
        </div>
      `;

      marker.bindPopup(popupHtml);

      marker.on("popupopen", () => {
        const btnId = `btn-select-${d.district.replace(/\s+/g, "_")}`;
        const btn = document.getElementById(btnId);
        if (btn) {
          btn.onclick = () => {
            onSelectDistrict(d.district);
          };
        }
      });

      marker.on("click", () => {
        onSelectDistrict(d.district);
      });

      marker.addTo(map);
      markersRef.current[d.district] = marker;
    });

    // If selectedDistrict has coordinates, zoom slightly to it
    const activeObj = validDistricts.find(
      (d) => d.district.toLowerCase() === selectedDistrict.toLowerCase()
    );
    if (activeObj && activeObj.latitude && activeObj.longitude) {
      map.setView([activeObj.latitude, activeObj.longitude], Math.max(map.getZoom(), 6), {
        animate: true,
      });
      const m = markersRef.current[activeObj.district];
      if (m) {
        m.openPopup();
      }
    }
  }, [isLeafletLoaded, validDistricts.length, selectedDistrict]);

  return (
    <div className="space-y-4">
      {/* Map Control / Header */}
      <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span>🗺️</span> National District Risk Map
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Real geographic coverage across {validDistricts.length} monitored agricultural districts in India. Click any marker to synchronize dashboard.
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
            <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block border border-white/20"></span>
            Low (&lt;45%)
          </span>
          <span className="flex items-center gap-1.5 text-amber-400 font-medium">
            <span className="w-3 h-3 rounded-full bg-amber-500 inline-block border border-white/20"></span>
            Medium (45-70%)
          </span>
          <span className="flex items-center gap-1.5 text-rose-400 font-medium">
            <span className="w-3 h-3 rounded-full bg-rose-500 inline-block border border-white/20"></span>
            High (&ge;70%)
          </span>
        </div>
      </div>

      {/* Main Map Viewport & District Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Map Container */}
        <div className="lg:col-span-8 bg-[#17221b] border border-[#23352a] rounded-2xl overflow-hidden shadow-lg h-[540px] relative">
          <div ref={mapContainerRef} className="w-full h-full z-0" />
          {!isLeafletLoaded && (
            <div className="absolute inset-0 bg-[#121815]/90 flex items-center justify-center text-gray-400 text-xs">
              <span className="animate-pulse">Loading Leaflet Map Tiles & Geospatial Markers...</span>
            </div>
          )}
        </div>

        {/* District Quick-Select Leaderboard */}
        <div className="lg:col-span-4 bg-[#17221b] border border-[#23352a] rounded-2xl p-4 space-y-3 h-[540px] flex flex-col">
          <div className="space-y-2">
            <h3 className="font-bold text-white text-xs uppercase tracking-wider flex items-center justify-between">
              <span>Districts ({displayedDistricts.length})</span>
              <span className="text-[10px] text-gray-400 font-normal">Click to focus</span>
            </h3>

            {/* Filter buttons */}
            <div className="grid grid-cols-4 gap-1 text-[11px]">
              {(["ALL", "Low", "Medium", "High"] as const).map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setFilterRisk(lvl)}
                  className={`py-1 px-2 rounded-lg text-center font-bold transition ${
                    filterRisk === lvl
                      ? "bg-emerald-700 text-white"
                      : "bg-[#1f2f25] text-gray-400 hover:text-white"
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <input
              type="text"
              placeholder="Filter district or state..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#121815] border border-[#23352a] text-white text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* List items */}
          <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
            {displayedDistricts.map((d) => {
              const isSelected = d.district.toLowerCase() === selectedDistrict.toLowerCase();
              return (
                <button
                  key={d.district}
                  onClick={() => onSelectDistrict(d.district)}
                  className={`w-full text-left p-2.5 rounded-xl border transition flex items-center justify-between ${
                    isSelected
                      ? "bg-[#1e382b] border-emerald-500 text-white"
                      : "bg-[#141d18] border-[#223528] text-gray-300 hover:bg-[#1a2820]"
                  }`}
                >
                  <div>
                    <p className="text-xs font-bold leading-tight">
                      {d.district} <span className="text-[10px] text-gray-400 font-normal">({d.state})</span>
                    </p>
                    <p className="text-[10px] text-gray-400 mt-0.5">
                      Crop: {d.current_crop || "Standard"} · Rec: {d.recommended_crop || "None"}
                    </p>
                  </div>
                  <div className="text-right">
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        d.risk_level === "High"
                          ? "bg-rose-950 text-rose-300 border border-rose-800"
                          : d.risk_level === "Medium"
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                      }`}
                    >
                      {d.consensus_risk !== undefined ? `${(d.consensus_risk * 100).toFixed(0)}%` : d.risk_level}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
