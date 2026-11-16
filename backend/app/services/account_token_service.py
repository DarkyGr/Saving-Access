"""
One-time account links (task 37.5): ``unlock`` after a lockout
(Requirement 16.2) and ``reset`` for a forgotten password (Requirement 16.3).

Same rules as the verification links: an opaque random token, only its
SHA-256 stored, one use, an expiry. Issuing a new link of a purpose retires
the older unused ones of that purpose, so only the latest email works.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.models import AccountToken, User
from app.utils.audit_columns import set_creation_audit

Purpose = Literal["unlock", "reset"]

LIFETIME: dict[str, timedelta] = {
    "unlock": timedelta(hours=24),
    "reset": timedelta(hours=1),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AccountTokenService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def issue(self, user: User, purpose: Purpose) -> str:
        """Create a link for *user* and return the raw token. Caller commits."""
        now = _now()
        for old in (
            self._db.query(AccountToken)
            .filter(
                AccountToken.user_id == user.user_id,
                AccountToken.purpose == purpose,
                AccountToken.used_at.is_(None),
            )
            .all()
        ):
            old.used_at = now
        raw = secrets.token_urlsafe(32)
        row = AccountToken(
            user_id=user.user_id,
            purpose=purpose,
            token_hash=_hash(raw),
            expires_at=now + LIFETIME[purpose],
        )
        set_creation_audit(row, user_id=user.user_id)
        self._db.add(row)
        return raw

    def peek(self, raw: str, purpose: Purpose) -> User | None:
        """The owner of a valid, unused *raw* link, without using it."""
        row = self._valid(raw, purpose)
        return self._db.get(User, row.user_id) if row else None

    def consume(self, raw: str, purpose: Purpose) -> User | None:
        """Mark *raw* used and return its owner, or None when it is unknown,
        used, expired or of another purpose. Caller commits."""
        row = self._valid(raw, purpose)
        if row is None:
            return None
        row.used_at = _now()
        return self._db.get(User, row.user_id)

    def _valid(self, raw: str, purpose: Purpose) -> AccountToken | None:
        if not raw:
            return None
        row = self._db.query(AccountToken).filter(AccountToken.token_hash == _hash(raw)).first()
        if row is None or row.purpose != purpose or row.used_at is not None or row.expires_at <= _now():
            return None
        return row
