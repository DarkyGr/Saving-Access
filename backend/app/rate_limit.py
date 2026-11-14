"""
Rate limiting (task 31.3) with slowapi.

- Anonymous endpoints (login, register, refresh) are limited per client IP.
- Endpoints that verify the *account password* (save, reveal, edit, delete)
  are limited per authenticated user, so a stolen access token cannot be
  used to brute-force the account password.

Configuration (env):
  RATE_LIMIT_ENABLED   "true" (default) / "false" — tests disable it
  RATE_LIMIT_STORAGE   limits storage URI, default "memory://". Use a shared
                       store such as "redis://host:6379" when running more
                       than one worker/process, otherwise each one counts
                       separately.
  RATE_LIMIT_LOGIN, RATE_LIMIT_REGISTER, RATE_LIMIT_REFRESH,
  RATE_LIMIT_ACCOUNT_PASSWORD  override the defaults below.
"""

import os

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

LOGIN_LIMIT = os.environ.get("RATE_LIMIT_LOGIN", "10/minute")
REGISTER_LIMIT = os.environ.get("RATE_LIMIT_REGISTER", "5/minute")
REFRESH_LIMIT = os.environ.get("RATE_LIMIT_REFRESH", "30/minute")
ACCOUNT_PASSWORD_LIMIT = os.environ.get("RATE_LIMIT_ACCOUNT_PASSWORD", "10/minute")


def _enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() not in {"0", "false", "no"}


def user_or_ip_key(request: Request) -> str:
    """Key by user_id from the bearer token when present, else by IP.

    The signature is not verified here (that happens in the endpoint's own
    dependency); an attacker forging a user_id only spends that user's quota
    on requests that will then fail authentication.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            claims = jwt.decode(auth[7:], options={"verify_signature": False})
            if "user_id" in claims:
                return f"user:{claims['user_id']}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE", "memory://"),
    enabled=_enabled(),
    headers_enabled=False,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait a minute and try again."},
        headers={"Retry-After": "60"},
    )
