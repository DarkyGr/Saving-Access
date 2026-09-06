"""
AuditService — writes immutable audit_log entries for every user-initiated
data operation.

AuditService.log() is called synchronously before the API response is
returned so that the audit trail is always committed before the caller
receives a success response.

Requirements: 1.8, 4.11, 4.12, 5.14, 6.8, 6.9, 7.7, 9.5, 9.8
"""

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditLog

# Valid operation values mirror the CHECK constraint defined in the DDL and
# the AuditLog ORM model.
_VALID_OPERATIONS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})


class AuditService:
    """Provides a single :meth:`log` method that persists an audit entry."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        user_id: int,
        operation: str,
        affected_record_id: int | None = None,
    ) -> AuditLog:
        """Write an audit_log row and commit synchronously.

        :param user_id: PK of the user who performed the operation.
        :param operation: One of ``"SELECT"``, ``"INSERT"``, ``"UPDATE"``,
            or ``"DELETE"``.  Any other value raises :class:`ValueError`.
        :param affected_record_id: The PK of the record that was acted upon.
            May be ``None`` when the operation is not tied to a specific row
            (e.g., a list query).
        :raises ValueError: If *operation* is not one of the four accepted
            values.
        :returns: The persisted :class:`AuditLog` ORM instance.
        """
        if operation not in _VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation '{operation}'. "
                f"Must be one of: {', '.join(sorted(_VALID_OPERATIONS))}."
            )

        entry = AuditLog(
            user_id=user_id,
            operation=operation,
            affected_record_id=affected_record_id,
            operation_date=date.today(),
            operation_time=datetime.now(timezone.utc).time().replace(tzinfo=None),
        )

        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)

        return entry
