"""
FastAPI application entry point for the password manager.

Responsibilities:
  - Instantiate the FastAPI app
  - Register CORSMiddleware with allowed origins from CORS_ORIGINS env var
  - Register global exception handlers for 401, 403, 404, 422, and 500
  - On startup validate security settings and seed default profiles
    (the schema itself is managed by Alembic)

Requirements 8.4 (HTTPS / CORS) and 8.6 (ORM / parameterized queries).
"""

import logging
import os
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env file variables before accessing any env vars.
# This is a no-op when the variables are already present in the environment.
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup checks and seed data.

    - Refuse to start with missing or weak secrets (task 31.1).
    - The schema is managed by Alembic (``alembic upgrade head``, task 31.6);
      the app no longer creates tables itself.
    - Seed the default profiles (idempotent).
    """
    from app.database import SessionLocal
    from app.security import validate_settings
    from app.seed import seed_default_profiles

    validate_settings()

    db = SessionLocal()
    try:
        seed_default_profiles(db)
    except Exception:  # noqa: BLE001 — e.g. migrations not applied yet
        logger.exception(
            "Could not seed default profiles. Did you run 'alembic upgrade head'?"
        )
    finally:
        db.close()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Save-Pass Password Manager",
    version="1.0.0",
    # Disable automatic /docs and /redoc in production so internal API
    # details are not exposed.  Can be toggled via env if needed.
    docs_url="/docs" if os.getenv("ENVIRONMENT", "development") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT", "development") != "production" else None,
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------
# CORS_ORIGINS is a comma-separated list of allowed origins, e.g.:
#   CORS_ORIGINS=http://localhost:5173,https://example.com
#
# Requirement 8.4 — backend configured to allow only the known frontend origin.

_raw_origins: str = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = [
    origin.strip() for origin in _raw_origins.split(",") if origin.strip()
]

# Rate limiting (task 31.3)
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.rate_limit import limiter, rate_limit_exceeded_handler  # noqa: E402

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------
# Each handler returns the exact JSON shape defined in the design document.
# Stack traces are written to server logs only — never to HTTP responses.


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Intercept all HTTPExceptions and map them to the standard JSON shapes
    defined in the design's Error Handling table.

    - 401 responses fall through to the default detail set by the raising code
      (e.g. "Not authenticated.", "Token expired.",
      "Account password verification failed.") — these are already specific.
    - 403 maps to "Forbidden." or "Access denied." depending on context.
    - 404 maps to "Not found."
    - Any other status code returns the original detail.
    """
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        detail = "Not found."
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        # The raising code sets a specific message when appropriate
        # ("Forbidden." vs "Access denied."); honour it if present.
        detail = exc.detail if exc.detail else "Forbidden."
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # The raising code is expected to supply the correct specific message.
        detail = exc.detail if exc.detail else "Not authenticated."
    else:
        detail = exc.detail

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Pydantic / FastAPI request validation errors (HTTP 422).

    Returns the standard Pydantic error detail structure so clients can
    identify exactly which fields failed validation.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected server errors (HTTP 500).

    - Full traceback is written to the server log for debugging.
    - Only a generic message is returned to the client — no stack trace is
      exposed in the HTTP response, in any environment.

    Requirement 8.6 (data security) — internal details must not leak.
    """
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.routers.admin_router import router as admin_router  # noqa: E402
from app.routers.auth_router import router as auth_router  # noqa: E402
from app.routers.credentials_router import router as credentials_router  # noqa: E402
from app.routers.profile_router import router as profile_router  # noqa: E402

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(credentials_router, prefix="/api/credentials", tags=["credentials"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(profile_router, prefix="/api/profile", tags=["profile"])
