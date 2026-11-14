"""
Auth router — registration, login, session refresh and logout.

Endpoints:
  POST /api/auth/register  → 201 {user_id, username, role}
  POST /api/auth/login     → 200 {access_token, token_type, expires_in}
                             + Set-Cookie refresh token (httpOnly)
  POST /api/auth/refresh   → 200 {access_token, ...} + rotated cookie, or 401
  POST /api/auth/logout    → 204, revokes the refresh token and clears the cookie

The access token is returned in the body and kept in React memory only. The
refresh token travels exclusively in an httpOnly cookie scoped to
``/api/auth`` (task 31.5), so JavaScript can never read it.

Cookie settings (env):
  COOKIE_SECURE    "true" (default). Browsers accept Secure cookies on
                   http://localhost; set "false" only for plain-HTTP hosts
                   other than localhost.
  COOKIE_SAMESITE  "strict" (default) | "lax" | "none" — use "none" (with
                   Secure) only if frontend and API are on different sites.

Requirements: 1.1–1.8, 2.1–2.5
"""

import os

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.rate_limit import LOGIN_LIMIT, REFRESH_LIMIT, REGISTER_LIMIT, limiter
from app.services.auth_service import AuthService
from app.services.refresh_token_service import RefreshTokenService, refresh_lifetime

router = APIRouter()

REFRESH_COOKIE = "sp_refresh"
_COOKIE_PATH = "/api/auth"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirmation: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterResponse(BaseModel):
    user_id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        max_age=int(refresh_lifetime().total_seconds()),
        path=_COOKIE_PATH,
        httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
        samesite=os.environ.get("COOKIE_SAMESITE", "strict").lower(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=_COOKIE_PATH)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@limiter.limit(REGISTER_LIMIT)
def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """Create a new user account (400/422 on validation or uniqueness failure)."""
    user = AuthService(db).register(body.model_dump())
    return RegisterResponse(user_id=user.user_id, username=user.username, role=user.role)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive an access token",
)
@limiter.limit(LOGIN_LIMIT)
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Authenticate with username and password.

    Returns a 15-minute access JWT and sets the refresh cookie. Any failure
    returns the same generic 401 (Requirement 2.3).
    """
    service = AuthService(db)
    token_data = service.login(body.model_dump())
    user_id = service.verify_token(token_data["access_token"])["user_id"]
    raw_refresh = RefreshTokenService(db).issue(user_id)
    db.commit()
    _set_refresh_cookie(response, raw_refresh)
    return LoginResponse(**token_data)


@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange the refresh cookie for a new access token",
)
@limiter.limit(REFRESH_LIMIT)
def refresh(
    request: Request,
    response: Response,
    sp_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> LoginResponse | JSONResponse:
    """Rotate the refresh cookie and return a new access token.

    401 when the cookie is missing, unknown, expired or already used.
    """
    result = RefreshTokenService(db).rotate(sp_refresh) if sp_refresh else None
    if result is None:
        expired = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Session expired."},
        )
        _clear_refresh_cookie(expired)
        return expired
    user, new_raw = result
    _set_refresh_cookie(response, new_raw)
    return LoginResponse(**AuthService(db).issue_access_token(user))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the refresh token and clear the cookie",
)
def logout(
    response: Response,
    sp_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Response:
    if sp_refresh:
        RefreshTokenService(db).revoke(sp_refresh)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
