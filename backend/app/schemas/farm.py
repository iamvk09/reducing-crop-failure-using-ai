"""Farm and crop cycle schemas."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class FarmCreateRequest(BaseModel):
    """Payload to register a new farm."""

    name: str = Field(..., description="Farm name or identifier", min_length=2)
    state: str = Field(..., description="Indian state name")
    district: str = Field(..., description="District name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    area_hectares: Optional[float] = Field(None, ge=0.01)
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = "Medium"


class FarmResponse(BaseModel):
    """Farm entity response."""

    id: str
    user_id: str
    name: str
    state: str
    district: str
    region: str
    latitude: float
    longitude: float
    area_hectares: Optional[float] = None
    soil_type: Optional[str] = None
    irrigation_level: Optional[str] = None
    created_at: datetime


class CropCreateRequest(BaseModel):
    """Payload to record an active crop cycle."""

    crop: str = Field(..., description="Crop name (e.g. Rice, Soybean)")
    season: str = Field(..., description="Season: Kharif, Rabi, Zaid")
    sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None


class CropResponse(BaseModel):
    """Crop cycle response."""

    id: str
    farm_id: str
    crop: str
    season: str
    sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None
    status: str = "active"
    is_active: bool = True
    created_at: datetime
