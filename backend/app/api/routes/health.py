"""Health check endpoint routes."""

from fastapi import APIRouter
from backend.app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service Health Check")
def health_check() -> HealthResponse:
    """Return status and version of the API service."""
    return HealthResponse(
        status="ok",
        service="crop-risk-api",
        version="0.1.0",
    )
