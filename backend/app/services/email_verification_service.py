"""
EmailVerificationService — verification links and the 30-day deadline
(Requirements 1.9, 1.10, 2.7–2.9; task 33.2).

- Opaque random token (``secrets.token_urlsafe``); only its SHA-256 is stored.
- Each link works once and expires after ``VERIFICATION_TOKEN_HOURS``.
- Resending issues a new link and never touches ``deactivation_deadline``
  (Requirement 2.8). Older unused links keep working until they expire.
- A deactivated account cannot be verified with a link; an admin restores it
  with ``python -m app.cli verify-email --username <name>``.
- Reminders (task 34.4): :meth:`send_due_reminders` emails a new link to
  unverified users ``VERIFICATION_REMINDER_DAYS`` before their deadline,
  once per threshold. Run by ``python -m app.cli send-verification-reminders``
  (the production "scheduler" service, hourly).
"""

from __future__ import annotations

import hashlib
import secrets
import logging
from datetime import UTC, date, datetime
from enum import Enum

from sqlalchemy.orm import Session

from app.models import EmailVerificationToken, User
from app.phase2 import (
    app_base_url,
    email_verification_enabled,
    is_deactivated,
    reminder_days,
    verification_token_lifetime,
)
from app.services.email_sender import OutgoingEmail, send_email
from app.utils.audit_columns import set_creation_audit, set_modification_audit


logger = logging.getLogger(__name__)


class VerifyResult(Enum):
    VERIFIED = "verified"
    INVALID = "invalid"
    DEACTIVATED = "deactivated"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_TEXTS = {
    "en": {
        "subject": "Verify your Save-Pass email address",
        "body": (
            "Hello {username},\n\n"
            "Please confirm your email address by opening this link:\n\n{link}\n\n"
            "The link expires in {hours} hours. If your email is not verified by "
            "{deadline}, the account will be deactivated.\n\n"
            "If you did not create a Save-Pass account, you can ignore this email.\n"
        ),
        "reminder_subject": "Reminder: verify your Save-Pass email",
        "reminder_body": (
            "Hello {username},\n\n"
            "Your email address is still not verified. On {deadline} your Save-Pass "
            "account will be deactivated unless you open this link:\n\n{link}\n\n"
            "The link expires in {hours} hours.\n"
        ),
    },
    "es": {
        "subject": "Verifica tu correo de Save-Pass",
        "body": (
            "Hola {username}:\n\n"
            "Confirma tu dirección de correo abriendo este enlace:\n\n{link}\n\n"
            "El enlace caduca en {hours} horas. Si el correo no está verificado el "
            "{deadline}, la cuenta se desactivará.\n\n"
            "Si no creaste una cuenta en Save-Pass, ignora este mensaje.\n"
        ),
        "reminder_subject": "Recordatorio: verifica tu correo de Save-Pass",
        "reminder_body": (
            "Hola {username}:\n\n"
            "Tu dirección de correo sigue sin verificar. El {deadline} tu cuenta de "
            "Save-Pass se desactivará si no abres este enlace:\n\n{link}\n\n"
            "El enlace caduca en {hours} horas.\n"
        ),
    },
}


def build_verification_email(
    user: User, raw_token: str, language: str | None, *, reminder: bool = False
) -> OutgoingEmail:
    language = language or user.preferred_language
    texts = _TEXTS.get((language or "en")[:2].lower(), _TEXTS["en"])
    prefix = "reminder_" if reminder else ""
    hours = int(verification_token_lifetime().total_seconds() // 3600)
    deadline = user.deactivation_deadline.isoformat() if user.deactivation_deadline else "-"
    link = f"{app_base_url()}/verify-email?token={raw_token}"
    return OutgoingEmail(
        to=user.email,
        subject=texts[prefix + "subject"],
        body=texts[prefix + "body"].format(
            username=user.username, link=link, hours=hours, deadline=deadline
        ),
    )


class EmailVerificationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def issue(self, user: User) -> str:
        """Create a verification token row and return the raw token. Caller commits."""
        raw = secrets.token_urlsafe(32)
        row = EmailVerificationToken(
            user_id=user.user_id,
            token_hash=_hash(raw),
            expires_at=_now() + verification_token_lifetime(),
        )
        set_creation_audit(row, user_id=user.user_id)
        self._db.add(row)
        return raw

    def verify(self, raw: str) -> VerifyResult:
        """Consume *raw* and mark the owner's email as verified. Commits."""
        row = (
            self._db.query(EmailVerificationToken)
            .filter(EmailVerificationToken.token_hash == _hash(raw))
            .first()
        )
        now = _now()
        if row is None or row.used_at is not None or row.expires_at <= now:
            return VerifyResult.INVALID

        user = self._db.query(User).filter(User.user_id == row.user_id).first()
        if user is None:
            return VerifyResult.INVALID
        if is_deactivated(user, now.date()):
            return VerifyResult.DEACTIVATED

        row.used_at = now
        set_modification_audit(row, user_id=user.user_id)
        if not user.email_verified:
            user.email_verified = True
            set_modification_audit(user, user_id=user.user_id)
        self._db.commit()
        return VerifyResult.VERIFIED

    def send_due_reminders(self, today: date, *, dry_run: bool = False) -> list[str]:
        """Email a new link to every unverified user who reached a reminder
        threshold. Each threshold is sent at most once per user; a user who
        skipped one (e.g. the job did not run) gets only the latest.

        :returns: usernames reminded (or that would be, with *dry_run*).
        """
        thresholds = reminder_days()
        if not email_verification_enabled() or not thresholds:
            return []
        reminded: list[str] = []
        candidates = (
            self._db.query(User)
            .filter(User.email_verified.is_(False), User.deactivation_deadline.isnot(None))
            .filter(User.deactivation_deadline >= today)
            .order_by(User.user_id)
            .all()
        )
        for user in candidates:
            days_left = (user.deactivation_deadline - today).days
            reached = [d for d in thresholds if days_left <= d]
            if not reached:
                continue
            target = min(reached)
            last = user.last_verification_reminder_days
            if last is not None and last <= target:
                continue
            reminded.append(user.username)
            if dry_run:
                continue
            raw = self.issue(user)
            if send_email(build_verification_email(user, raw, None, reminder=True)):
                user.last_verification_reminder_days = target
                set_modification_audit(user, user_id=user.user_id)
            else:
                reminded.pop()
                logger.warning("Reminder for user %s not sent; will retry", user.user_id)
            self._db.commit()
        return reminded
