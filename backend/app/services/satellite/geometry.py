import hashlib
import json
import math
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, Field


def normalize_coordinates(coords: Any, decimals: int = 6) -> Any:
    """Recursively round floating-point coordinates to a fixed precision for stable hashing."""
    if isinstance(coords, (float, int)):
        return round(float(coords), decimals)
    elif isinstance(coords, (list, tuple)):
        return [normalize_coordinates(item, decimals) for item in coords]
    return coords


def compute_geometry_fingerprint(
    geometry_type: str,
    coordinates: Any,
    buffer_meters: float = 0.0,
) -> str:
    """Generate a stable, deterministic SHA-256 geometry fingerprint."""
    norm_coords = normalize_coordinates(coordinates, decimals=6)
    if geometry_type == "buffered_point":
        if isinstance(norm_coords, list) and len(norm_coords) >= 2:
            lon, lat = float(norm_coords[0]), float(norm_coords[1])
        else:
            lon, lat = 0.0, 0.0
        buf = round(float(buffer_meters), 1)
        payload = f"buffered_point:{lat:.6f},{lon:.6f},{buf:.1f}"
        h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"buffered_point:{h}"
    else:
        serialized = json.dumps(norm_coords, separators=(",", ":"))
        payload = f"{geometry_type}:{serialized}"
        h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{geometry_type}:{h}"


class FarmGeometry(BaseModel):
    """Encapsulates spatial bounds for satellite pixel reductions."""
    geometry_type: Literal["polygon", "multipolygon", "buffered_point"] = "buffered_point"
    coordinates: Any  # [lon, lat] or GeoJSON polygon / multipolygon coordinate rings
    buffer_meters: float = Field(default=100.0, description="Buffer radius in meters for point geometry")
    area_hectares: Optional[float] = None
    is_fallback: bool = True  # True if using buffered point rather than verified cadastral polygon

    @property
    def fingerprint(self) -> str:
        """Deterministic geometry fingerprint for cache identity and observation matching."""
        return compute_geometry_fingerprint(
            geometry_type=self.geometry_type,
            coordinates=self.coordinates,
            buffer_meters=self.buffer_meters,
        )

    @classmethod
    def from_lat_lon(
        cls,
        latitude: float,
        longitude: float,
        area_hectares: Optional[float] = None,
        default_buffer_m: float = 100.0,
    ) -> "FarmGeometry":
        """Create a point-buffered geometry from lat/lon coordinates."""
        # If area_hectares is provided and valid, derive an equivalent circular radius: r = sqrt(area * 10000 / pi)
        buffer_radius = default_buffer_m
        if area_hectares and area_hectares > 0:
            derived_r = math.sqrt((area_hectares * 10000.0) / math.pi)
            buffer_radius = min(max(derived_r, 50.0), 1000.0)  # Bound between 50m and 1km

        return cls(
            geometry_type="buffered_point",
            coordinates=[longitude, latitude],
            buffer_meters=round(buffer_radius, 1),
            area_hectares=area_hectares,
            is_fallback=True,
        )

    @classmethod
    def from_geojson_polygon(
        cls,
        polygon_coords: List[List[List[float]]],
        area_hectares: Optional[float] = None,
    ) -> "FarmGeometry":
        """Create a polygon geometry from GeoJSON coordinate rings."""
        return cls(
            geometry_type="polygon",
            coordinates=polygon_coords,
            buffer_meters=0.0,
            area_hectares=area_hectares,
            is_fallback=False,
        )

    @classmethod
    def from_farm(cls, farm: Any) -> "FarmGeometry":
        """Construct FarmGeometry prioritizing cadastral GeoJSON polygon over buffered point."""
        boundary = getattr(farm, "boundary_geojson", None)
        if boundary is None and isinstance(farm, dict):
            boundary = farm.get("boundary_geojson")

        area_ha = getattr(farm, "area_hectares", None)
        if area_ha is None and isinstance(farm, dict):
            area_ha = farm.get("area_hectares")

        if isinstance(boundary, dict) and boundary.get("coordinates"):
            b_type = boundary.get("type")
            coords = boundary.get("coordinates")
            if b_type == "Polygon" and isinstance(coords, list) and len(coords) > 0:
                # Ensure linear ring has at least 4 coordinates [lon, lat]
                ring = coords[0]
                if isinstance(ring, list) and len(ring) >= 4:
                    return cls(
                        geometry_type="polygon",
                        coordinates=coords,
                        buffer_meters=0.0,
                        area_hectares=area_ha,
                        is_fallback=False,
                    )
            elif b_type == "MultiPolygon" and isinstance(coords, list) and len(coords) > 0:
                first_poly = coords[0]
                if isinstance(first_poly, list) and len(first_poly) > 0 and len(first_poly[0]) >= 4:
                    return cls(
                        geometry_type="multipolygon",
                        coordinates=coords,
                        buffer_meters=0.0,
                        area_hectares=area_ha,
                        is_fallback=False,
                    )

        lat = getattr(farm, "latitude", None)
        if lat is None and isinstance(farm, dict):
            lat = farm.get("latitude")

        lon = getattr(farm, "longitude", None)
        if lon is None and isinstance(farm, dict):
            lon = farm.get("longitude")

        return cls.from_lat_lon(
            latitude=float(lat),
            longitude=float(lon),
            area_hectares=float(area_ha) if area_ha is not None else None,
        )

    def to_ee_geometry(self, ee_module: Any) -> Any:
        """Convert to Google Earth Engine ee.Geometry object."""
        if self.geometry_type == "polygon":
            return ee_module.Geometry.Polygon(self.coordinates)
        elif self.geometry_type == "multipolygon":
            return ee_module.Geometry.MultiPolygon(self.coordinates)
        else:
            # Point with buffer
            point = ee_module.Geometry.Point(self.coordinates)
            return point.buffer(self.buffer_meters)
