"""
Profile router — the current user's role and permissions.

Endpoints:
  GET  /api/profile/permissions        → 200 {"role": str, "permissions": list[str]}
  GET  /api/profile/preferences        → 200 {"list_views": {...}} (task 37.2)
  PUT  /api/profile/preferences/list-view {"key", "view"} → 200, saved in the account
  PUT  /api/profile/preferences        theme, accent, start page, private mode, language (37.3)
  GET/PUT /api/profile/me              account data and display name (37.3)
  PUT  /api/profile/avatar/preset | /avatar/image, DELETE /avatar, GET /avatar/image
  POST /api/profile/password           change it (current one required; other sessions end)
  GET  /api/profile/sessions, DELETE /api/profile/sessions/{id}  active devices
  POST /api/profile/verification-email → 202, sends a new verification email
                                         (spec Phase 2, Requirement 2.8)

Used by the frontend ``ProtectedRoute`` and menu to decide which screens the
user may open (Requirement 3.5). The list is explicit for every role, Admin
included (task 37.1); the role is the one stored now, not the token's.
"""

import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import get_current_claims
from app.models import (
    AccountToken,
    Credential,
    EmailVerificationToken,
    RecoveryCode,
    RefreshToken,
    TrustedDevice,
    User,
    UserPreference,
)
from app.services.trusted_devices import TrustedDeviceService
from app.phase2 import email_verification_enabled, is_deactivated, normalize_language
from app.rate_limit import ACCOUNT_PASSWORD_LIMIT, RESEND_VERIFICATION_LIMIT, limiter, user_or_ip_key
from app.security import hash_password, verify_password
from app.services.auth_service import validate_password_strength
from app.services.refresh_token_service import RefreshTokenService
from app.services.audit_service import AuditService
from app.services.security_notice import (
    account_deleted_email,
    export_email,
    password_changed_email,
    recovery_codes_email,
    two_factor_enabled_email,
)
from app.services.encryptor_service import EncryptorService
from app.routers.credentials_router import _last_changed
from app.services.two_factor import TwoFactorService, two_factor_required
from app.services.system_settings import get_int
from app.services.email_sender import send_email
from app.services.email_verification_service import (
    EmailVerificationService,
    build_verification_email,
)
from app.permissions import permissions_for
from app.utils.audit_columns import set_creation_audit, set_modification_audit, utc_date_time

router = APIRouter()


class PermissionsResponse(BaseModel):
    role: str
    permissions: list[str]


@router.get(
    "/permissions",
    response_model=PermissionsResponse,
    summary="The current user's role and permissions",
)
def get_my_permissions(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PermissionsResponse:
    user = db.query(User.role).filter(User.user_id == claims["user_id"]).first()
    if user is None:
        # User deleted after the token was issued.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return PermissionsResponse(role=user.role, permissions=sorted(permissions_for(user.role)))


LIST_KEYS = ("credentials", "users")
THEMES = ("light", "dark", "system")
ACCENTS = ("indigo", "blue", "emerald", "violet", "rose", "amber")
START_PAGES = ("home", "credentials", "credentials-new")
AVATAR_PRESETS = (
    "key", "shield", "lock", "star", "sun", "moon", "leaf", "wave", "mountain", "rocket", "heart", "bolt",
)
# Built-in names only: letters (any language), digits, spaces and . , ' - _
DISPLAY_NAME = re.compile(r"^[\w .,'\-]{2,60}$", re.UNICODE)
AVATAR_MAX_BYTES = 256 * 1024
# The browser re-encodes the picture before upload; the server still checks
# the real format from its first bytes, never from the declared type.
_SIGNATURES = (
    ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ("image/webp", lambda b: len(b) > 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
)


class PreferencesResponse(BaseModel):
    list_views: dict[str, Literal["list", "grid"]]
    theme: Literal["light", "dark", "system"] = "system"
    accent: str = "indigo"
    start_page: str = "home"
    private_mode: bool = False
    language: str | None = None
    avatar_preset: str | None = None
    has_avatar_image: bool = False


class ListViewRequest(BaseModel):
    key: Literal["credentials", "users"]
    view: Literal["list", "grid"]


class PreferencesUpdate(BaseModel):
    """Only the fields sent are changed (Requirement 14.1–14.3)."""

    theme: Literal["light", "dark", "system"] | None = None
    accent: Literal["indigo", "blue", "emerald", "violet", "rose", "amber"] | None = None
    start_page: Literal["home", "credentials", "credentials-new"] | None = None
    private_mode: bool | None = None
    language: Literal["en", "es"] | None = None


def _known_views(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in LIST_KEYS and v in ("list", "grid")}


def _user(db: Session, claims: dict) -> User:
    user = db.query(User).filter(User.user_id == claims["user_id"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _prefs(db: Session, user_id: int, *, create: bool = False) -> UserPreference | None:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if pref is None and create:
        pref = UserPreference(
            user_id=user_id,
            list_views={},
            theme="system",
            accent="indigo",
            start_page="home",
            private_mode=False,
        )
        set_creation_audit(pref, user_id=user_id)
        db.add(pref)
    return pref


def _touch(db: Session, pref: UserPreference, user_id: int) -> None:
    """Modification audit columns, except on the row this request created."""
    if pref not in db.new:
        set_modification_audit(pref, user_id=user_id)


def _preferences_response(user: User, pref: UserPreference | None) -> PreferencesResponse:
    if pref is None:
        return PreferencesResponse(list_views={}, language=user.preferred_language)
    return PreferencesResponse(
        list_views=_known_views(pref.list_views),
        theme=pref.theme if pref.theme in THEMES else "system",
        accent=pref.accent if pref.accent in ACCENTS else "indigo",
        start_page=pref.start_page if pref.start_page in START_PAGES else "home",
        private_mode=bool(pref.private_mode),
        language=user.preferred_language,
        avatar_preset=pref.avatar_preset if pref.avatar_preset in AVATAR_PRESETS else None,
        has_avatar_image=pref.avatar_image is not None,
    )


@router.get(
    "/preferences",
    response_model=PreferencesResponse,
    summary="The current user's interface preferences",
)
def get_my_preferences(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    """Choices saved in the account (Requirements 13.4, 14); defaults until changed."""
    user = _user(db, claims)
    return _preferences_response(user, _prefs(db, user.user_id))


@router.put(
    "/preferences",
    response_model=PreferencesResponse,
    summary="Change theme, accent, start page, private mode or language",
)
def update_my_preferences(
    body: PreferencesUpdate,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    user = _user(db, claims)
    pref = _prefs(db, user.user_id, create=True)
    for field in ("theme", "accent", "start_page", "private_mode"):
        value = getattr(body, field)
        if value is not None:
            setattr(pref, field, value)
    if body.language is not None:
        user.preferred_language = body.language
        set_modification_audit(user, user_id=user.user_id)
    _touch(db, pref, user.user_id)
    db.commit()
    return _preferences_response(user, pref)


@router.put(
    "/preferences/list-view",
    response_model=PreferencesResponse,
    summary="Save list or grid for one listing",
)
def set_my_list_view(
    body: ListViewRequest,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    user = _user(db, claims)
    pref = _prefs(db, user.user_id, create=True)
    # A new dict, so SQLAlchemy sees the JSON column change.
    pref.list_views = {**_known_views(pref.list_views), body.key: body.view}
    _touch(db, pref, user.user_id)
    db.commit()
    return _preferences_response(user, pref)


# --- Profile (task 37.3, Requirement 14.1) ----------------------------------


class TwoFactorStatus(BaseModel):
    enabled: bool
    enabled_at: str | None
    recovery_codes_left: int
    required: bool


def _two_factor_status(db: Session, user: User) -> TwoFactorStatus:
    service = TwoFactorService(db)
    return TwoFactorStatus(
        enabled=service.enabled(user),
        enabled_at=user.totp_enabled_at.strftime("%Y-%m-%dT%H:%M:%SZ") if user.totp_enabled_at else None,
        recovery_codes_left=service.recovery_left(user),
        required=two_factor_required(),
    )


class MeResponse(BaseModel):
    user_id: int
    user_code: str
    username: str
    display_name: str | None
    email: str
    role: str
    email_verified: bool
    preferences: PreferencesResponse
    two_factor: TwoFactorStatus


class DisplayNameUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)


@router.get("/me", response_model=MeResponse, summary="The signed-in account and its preferences")
def get_me(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> MeResponse:
    user = _user(db, claims)
    return MeResponse(
        user_id=user.user_id,
        user_code=user.user_code,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        email_verified=bool(user.email_verified),
        preferences=_preferences_response(user, _prefs(db, user.user_id)),
        two_factor=_two_factor_status(db, user),
    )


@router.put("/me", response_model=MeResponse, summary="Change the display name (empty = use the username)")
def update_me(
    body: DisplayNameUpdate,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> MeResponse:
    user = _user(db, claims)
    name = (body.display_name or "").strip()
    if name and not DISPLAY_NAME.match(name):
        raise HTTPException(status_code=422, detail="Invalid display name.")
    user.display_name = name or None
    set_modification_audit(user, user_id=user.user_id)
    db.commit()
    return get_me(claims, db)


# --- Avatar -------------------------------------------------------------------


class AvatarPresetRequest(BaseModel):
    preset: str


@router.put("/avatar/preset", response_model=PreferencesResponse, summary="Use a built-in icon")
def set_avatar_preset(
    body: AvatarPresetRequest,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    if body.preset not in AVATAR_PRESETS:
        raise HTTPException(status_code=422, detail="Unknown avatar.")
    user = _user(db, claims)
    pref = _prefs(db, user.user_id, create=True)
    pref.avatar_preset = body.preset
    pref.avatar_image = None
    pref.avatar_mime = None
    _touch(db, pref, user.user_id)
    db.commit()
    return _preferences_response(user, pref)


@router.put("/avatar/image", response_model=PreferencesResponse, summary="Upload a picture (PNG, JPEG or WebP)")
async def set_avatar_image(
    request: Request,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    data = await request.body()
    if not data or len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The picture must be at most 256 KB.")
    mime = next((m for m, matches in _SIGNATURES if matches(data)), None)
    if mime is None:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG or WebP pictures.")
    user = _user(db, claims)
    pref = _prefs(db, user.user_id, create=True)
    pref.avatar_image = data
    pref.avatar_mime = mime
    pref.avatar_preset = None
    _touch(db, pref, user.user_id)
    db.commit()
    return _preferences_response(user, pref)


@router.delete("/avatar", response_model=PreferencesResponse, summary="Back to the initials")
def clear_avatar(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> PreferencesResponse:
    user = _user(db, claims)
    pref = _prefs(db, user.user_id)
    if pref is not None:
        pref.avatar_preset = None
        pref.avatar_image = None
        pref.avatar_mime = None
        _touch(db, pref, user.user_id)
        db.commit()
    return _preferences_response(user, pref)


@router.get("/avatar/image", summary="The uploaded picture")
def get_avatar_image(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> Response:
    pref = _prefs(db, claims["user_id"])
    if pref is None or pref.avatar_image is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(
        content=pref.avatar_image,
        media_type=pref.avatar_mime or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
            "Cache-Control": "no-store",
        },
    )


# --- Password (Requirement 14.4) ----------------------------------------------


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)
    new_password_confirmation: str = Field(max_length=256)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, summary="Change the account password")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def change_password(
    request: Request,
    body: PasswordChangeRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Response:
    """Needs the current password; applies the sign-up policy; ends every other
    session (this one stays) and emails a security notice."""
    user = _user(db, claims)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Account password verification failed.")
    if body.new_password != body.new_password_confirmation:
        raise HTTPException(status_code=400, detail="Password and password confirmation do not match.")
    errors = validate_password_strength(body.new_password)
    if errors:
        raise HTTPException(status_code=400, detail={"password_errors": errors})
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The new password must be different.")
    user.password_hash = hash_password(body.new_password)
    set_modification_audit(user, user_id=user.user_id)
    RefreshTokenService(db).revoke_all(user.user_id, keep_family=claims.get("sid"))
    TrustedDeviceService(db).forget_all(user.user_id)  # Requirement 21.4
    AuditService(db).log(user.user_id, "UPDATE", user.user_id, commit=False, action="account.password")
    db.commit()
    background_tasks.add_task(send_email, password_changed_email(user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Active sessions (Requirement 14.5) ----------------------------------------


class SessionItem(BaseModel):
    session_id: str
    user_agent: str | None
    client_ip: str | None
    started: str
    last_active: str
    current: bool


def _iso(value) -> str:
    return value.isoformat(timespec="seconds") + "Z"


@router.get("/sessions", response_model=list[SessionItem], summary="Devices where the account is signed in")
def list_sessions(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> list[SessionItem]:
    current = claims.get("sid")
    return [
        SessionItem(
            session_id=s["session_id"],
            user_agent=s["user_agent"],
            client_ip=s["client_ip"],
            started=_iso(s["started"]),
            last_active=_iso(s["last_active"]),
            current=s["session_id"] == current,
        )
        for s in RefreshTokenService(db).active_sessions(claims["user_id"])
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a session on another device",
)
def end_session(
    session_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Response:
    """The current session ends with Log out instead (it also clears the cookie)."""
    if session_id == claims.get("sid"):
        raise HTTPException(status_code=400, detail="Use Log out to end this session.")
    if not RefreshTokenService(db).revoke_family(session_id, claims["user_id"]):
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ResendVerificationRequest(BaseModel):
    language: str | None = Field(default=None, max_length=8)


@router.post(
    "/verification-email",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a new email verification link",
)
@limiter.limit(RESEND_VERIFICATION_LIMIT, key_func=user_or_ip_key)
def resend_verification_email(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ResendVerificationRequest | None = None,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> dict:
    """Issue a new link without changing the deactivation deadline
    (Requirement 2.8). 404 when email verification is off, 409 when the
    email is already verified, 403 when the account is deactivated."""
    if not email_verification_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    user = db.query(User).filter(User.user_id == claims["user_id"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if user.email_verified:
        raise HTTPException(status_code=409, detail="Email already verified.")
    if is_deactivated(user, utc_date_time()[0]):
        raise HTTPException(status_code=403, detail="Account deactivated.")
    language = normalize_language(body.language if body else None)
    if language:
        user.preferred_language = language
    raw = EmailVerificationService(db).issue(user)
    db.commit()
    background_tasks.add_task(send_email, build_verification_email(user, raw, language))
    return {"detail": "Verification email sent."}


# --- Two-factor authentication (task 37.5, Requirement 16.1) -------------------


class TwoFactorSetupRequest(BaseModel):
    account_password: str = Field(max_length=256)


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TwoFactorCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class RecoveryCodesRequest(BaseModel):
    account_password: str = Field(max_length=256)
    code: str = Field(min_length=1, max_length=32)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


def _check_password(user: User, raw: str) -> None:
    if not verify_password(raw, user.password_hash):
        raise HTTPException(status_code=401, detail="Account password verification failed.")


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse, summary="Start setting up 2FA (new device)")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def two_factor_setup(
    request: Request,
    body: TwoFactorSetupRequest,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> TwoFactorSetupResponse:
    """Needs the account password. The current second factor keeps working
    until the new one is confirmed with a code."""
    user = _user(db, claims)
    _check_password(user, body.account_password)
    secret, uri = TwoFactorService(db).start_setup(user)
    db.commit()
    return TwoFactorSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/confirm", response_model=RecoveryCodesResponse, summary="Turn the new 2FA device on")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def two_factor_confirm(
    request: Request,
    body: TwoFactorCodeRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> RecoveryCodesResponse:
    """A code from the new device switches to it and issues 10 new recovery
    codes (shown once); a security notice is emailed (Requirement 16.7)."""
    user = _user(db, claims)
    codes = TwoFactorService(db).confirm_setup(user, body.code)
    if codes is None:
        raise HTTPException(status_code=400, detail="Invalid code.")
    TrustedDeviceService(db).forget_all(user.user_id)  # Requirement 21.4: new phone
    set_modification_audit(user, user_id=user.user_id)
    AuditService(db).log(user.user_id, "UPDATE", user.user_id, commit=False, action="account.2fa_setup")
    db.commit()
    background_tasks.add_task(send_email, two_factor_enabled_email(user))
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesResponse, summary="Replace the recovery codes")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def two_factor_recovery_codes(
    request: Request,
    body: RecoveryCodesRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> RecoveryCodesResponse:
    """Needs the account password and a current code; the old codes stop
    working. A security notice is emailed (Requirement 16.7)."""
    user = _user(db, claims)
    _check_password(user, body.account_password)
    service = TwoFactorService(db)
    if not service.enabled(user):
        raise HTTPException(status_code=409, detail="Two-factor authentication is not set up.")
    if service.check(user, body.code, allow_recovery=False) is None:
        raise HTTPException(status_code=400, detail="Invalid code.")
    codes = service.new_recovery_codes(user)
    AuditService(db).log(user.user_id, "UPDATE", user.user_id, commit=False, action="account.recovery_codes")
    db.commit()
    background_tasks.add_task(send_email, recovery_codes_email(user))
    return RecoveryCodesResponse(recovery_codes=codes)


# --- Session limits and re-authentication (task 37.5, Requirement 16.4–16.5) ---


class SessionLimits(BaseModel):
    idle_seconds: int
    expires_in_seconds: int | None
    extend_minutes: int
    reauth_minutes: int


def _live_session(db: Session, claims: dict):
    sid = claims.get("sid")
    row = RefreshTokenService(db).live(sid, claims["user_id"]) if sid else None
    if row is None:
        raise HTTPException(status_code=401, detail="Session expired.")
    return row


def _limits(db: Session, row) -> SessionLimits:
    now = datetime.now(UTC).replace(tzinfo=None)
    left = int((row.session_expires_at - now).total_seconds()) if row.session_expires_at else None
    return SessionLimits(
        idle_seconds=get_int(db, "session_idle_minutes") * 60,
        expires_in_seconds=max(left, 0) if left is not None else None,
        extend_minutes=get_int(db, "session_extend_minutes"),
        reauth_minutes=get_int(db, "admin_reauth_minutes"),
    )


@router.get("/session", response_model=SessionLimits, summary="This session's limits")
def session_limits(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> SessionLimits:
    """Seconds, not timestamps, so the browser's clock does not matter."""
    return _limits(db, _live_session(db, claims))


@router.post("/session/ping", status_code=status.HTTP_204_NO_CONTENT, summary="Activity in the browser")
def session_ping(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> Response:
    """Sent at most once a minute while the person uses any tab; without it
    the session ends after ``session_idle_minutes``."""
    row = _live_session(db, claims)
    RefreshTokenService(db).touch(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/session/extend", response_model=SessionLimits, summary="Push the maximum length back")
def session_extend(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> SessionLimits:
    row = _live_session(db, claims)
    RefreshTokenService(db).extend(row)
    db.commit()
    return _limits(db, row)


class ReauthRequest(BaseModel):
    account_password: str = Field(max_length=256)


@router.post("/session/reauth", status_code=status.HTTP_204_NO_CONTENT, summary="Confirm the password for administration")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def session_reauth(
    request: Request,
    body: ReauthRequest,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Response:
    user = _user(db, claims)
    row = _live_session(db, claims)
    _check_password(user, body.account_password)
    RefreshTokenService(db).mark_reauth(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Export my data and delete my account (task 35.8, Requirement 19) ----------


class SensitiveRequest(BaseModel):
    account_password: str = Field(max_length=256)
    # Required when two-step verification is on (app code, not a recovery code).
    code: str | None = Field(default=None, max_length=32)


class ExportRequest(SensitiveRequest):
    format: Literal["csv", "json"] = "csv"


class DeleteAccountRequest(SensitiveRequest):
    confirm_username: str = Field(max_length=64)


def _check_sensitive(db: Session, user: User, body: SensitiveRequest) -> None:
    """Account password, plus a current app code when 2FA is on."""
    _check_password(user, body.account_password)
    two_factor = TwoFactorService(db)
    if two_factor.enabled(user) and (
        not body.code or two_factor.check(user, body.code, allow_recovery=False) is None
    ):
        raise HTTPException(status_code=400, detail="Invalid code.")


def _cell(value: str) -> str:
    """Keep a spreadsheet from running a name or login as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.post("/export", summary="Download all my saved credentials")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def export_credentials(
    request: Request,
    body: ExportRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Response:
    """Requirement 19.1. The file is plain text by nature: the response is
    never cached, the export is audited and the owner gets an email."""
    import csv
    import io
    import json

    user = _user(db, claims)
    _check_sensitive(db, user, body)
    encryptor = EncryptorService()
    rows = (
        db.query(Credential)
        .filter(Credential.user_id == user.user_id)
        .order_by(Credential.website_name, Credential.credential_id)
        .all()
    )
    items = [
        {
            "website_name": row.website_name,
            "email_or_username": row.email_or_username,
            "is_username_login": bool(row.is_username_login),
            "password": encryptor.decrypt(row.encrypted_password),
            "last_changed": _last_changed(row),
        }
        for row in rows
    ]
    day = utc_date_time()[0].strftime("%Y%m%d")
    if body.format == "json":
        content = json.dumps({"exported_at": utc_date_time()[0].isoformat(), "credentials": items}, ensure_ascii=False, indent=2)
        media, name = "application/json", f"save-pass-export-{day}.json"
    else:
        out = io.StringIO()
        writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(["website_name", "email_or_username", "is_username_login", "password", "last_changed"])
        for item in items:
            # The password is written exactly as saved, so another manager imports it unchanged.
            writer.writerow([
                _cell(item["website_name"]), _cell(item["email_or_username"]),
                "yes" if item["is_username_login"] else "no", item["password"], item["last_changed"],
            ])
        content = out.getvalue()
        media, name = "text/csv", f"save-pass-export-{day}.csv"
    AuditService(db).log(
        user.user_id, "SELECT", None, commit=False, action="account.export", detail=f"{len(items)} {body.format}"
    )
    db.commit()
    background_tasks.add_task(send_email, export_email(user))
    return Response(
        content=content.encode("utf-8"),
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT, summary="Delete my account")
@limiter.limit(ACCOUNT_PASSWORD_LIMIT, key_func=user_or_ip_key)
def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Response:
    """Requirement 19.2–19.4. Everything personal is erased; the row stays
    anonymised (no name, email or usable password) so the audit log keeps who
    did what. The username and email become free. The last Admin cannot."""
    import secrets as _secrets

    user = _user(db, claims)
    _check_sensitive(db, user, body)
    if body.confirm_username.strip() != user.username:
        raise HTTPException(status_code=400, detail="Type your username to confirm.")
    if user.role == "Admin":
        others = (
            db.query(User)
            .filter(User.role == "Admin", User.user_id != user.user_id, User.deleted_at.is_(None))
            .count()
        )
        if others == 0:
            raise HTTPException(status_code=409, detail="The last Admin cannot delete their account.")

    notice = account_deleted_email(user)
    for model in (Credential, UserPreference, RefreshToken, RecoveryCode, AccountToken, EmailVerificationToken, TrustedDevice):
        db.query(model).filter(model.user_id == user.user_id).delete(synchronize_session=False)
    AuditService(db).log(user.user_id, "DELETE", user.user_id, commit=False, action="account.delete")
    tag = f"deleted-{user.user_code}"
    user.username = tag
    user.email = f"{tag.lower()}@deleted.invalid"
    user.password_hash = hash_password(_secrets.token_urlsafe(32))
    user.display_name = None
    user.role = "User"
    user.email_verified = False
    user.preferred_language = None
    user.totp_secret = None
    user.totp_pending_secret = None
    user.totp_enabled_at = None
    user.totp_last_step = None
    user.locked_at = None
    user.failed_attempts = 0
    user.deleted_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    set_modification_audit(user, user_id=user.user_id)
    db.commit()
    background_tasks.add_task(send_email, notice)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Trusted devices (Requirement 21) -----------------------------------------


class TrustedDeviceItem(BaseModel):
    device_id: int
    user_agent: str | None
    trusted_at: str
    expires_at: str
    last_used_at: str | None


def _iso_z(value) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


@router.get("/trusted-devices", response_model=list[TrustedDeviceItem], summary="Browsers that skip the two-step code")
def trusted_devices(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> list[TrustedDeviceItem]:
    return [
        TrustedDeviceItem(
            device_id=row.trusted_device_id,
            user_agent=row.user_agent,
            trusted_at=_iso_z(row.trusted_at),
            expires_at=_iso_z(row.expires_at),
            last_used_at=_iso_z(row.last_used_at),
        )
        for row in TrustedDeviceService(db).list(claims["user_id"])
    ]


@router.delete("/trusted-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Forget one trusted device")
def forget_trusted_device(device_id: int, claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> Response:
    if not TrustedDeviceService(db).forget(device_id, claims["user_id"]):
        raise HTTPException(status_code=404, detail="Not found.")
    AuditService(db).log(claims["user_id"], "DELETE", device_id, commit=False, action="account.forget_devices", detail="1")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trusted-devices", status_code=status.HTTP_204_NO_CONTENT, summary="Forget every trusted device")
def forget_all_trusted_devices(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> Response:
    count = TrustedDeviceService(db).forget_all(claims["user_id"])
    AuditService(db).log(claims["user_id"], "DELETE", None, commit=False, action="account.forget_devices", detail=str(count))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

