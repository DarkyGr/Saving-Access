"""
RefreshTokenService — long-lived session handle stored in an httpOnly cookie
(task 31.5).

The access JWT stays in React memory (Requirement 8.3 / design). The refresh
token lets the SPA obtain a new access token after a page reload or when the
15-minute access token expires, without ever being readable by JavaScript.

- Opaque random token (``secrets.token_urlsafe``); only its SHA-256 is stored.
- Rotated on every use: the old row is revoked, a new one is issued in the
  same family.
- Reuse of an already-revoked token revokes the whole family (the token was
  probably stolen) and fails.
- Lifetime: ``REFRESH_EXPIRE_HOURS`` (default 8).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session

from app.models import RefreshToken, User
from app.utils.audit_columns import set_creation_audit, set_modification_audit


def _now() -> datetime:
    # Naive UTC: portable across PostgreSQL TIMESTAMP and SQLite.
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_lifetime() -> timedelta:
    return timedelta(hours=float(os.environ.get("REFRESH_EXPIRE_HOURS", "8")))


class RefreshTokenService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def issue(self, user_id: int, family_id: str | None = None) -> str:
        """Create a new refresh token row and return the raw token. Caller commits."""
        raw = secrets.token_urlsafe(48)
        row = RefreshToken(
            user_id=user_id,
            token_hash=_hash(raw),
            family_id=family_id or secrets.token_hex(16),
            expires_at=_now() + refresh_lifetime(),
        )
        set_creation_audit(row, user_id=user_id)
        self._db.add(row)
        return raw

    def rotate(self, raw: str) -> tuple[User, str] | None:
        """Validate *raw*, revoke it and issue its successor.

        :returns: ``(user, new_raw_token)`` or ``None`` when the token is
            unknown, expired, revoked (reuse → whole family revoked) or the
            user no longer exists. Commits.
        """
        row = (
            self._db.query(RefreshToken)
            .filter(RefreshToken.token_hash == _hash(raw))
            .first()
        )
        if row is None:
            return None

        now = _now()
        if row.revoked_at is not None:
            self._revoke_family(row.family_id, row.user_id)
            self._db.commit()
            return None
        if row.expires_at <= now:
            return None

        user = self._db.query(User).filter(User.user_id == row.user_id).first()
        if user is None:
            return None

        row.revoked_at = now
        set_modification_audit(row, user_id=row.user_id)
        new_raw = self.issue(row.user_id, family_id=row.family_id)
        self._db.commit()
        return user, new_raw

    def revoke(self, raw: str) -> None:
        """Revoke *raw* (logout). Unknown tokens are ignored. Commits."""
        row = (
            self._db.query(RefreshToken)
            .filter(RefreshToken.token_hash == _hash(raw))
            .first()
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = _now()
            set_modification_audit(row, user_id=row.user_id)
            self._db.commit()

    def _revoke_family(self, family_id: str, user_id: int) -> None:
        now = _now()
        for row in (
            self._db.query(RefreshToken)
            .filter(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .all()
        ):
            row.revoked_at = now
            set_modification_audit(row, user_id=user_id)
