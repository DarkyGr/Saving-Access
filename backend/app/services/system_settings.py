"""
System parameters set by the Admin (Requirement 16.8, task 37.5).

Each parameter declares its default, range and suggested value here; the
``system_settings`` table only holds the values the Admin changed. Reading a
parameter that was never set returns its default, so a fresh installation
works without any row.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.utils.audit_columns import set_creation_audit, set_modification_audit


@dataclass(frozen=True)
class IntParameter:
    key: str
    default: int
    minimum: int
    maximum: int
    group: str


# Security values (Requirement 16.2, 16.4, 16.5). The default is also the
# suggested value shown on the System parameters screen.
PARAMETERS: dict[str, IntParameter] = {
    p.key: p
    for p in (
        IntParameter("lockout_attempts", 5, 3, 20, "security"),
        IntParameter("session_idle_minutes", 15, 5, 240, "sessions"),
        IntParameter("session_max_minutes", 480, 60, 1440, "sessions"),
        IntParameter("session_extend_minutes", 30, 5, 240, "sessions"),
        IntParameter("admin_reauth_minutes", 5, 0, 60, "security"),
        # Requirement 21: days a browser may skip the two-step code (0 = never).
        IntParameter("trusted_device_days", 30, 0, 90, "security"),
    )
}


class SettingError(ValueError):
    """A value outside its parameter's range, or an unknown parameter."""


def get_int(db: Session, key: str) -> int:
    parameter = PARAMETERS[key]
    row = db.get(SystemSetting, key)
    if row is None:
        return parameter.default
    try:
        value = int(json.loads(row.value))
    except (TypeError, ValueError):
        return parameter.default
    # A row written before a range changed is clamped, never trusted blindly.
    return min(max(value, parameter.minimum), parameter.maximum)


def all_values(db: Session) -> dict[str, int]:
    return {key: get_int(db, key) for key in PARAMETERS}


def update(db: Session, changes: dict[str, object], admin_id: int) -> list[str]:
    """Validate every change first, then save them. Returns the keys that
    actually changed. Caller commits. Raises :class:`SettingError`."""
    clean: dict[str, int] = {}
    for key, raw in changes.items():
        parameter = PARAMETERS.get(key)
        if parameter is None:
            raise SettingError(f"Unknown parameter: {key}.")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise SettingError(f"{key} must be a whole number.")
        if not parameter.minimum <= raw <= parameter.maximum:
            raise SettingError(f"{key} must be between {parameter.minimum} and {parameter.maximum}.")
        clean[key] = raw

    changed: list[str] = []
    for key, value in clean.items():
        row = db.get(SystemSetting, key)
        if row is None:
            if value == PARAMETERS[key].default:
                continue
            row = SystemSetting(key=key, value=json.dumps(value))
            set_creation_audit(row, user_id=admin_id)
            db.add(row)
        else:
            if json.loads(row.value) == value:
                continue
            row.value = json.dumps(value)
            set_modification_audit(row, user_id=admin_id)
        changed.append(key)
    return changed


# --- Email settings (sign-up verification, SMTP) ------------------------------
#
# Read by code that has no database session (sending an email from a
# background task, the Phase 2 checks), so they live in a process cache that
# each request refreshes at most every SETTINGS_CACHE_SECONDS (default 10).
# A key the Admin never set falls back to the environment.

EMAIL_KEYS = ("email_verification", "smtp")
SMTP_SECURITY = ("starttls", "ssl", "none")

_cache: dict[str, Any] = {}
_loaded_at: float | None = None


def _cache_seconds() -> float:
    return float(os.environ.get("SETTINGS_CACHE_SECONDS", "10"))


def cache_is_fresh() -> bool:
    return _loaded_at is not None and time.monotonic() - _loaded_at < _cache_seconds()


def refresh_cache(db: Session, *, force: bool = False) -> None:
    global _cache, _loaded_at
    if not force and cache_is_fresh():
        return
    now = time.monotonic()
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(EMAIL_KEYS)).all()
    _cache = {row.key: json.loads(row.value) for row in rows}
    _loaded_at = now


def cached(key: str) -> Any | None:
    """The Admin's value for *key*, or None when it was never set."""
    return _cache.get(key)


def set_json(db: Session, key: str, value: Any, admin_id: int) -> None:
    """Store a JSON value (email settings). Caller commits."""
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=json.dumps(value))
        set_creation_audit(row, user_id=admin_id)
        db.add(row)
    else:
        row.value = json.dumps(value)
        set_modification_audit(row, user_id=admin_id)


def get_json(db: Session, key: str) -> Any | None:
    row = db.get(SystemSetting, key)
    return json.loads(row.value) if row else None

