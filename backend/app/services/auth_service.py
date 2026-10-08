"""
AuthService — handles user registration, login, JWT issuance, and
account-password verification.

Requirements: 1.3–1.7, 2.2–2.4, 8.5
"""

import os
from datetime import date, datetime, timezone, timedelta
from typing import Any

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy.orm import Session

from app.models import User
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
        self._secret: str = os.environ.get("JWT_SECRET", "changeme")
        self._algorithm: str = os.environ.get("JWT_ALGORITHM", "HS256")
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
        rounds = int(os.environ.get("BCRYPT_ROUNDS", "12"))
        password_hash: str = bcrypt_hasher.using(rounds=rounds).hash(password)

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
            raise _generic

        # Verify bcrypt hash; bcrypt.verify returns False on mismatch
        try:
            valid = bcrypt_hasher.verify(password, user.password_hash)
        except Exception:
            raise _generic

        if not valid:
            raise _generic

        # Issue JWT (Requirement 2.4)
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=self._expire_minutes)
        token_data = {
            "user_id": user.user_id,
            "role": user.role,
            "exp": exp,
        }
        access_token: str = jwt.encode(
            token_data, self._secret, algorithm=self._algorithm
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self._expire_minutes * 60,
        }

    def verify_token(self, token: str) -> dict:
        """Decode and validate a JWT.

        :param token: Raw JWT string from the ``Authorization: Bearer`` header.
        :raises HTTPException 401: if the token is expired or has an invalid
            signature / structure.
        :returns: The decoded payload dict (includes ``user_id``, ``role``,
            ``exp``).
        """
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._algorithm]
            )
            return payload
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired.")
        except JWTError:
            raise HTTPException(status_code=401, detail="Not authenticated.")

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
        try:
            return bool(bcrypt_hasher.verify(raw, user.password_hash))
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Module-level convenience: expose the validator for direct import in tests
# ---------------------------------------------------------------------------

validate_password_strength = _validate_password_strength
