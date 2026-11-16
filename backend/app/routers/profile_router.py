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
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import get_current_claims
from app.models import User, UserPreference
from app.phase2 import email_verification_enabled, is_deactivated, normalize_language
from app.rate_limit import ACCOUNT_PASSWORD_LIMIT, RESEND_VERIFICATION_LIMIT, limiter, user_or_ip_key
from app.security import hash_password, verify_password
from app.services.auth_service import validate_password_strength
from app.services.refresh_token_service import RefreshTokenService
from app.services.audit_service import AuditService
from app.services.security_notice import password_changed_email
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


class MeResponse(BaseModel):
    user_id: int
    user_code: str
    username: str
    display_name: str | None
    email: str
    role: str
    email_verified: bool
    preferences: PreferencesResponse


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
