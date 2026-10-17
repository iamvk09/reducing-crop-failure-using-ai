"""Application configuration loaded from environment variables."""

import json
from pathlib import Path
from typing import List, Optional, Union
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

    # Security & Rate Limiting Configuration
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_PREDICTIONS_PER_MIN: int = 10
    RATE_LIMIT_DIAGNOSTICS_PER_MIN: int = 5
    RATE_LIMIT_GENERAL_PER_MIN: int = 60
    RATE_LIMIT_UNAUTH_PER_MIN: int = 20
    CORS_ORIGINS: Union[List[str], str] = ["*"]
    TRUSTED_PROXIES: Union[List[str], str] = ["127.0.0.1", "::1"]

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, value: Union[List[str], str]) -> List[str]:
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [proxy.strip() for proxy in value.split(",") if proxy.strip()]
        return value

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

    # =========================================================================
    # Supabase Infrastructure Configuration
    # =========================================================================

    # PUBLIC / BROWSER CLIENT (Next.js / Frontend):
    NEXT_PUBLIC_SUPABASE_URL: Optional[str] = None
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: Optional[str] = None
    NEXT_PUBLIC_SUPABASE_ANON_KEY: Optional[str] = None

    # SERVER ONLY (Backend Operations):
    SUPABASE_URL: str = Field(default="https://placeholder.supabase.co")
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = None
    SUPABASE_SECRET_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: str = Field(default="placeholder-jwt-secret")

    # LEGACY COMPATIBILITY (Fallback if new variable names are not set):
    SUPABASE_ANON_KEY: str = Field(default="placeholder-anon-key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="placeholder-service-role-key")

    @property
    def effective_supabase_url(self) -> str:
        """Resolve Supabase URL preferring SUPABASE_URL with fallback to NEXT_PUBLIC_SUPABASE_URL."""
        return (
            self.SUPABASE_URL
            if self.SUPABASE_URL and self.SUPABASE_URL != "https://placeholder.supabase.co"
            else (self.NEXT_PUBLIC_SUPABASE_URL or self.SUPABASE_URL)
        )

    @property
    def effective_supabase_publishable_key(self) -> str:
        """Resolve Supabase publishable key preferring new standard name with legacy fallbacks."""
        return (
            self.SUPABASE_PUBLISHABLE_KEY
            or self.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
            or (self.SUPABASE_ANON_KEY if self.SUPABASE_ANON_KEY != "placeholder-anon-key" else None)
            or self.NEXT_PUBLIC_SUPABASE_ANON_KEY
            or self.SUPABASE_ANON_KEY
        )

    @property
    def effective_supabase_secret_key(self) -> str:
        """Resolve Supabase secret key preferring SUPABASE_SECRET_KEY with fallback to SUPABASE_SERVICE_ROLE_KEY."""
        return (
            self.SUPABASE_SECRET_KEY
            or self.SUPABASE_SERVICE_ROLE_KEY
        )

    @property
    def effective_supabase_jwt_secret(self) -> str:
        """Resolve Supabase JWT signing secret."""
        return self.SUPABASE_JWT_SECRET

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")

    # Google Earth Engine
    GEE_PROJECT_ID: str = Field(default="")
    GEE_SERVICE_ACCOUNT_EMAIL: str = Field(default="")
    GEE_PRIVATE_KEY: str = Field(default="")

    # Weather & External Services
    OPENMETEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_CACHE_TTL_SECONDS: int = 1800
    # SMS & Notification Infrastructure (Zero-cost defaults)
    SMS_ENABLED: bool = Field(default=False)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None)
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None)
    TWILIO_PHONE_NUMBER: Optional[str] = Field(default=None)
    SMS_MAX_RETRIES: int = Field(default=3)
    SMS_REQUEST_TIMEOUT_SECONDS: float = Field(default=10.0)

    # WhatsApp Channel Infrastructure (Defaults to False, Twilio WhatsApp sender / templates)
    WHATSAPP_ENABLED: bool = Field(default=False)
    TWILIO_WHATSAPP_NUMBER: Optional[str] = Field(default=None)  # e.g., 'whatsapp:+14155238886'
    TWILIO_WHATSAPP_CONTENT_SID: Optional[str] = Field(default=None)  # Approved template SID for WhatsApp
    WHATSAPP_REQUEST_TIMEOUT_SECONDS: float = Field(default=10.0)

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
