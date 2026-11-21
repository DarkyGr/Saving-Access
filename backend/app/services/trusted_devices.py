"""
Trusted devices: skip the two-step code on one browser for a while
(Requirement 21).

The browser keeps a random token in an httpOnly, Secure, SameSite=Strict
cookie scoped to ``/api/auth``; the database keeps only its SHA-256, the
device description and the expiry. A token only ever skips the code for the
account it was issued to, and never the password.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import TrustedDevice, User
from app.services.system_settings import get_int
from app.utils.audit_columns import set_creation_audit

COOKIE = "sp_device"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def trust_days(db: Session) -> int:
    return get_int(db, "trusted_device_days")


class TrustedDeviceService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def issue(self, user: User, user_agent: str | None) -> tuple[str, int]:
        """New token for this browser → ``(raw, max_age_seconds)``. Caller commits."""
        days = trust_days(self._db)
        raw = secrets.token_urlsafe(32)
        now = _now()
        row = TrustedDevice(
            user_id=user.user_id,
            token_hash=_hash(raw),
            user_agent=(user_agent or "")[:256] or None,
            trusted_at=now,
            expires_at=now + timedelta(days=days),
        )
        set_creation_audit(row, user_id=user.user_id)
        self._db.add(row)
        return raw, days * 86400

    def is_trusted(self, raw: str | None, user: User) -> bool:
        """True when *raw* is a live token of *user* (and trusting is on).
        Marks it used. Caller commits."""
        if not raw or trust_days(self._db) == 0:
            return False
        row = (
            self._db.query(TrustedDevice)
            .filter(TrustedDevice.token_hash == _hash(raw), TrustedDevice.user_id == user.user_id)
            .first()
        )
        if row is None or row.expires_at <= _now():
            return False
        row.last_used_at = _now()
        return True

    def list(self, user_id: int) -> list[TrustedDevice]:
        return (
            self._db.query(TrustedDevice)
            .filter(TrustedDevice.user_id == user_id, TrustedDevice.expires_at > _now())
            .order_by(TrustedDevice.trusted_at.desc())
            .all()
        )

    def forget(self, device_id: int, user_id: int) -> bool:
        """Caller commits."""
        return (
            self._db.query(TrustedDevice)
            .filter(TrustedDevice.trusted_device_id == device_id, TrustedDevice.user_id == user_id)
            .delete()
            > 0
        )

    def forget_all(self, user_id: int) -> int:
        """Every trusted device of the account. Caller commits."""
        return self._db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).delete()
