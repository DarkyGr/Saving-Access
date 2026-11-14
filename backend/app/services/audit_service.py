"""
AuditService — writes immutable audit_log entries for every user-initiated
data operation.

AuditService.log() is called synchronously before the API response is
returned. Routers pass ``commit=False`` and commit the data change and the
audit row in one transaction (task 31.4): either both persist or neither.

Requirements: 1.8, 4.11, 4.12, 5.14, 6.8, 6.9, 7.7, 9.5, 9.8
"""


from sqlalchemy.orm import Session

from app.models import AuditLog
from app.utils.audit_columns import utc_date_time

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
        *,
        commit: bool = True,
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

        op_date, op_time = utc_date_time()
        entry = AuditLog(
            user_id=user_id,
            operation=operation,
            affected_record_id=affected_record_id,
            operation_date=op_date,
            operation_time=op_time,
        )

        self._db.add(entry)
        if commit:
            self._db.commit()
            self._db.refresh(entry)
        else:
            # Caller commits the data change and this row together, so a
            # mutation can never be persisted without its audit entry.
            self._db.flush()

        return entry
