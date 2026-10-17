"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

export interface LatLngPoint {
  lat: number;
  lng: number;
}

export interface BoundaryMapperProps {
  latitude: number;
  longitude: number;
  initialBoundary?: Record<string, any> | null;
  onBoundaryChange?: (boundary: Record<string, any> | null, calculatedHectares: number | null) => void;
  readOnly?: boolean;
  reportedHectares?: number | null;
}

// Check if segment p1->p2 strictly crosses segment p3->p4
function checkSegmentsCross(
  p1: LatLngPoint,
  p2: LatLngPoint,
  p3: LatLngPoint,
  p4: LatLngPoint
): boolean {
  function ccw(a: LatLngPoint, b: LatLngPoint, c: LatLngPoint): boolean {
    return (c.lat - a.lat) * (b.lng - a.lng) > (b.lat - a.lat) * (c.lng - a.lng);
  }

  // If segments share an endpoint, they do not cross
  if (
    (Math.abs(p1.lat - p3.lat) < 1e-9 && Math.abs(p1.lng - p3.lng) < 1e-9) ||
    (Math.abs(p1.lat - p4.lat) < 1e-9 && Math.abs(p1.lng - p4.lng) < 1e-9) ||
    (Math.abs(p2.lat - p3.lat) < 1e-9 && Math.abs(p2.lng - p3.lng) < 1e-9) ||
    (Math.abs(p2.lat - p4.lat) < 1e-9 && Math.abs(p2.lng - p4.lng) < 1e-9)
  ) {
    return false;
  }

  return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && ccw(p1, p2, p3) !== ccw(p1, p2, p4);
}

// Check if any edges in polygon with N unique vertices cross
export function isPolygonSelfIntersecting(vertices: LatLngPoint[]): boolean {
  const n = vertices.length;
  if (n < 4) return false;
  for (let i = 0; i < n; i++) {
    const p1 = vertices[i];
    const p2 = vertices[(i + 1) % n];
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue; // adjacent closing edge
      const p3 = vertices[j];
      const p4 = vertices[(j + 1) % n];
      if (checkSegmentsCross(p1, p2, p3, p4)) {
        return true;
      }
    }
  }
  return false;
}

// Calculate true geodesic spherical area in hectares using WGS84 authalic sphere approximation
export function calculateGeodesicAreaHectares(latlngs: LatLngPoint[]): number {
  if (latlngs.length < 3) return 0;
  const R = 6378137.0; // Earth mean radius in meters
  let area = 0.0;
  const n = latlngs.length;

  for (let i = 0; i < n; i++) {
    const p1 = latlngs[i];
    const p2 = latlngs[(i + 1) % n];
    const lon1 = (p1.lng * Math.PI) / 180.0;
    const lat1 = (p1.lat * Math.PI) / 180.0;
    const lon2 = (p2.lng * Math.PI) / 180.0;
    const lat2 = (p2.lat * Math.PI) / 180.0;
    area += (lon2 - lon1) * (2.0 + Math.sin(lat1) + Math.sin(lat2));
  }

  const areaSqMeters = Math.abs((area * (R * R)) / 2.0);
  return Number((areaSqMeters / 10000.0).toFixed(2));
}

export const BoundaryMapper: React.FC<BoundaryMapperProps> = ({
  latitude,
  longitude,
  initialBoundary,
  onBoundaryChange,
  readOnly = false,
  reportedHectares,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<any>(null);
  const centerMarkerRef = useRef<any>(null);
  const bufferCircleRef = useRef<any>(null);
  const polygonLayerRef = useRef<any>(null);
  const polylineLayerRef = useRef<any>(null);
  const vertexMarkersRef = useRef<any[]>([]);

  const [isLeafletLoaded, setIsLeafletLoaded] = useState(false);
  const [vertices, setVertices] = useState<LatLngPoint[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Keep ref to latest vertices & state for Leaflet map event handlers
  const verticesRef = useRef<LatLngPoint[]>([]);
  verticesRef.current = vertices;

  const isDrawingRef = useRef<boolean>(isDrawing);
  isDrawingRef.current = isDrawing;

  const readOnlyRef = useRef<boolean>(readOnly);
  readOnlyRef.current = readOnly;

  // Load Leaflet dynamically via CDN if not present
  useEffect(() => {
    if (typeof window === "undefined") return;

    if ((window as any).L) {
      setIsLeafletLoaded(true);
      return;
    }

    const existingLink = document.querySelector('link[href*="leaflet.css"]');
    if (!existingLink) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    const existingScript = document.querySelector('script[src*="leaflet.js"]');
    if (existingScript) {
      existingScript.addEventListener("load", () => setIsLeafletLoaded(true));
      if ((window as any).L) setIsLeafletLoaded(true);
      return;
    }

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.async = true;
    script.onload = () => {
      setIsLeafletLoaded(true);
    };
    document.body.appendChild(script);
  }, []);

  // Parse initial GeoJSON boundary
  useEffect(() => {
    if (
      initialBoundary &&
      initialBoundary.type === "Polygon" &&
      Array.isArray(initialBoundary.coordinates) &&
      initialBoundary.coordinates.length > 0
    ) {
      const ring = initialBoundary.coordinates[0];
      if (Array.isArray(ring) && ring.length >= 4) {
        // GeoJSON closed ring has last point == first point
        const initialVertices: LatLngPoint[] = ring.slice(0, -1).map((coord: number[]) => ({
          lat: Number(coord[1]),
          lng: Number(coord[0]),
        }));
        setVertices(initialVertices);
        setIsDrawing(false);
        return;
      }
    }
    setVertices([]);
  }, [initialBoundary]);

  // Synchronize boundary to parent and validate geometry
  const validateAndSync = useCallback(
    (currentVertices: LatLngPoint[]) => {
      if (!onBoundaryChange) return;

      if (currentVertices.length === 0) {
        setValidationError(null);
        onBoundaryChange(null, null);
        return;
      }

      if (currentVertices.length < 3) {
        setValidationError("Boundary needs at least 3 vertices to enclose a field area.");
        onBoundaryChange(null, null);
        return;
      }

      if (isPolygonSelfIntersecting(currentVertices)) {
        setValidationError("Self-intersecting polygon: Boundary edges cannot cross each other.");
        onBoundaryChange(null, null);
        return;
      }

      setValidationError(null);
      const calculatedAreaHa = calculateGeodesicAreaHectares(currentVertices);

      // GeoJSON Polygon closed ring: [ [lon, lat], ..., [lon, lat] ]
      const ring = currentVertices.map((p) => [
        Number(p.lng.toFixed(6)),
        Number(p.lat.toFixed(6)),
      ]);
      ring.push(ring[0]); // Close ring

      const geojson = {
        type: "Polygon",
        coordinates: [ring],
      };

      onBoundaryChange(geojson, calculatedAreaHa);
    },
    [onBoundaryChange]
  );

  // Initialize and update Leaflet Map
  useEffect(() => {
    if (!isLeafletLoaded || !mapContainerRef.current) return;
    const L = (window as any).L;
    if (!L) return;

    // Validate coordinates
    const validLat = typeof latitude === "number" && !isNaN(latitude) && latitude >= -90 && latitude <= 90 ? latitude : 18.5204;
    const validLng = typeof longitude === "number" && !isNaN(longitude) && longitude >= -180 && longitude <= 180 ? longitude : 73.8567;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [validLat, validLng],
        zoom: 16,
        zoomControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      // Map click handler for adding vertices when drawing
      map.on("click", (e: any) => {
        if (readOnlyRef.current) return;
        const newPoint: LatLngPoint = {
          lat: Number(e.latlng.lat.toFixed(6)),
          lng: Number(e.latlng.lng.toFixed(6)),
        };

        const updated = [...verticesRef.current, newPoint];
        setVertices(updated);
        validateAndSync(updated);
      });

      mapInstanceRef.current = map;
    } else {
      mapInstanceRef.current.setView([validLat, validLng], mapInstanceRef.current.getZoom() || 16);
    }

    const map = mapInstanceRef.current;

    // Center Marker (Gold Pin)
    if (centerMarkerRef.current) centerMarkerRef.current.remove();
    const centerIcon = L.divIcon({
      className: "farm-center-icon",
      html: `
        <div style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;background:#f59e0b;color:#ffffff;border:2px solid #ffffff;border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,0.4);font-size:12px;font-weight:bold;">
          📍
        </div>
      `,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });

    centerMarkerRef.current = L.marker([validLat, validLng], { icon: centerIcon, zIndexOffset: 1000 })
      .bindPopup(`<b>Farm GPS Center</b><br>${validLat.toFixed(4)}°N, ${validLng.toFixed(4)}°E`)
      .addTo(map);

    // Point Buffer Fallback Circle (when no valid polygon vertices)
    if (bufferCircleRef.current) bufferCircleRef.current.remove();
    const hasPolygon = vertices.length >= 3 && !isPolygonSelfIntersecting(vertices);

    if (!hasPolygon) {
      const bufferRadiusM = reportedHectares && reportedHectares > 0
        ? Math.min(Math.max(Math.sqrt((reportedHectares * 10000.0) / Math.PI), 50.0), 1000.0)
        : 100.0;

      bufferCircleRef.current = L.circle([validLat, validLng], {
        radius: bufferRadiusM,
        color: "#f59e0b",
        weight: 1.5,
        dashArray: "5, 5",
        fillColor: "#fbbf24",
        fillOpacity: 0.15,
      })
        .bindTooltip("Approximate location buffer — not a surveyed boundary", { sticky: true })
        .addTo(map);
    }

    // Clear prior polygon & vertex markers
    if (polygonLayerRef.current) polygonLayerRef.current.remove();
    if (polylineLayerRef.current) polylineLayerRef.current.remove();
    vertexMarkersRef.current.forEach((m) => m.remove());
    vertexMarkersRef.current = [];

    // Render Polygon or Incomplete Polyline
    const latLngArrays = vertices.map((v) => [v.lat, v.lng]);

    if (vertices.length >= 3) {
      const selfIntersect = isPolygonSelfIntersecting(vertices);
      polygonLayerRef.current = L.polygon(latLngArrays, {
        color: selfIntersect ? "#ef4444" : "#10b981",
        weight: 2.5,
        fillColor: selfIntersect ? "#f87171" : "#10b981",
        fillOpacity: selfIntersect ? 0.25 : 0.2,
      }).addTo(map);
    } else if (vertices.length > 0) {
      polylineLayerRef.current = L.polyline(latLngArrays, {
        color: "#10b981",
        weight: 2,
        dashArray: "4, 4",
      }).addTo(map);
    }

    // Render Draggable Vertex Markers
    vertices.forEach((v, idx) => {
      const vertexIcon = L.divIcon({
        className: "custom-vertex-icon",
        html: `
          <div style="background:#10b981;color:#ffffff;border:2px solid #ffffff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:bold;box-shadow:0 1px 4px rgba(0,0,0,0.3);cursor:${readOnly ? "default" : "move"};">
            ${idx + 1}
          </div>
        `,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });

      const marker = L.marker([v.lat, v.lng], {
        icon: vertexIcon,
        draggable: !readOnly,
      }).addTo(map);

      if (!readOnly) {
        marker.on("drag", (e: any) => {
          const newPos = e.target.getLatLng();
          const next = [...verticesRef.current];
          next[idx] = {
            lat: Number(newPos.lat.toFixed(6)),
            lng: Number(newPos.lng.toFixed(6)),
          };
          setVertices(next);
        });

        marker.on("dragend", () => {
          validateAndSync(verticesRef.current);
        });

        marker.bindPopup(`
          <div style="font-size:12px;text-align:center;">
            <b>Vertex ${idx + 1}</b><br/>
            ${v.lat.toFixed(5)}°N, ${v.lng.toFixed(5)}°E<br/>
            <button id="del-vertex-${idx}" style="margin-top:6px;padding:3px 8px;background:#ef4444;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;">
              🗑️ Delete Vertex
            </button>
          </div>
        `);

        marker.on("popupopen", () => {
          const btn = document.getElementById(`del-vertex-${idx}`);
          if (btn) {
            btn.onclick = () => {
              const updated = verticesRef.current.filter((_, i) => i !== idx);
              setVertices(updated);
              validateAndSync(updated);
            };
          }
        });
      }

      vertexMarkersRef.current.push(marker);
    });
  }, [isLeafletLoaded, latitude, longitude, vertices, readOnly, reportedHectares, validateAndSync]);

  // Handler: Add Rectangular Box
  const handleAutoBox = () => {
    if (readOnly) return;
    const ha = reportedHectares && reportedHectares > 0 ? reportedHectares : 2.5;
    const sideM = Math.sqrt(ha * 10000.0);
    const dlat = (sideM / 2.0) / 110574.0;
    const dlng = (sideM / 2.0) / (111320.0 * Math.cos((latitude * Math.PI) / 180.0));

    const boxVertices: LatLngPoint[] = [
      { lat: Number((latitude + dlat).toFixed(6)), lng: Number((longitude - dlng).toFixed(6)) }, // Top-Left
      { lat: Number((latitude + dlat).toFixed(6)), lng: Number((longitude + dlng).toFixed(6)) }, // Top-Right
      { lat: Number((latitude - dlat).toFixed(6)), lng: Number((longitude + dlng).toFixed(6)) }, // Bottom-Right
      { lat: Number((latitude - dlat).toFixed(6)), lng: Number((longitude - dlng).toFixed(6)) }, // Bottom-Left
    ];

    setVertices(boxVertices);
    setIsDrawing(false);
    validateAndSync(boxVertices);

    if (mapInstanceRef.current) {
      mapInstanceRef.current.fitBounds(boxVertices.map((p) => [p.lat, p.lng]), { padding: [30, 30] });
    }
  };

  // Handler: Reset / Clear
  const handleClear = () => {
    if (readOnly) return;
    setVertices([]);
    setIsDrawing(false);
    setValidationError(null);
    if (onBoundaryChange) onBoundaryChange(null, null);

    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView([latitude, longitude], 16);
    }
  };

  const calculatedHa = vertices.length >= 3 && !isPolygonSelfIntersecting(vertices)
    ? calculateGeodesicAreaHectares(vertices)
    : null;

  const isCustomPolygon = vertices.length >= 3 && !isPolygonSelfIntersecting(vertices);

  // Compute difference between reported and calculated area
  const areaDifference = reportedHectares && calculatedHa !== null
    ? Number((calculatedHa - reportedHectares).toFixed(2))
    : null;

  return (
    <div className="space-y-3">
      {/* Component Header & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-gray-900">🗺️ Plot Boundary Mapping</span>
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
              isCustomPolygon
                ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                : "bg-amber-50 text-amber-800 border-amber-300"
            }`}
          >
            {isCustomPolygon
              ? "✓ Custom Field Boundary Active"
              : "Approximate location buffer — not a surveyed boundary"}
          </span>
        </div>

        {!readOnly && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setIsDrawing((d) => !d)}
              className={`text-xs px-2.5 py-1 rounded-lg font-semibold border transition ${
                isDrawing
                  ? "bg-emerald-600 text-white border-emerald-700 shadow-sm"
                  : "bg-white text-emerald-800 border-emerald-300 hover:bg-emerald-50"
              }`}
            >
              {isDrawing ? "✏️ Drawing Active (Click Map)" : "✏️ Add Vertices"}
            </button>

            <button
              type="button"
              onClick={handleAutoBox}
              className="text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 px-2.5 py-1 rounded-lg font-semibold transition"
              title="Create rectangular boundary from reported area"
            >
              📐 Auto-Box ({reportedHectares || 2.5} ha)
            </button>

            {vertices.length > 0 && (
              <button
                type="button"
                onClick={handleClear}
                className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-2.5 py-1 rounded-lg font-semibold transition"
              >
                Clear / Fallback
              </button>
            )}
          </div>
        )}
      </div>

      {/* Validation Warning Alert */}
      {validationError && (
        <div className="p-2.5 bg-red-50 border border-red-200 rounded-xl text-red-800 text-xs font-semibold flex items-center gap-2">
          <span>⚠️</span>
          <span>{validationError}</span>
        </div>
      )}

      {/* Interactive Geographic Leaflet Map */}
      <div className="relative border border-gray-300 rounded-2xl overflow-hidden shadow-sm bg-slate-100">
        <div
          ref={mapContainerRef}
          className="w-full h-80 sm:h-96 z-0"
          style={{ minHeight: "320px" }}
        />

        {/* Drawing Mode Overlay Banner */}
        {isDrawing && !readOnly && (
          <div className="absolute top-2 left-1/2 transform -translate-x-1/2 z-[1000] bg-emerald-900/90 backdrop-blur-sm text-white px-3 py-1 rounded-full text-xs font-medium shadow-md border border-emerald-500/50 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            <span>Click on the map to place boundary vertices</span>
            <button
              type="button"
              onClick={() => setIsDrawing(false)}
              className="ml-1 text-[11px] underline hover:text-emerald-200 font-bold"
            >
              Done
            </button>
          </div>
        )}
      </div>

      {/* Geographic Statistics & Disclaimers */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
        <div className="bg-white p-3 rounded-xl border border-gray-200 shadow-xs">
          <span className="text-gray-500 block">Boundary Status</span>
          <span className="font-bold text-gray-900 text-sm">
            {isCustomPolygon
              ? `${vertices.length} Vertices (Closed Polygon)`
              : "Point Fallback (0 Vertices)"}
          </span>
        </div>

        <div className="bg-white p-3 rounded-xl border border-gray-200 shadow-xs">
          <span className="text-gray-500 block">Calculated Geodesic Area</span>
          <span className="font-bold text-emerald-800 text-sm">
            {calculatedHa !== null ? `${calculatedHa} Hectares` : "— (Point Buffer)"}
          </span>
          {areaDifference !== null && (
            <span
              className={`text-[10px] block font-semibold ${
                Math.abs(areaDifference) > 0.5 ? "text-amber-700" : "text-gray-500"
              }`}
            >
              Diff vs Reported: {areaDifference > 0 ? `+${areaDifference}` : areaDifference} ha
            </span>
          )}
        </div>

        <div className="bg-white p-3 rounded-xl border border-gray-200 shadow-xs">
          <span className="text-gray-500 block">Farmer-Reported Area</span>
          <span className="font-bold text-gray-900 text-sm">
            {reportedHectares ? `${reportedHectares} Hectares` : "Not Specified"}
          </span>
          <span className="text-[10px] text-gray-400 block">Preserved separately</span>
        </div>
      </div>

      {!readOnly && (
        <div className="p-3 bg-emerald-50/70 rounded-xl border border-emerald-100 text-[11px] text-emerald-900 space-y-1">
          <p className="font-semibold">💡 Interactive Field Mapping Controls:</p>
          <ul className="list-disc list-inside space-y-0.5 text-emerald-800">
            <li>Click <b>✏️ Add Vertices</b>, then click around your farm on OpenStreetMap to trace the field perimeter.</li>
            <li>Drag any vertex marker to adjust the boundary shape. Click a vertex marker to delete it.</li>
            <li>Calculated area updates dynamically in hectares using true geodesic spherical projection.</li>
            <li>If no boundary is mapped, Sentinel-2 vegetation and weather will use the approximate point-buffer fallback.</li>
          </ul>
        </div>
      )}
    </div>
  );
};
