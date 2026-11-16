"""
Profile router — the current user's role and permissions.

Endpoints:
  GET  /api/profile/permissions        → 200 {"role": str, "permissions": list[str]}
  GET  /api/profile/preferences        → 200 {"list_views": {...}} (task 37.2)
  PUT  /api/profile/preferences/list-view {"key", "view"} → 200, saved in the account
  POST /api/profile/verification-email → 202, sends a new verification email
                                         (spec Phase 2, Requirement 2.8)

Used by the frontend ``ProtectedRoute`` and menu to decide which screens the
user may open (Requirement 3.5). The list is explicit for every role, Admin
included (task 37.1); the role is the one stored now, not the token's.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import get_current_claims
from app.models import User, UserPreference
from app.phase2 import email_verification_enabled, is_deactivated, normalize_language
from app.rate_limit import RESEND_VERIFICATION_LIMIT, limiter, user_or_ip_key
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


class PreferencesResponse(BaseModel):
    list_views: dict[str, Literal["list", "grid"]]


class ListViewRequest(BaseModel):
    key: Literal["credentials", "users"]
    view: Literal["list", "grid"]


def _known_views(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in LIST_KEYS and v in ("list", "grid")}


@router.get(
    "/preferences",
    response_model=PreferencesResponse,
    summary="The current user's interface preferences",
)
def get_my_preferences(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    """Choices saved in the account (Requirement 13.4); empty until changed."""
    pref = db.query(UserPreference).filter(UserPreference.user_id == claims["user_id"]).first()
    return PreferencesResponse(list_views=_known_views(pref.list_views if pref else {}))


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
    user_id: int = claims["user_id"]
    if db.query(User.user_id).filter(User.user_id == user_id).first() is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if pref is None:
        pref = UserPreference(user_id=user_id, list_views={body.key: body.view})
        set_creation_audit(pref, user_id=user_id)
        db.add(pref)
    else:
        # A new dict, so SQLAlchemy sees the JSON column change.
        pref.list_views = {**_known_views(pref.list_views), body.key: body.view}
        set_modification_audit(pref, user_id=user_id)
    db.commit()
    return PreferencesResponse(list_views=_known_views(pref.list_views))


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
