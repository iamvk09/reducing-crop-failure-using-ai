"""FastAPI application entrypoint for Crop Risk Intelligence API."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.routes import auth, experts, farms, health, neuro_fuzzy, notifications, predictions, recommendations, weather
from backend.app.core.config import settings
from backend.app.core.logging import logger

from contextlib import asynccontextmanager

from backend.app.core.supabase import supabase_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle events."""
    logger.info(f"Starting {settings.APP_NAME} in '{settings.APP_ENV}' mode.")
    # Fail-fast guard against running in production without persistent storage
    supabase_client.validate_production_configuration()
    # Warm up ML runtime artifacts for non-testing environments to eliminate cold-start spikes
    if settings.APP_ENV != "testing":
        try:
            from backend.app.services.prediction_service import prediction_service
            prediction_service.warmup_artifacts()
        except Exception as exc:
            logger.warning("Startup model warmup skipped or deferred: %s", exc)
    yield
    logger.info(f"Shutting down {settings.APP_NAME}.")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="Backend API for real-time crop failure risk prediction, advisories, digital twin simulations, and live weather telemetry.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# -----------------------------------------------------------------------------
# Security & Correlation ID Middleware
import re
import uuid

_SAFE_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")

@app.middleware("http")
async def security_and_correlation_headers_middleware(request: Request, call_next):
    """Inject security headers and correlation ID to all API responses."""
    raw_id = request.headers.get("X-Request-ID")
    if raw_id and _SAFE_REQUEST_ID_REGEX.match(raw_id):
        request_id = raw_id
    else:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Modern APIs use CSP frame-ancestors rather than legacy X-XSS-Protection.
    # Documentation interfaces (/docs, /redoc) require CDN bundles, fonts, and inline styles.
    # All other API routes strictly enforce default-src 'none'.
    path = request.url.path.rstrip("/")
    if path in ("/docs", "/redoc"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


# -----------------------------------------------------------------------------
# CORS Middleware
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Global Exception Handlers (Never expose internal stack traces to users)
# -----------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle standard HTTP exceptions with structured JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request payload schema validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Invalid request payload schema or parameters.",
            "errors": jsonable_encoder(exc.errors()),
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler ensuring stack traces are logged but not leaked."""
    logger.exception(f"Unhandled server error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred. Please try again later.",
            "status_code": 500,
        },
    )


# -----------------------------------------------------------------------------
# Route Registration
# -----------------------------------------------------------------------------
# Root-level health check (e.g. for container orchestrators / load balancers)
app.include_router(health.router)

# Versioned API v1 Router
API_V1_PREFIX = f"/api/{settings.API_VERSION}"
app.include_router(health.router, prefix=API_V1_PREFIX)
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(farms.router, prefix=API_V1_PREFIX)
app.include_router(predictions.router, prefix=API_V1_PREFIX)
app.include_router(recommendations.router, prefix=API_V1_PREFIX)
app.include_router(experts.router, prefix=API_V1_PREFIX)
app.include_router(neuro_fuzzy.router, prefix=API_V1_PREFIX)
app.include_router(notifications.router, prefix=API_V1_PREFIX)
app.include_router(weather.router, prefix=API_V1_PREFIX)
