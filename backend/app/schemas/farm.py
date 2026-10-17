"""Farm and crop cycle schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


def _check_segments_cross(p1: List[float], p2: List[float], p3: List[float], p4: List[float]) -> bool:
    """Check if segment p1->p2 strictly intersects segment p3->p4."""
    def ccw(a: List[float], b: List[float], c: List[float]) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    # If segments share an endpoint, they do not cross
    if (abs(p1[0] - p3[0]) < 1e-9 and abs(p1[1] - p3[1]) < 1e-9) or \
       (abs(p1[0] - p4[0]) < 1e-9 and abs(p1[1] - p4[1]) < 1e-9) or \
       (abs(p2[0] - p3[0]) < 1e-9 and abs(p2[1] - p3[1]) < 1e-9) or \
       (abs(p2[0] - p4[0]) < 1e-9 and abs(p2[1] - p4[1]) < 1e-9):
        return False

    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


def validate_geojson_geometry(v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Validate GeoJSON Polygon or MultiPolygon structure, coordinate boundaries, and self-intersection."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("boundary_geojson must be a dictionary")
    geo_type = v.get("type")
    if geo_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("boundary_geojson 'type' must be 'Polygon' or 'MultiPolygon'")
    coordinates = v.get("coordinates")
    if not isinstance(coordinates, list):
        raise ValueError("boundary_geojson 'coordinates' must be a list")

    def _validate_polygon_ring(ring: Any) -> None:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("Linear ring must have at least 4 positions (at least 3 unique vertices plus closure)")
        if ring[0] != ring[-1]:
            raise ValueError("Linear ring first and last positions must be identical (closed ring)")
        for pos in ring:
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                raise ValueError("Position must have at least [longitude, latitude]")
            lon, lat = float(pos[0]), float(pos[1])
            if not (-180.0 <= lon <= 180.0):
                raise ValueError(f"Longitude {lon} out of range [-180, 180]")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude {lat} out of range [-90, 90]")

        # Validate non-self-intersection
        n = len(ring) - 1
        for i in range(n):
            p1 = [float(ring[i][0]), float(ring[i][1])]
            p2 = [float(ring[i + 1][0]), float(ring[i + 1][1])]
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                p3 = [float(ring[j][0]), float(ring[j][1])]
                p4 = [float(ring[j + 1][0]), float(ring[j + 1][1])]
                if _check_segments_cross(p1, p2, p3, p4):
                    raise ValueError(f"Polygon boundary is self-intersecting between segments ({i},{i+1}) and ({j},{j+1})")

    if geo_type == "Polygon":
        if len(coordinates) == 0:
            raise ValueError("Polygon must have at least one linear ring")
        for ring in coordinates:
            _validate_polygon_ring(ring)
    elif geo_type == "MultiPolygon":
        if len(coordinates) == 0:
            raise ValueError("MultiPolygon must have at least one polygon")
        for poly in coordinates:
            if not isinstance(poly, list) or len(poly) == 0:
                raise ValueError("MultiPolygon elements must be lists of rings")
            for ring in poly:
                _validate_polygon_ring(ring)
    return v


class FarmCreateRequest(BaseModel):
    """Payload to register a new farm."""

    name: str = Field(..., description="Farm name or identifier", min_length=2, max_length=100)
    state: str = Field(..., description="Indian state name", min_length=2, max_length=100)
    district: str = Field(..., description="District name", min_length=2, max_length=100)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate")
    area_hectares: Optional[float] = Field(None, gt=0.0, le=100000.0, description="Farm area in hectares")
    village: Optional[str] = Field(None, max_length=100, description="Village or local area name")
    region: Optional[str] = Field(None, max_length=100, description="Agro-climatic region")
    soil_type: Optional[str] = Field(None, max_length=50, description="Dominant soil type")
    irrigation_level: Optional[str] = Field("Medium", max_length=50, description="Irrigation accessibility")
    boundary_geojson: Optional[Dict[str, Any]] = Field(None, description="Optional GeoJSON Polygon or MultiPolygon boundary")

    @field_validator("boundary_geojson")
    @classmethod
    def check_boundary_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return validate_geojson_geometry(v)


class FarmUpdateRequest(BaseModel):
    """Payload to partially update farm details."""

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    area_hectares: Optional[float] = Field(None, gt=0.0, le=100000.0)
    village: Optional[str] = Field(None, max_length=100)
    soil_type: Optional[str] = Field(None, max_length=50)
    irrigation_level: Optional[str] = Field(None, max_length=50)
    boundary_geojson: Optional[Dict[str, Any]] = Field(None, description="Optional GeoJSON Polygon or MultiPolygon boundary")

    @field_validator("boundary_geojson")
    @classmethod
    def check_boundary_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return validate_geojson_geometry(v)


class FarmResponse(BaseModel):
    """Farm entity representation."""

    id: str
    user_id: str
    name: str
    state: str
    district: str
    region: Optional[str] = None
    latitude: float
    longitude: float
    area_hectares: Optional[float] = None
    village: Optional[str] = None
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = None
    boundary_geojson: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class CropCreateRequest(BaseModel):
    """Payload to record an active crop cycle."""

    crop: str = Field(..., description="Crop name (e.g. Rice, Wheat, Cotton, Soybean)", min_length=2, max_length=100)
    season: str = Field(..., description="Season: Kharif, Rabi, Zaid, Whole Year", min_length=2, max_length=50)
    soil_type: Optional[str] = Field(None, max_length=50)
    irrigation_level: Optional[str] = Field(None, max_length=50)
    sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None
    growth_stage: Optional[str] = Field(None, max_length=50, description="Current growth stage: Sowing, Vegetative, Flowering, Maturity")
    status: Optional[str] = Field("active", max_length=20, description="active, harvested, or failed")


class CropUpdateRequest(BaseModel):
    """Payload to update an existing crop cycle."""

    crop: Optional[str] = Field(None, min_length=2, max_length=100)
    season: Optional[str] = Field(None, min_length=2, max_length=50)
    soil_type: Optional[str] = Field(None, max_length=50)
    irrigation_level: Optional[str] = Field(None, max_length=50)
    sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None
    growth_stage: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class CropResponse(BaseModel):
    """Crop cycle representation."""

    id: str
    farm_id: str
    crop: str
    season: str
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = None
    sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None
    growth_stage: Optional[str] = None
    status: str = "active"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
