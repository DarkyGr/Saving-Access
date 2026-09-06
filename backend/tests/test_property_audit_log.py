"""
Property-based tests for AuditService.

Feature: password-manager-website

Properties tested:
  Property 13: Audit Log Entry on Every Mutation and Reveal
               — Validates: Requirements 4.12, 5.14, 6.9, 7.7
"""

from datetime import date, time

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.models import User, AuditLog
from app.services.audit_service import AuditService


# ---------------------------------------------------------------------------
# In-memory SQLite helpers
# ---------------------------------------------------------------------------
# We only need `users` and `audit_log` tables.  Other tables use JSONB
# (PostgreSQL-specific) and are intentionally excluded.
#
# FK enforcement is disabled via a SQLite PRAGMA so that we can insert
# audit_log rows with arbitrary user_id values without needing a real user row
# for every Hypothesis-generated integer — this keeps the tests fast and
# self-contained while still validating AuditService's own logic.
# ---------------------------------------------------------------------------

def _make_sqlite_session() -> Session:
    """Return a fresh in-memory SQLite session with only the tables we need."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Disable FK enforcement so arbitrary user_id values are accepted.
    @event.listens_for(engine, "connect")
    def _disable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    # Create only the two tables required for AuditService tests.
    User.__table__.create(bind=engine, checkfirst=True)
    AuditLog.__table__.create(bind=engine, checkfirst=True)

    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return TestSession()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid operations exactly matching the AuditService allowlist.
_valid_operations = st.sampled_from(["SELECT", "INSERT", "UPDATE", "DELETE"])

# Positive integers as user / record IDs (mirrors INTEGER PK domain).
_positive_int = st.integers(min_value=1, max_value=2_147_483_647)

# Optional affected_record_id: None OR a positive integer.
_optional_record_id = st.one_of(st.none(), _positive_int)

# Invalid operation strings: anything except the four valid values.
_invalid_operations = st.text(min_size=0).filter(
    lambda s: s not in {"SELECT", "INSERT", "UPDATE", "DELETE"}
)


# ---------------------------------------------------------------------------
# Unit tests — concrete examples
# ---------------------------------------------------------------------------

class TestAuditServiceUnit:
    """Concrete examples that verify the basic contract of AuditService."""

    def test_log_insert_persists_row(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        entry = svc.log(user_id=1, operation="INSERT", affected_record_id=42)

        assert entry.log_id is not None
        assert entry.user_id == 1
        assert entry.operation == "INSERT"
        assert entry.affected_record_id == 42
        assert isinstance(entry.operation_date, date)
        assert isinstance(entry.operation_time, time)
        db.close()

    def test_log_select_with_none_record_id(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        entry = svc.log(user_id=7, operation="SELECT", affected_record_id=None)

        assert entry.operation == "SELECT"
        assert entry.affected_record_id is None
        db.close()

    def test_log_update(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        entry = svc.log(user_id=3, operation="UPDATE", affected_record_id=99)

        assert entry.operation == "UPDATE"
        assert entry.user_id == 3
        assert entry.affected_record_id == 99
        db.close()

    def test_log_delete(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        entry = svc.log(user_id=5, operation="DELETE", affected_record_id=11)

        assert entry.operation == "DELETE"
        assert entry.affected_record_id == 11
        db.close()

    def test_invalid_operation_raises_value_error(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        with pytest.raises(ValueError, match="Invalid operation"):
            svc.log(user_id=1, operation="TRUNCATE")
        db.close()

    def test_empty_operation_raises_value_error(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        with pytest.raises(ValueError):
            svc.log(user_id=1, operation="")
        db.close()

    def test_multiple_log_entries_accumulate(self):
        """Each call to log() should produce a separate row."""
        db = _make_sqlite_session()
        svc = AuditService(db)

        e1 = svc.log(user_id=1, operation="INSERT", affected_record_id=1)
        e2 = svc.log(user_id=1, operation="UPDATE", affected_record_id=1)
        e3 = svc.log(user_id=1, operation="DELETE", affected_record_id=1)

        assert e1.log_id != e2.log_id != e3.log_id
        rows = db.query(AuditLog).all()
        assert len(rows) == 3
        db.close()

    def test_operation_date_is_today(self):
        db = _make_sqlite_session()
        svc = AuditService(db)
        entry = svc.log(user_id=1, operation="SELECT")
        assert entry.operation_date == date.today()
        db.close()


# ---------------------------------------------------------------------------
# Property 13: Audit Log Entry on Every Mutation and Reveal
# Validates: Requirements 4.12, 5.14, 6.9, 7.7
# ---------------------------------------------------------------------------

class TestAuditLogEntryOnEveryOperation:
    """
    Property 13: Audit Log Entry on Every Mutation and Reveal

    For any valid (user_id, operation, affected_record_id) triple, calling
    AuditService.log() SHALL produce an audit_log row with:
      - the exact operation string that was passed in
      - the exact user_id that was passed in
      - the exact affected_record_id that was passed in (including None)
      - a non-null operation_date equal to today's date
      - a non-null operation_time

    Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
    Validates: Requirements 4.12, 5.14, 6.9, 7.7
    """

    @given(
        user_id=_positive_int,
        operation=_valid_operations,
        affected_record_id=_optional_record_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_log_row_fields_match_inputs(
        self, user_id: int, operation: str, affected_record_id: int | None
    ):
        """
        After calling AuditService.log(user_id, operation, affected_record_id),
        the returned AuditLog entry has the exact field values that were passed
        in and non-null timestamp columns.

        Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
        Validates: Requirements 4.12, 5.14, 6.9, 7.7
        """
        db = _make_sqlite_session()
        svc = AuditService(db)

        entry = svc.log(
            user_id=user_id,
            operation=operation,
            affected_record_id=affected_record_id,
        )

        # 1. Primary-key assigned — the row was actually persisted.
        assert entry.log_id is not None, (
            "log_id is None — the row was not committed to the database."
        )

        # 2. operation field matches exactly.
        assert entry.operation == operation, (
            f"Expected operation={operation!r}, got {entry.operation!r}"
        )

        # 3. user_id field matches exactly.
        assert entry.user_id == user_id, (
            f"Expected user_id={user_id}, got {entry.user_id}"
        )

        # 4. affected_record_id matches (including None).
        assert entry.affected_record_id == affected_record_id, (
            f"Expected affected_record_id={affected_record_id!r}, "
            f"got {entry.affected_record_id!r}"
        )

        # 5. operation_date is non-null and equals today.
        assert entry.operation_date is not None, "operation_date must not be None"
        assert entry.operation_date == date.today(), (
            f"Expected operation_date={date.today()}, got {entry.operation_date}"
        )

        # 6. operation_time is non-null.
        assert entry.operation_time is not None, "operation_time must not be None"

        db.close()

    @given(
        user_id=_positive_int,
        operation=_valid_operations,
        affected_record_id=_optional_record_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_log_row_is_queryable_after_commit(
        self, user_id: int, operation: str, affected_record_id: int | None
    ):
        """
        The committed row is findable via a DB query, confirming the session
        was actually flushed and committed (not just held in memory).

        Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
        Validates: Requirements 4.12, 5.14, 6.9, 7.7
        """
        db = _make_sqlite_session()
        svc = AuditService(db)

        returned_entry = svc.log(
            user_id=user_id,
            operation=operation,
            affected_record_id=affected_record_id,
        )

        # Query the DB directly to confirm the row is durably stored.
        queried = db.query(AuditLog).filter(
            AuditLog.log_id == returned_entry.log_id
        ).one_or_none()

        assert queried is not None, (
            f"Row with log_id={returned_entry.log_id} not found after commit."
        )
        assert queried.operation == operation
        assert queried.user_id == user_id
        assert queried.affected_record_id == affected_record_id

        db.close()

    @given(
        user_id=_positive_int,
        operations=st.lists(
            _valid_operations, min_size=2, max_size=4
        ),
        affected_record_id=_positive_int,
    )
    @settings(max_examples=100, deadline=None)
    def test_every_call_produces_a_distinct_row(
        self, user_id: int, operations: list[str], affected_record_id: int
    ):
        """
        Each call to AuditService.log() produces a separate, distinct row —
        multiple operations on the same record all leave individual audit
        trail entries.

        Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
        Validates: Requirements 4.12, 5.14, 6.9, 7.7
        """
        db = _make_sqlite_session()
        svc = AuditService(db)

        entries = [
            svc.log(
                user_id=user_id,
                operation=op,
                affected_record_id=affected_record_id,
            )
            for op in operations
        ]

        # All log_ids must be distinct (each call creates a new row).
        log_ids = [e.log_id for e in entries]
        assert len(set(log_ids)) == len(log_ids), (
            f"Duplicate log_ids found: {log_ids} — some calls did not create "
            "separate rows."
        )

        # Total row count in DB must equal the number of calls made.
        total_rows = db.query(AuditLog).count()
        assert total_rows == len(operations), (
            f"Expected {len(operations)} rows, found {total_rows}"
        )

        db.close()


# ---------------------------------------------------------------------------
# Invalid operation property — ValueError for any non-valid operation string
# ---------------------------------------------------------------------------

class TestInvalidOperationRaisesValueError:
    """
    AuditService.log() must raise ValueError for any operation string that is
    not one of SELECT, INSERT, UPDATE, DELETE.

    Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
    Validates: Requirements 4.12, 5.14, 6.9, 7.7
    """

    @given(
        user_id=_positive_int,
        operation=_invalid_operations,
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_operation_always_raises(self, user_id: int, operation: str):
        """
        For any operation string outside the valid set, AuditService.log()
        SHALL raise a ValueError before touching the database.

        Feature: password-manager-website, Property 13: Audit Log Entry on Every Mutation and Reveal
        Validates: Requirements 4.12, 5.14, 6.9, 7.7
        """
        db = _make_sqlite_session()
        svc = AuditService(db)

        with pytest.raises(ValueError):
            svc.log(user_id=user_id, operation=operation)

        # The DB must be untouched — no rows written on invalid input.
        assert db.query(AuditLog).count() == 0, (
            "AuditLog row was committed despite an invalid operation value."
        )

        db.close()
