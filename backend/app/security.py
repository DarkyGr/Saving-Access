"""
Security primitives: settings validation, password hashing and JWT handling.

Replaces the unmaintained ``passlib`` and ``python-jose`` (task 31.2):

- Passwords: ``bcrypt`` directly. Hashes use the standard ``$2b$`` format, so
  hashes created earlier through passlib keep verifying.
- Tokens: ``PyJWT``.

``validate_settings()`` runs at startup and refuses to boot with a missing or
weak ``JWT_SECRET`` or an invalid ``FERNET_KEY`` (task 31.1).
"""

from __future__ import annotations

import os
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet

MIN_JWT_SECRET_LENGTH = 32
_KNOWN_WEAK_SECRETS = {"changeme", "secret", "jwt_secret", "your-secret-key"}

# bcrypt only uses the first 72 bytes. passlib truncated silently; bcrypt>=5
# raises instead, so truncate explicitly to keep old hashes valid.
_BCRYPT_MAX_BYTES = 72


class SettingsError(RuntimeError):
    """Raised when required security settings are missing or unsafe."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise SettingsError("JWT_SECRET is not set.")
    return secret


def get_jwt_algorithm() -> str:
    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    if algorithm not in {"HS256", "HS384", "HS512"}:
        raise SettingsError(f"JWT_ALGORITHM {algorithm!r} is not supported.")
    return algorithm


def validate_settings() -> None:
    """Fail fast on unsafe configuration. Called once at application startup."""
    problems: list[str] = []

    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        problems.append("JWT_SECRET is not set.")
    elif len(secret) < MIN_JWT_SECRET_LENGTH or secret.lower() in _KNOWN_WEAK_SECRETS:
        problems.append(
            f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} random characters "
            '(generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))").'
        )

    keys = [k.strip() for k in os.environ.get("FERNET_KEY", "").split(",") if k.strip()]
    if not keys:
        problems.append("FERNET_KEY is not set.")
    else:
        try:
            # Several comma-separated keys are allowed during a rotation.
            for key in keys:
                Fernet(key.encode())
        except (ValueError, TypeError):
            problems.append(
                "FERNET_KEY is not a valid Fernet key (generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").'
            )

    try:
        get_jwt_algorithm()
    except SettingsError as exc:
        problems.append(str(exc))

    if problems:
        raise SettingsError("Unsafe configuration:\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def _bcrypt_rounds() -> int:
    return int(os.environ.get("BCRYPT_ROUNDS", "12"))


def _encode_password(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode_password(password), bcrypt.gensalt(rounds=_bcrypt_rounds())).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True iff *password* matches *password_hash*. Never raises."""
    try:
        return bcrypt.checkpw(_encode_password(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


_dummy_hash: str | None = None


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check when the user does not exist.

    Prevents username enumeration through login response timing.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("timing-equaliser-not-a-real-password")
    verify_password(password, _dummy_hash)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

ExpiredSignatureError = jwt.ExpiredSignatureError
InvalidTokenError = jwt.InvalidTokenError


def encode_token(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, get_jwt_secret(), algorithm=get_jwt_algorithm())


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify *token*. Raises ExpiredSignatureError / InvalidTokenError."""
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[get_jwt_algorithm()],
        options={"require": ["exp"]},
    )
