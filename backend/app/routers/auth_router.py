"""
Auth router — registration, login, session refresh and logout.

Endpoints:
  POST /api/auth/register  → 201 {user_id, username, role}
  POST /api/auth/login     → 200 {access_token, token_type, expires_in}
                             + Set-Cookie refresh token (httpOnly)
  POST /api/auth/refresh   → 200 {access_token, ...} + rotated cookie, or 401
  POST /api/auth/logout    → 204, revokes the refresh token and clears the cookie
  GET  /api/auth/config    → 200 {captcha_site_key, email_verification}
  POST /api/auth/verify-email → 200, consumes a verification link (spec Phase 2)
  POST /api/auth/unlock    → 200, consumes an emailed unlock link (task 37.5)

The access token is returned in the body and kept in React memory only. The
refresh token travels exclusively in an httpOnly cookie scoped to
``/api/auth`` (task 31.5), so JavaScript can never read it.

Cookie settings (env):
  COOKIE_SECURE    "true" (default). Browsers accept Secure cookies on
                   http://localhost; set "false" only for plain-HTTP hosts
                   other than localhost.
  COOKIE_SAMESITE  "strict" (default) | "lax" | "none" — use "none" (with
                   Secure) only if frontend and API are on different sites.

Requirements: 1.1–1.10, 2.1–2.9
"""

import os

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.phase2 import (
    captcha_enabled,
    captcha_site_key,
    email_verification_enabled,
    normalize_language,
)
from app.rate_limit import (
    LOGIN_LIMIT,
    REFRESH_LIMIT,
    REGISTER_LIMIT,
    VERIFY_EMAIL_LIMIT,
    client_ip,
    limiter,
)
from app.services.account_token_service import AccountTokenService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.captcha_service import verify_captcha
from app.services.email_sender import send_email
from app.services.email_verification_service import (
    EmailVerificationService,
    VerifyResult,
    build_verification_email,
)
from app.services.refresh_token_service import RefreshTokenService, refresh_lifetime

router = APIRouter()

REFRESH_COOKIE = "sp_refresh"
CAPTCHA_FAILED = "CAPTCHA verification failed."
INVALID_VERIFICATION_LINK = "Invalid or expired verification link."
_COOKIE_PATH = "/api/auth"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirmation: str
    # UI language for the verification email ("en" / "es").
    language: str | None = Field(default=None, max_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str
    # hCaptcha response token; required only when CAPTCHA is configured.
    captcha_token: str | None = Field(default=None, max_length=4096)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class AuthConfigResponse(BaseModel):
    captcha_site_key: str | None
    email_verification: bool


class RegisterResponse(BaseModel):
    user_id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    email_verification_required: bool = False
    deactivation_deadline: str | None = None


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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """Create a new user account (400/422 on validation or uniqueness failure).

    With email verification on, a verification email is sent after the
    response (Requirement 1.10); a delivery failure does not undo sign-up.
    """
    user = AuthService(db).register(body.model_dump(exclude={"language"}))
    language = normalize_language(body.language)
    if language:
        user.preferred_language = language
    AuditService(db).log(user.user_id, "INSERT", user.user_id, commit=False, action="account.register")
    db.commit()
    if email_verification_enabled():
        raw = EmailVerificationService(db).issue(user)
        db.commit()
        background_tasks.add_task(send_email, build_verification_email(user, raw, body.language))
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
) -> LoginResponse | JSONResponse:
    """Authenticate with username and password.

    Returns a 15-minute access JWT and sets the refresh cookie. Any failure
    returns the same generic 401 (Requirement 2.3). With CAPTCHA configured
    the challenge must pass first (400, Requirement 2.6); an unverified
    account past its deadline gets 403 (Requirement 2.9).
    """
    if captcha_enabled() and not verify_captcha(
        body.captcha_token, request.client.host if request.client else None
    ):
        raise HTTPException(status_code=400, detail=CAPTCHA_FAILED)
    service = AuthService(db)
    try:
        token_data = service.login(body.model_dump(exclude={"captcha_token"}))
    except HTTPException as error:
        notice = getattr(service, "lock_notice", None)
        if notice is None:
            raise
        # The lock email goes out after the (still generic) response.
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
            background=BackgroundTask(send_email, notice),
        )
    user_id = service.verify_token(token_data["access_token"])["user_id"]
    sessions = RefreshTokenService(db)
    raw_refresh = sessions.issue(
        user_id, user_agent=request.headers.get("user-agent"), client_ip=client_ip(request)
    )
    AuditService(db).log(user_id, "SELECT", user_id, commit=False, action="account.login")
    db.commit()
    _set_refresh_cookie(response, raw_refresh)
    user = db.query(User).filter(User.user_id == user_id).one()
    # Same body, now bound to the new session (sid, task 37.3).
    return LoginResponse(**service.issue_access_token(user, session_id=sessions.last_family_id))


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
    sessions = RefreshTokenService(db)
    result = (
        sessions.rotate(sp_refresh, user_agent=request.headers.get("user-agent"), client_ip=client_ip(request))
        if sp_refresh
        else None
    )
    if result is None:
        expired = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Session expired."},
        )
        _clear_refresh_cookie(expired)
        return expired
    user, new_raw = result
    _set_refresh_cookie(response, new_raw)
    return LoginResponse(**AuthService(db).issue_access_token(user, session_id=sessions.last_family_id))


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


@router.get(
    "/config",
    response_model=AuthConfigResponse,
    summary="Public settings the login and sign-up pages need",
)
def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(
        captcha_site_key=captcha_site_key(),
        email_verification=email_verification_enabled(),
    )


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    summary="Consume an email verification link",
)
@limiter.limit(VERIFY_EMAIL_LIMIT)
def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> dict:
    """200 when verified; 400 for an unknown, used or expired link; 403 when
    the account was already deactivated (Requirements 1.10, 2.9)."""
    if not email_verification_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    result = EmailVerificationService(db).verify(body.token)
    if result is VerifyResult.DEACTIVATED:
        raise HTTPException(status_code=403, detail="Account deactivated.")
    if result is VerifyResult.INVALID:
        raise HTTPException(status_code=400, detail=INVALID_VERIFICATION_LINK)
    return {"detail": "Email verified."}


@router.post(
    "/unlock",
    status_code=status.HTTP_200_OK,
    summary="Consume an emailed unlock link",
)
@limiter.limit(VERIFY_EMAIL_LIMIT)
def unlock_account(
    request: Request,
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 16.2: the link from the lock email unlocks the account
    (once, within 24 hours). 400 for an unknown, used or expired link."""
    user = AccountTokenService(db).consume(body.token, "unlock")
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")
    user.locked_at = None
    user.failed_attempts = 0
    AuditService(db).log(user.user_id, "UPDATE", user.user_id, commit=False, action="account.unlock")
    db.commit()
    return {"detail": "Account unlocked."}
