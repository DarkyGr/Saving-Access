"""
System parameters set by the Admin (Requirement 16.8, task 37.5).

Each parameter declares its default, range and suggested value here; the
``system_settings`` table only holds the values the Admin changed. Reading a
parameter that was never set returns its default, so a fresh installation
works without any row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

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
