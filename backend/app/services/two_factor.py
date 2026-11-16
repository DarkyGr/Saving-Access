"""
Two-factor authentication (Requirement 16.1, task 37.5).

- The TOTP secret is stored Fernet-encrypted, like credentials. A new one
  waits in ``totp_pending_secret`` until a code from the app confirms it, so
  setting up again never breaks the second factor that already works.
- 10 one-time recovery codes (``XXXXX-XXXXX``, about 50 bits each); only
  their SHA-256 is stored. New codes replace all the old ones.
- A TOTP code is accepted once: ``totp_last_step`` remembers the last step.

``TWO_FACTOR_REQUIRED`` (default "true") makes every account set it up right
after its password; production refuses "false". Tests and the E2E run turn
it off, and an account that has 2FA always needs it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import RecoveryCode, User
from app.services.encryptor_service import EncryptorService
from app.utils import totp
from app.utils.audit_columns import set_creation_audit

RECOVERY_CODES = 10
RECOVERY_WARNING = 3
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def two_factor_required() -> bool:
    return os.environ.get("TWO_FACTOR_REQUIRED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _hash(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode("ascii", "ignore")).hexdigest()


def _new_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


class TwoFactorService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._crypto = EncryptorService()

    # ── State ────────────────────────────────────────────────────────────
    @staticmethod
    def enabled(user: User) -> bool:
        return user.totp_enabled_at is not None and user.totp_secret is not None

    def recovery_left(self, user: User) -> int:
        return (
            self._db.query(RecoveryCode)
            .filter(RecoveryCode.user_id == user.user_id, RecoveryCode.used_at.is_(None))
            .count()
        )

    # ── Setting up ───────────────────────────────────────────────────────
    def start_setup(self, user: User) -> tuple[str, str]:
        """New pending secret → ``(secret, otpauth_uri)``. Caller commits."""
        secret = totp.new_secret()
        user.totp_pending_secret = self._crypto.encrypt(secret)
        return secret, totp.otpauth_uri(secret, user.username)

    def confirm_setup(self, user: User, code: str) -> list[str] | None:
        """Turn the pending secret on when *code* matches it; returns the new
        recovery codes, or None. Caller commits."""
        if user.totp_pending_secret is None:
            return None
        secret = self._crypto.decrypt(user.totp_pending_secret)
        step = totp.matching_step(secret, code, after=None)
        if step is None:
            return None
        user.totp_secret = user.totp_pending_secret
        user.totp_pending_secret = None
        user.totp_enabled_at = _now()
        user.totp_last_step = step
        return self.new_recovery_codes(user)

    def new_recovery_codes(self, user: User) -> list[str]:
        """Replace every recovery code of *user*. Caller commits."""
        self._db.query(RecoveryCode).filter(RecoveryCode.user_id == user.user_id).delete()
        codes = [_new_code() for _ in range(RECOVERY_CODES)]
        for code in codes:
            row = RecoveryCode(user_id=user.user_id, code_hash=_hash(code))
            set_creation_audit(row, user_id=user.user_id)
            self._db.add(row)
        return codes

    def reset(self, user: User) -> None:
        """The Admin's reset: no second factor until it is set up again."""
        user.totp_secret = None
        user.totp_pending_secret = None
        user.totp_enabled_at = None
        user.totp_last_step = None
        self._db.query(RecoveryCode).filter(RecoveryCode.user_id == user.user_id).delete()

    # ── Checking ─────────────────────────────────────────────────────────
    def check(self, user: User, code: str, *, allow_recovery: bool = True) -> Literal["totp", "recovery"] | None:
        """Accept a current TOTP code or (unless *allow_recovery* is False) an
        unused recovery code, which is used up on success. Caller commits."""
        if not self.enabled(user):
            return None
        secret = self._crypto.decrypt(user.totp_secret)
        step = totp.matching_step(secret, code, after=user.totp_last_step)
        if step is not None:
            user.totp_last_step = step
            return "totp"
        if not allow_recovery or len(_normalize(code)) != 10:
            return None
        row = (
            self._db.query(RecoveryCode)
            .filter(
                RecoveryCode.user_id == user.user_id,
                RecoveryCode.code_hash == _hash(code),
                RecoveryCode.used_at.is_(None),
            )
            .first()
        )
        if row is None:
            return None
        row.used_at = _now()
        self._db.flush()  # so recovery_left() already counts it as used
        return "recovery"
