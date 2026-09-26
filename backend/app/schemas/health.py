"""Health check response schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Standardized health check response."""

    status: str = Field(default="ok", description="Service health status")
    service: str = Field(default="crop-risk-api", description="Service identifier")
    version: str = Field(default="0.1.0", description="Semantic API version")
