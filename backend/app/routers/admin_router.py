"""
Admin router — accounts and the audit view (Requirements 3.6, 3.7, 15).

Endpoints:
  GET  /api/admin/users                        → every account with its role and status
  PUT  /api/admin/users/{user_id}/role         → change another account's role
  POST /api/admin/users/{user_id}/deactivate   → deactivate another account, with a reason
  POST /api/admin/users/{user_id}/reactivate   → let a deactivated account sign in again
  GET  /api/admin/audit                        → who did what and when (newest first)

Account endpoints need ``users.manage`` and the audit view ``audit.view``;
only the Admin role grants them. Nothing here returns password hashes or
anything stored in a credential, and nobody's vault is touched.
"""

from datetime import UTC, date, datetime, time
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.middleware.permissions import require_permission
from app.models import AuditLog, User
from app.phase2 import deactivation_deadline_for, deadline_passed, verification_required
from app.services.audit_service import ACTIONS, AuditService
from app.services.email_sender import send_email
from app.services.refresh_token_service import RefreshTokenService
from app.services.security_notice import account_deactivated_email, account_reactivated_email
from app.utils.audit_columns import set_modification_audit, utc_date_time

router = APIRouter()

Status = Literal["active", "deactivated", "unverified"]

# The audit view returns at most this many rows (newest first); narrower
# filters reach older ones.
AUDIT_LIMIT = 1000


def _iso(day: date | None, at: time | None = None) -> str | None:
    if day is None:
        return None
    return f"{day.isoformat()}T{(at or time()).strftime('%H:%M:%S')}Z"


def _status_of(user: User) -> Status:
    today = utc_date_time()[0]
    if user.deactivated_at is not None or deadline_passed(user, today):
        return "deactivated"
    if verification_required(user):
        return "unverified"
    return "active"


class UserListItem(BaseModel):
    """Single account returned by GET /api/admin/users (no password hash)."""

    user_id: int
    user_code: str
    username: str
    display_name: str | None
    email: str
    role: str
    email_verified: bool
    status: Status
    # "admin" when the Admin deactivated it, "deadline" when the email was
    # never verified in time (Requirement 2.9), null when active.
    deactivated_by: Literal["admin", "deadline"] | None
    deactivated_at: str | None
    deactivation_reason: str | None
    created: str | None


def _list_item(user: User) -> UserListItem:
    state = _status_of(user)
    by: Literal["admin", "deadline"] | None = None
    if state == "deactivated":
        by = "admin" if user.deactivated_at is not None else "deadline"
    return UserListItem(
        user_id=user.user_id,
        user_code=user.user_code,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        email_verified=user.email_verified,
        status=state,
        deactivated_by=by,
        deactivated_at=(user.deactivated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if user.deactivated_at else None),
        deactivation_reason=user.deactivation_reason,
        created=_iso(user.creation_date, user.creation_time),
    )


class ChangeRoleRequest(BaseModel):
    role: Literal["User", "Admin"]


class ChangeRoleResponse(BaseModel):
    user_id: int
    role: str


class DeactivateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        # Spaces collapse; deactivate_user then rejects what is left if short.
        return " ".join(value.split())


class AuditPerson(BaseModel):
    user_id: int
    user_code: str
    username: str


class AuditItem(BaseModel):
    log_id: int
    at: str
    action: str
    actor: AuditPerson
    target: AuditPerson | None
    # The credential's number for credential.* rows; never its contents.
    record_id: int | None
    detail: str | None

    model_config = ConfigDict(from_attributes=True)


class AuditResponse(BaseModel):
    items: list[AuditItem]
    truncated: bool


def _target(db: Session, user_id: int, admin_id: int, *, action: str) -> User:
    if user_id == admin_id:
        detail = "You cannot change your own role." if action == "role" else "You cannot deactivate your own account."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    target: User | None = db.query(User).filter(User.user_id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return target


@router.get(
    "/users",
    response_model=list[UserListItem],
    status_code=status.HTTP_200_OK,
    summary="List all users with their role and status",
)
def list_users(
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> list[UserListItem]:
    return [_list_item(u) for u in db.query(User).order_by(User.user_id).all()]


@router.put(
    "/users/{user_id}/role",
    response_model=ChangeRoleResponse,
    status_code=status.HTTP_200_OK,
    summary="Change another user's role",
)
def change_user_role(
    user_id: int,
    body: ChangeRoleRequest,
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> ChangeRoleResponse:
    """Set *user_id*'s role and its modification Audit_Columns (Property 8).

    An Admin cannot change their own role, so at least one Admin always
    remains (Requirement 3.7).
    """
    admin_id: int = claims["user_id"]
    target = _target(db, user_id, admin_id, action="role")
    if target.role != body.role:
        previous = target.role
        target.role = body.role
        set_modification_audit(target, user_id=admin_id)
        AuditService(db).log(
            admin_id, "UPDATE", target.user_id, commit=False,
            action="user.role", target_user_id=target.user_id, detail=f"{previous}→{body.role}",
        )
        db.commit()
    return ChangeRoleResponse(user_id=target.user_id, role=target.role)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserListItem,
    status_code=status.HTTP_200_OK,
    summary="Deactivate another account with a reason",
)
def deactivate_user(
    user_id: int,
    body: DeactivateRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> UserListItem:
    """Requirement 15.2–15.3: the account can no longer sign in, every session
    ends at once (its access tokens stop too) and the owner gets an email with
    the reason. The Admin cannot deactivate their own account. Credentials are
    kept untouched."""
    admin_id: int = claims["user_id"]
    if len(body.reason) < 3:
        raise HTTPException(status_code=422, detail="Reason must have at least 3 characters.")
    target = _target(db, user_id, admin_id, action="deactivate")
    if target.deactivated_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already deactivated.")
    target.deactivated_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    target.deactivation_reason = body.reason
    set_modification_audit(target, user_id=admin_id)
    RefreshTokenService(db).revoke_all(target.user_id)
    AuditService(db).log(
        admin_id, "UPDATE", target.user_id, commit=False,
        action="user.deactivate", target_user_id=target.user_id,
    )
    db.commit()
    background_tasks.add_task(send_email, account_deactivated_email(target, body.reason))
    return _list_item(target)


@router.post(
    "/users/{user_id}/reactivate",
    response_model=UserListItem,
    status_code=status.HTTP_200_OK,
    summary="Let a deactivated account sign in again",
)
def reactivate_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> UserListItem:
    """Requirement 15.2: lifts the Admin's deactivation. An account that was
    closed for not verifying its email in time gets a new deadline (the same
    period as at sign-up) instead of being marked verified."""
    admin_id: int = claims["user_id"]
    target = _target(db, user_id, admin_id, action="reactivate")
    today = utc_date_time()[0]
    by_deadline = deadline_passed(target, today)
    if target.deactivated_at is None and not by_deadline:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account is not deactivated.")
    target.deactivated_at = None
    target.deactivation_reason = None
    if by_deadline:
        target.deactivation_deadline = deactivation_deadline_for(today)
        target.last_verification_reminder_days = None
    set_modification_audit(target, user_id=admin_id)
    AuditService(db).log(
        admin_id, "UPDATE", target.user_id, commit=False,
        action="user.reactivate", target_user_id=target.user_id,
    )
    db.commit()
    background_tasks.add_task(send_email, account_reactivated_email(target))
    return _list_item(target)


@router.get(
    "/audit",
    response_model=AuditResponse,
    status_code=status.HTTP_200_OK,
    summary="Who did what and when, newest first",
)
def audit_view(
    action: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    claims: dict = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> AuditResponse:
    """Requirement 15.4. Filters: one action, a person (username, email or
    user ID of whoever did it or whoever it was done to) and a UTC date range.
    Rows name the credential by number only: never its site, login or
    password."""
    if action and action not in ACTIONS:
        raise HTTPException(status_code=422, detail="Unknown action.")
    actor = aliased(User)
    target = aliased(User)
    query = (
        db.query(AuditLog, actor, target)
        .join(actor, AuditLog.user_id == actor.user_id)
        .outerjoin(target, AuditLog.target_user_id == target.user_id)
    )
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        query = query.filter(AuditLog.operation_date >= date_from)
    if date_to:
        query = query.filter(AuditLog.operation_date <= date_to)
    term = " ".join((q or "").split())
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.filter(
            or_(
                *(
                    column.ilike(like, escape="\\")
                    for person in (actor, target)
                    for column in (person.username, person.email, person.user_code)
                )
            )
        )
    rows = (
        query.order_by(AuditLog.operation_date.desc(), AuditLog.operation_time.desc(), AuditLog.log_id.desc())
        .limit(AUDIT_LIMIT + 1)
        .all()
    )

    def person(u: User | None) -> AuditPerson | None:
        return AuditPerson(user_id=u.user_id, user_code=u.user_code, username=u.username) if u else None

    items = [
        AuditItem(
            log_id=log.log_id,
            at=_iso(log.operation_date, log.operation_time) or "",
            action=log.action or "credential.reveal",
            actor=person(who),
            target=person(whom),
            record_id=log.affected_record_id if (log.action or "").startswith("credential.") else None,
            detail=log.detail,
        )
        for log, who, whom in rows[:AUDIT_LIMIT]
    ]
    return AuditResponse(items=items, truncated=len(rows) > AUDIT_LIMIT)
