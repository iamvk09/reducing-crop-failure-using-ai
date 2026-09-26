"""Farm management routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import get_current_user, get_farmer_user
from backend.app.core.security import AuthenticatedUser
from backend.app.schemas.farm import CropCreateRequest, CropResponse, FarmCreateRequest, FarmResponse

router = APIRouter(prefix="/farms", tags=["Farms"])


@router.get("", response_model=List[FarmResponse], summary="List User Farms")
def list_farms(user: AuthenticatedUser = Depends(get_farmer_user)) -> List[FarmResponse]:
    """Retrieve all farms belonging to the authenticated farmer."""
    # Scaffolded route: will connect to Supabase repository
    return []


@router.post("", response_model=FarmResponse, status_code=status.HTTP_201_CREATED, summary="Create Farm")
def create_farm(
    farm_in: FarmCreateRequest,
    user: AuthenticatedUser = Depends(get_farmer_user),
) -> FarmResponse:
    """Register a new farm plot with geo-coordinates."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Farm persistence will be enabled with Supabase integration.",
    )


@router.get("/{farm_id}", response_model=FarmResponse, summary="Get Farm Details")
def get_farm(
    farm_id: str,
    user: AuthenticatedUser = Depends(get_farmer_user),
) -> FarmResponse:
    """Retrieve details for a specific farm."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Farm lookup will be enabled with Supabase integration.",
    )


@router.post("/{farm_id}/crops", response_model=CropResponse, status_code=status.HTTP_201_CREATED, summary="Register Crop Cycle")
def register_crop_cycle(
    farm_id: str,
    crop_in: CropCreateRequest,
    user: AuthenticatedUser = Depends(get_farmer_user),
) -> CropResponse:
    """Record an active crop planting cycle on a farm."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Crop cycle persistence will be enabled with Supabase integration.",
    )
