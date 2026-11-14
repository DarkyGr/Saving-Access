"""
AuthService — handles user registration, login, JWT issuance, and
account-password verification.

Requirements: 1.3–1.7, 2.2–2.4, 8.5
"""

import os
from datetime import date, datetime, timezone, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.security import (
    ExpiredSignatureError,
    InvalidTokenError,
    burn_password_check,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)
from app.utils.email_validator import validate_email as _validate_email_format


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_SYMBOLS = set("@$!")
_MIN_LENGTH = 12


def _validate_password_strength(password: str) -> list[str]:
    """Return a list of human-readable error strings for every unmet rule.

    An empty list means the password is valid.

    Rules (Requirement 1.5):
      1. Minimum 12 characters
      2. At least one uppercase letter
      3. At least one lowercase letter
      4. At least one digit
      5. At least one symbol from {@, $, !}
    """
    errors: list[str] = []

    if len(password) < _MIN_LENGTH:
        errors.append(f"Password must be at least {_MIN_LENGTH} characters long.")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit.")
    if not any(c in _REQUIRED_SYMBOLS for c in password):
        errors.append("Password must contain at least one symbol from: @, $, !.")

    return errors


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------


class AuthService:
    """Encapsulates all authentication and authorisation logic."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._expire_minutes: int = int(
            os.environ.get("JWT_EXPIRE_MINUTES", "15")
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def register(self, payload: dict[str, Any]) -> User:
        """Validate and create a new user account.

        :param payload: dict with keys ``username``, ``email``,
            ``password``, ``password_confirmation``.
        :raises HTTPException 400: on validation failure (strength, match,
            duplicate username/email).
        :returns: The newly persisted :class:`User` ORM instance.
        """
        username: str = payload["username"]
        email: str = payload["email"]
        password: str = payload["password"]
        confirmation: str = payload["password_confirmation"]

        # 1. Password confirmation match (Requirement 1.3 / 1.4)
        if password != confirmation:
            raise HTTPException(
                status_code=400,
                detail="Password and password confirmation do not match.",
            )

        # 2. Password strength (Requirement 1.5 / 1.6)
        strength_errors = _validate_password_strength(password)
        if strength_errors:
            raise HTTPException(
                status_code=400,
                detail={"password_errors": strength_errors},
            )

        # 3. Email format + disposable-domain check (Requirement 4.13)
        if not _validate_email_format(email):
            raise HTTPException(
                status_code=422,
                detail="Invalid email address or disposable email domains are not allowed.",
            )

        # 4. Duplicate username (Requirement 1.2)
        if self._db.query(User).filter(User.username == username).first():
            raise HTTPException(
                status_code=400,
                detail="Username is already taken.",
            )

        # 5. Duplicate email
        if self._db.query(User).filter(User.email == email).first():
            raise HTTPException(
                status_code=400,
                detail="Email address is already registered.",
            )

        # 6. Hash password (Requirement 1.7, 8.5)
        password_hash: str = hash_password(password)

        # 7. Create user with audit columns (Requirement 1.8)
        now_date = date.today()
        now_time = datetime.now(timezone.utc).time().replace(tzinfo=None)
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role="User",
            email_verified=False,
            creation_date=now_date,
            creation_time=now_time,
            creation_user_id=None,  # self-referential; set after first commit
        )

        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)

        # Back-fill creation_user_id with the new user's own id
        user.creation_user_id = user.user_id
        # Give the account a usable profile (Requirement 3.4); without one
        # a new User could not open any screen.
        from app.seed import assign_default_profile

        assign_default_profile(self._db, user.user_id)
        self._db.commit()
        self._db.refresh(user)

        return user

    def login(self, payload: dict[str, Any]) -> dict:
        """Authenticate a user and issue a JWT access token.

        On any failure (wrong username, wrong password, inactive account),
        always returns the same generic error to avoid leaking which field
        was wrong (Requirement 2.3).

        :param payload: dict with keys ``username`` and ``password``.
        :raises HTTPException 401: on any authentication failure.
        :returns: ``{"access_token": ..., "token_type": "bearer", "expires_in": 900}``
        """
        _generic = HTTPException(
            status_code=401,
            detail="Invalid credentials.",
        )

        username: str = payload.get("username", "")
        password: str = payload.get("password", "")

        user: User | None = (
            self._db.query(User).filter(User.username == username).first()
        )
        if user is None:
            # Same bcrypt cost as a real check: no username enumeration by timing.
            burn_password_check(password)
            raise _generic

        if not verify_password(password, user.password_hash):
            raise _generic

        return self.issue_access_token(user)

    def issue_access_token(self, user: User) -> dict:
        """Return the login/refresh response body with a fresh access token.

        Claims (Requirement 2.4): ``user_id``, ``username`` and ``role`` (all
        required by the frontend AuthContext), ``type="access"`` and ``exp``.
        """
        now = datetime.now(timezone.utc)
        token_data = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self._expire_minutes),
        }
        return {
            "access_token": encode_token(token_data),
            "token_type": "bearer",
            "expires_in": self._expire_minutes * 60,
        }

    def verify_token(self, token: str) -> dict:
        """Decode and validate an access JWT.

        :raises HTTPException 401: if the token is expired, has an invalid
            signature / structure, or is not an access token.
        :returns: The decoded payload dict.
        """
        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired.")
        except InvalidTokenError:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        # Tokens issued before task 31.5 carry no "type"; accept them until
        # they expire (15 min), reject anything explicitly non-access.
        if payload.get("type", "access") != "access" or "user_id" not in payload:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return payload

    def check_account_password(self, user_id: int, raw: str) -> bool:
        """Verify that *raw* matches the stored bcrypt hash for *user_id*.

        :param user_id: The user's PK.
        :param raw: The plaintext password submitted by the client.
        :returns: ``True`` if the password matches, ``False`` otherwise.
            Never raises on a wrong password.
        """
        user: User | None = (
            self._db.query(User).filter(User.user_id == user_id).first()
        )
        if user is None:
            return False
        return verify_password(raw, user.password_hash)


# ---------------------------------------------------------------------------
# Module-level convenience: expose the validator for direct import in tests
# ---------------------------------------------------------------------------

validate_password_strength = _validate_password_strength
