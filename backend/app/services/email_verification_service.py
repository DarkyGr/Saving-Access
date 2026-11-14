"""
EmailVerificationService — verification links and the 30-day deadline
(Requirements 1.9, 1.10, 2.7–2.9; task 33.2).

- Opaque random token (``secrets.token_urlsafe``); only its SHA-256 is stored.
- Each link works once and expires after ``VERIFICATION_TOKEN_HOURS``.
- Resending issues a new link and never touches ``deactivation_deadline``
  (Requirement 2.8). Older unused links keep working until they expire.
- A deactivated account cannot be verified with a link; an admin restores it
  with ``python -m app.cli verify-email --username <name>``.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy.orm import Session

from app.models import EmailVerificationToken, User
from app.phase2 import app_base_url, is_deactivated, verification_token_lifetime
from app.services.email_sender import OutgoingEmail
from app.utils.audit_columns import set_creation_audit, set_modification_audit


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
    },
}


def build_verification_email(user: User, raw_token: str, language: str | None) -> OutgoingEmail:
    texts = _TEXTS.get((language or "en")[:2].lower(), _TEXTS["en"])
    hours = int(verification_token_lifetime().total_seconds() // 3600)
    deadline = user.deactivation_deadline.isoformat() if user.deactivation_deadline else "-"
    link = f"{app_base_url()}/verify-email?token={raw_token}"
    return OutgoingEmail(
        to=user.email,
        subject=texts["subject"],
        body=texts["body"].format(
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
