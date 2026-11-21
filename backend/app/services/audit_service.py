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

# Task 37.4: the audit view names what happened. Credential routes pass only
# the operation, which maps to these; other events name their action.
_CREDENTIAL_ACTIONS = {
    "INSERT": "credential.create",
    "UPDATE": "credential.edit",
    "DELETE": "credential.delete",
    "SELECT": "credential.reveal",
}

ACTIONS: tuple[str, ...] = (
    *_CREDENTIAL_ACTIONS.values(),
    "account.register",
    "account.login",
    "account.password",
    "account.unlock",
    "account.password_reset",
    "account.export",
    "account.delete",
    "account.2fa_setup",
    "account.recovery_codes",
    "account.trust_device",
    "account.forget_devices",
    "user.role",
    "user.deactivate",
    "user.reactivate",
    "user.unlock",
    "user.reset_2fa",
    "settings.update",
)


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
        action: str | None = None,
        target_user_id: int | None = None,
        detail: str | None = None,
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

        action = action or _CREDENTIAL_ACTIONS[operation]
        if action not in ACTIONS:
            raise ValueError(f"Invalid action '{action}'.")

        op_date, op_time = utc_date_time()
        entry = AuditLog(
            user_id=user_id,
            operation=operation,
            affected_record_id=affected_record_id,
            operation_date=op_date,
            operation_time=op_time,
            action=action,
            target_user_id=target_user_id,
            detail=detail,
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
