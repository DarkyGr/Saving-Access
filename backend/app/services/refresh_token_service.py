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
- A family is one signed-in device: its id goes into the access token as
  ``sid``, so ending the session (logout, "end session", password change)
  also stops its access token at once (task 37.3). Each row keeps the
  device's user agent and IP for "Active sessions".
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session

from app.models import RefreshToken, User
from app.phase2 import is_deactivated
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

    def issue(
        self,
        user_id: int,
        family_id: str | None = None,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> str:
        """Create a new refresh token row and return the raw token. Caller commits."""
        raw = secrets.token_urlsafe(48)
        row = RefreshToken(
            user_id=user_id,
            token_hash=_hash(raw),
            family_id=family_id or secrets.token_hex(16),
            expires_at=_now() + refresh_lifetime(),
            user_agent=(user_agent or "")[:256] or None,
            client_ip=(client_ip or "")[:45] or None,
        )
        set_creation_audit(row, user_id=user_id)
        self._db.add(row)
        self.last_family_id = row.family_id
        return raw

    def family_of(self, raw: str) -> str | None:
        row = self._db.query(RefreshToken.family_id).filter(RefreshToken.token_hash == _hash(raw)).first()
        return row.family_id if row else None

    def is_active(self, family_id: str, user_id: int) -> bool:
        """True while the family has an unrevoked, unexpired token."""
        return (
            self._db.query(RefreshToken.refresh_token_id)
            .filter(
                RefreshToken.family_id == family_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > _now(),
            )
            .first()
            is not None
        )

    def active_sessions(self, user_id: int) -> list[dict]:
        """One entry per signed-in device: newest activity first."""
        now = _now()
        rows = self._db.query(RefreshToken).filter(RefreshToken.user_id == user_id).all()
        by_family: dict[str, list[RefreshToken]] = {}
        for row in rows:
            by_family.setdefault(row.family_id, []).append(row)
        sessions = []
        for family_id, family in by_family.items():
            live = [r for r in family if r.revoked_at is None and r.expires_at > now]
            if not live:
                continue
            latest = max(live, key=lambda r: (r.creation_date, r.creation_time))
            first = min(family, key=lambda r: (r.creation_date, r.creation_time))
            sessions.append(
                {
                    "session_id": family_id,
                    "user_agent": latest.user_agent,
                    "client_ip": latest.client_ip,
                    "started": datetime.combine(first.creation_date, first.creation_time),
                    "last_active": datetime.combine(latest.creation_date, latest.creation_time),
                    "expires_at": latest.expires_at,
                }
            )
        return sorted(sessions, key=lambda s: s["last_active"], reverse=True)

    def revoke_family(self, family_id: str, user_id: int) -> bool:
        """End one session of *user_id*. False if it is not theirs or not active. Commits."""
        if not self.is_active(family_id, user_id):
            return False
        self._revoke_family(family_id, user_id)
        self._db.commit()
        return True

    def revoke_all(self, user_id: int, *, keep_family: str | None = None) -> int:
        """End every session of *user_id* except *keep_family*. Caller commits."""
        families = {
            r.family_id
            for r in self._db.query(RefreshToken.family_id)
            .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .all()
        }
        families.discard(keep_family)
        for family_id in families:
            self._revoke_family(family_id, user_id)
        return len(families)

    def rotate(
        self, raw: str, *, user_agent: str | None = None, client_ip: str | None = None
    ) -> tuple[User, str] | None:
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
        if is_deactivated(user, now.date()):
            # Deadline passed during an open session (Requirement 2.9).
            self._revoke_family(row.family_id, row.user_id)
            self._db.commit()
            return None

        row.revoked_at = now
        set_modification_audit(row, user_id=row.user_id)
        new_raw = self.issue(
            row.user_id,
            family_id=row.family_id,
            user_agent=user_agent or row.user_agent,
            client_ip=client_ip or row.client_ip,
        )
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
