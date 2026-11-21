"""
Admin router — accounts and the audit view (Requirements 3.6, 3.7, 15).

Endpoints:
  GET  /api/admin/users                        → every account with its role and status
  PUT  /api/admin/users/{user_id}/role         → change another account's role
  POST /api/admin/users/{user_id}/deactivate   → deactivate another account, with a reason
  POST /api/admin/users/{user_id}/reactivate   → let a deactivated account sign in again
  POST /api/admin/users/{user_id}/unlock       → clear a lockout (task 37.5)
  POST /api/admin/users/{user_id}/reset-2fa    → set two-factor up again (task 37.5)
  GET  /api/admin/audit                        → who did what and when (newest first)
  GET  /api/admin/settings                     → system parameters (task 37.5)
  PUT  /api/admin/settings                     → change some of them
  GET  /api/admin/settings/email               → sign-up verification and SMTP (task 37.5)
  PUT  /api/admin/settings/email               → change them (SMTP password write-only)
  POST /api/admin/settings/email/test          → send a test email now

Account endpoints need ``users.manage``, the audit view ``audit.view`` and
the parameters ``settings.manage``; only the Admin role grants them. Nothing here returns password hashes or
anything stored in a credential, and nobody's vault is touched.
"""

from datetime import UTC, date, datetime, time
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.rate_limit import limiter
from app.middleware.permissions import require_permission, require_recent_auth
from app.models import AuditLog, User
from app.phase2 import deactivation_deadline_for, deadline_passed, verification_required
from app.services.audit_service import ACTIONS, AuditService
from app.services.email_sender import send_email
from app.services.refresh_token_service import RefreshTokenService
from app.services import system_settings
from app.services.security_notice import (
    account_deactivated_email,
    account_reactivated_email,
    two_factor_reset_email,
)
from app.services.two_factor import TwoFactorService
from app.services.trusted_devices import TrustedDeviceService
from app.utils.audit_columns import set_modification_audit, utc_date_time

router = APIRouter()

Status = Literal["active", "deactivated", "locked", "unverified"]

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
    if user.locked_at is not None:
        return "locked"
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
    locked_at: str | None
    two_factor: bool
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
        locked_at=(user.locked_at.strftime("%Y-%m-%dT%H:%M:%SZ") if user.locked_at else None),
        two_factor=TwoFactorService.enabled(user),
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
    target: User | None = db.query(User).filter(User.user_id == user_id, User.deleted_at.is_(None)).first()
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
    # Deleted accounts (task 35.8) are only anonymised rows kept for the audit log.
    return [_list_item(u) for u in db.query(User).filter(User.deleted_at.is_(None)).order_by(User.user_id).all()]


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
    _recent: None = Depends(require_recent_auth),
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
    _recent: None = Depends(require_recent_auth),
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
    _recent: None = Depends(require_recent_auth),
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


@router.post(
    "/users/{user_id}/unlock",
    response_model=UserListItem,
    status_code=status.HTTP_200_OK,
    summary="Clear another account's lockout",
)
def unlock_user(
    user_id: int,
    claims: dict = Depends(require_permission("users.manage")),
    _recent: None = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> UserListItem:
    """Requirement 16.2 / 15.2: the Admin unlocks an account locked by wrong
    passwords or codes. 409 when it is not locked."""
    admin_id: int = claims["user_id"]
    target = _target(db, user_id, admin_id, action="unlock")
    if target.locked_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account is not locked.")
    target.locked_at = None
    target.failed_attempts = 0
    set_modification_audit(target, user_id=admin_id)
    AuditService(db).log(
        admin_id, "UPDATE", target.user_id, commit=False,
        action="user.unlock", target_user_id=target.user_id,
    )
    db.commit()
    return _list_item(target)


@router.post(
    "/users/{user_id}/reset-2fa",
    response_model=UserListItem,
    status_code=status.HTTP_200_OK,
    summary="Make another account set two-factor up again",
)
def reset_two_factor(
    user_id: int,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(require_permission("users.manage")),
    _recent: None = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> UserListItem:
    """Requirement 15.2: for a person who lost their device and codes. Their
    sessions end and the next sign-in sets 2FA up again; they get an email.
    409 when 2FA is not set up."""
    admin_id: int = claims["user_id"]
    target = _target(db, user_id, admin_id, action="reset-2fa")
    if not TwoFactorService.enabled(target):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is not set up.")
    TwoFactorService(db).reset(target)
    TrustedDeviceService(db).forget_all(target.user_id)  # Requirement 21.4
    set_modification_audit(target, user_id=admin_id)
    RefreshTokenService(db).revoke_all(target.user_id)
    AuditService(db).log(
        admin_id, "UPDATE", target.user_id, commit=False,
        action="user.reset_2fa", target_user_id=target.user_id,
    )
    db.commit()
    background_tasks.add_task(send_email, two_factor_reset_email(target))
    return _list_item(target)


class ParameterItem(BaseModel):
    key: str
    group: str
    value: int
    default: int
    minimum: int
    maximum: int


def _parameters(db: Session) -> list[ParameterItem]:
    values = system_settings.all_values(db)
    return [
        ParameterItem(
            key=p.key, group=p.group, value=values[p.key],
            default=p.default, minimum=p.minimum, maximum=p.maximum,
        )
        for p in system_settings.PARAMETERS.values()
    ]


@router.get(
    "/settings",
    response_model=list[ParameterItem],
    status_code=status.HTTP_200_OK,
    summary="System parameters with their range and suggested value",
)
def get_settings(
    claims: dict = Depends(require_permission("settings.manage")),
    db: Session = Depends(get_db),
) -> list[ParameterItem]:
    return _parameters(db)


@router.put(
    "/settings",
    response_model=list[ParameterItem],
    status_code=status.HTTP_200_OK,
    summary="Change system parameters",
)
def put_settings(
    body: dict[str, int],
    claims: dict = Depends(require_permission("settings.manage")),
    _recent: None = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> list[ParameterItem]:
    """Requirement 16.8: every value is checked against its range before any
    is saved (422 otherwise); the change is audited by name, never by value."""
    admin_id: int = claims["user_id"]
    try:
        changed = system_settings.update(db, body, admin_id)
    except system_settings.SettingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if changed:
        AuditService(db).log(
            admin_id, "UPDATE", None, commit=False,
            action="settings.update", detail=",".join(sorted(changed))[:64],
        )
    db.commit()
    return _parameters(db)


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


# --- Email settings (task 37.5, Requirement 16.8) ------------------------------


class SmtpIn(BaseModel):
    # Empty host = no SMTP here: the server's environment decides.
    host: str = Field(default="", max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    username: str = Field(default="", max_length=254)
    from_address: EmailStr | Literal[""] = ""
    # Write-only: empty keeps the saved one; clear_password removes it.
    password: str = Field(default="", max_length=512)
    clear_password: bool = False


class EmailSettingsIn(BaseModel):
    email_verification: bool | None = None
    smtp: SmtpIn | None = None


class SmtpOut(BaseModel):
    host: str
    port: int
    security: str
    username: str
    from_address: str
    has_password: bool
    configured: bool


class EmailSettingsOut(BaseModel):
    email_verification: bool
    smtp: SmtpOut
    app_base_url_set: bool
    # What sends email when no SMTP is set here: console, file or smtp.
    environment_backend: str


class TestEmailIn(BaseModel):
    to: EmailStr | None = None


class TestEmailOut(BaseModel):
    ok: bool
    backend: str
    error: str | None = None


def _email_settings(db: Session) -> EmailSettingsOut:
    import os

    from app.phase2 import app_base_url, email_verification_enabled

    smtp = system_settings.get_json(db, "smtp") or {}
    return EmailSettingsOut(
        email_verification=email_verification_enabled(),
        smtp=SmtpOut(
            host=smtp.get("host", ""),
            port=int(smtp.get("port") or 587),
            security=smtp.get("security") or "starttls",
            username=smtp.get("username", ""),
            from_address=smtp.get("from_address", ""),
            has_password=bool(smtp.get("password")),
            configured=bool(smtp.get("host") and smtp.get("from_address")),
        ),
        app_base_url_set=bool(app_base_url()),
        environment_backend=os.environ.get("EMAIL_BACKEND", "console").strip().lower(),
    )


@router.get(
    "/settings/email",
    response_model=EmailSettingsOut,
    status_code=status.HTTP_200_OK,
    summary="Sign-up email verification and outgoing email",
)
def get_email_settings(
    claims: dict = Depends(require_permission("settings.manage")),
    db: Session = Depends(get_db),
) -> EmailSettingsOut:
    """The SMTP password is never returned: only whether one is saved."""
    system_settings.refresh_cache(db, force=True)
    return _email_settings(db)


@router.put(
    "/settings/email",
    response_model=EmailSettingsOut,
    status_code=status.HTTP_200_OK,
    summary="Change sign-up email verification and outgoing email",
)
def put_email_settings(
    body: EmailSettingsIn,
    claims: dict = Depends(require_permission("settings.manage")),
    _recent: None = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> EmailSettingsOut:
    """Requirement 16.8. The SMTP password is stored Fernet-encrypted and
    never shown again. Verification can only be turned on when the server
    knows its public address (APP_BASE_URL), which the links need."""
    from app.phase2 import app_base_url
    from app.services.encryptor_service import EncryptorService

    admin_id: int = claims["user_id"]
    changed: list[str] = []
    if body.email_verification is not None:
        if body.email_verification and not app_base_url():
            raise HTTPException(status_code=422, detail="APP_BASE_URL is not set on the server.")
        system_settings.set_json(db, "email_verification", body.email_verification, admin_id)
        changed.append("email_verification")
    if body.smtp is not None:
        new = body.smtp
        old = system_settings.get_json(db, "smtp") or {}
        host = new.host.strip()
        if host and not new.from_address:
            raise HTTPException(status_code=422, detail="The sender address is required.")
        password = old.get("password", "")
        if new.clear_password or not host:
            password = ""
        elif new.password:
            password = EncryptorService().encrypt(new.password).decode("ascii")
        value = (
            {
                "host": host,
                "port": new.port,
                "security": new.security,
                "username": new.username.strip(),
                "from_address": str(new.from_address),
                "password": password,
            }
            if host
            else {}
        )
        system_settings.set_json(db, "smtp", value, admin_id)
        changed.append("smtp")
    if changed:
        AuditService(db).log(
            admin_id, "UPDATE", None, commit=False, action="settings.update", detail=",".join(changed)
        )
    db.commit()
    system_settings.refresh_cache(db, force=True)
    return _email_settings(db)


@router.post(
    "/settings/email/test",
    response_model=TestEmailOut,
    status_code=status.HTTP_200_OK,
    summary="Send a test email with the current settings",
)
@limiter.limit("5/minute")
def test_email(
    request: Request,
    body: TestEmailIn,
    claims: dict = Depends(require_permission("settings.manage")),
    db: Session = Depends(get_db),
) -> TestEmailOut:
    """Sent right away (not in the background) so the result can be shown.
    Goes to the Admin's own address unless another one is given."""
    from app.services.email_sender import OutgoingEmail, _backend, deliver

    system_settings.refresh_cache(db, force=True)
    admin = db.get(User, claims["user_id"])
    to = str(body.to) if body.to else admin.email
    message = OutgoingEmail(
        to=to,
        subject="Save-Pass: test email",
        body="This is a test email from Save-Pass System parameters. If you read it, outgoing email works.\n",
    )
    try:
        backend = deliver(message)
    except Exception as error:  # noqa: BLE001 — the reason is shown to the Admin
        return TestEmailOut(ok=False, backend=_backend(), error=f"{type(error).__name__}: {str(error)[:200]}")
    return TestEmailOut(ok=True, backend=backend)

