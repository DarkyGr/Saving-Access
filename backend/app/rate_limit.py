"""
Rate limiting (task 31.3) with slowapi.

- Anonymous endpoints (login, register, refresh) are limited per client IP.
- Endpoints that verify the *account password* (save, reveal, edit, delete)
  are limited per authenticated user, so a stolen access token cannot be
  used to brute-force the account password.

Configuration (env):
  RATE_LIMIT_ENABLED   "true" (default) / "false" — tests disable it
  RATE_LIMIT_STORAGE   limits storage URI, default "memory://". Use a shared
                       store such as "redis://host:6379/0" when running more
                       than one worker/process, otherwise each one counts
                       separately. Production uses the compose "redis"
                       service (task 34.2).
  RATE_LIMIT_FALLBACK  limit applied per client IP, in memory, while the
                       shared store is unreachable (default "60/minute"), so
                       a Redis outage neither takes the API down nor removes
                       brute-force protection entirely.
  RATE_LIMIT_LOGIN, RATE_LIMIT_REGISTER, RATE_LIMIT_REFRESH,
  RATE_LIMIT_ACCOUNT_PASSWORD, RATE_LIMIT_VERIFY_EMAIL,
  RATE_LIMIT_RESEND_VERIFICATION  override the defaults below.
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
VERIFY_EMAIL_LIMIT = os.environ.get("RATE_LIMIT_VERIFY_EMAIL", "10/minute")
RESEND_VERIFICATION_LIMIT = os.environ.get("RATE_LIMIT_RESEND_VERIFICATION", "3/hour")


def _enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() not in {"0", "false", "no"}


_LOOPBACK = {"127.0.0.1", "::1"}


def client_ip(request: Request) -> str:
    """The device's address, for per-IP limits.

    Behind IIS on the same machine (local installation, task 36) every request
    comes from 127.0.0.1 and ARR's X-Forwarded-For carries "ip:port", so the
    site sets ``CLIENT_IP_HEADER`` (X-Client-IP) to the connection's address,
    overwriting whatever the browser sent. The header is trusted only when the
    peer is this machine; otherwise (Docker behind Caddy, which uses
    --proxy-headers) the connection's address is used as before.
    """
    peer = get_remote_address(request)
    header = os.environ.get("CLIENT_IP_HEADER", "").strip()
    if header and peer in _LOOPBACK:
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return peer


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
    return f"ip:{client_ip(request)}"


STORAGE_URI = os.environ.get("RATE_LIMIT_STORAGE", "memory://")
FALLBACK_LIMIT = os.environ.get("RATE_LIMIT_FALLBACK", "60/minute")

def build_limiter(storage_uri: str = STORAGE_URI, fallback: str = FALLBACK_LIMIT) -> Limiter:
    """Limiter on *storage_uri*; a shared store falls back to memory when down."""
    shared = not storage_uri.startswith("memory://")
    # slowapi turns the fallback on whenever a fallback list is given.
    return Limiter(
        key_func=client_ip,
        storage_uri=storage_uri,
        enabled=_enabled(),
        headers_enabled=False,
        in_memory_fallback_enabled=shared,
        in_memory_fallback=[fallback] if shared else [],
    )


limiter = build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait a minute and try again."},
        headers={"Retry-After": "60"},
    )
