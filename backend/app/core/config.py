"""Application configuration loaded from environment variables."""

import json
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable bindings."""

    # Application Metadata
    APP_NAME: str = "Crop Risk Intelligence API"
    APP_ENV: str = "development"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS Configuration
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[List[str], str]) -> List[str]:
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # Supabase Infrastructure Configuration
    SUPABASE_URL: str = Field(default="https://placeholder.supabase.co")
    SUPABASE_ANON_KEY: str = Field(default="placeholder-anon-key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="placeholder-service-role-key")
    SUPABASE_JWT_SECRET: str = Field(default="placeholder-jwt-secret")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")

    # Weather & External Services
    OPENMETEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_CACHE_TTL_SECONDS: int = 1800

    # ML Model Artifact Paths
    RUNTIME_MODEL_BUNDLE_PATH: str = "models/agri_ai_runtime_bundle.pkl"
    SPECIALIZED_MODELS_DIR: str = "models/specialized"
    DISTRICT_DATASET_PATH: str = "data/district_dataset.csv"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
