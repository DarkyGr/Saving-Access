"""
Audit column helpers for SQLAlchemy model instances.

These functions populate the six standard audit columns defined in the ERD
and required by Requirement 9.8:

  Creation:     creation_date, creation_time, creation_user_id
  Modification: modification_date, modification_time, modification_user_id

Usage:
    from app.utils.audit_columns import set_creation_audit, set_modification_audit

    # On record creation:
    set_creation_audit(record, user_id=requesting_user_id)

    # On record update:
    set_modification_audit(record, user_id=requesting_user_id)
"""

from datetime import UTC, date, datetime, time
from typing import Any


def utc_date_time() -> tuple[date, time]:
    """Current UTC date and time taken from the *same* instant.

    Earlier code combined ``date.today()`` (server local date) with a UTC
    time, which could disagree around midnight (task 32.3).
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.date(), now.time()


def set_creation_audit(record: Any, user_id: int | None) -> None:
    """Populate creation_date / creation_time (UTC) and creation_user_id."""
    record.creation_date, record.creation_time = utc_date_time()
    record.creation_user_id = user_id


def set_modification_audit(record: Any, user_id: int) -> None:
    """Populate modification_date / modification_time (UTC) and modification_user_id."""
    record.modification_date, record.modification_time = utc_date_time()
    record.modification_user_id = user_id
