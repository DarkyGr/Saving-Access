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

from datetime import date, datetime
from typing import Any


def set_creation_audit(record: Any, user_id: int) -> None:
    """
    Populate the three creation audit columns on a SQLAlchemy model instance.

    Sets:
      - record.creation_date       → date.today()
      - record.creation_time       → datetime.utcnow().time()
      - record.creation_user_id    → user_id

    Args:
        record:  Any SQLAlchemy mapped instance that has the three creation
                 audit columns.
        user_id: The primary key of the user performing the operation.
    """
    record.creation_date = date.today()
    record.creation_time = datetime.utcnow().time()
    record.creation_user_id = user_id


def set_modification_audit(record: Any, user_id: int) -> None:
    """
    Populate the three modification audit columns on a SQLAlchemy model instance.

    Sets:
      - record.modification_date       → date.today()
      - record.modification_time       → datetime.utcnow().time()
      - record.modification_user_id    → user_id

    Args:
        record:  Any SQLAlchemy mapped instance that has the three modification
                 audit columns.
        user_id: The primary key of the user performing the operation.
    """
    record.modification_date = date.today()
    record.modification_time = datetime.utcnow().time()
    record.modification_user_id = user_id
