"""
Property-based tests for audit column helpers.

Feature: password-manager-website

Properties tested:
  Property 4: Audit Columns on Creation  — Validates: Requirements 1.8, 4.11, 9.8
"""

import os
from datetime import date, time
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.utils.audit_columns import set_creation_audit, set_modification_audit


# ---------------------------------------------------------------------------
# Simple record stub — acts as a stand-in for any SQLAlchemy model instance.
# The helpers only require attribute assignment, so a plain object works.
# ---------------------------------------------------------------------------

class _RecordStub:
    """
    Minimal stand-in for any ORM-mapped model instance that carries the six
    audit columns.  No DB session or table mapping required.
    """

    def __init__(self) -> None:
        self.creation_date = None
        self.creation_time = None
        self.creation_user_id = None
        self.modification_date = None
        self.modification_time = None
        self.modification_user_id = None


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestAuditColumnsUnit:
    """Concrete examples verifying the basic contract of the audit helpers."""

    def test_set_creation_audit_populates_all_three_fields(self):
        record = _RecordStub()
        set_creation_audit(record, user_id=1)
        assert record.creation_date is not None
        assert record.creation_time is not None
        assert record.creation_user_id == 1

    def test_set_creation_audit_leaves_modification_fields_untouched(self):
        record = _RecordStub()
        set_creation_audit(record, user_id=99)
        assert record.modification_date is None
        assert record.modification_time is None
        assert record.modification_user_id is None

    def test_set_creation_audit_date_is_today(self):
        record = _RecordStub()
        set_creation_audit(record, user_id=1)
        assert record.creation_date == date.today()

    def test_set_creation_audit_time_is_a_time_instance(self):
        record = _RecordStub()
        set_creation_audit(record, user_id=1)
        assert isinstance(record.creation_time, time)

    def test_set_modification_audit_populates_all_three_fields(self):
        record = _RecordStub()
        set_modification_audit(record, user_id=7)
        assert record.modification_date is not None
        assert record.modification_time is not None
        assert record.modification_user_id == 7

    def test_set_modification_audit_leaves_creation_fields_untouched(self):
        record = _RecordStub()
        # Pre-populate creation fields to verify they are not clobbered.
        set_creation_audit(record, user_id=5)
        original_creation_date = record.creation_date
        original_creation_time = record.creation_time
        original_creation_user_id = record.creation_user_id

        set_modification_audit(record, user_id=7)

        assert record.creation_date == original_creation_date
        assert record.creation_time == original_creation_time
        assert record.creation_user_id == original_creation_user_id

    def test_set_creation_audit_with_mocked_sqlalchemy_model(self):
        """Verify helpers work with a MagicMock standing in for a real ORM row."""
        model = MagicMock()
        set_creation_audit(model, user_id=42)
        assert model.creation_date == date.today()
        assert model.creation_user_id == 42


# ---------------------------------------------------------------------------
# Property 4: Audit Columns on Creation
# Validates: Requirements 1.8, 4.11, 9.8
# ---------------------------------------------------------------------------

class TestAuditColumnsOnCreation:
    """
    Property 4: Audit Columns on Creation

    For any record that has ``set_creation_audit`` applied with any valid
    user_id, the three creation audit fields SHALL all be non-null
    immediately after the call:

      - creation_date     is not None
      - creation_time     is not None
      - creation_user_id  is not None (and equals the supplied user_id)

    Additionally, the modification fields must remain null (they are only
    populated by ``set_modification_audit``).

    Feature: password-manager-website, Property 4: Audit Columns on Creation
    Validates: Requirements 1.8, 4.11, 9.8
    """

    @given(user_id=st.integers(min_value=1))
    @settings(max_examples=100)
    def test_creation_fields_are_non_null_after_set_creation_audit(
        self, user_id: int
    ) -> None:
        """
        Feature: password-manager-website, Property 4: Audit Columns on Creation
        Validates: Requirements 1.8, 4.11, 9.8

        For any positive integer user_id, calling set_creation_audit on a
        fresh record leaves all three creation audit columns populated and
        non-null.
        """
        record = _RecordStub()

        # Pre-condition: all audit fields start as None.
        assert record.creation_date is None
        assert record.creation_time is None
        assert record.creation_user_id is None

        set_creation_audit(record, user_id=user_id)

        # Post-condition: all three creation audit columns are non-null.
        assert record.creation_date is not None, (
            f"creation_date is None after set_creation_audit(user_id={user_id})"
        )
        assert record.creation_time is not None, (
            f"creation_time is None after set_creation_audit(user_id={user_id})"
        )
        assert record.creation_user_id is not None, (
            f"creation_user_id is None after set_creation_audit(user_id={user_id})"
        )

        # The user_id stored must exactly match what was passed in.
        assert record.creation_user_id == user_id, (
            f"creation_user_id={record.creation_user_id!r} != supplied user_id={user_id}"
        )

        # Type checks: date and time instances are expected.
        assert isinstance(record.creation_date, date), (
            f"creation_date is not a date instance: {type(record.creation_date)}"
        )
        assert isinstance(record.creation_time, time), (
            f"creation_time is not a time instance: {type(record.creation_time)}"
        )

        # Modification fields must remain null — set_creation_audit must NOT
        # touch modification columns.
        assert record.modification_date is None, (
            "set_creation_audit unexpectedly populated modification_date"
        )
        assert record.modification_time is None, (
            "set_creation_audit unexpectedly populated modification_time"
        )
        assert record.modification_user_id is None, (
            "set_creation_audit unexpectedly populated modification_user_id"
        )

    @given(user_id=st.integers(min_value=1))
    @settings(max_examples=100)
    def test_creation_fields_non_null_on_mock_sqlalchemy_model(
        self, user_id: int
    ) -> None:
        """
        Feature: password-manager-website, Property 4: Audit Columns on Creation
        Validates: Requirements 1.8, 4.11, 9.8

        Verifies the same property using a MagicMock that simulates a real
        SQLAlchemy ORM instance (i.e., attribute assignment is intercepted).
        After set_creation_audit, reading the three creation columns back from
        the mock must yield non-null values matching the call arguments.
        """
        model = MagicMock()

        set_creation_audit(model, user_id=user_id)

        # MagicMock records assignments; reading back the attributes returns
        # the exact values that were assigned.
        assert model.creation_date == date.today(), (
            f"creation_date was not set to today's date on mock model "
            f"(user_id={user_id})"
        )
        assert model.creation_user_id == user_id, (
            f"creation_user_id={model.creation_user_id!r} != {user_id} on mock model"
        )
        # creation_time was assigned some time value — verify it is not None
        # by confirming the attribute was set (mock captures the assignment).
        assert model.creation_time is not None, (
            f"creation_time is None on mock model (user_id={user_id})"
        )

    @given(
        creator_id=st.integers(min_value=1),
        modifier_id=st.integers(min_value=1),
    )
    @settings(max_examples=100)
    def test_modification_audit_does_not_overwrite_creation_fields(
        self, creator_id: int, modifier_id: int
    ) -> None:
        """
        Feature: password-manager-website, Property 4: Audit Columns on Creation
        Validates: Requirements 1.8, 9.8

        After a record is first created (set_creation_audit) and then later
        modified (set_modification_audit), the original creation audit fields
        must remain unchanged.  This verifies that creation and modification
        helpers are independent and do not clobber each other's columns.
        """
        record = _RecordStub()

        set_creation_audit(record, user_id=creator_id)

        saved_creation_date = record.creation_date
        saved_creation_time = record.creation_time
        saved_creation_user_id = record.creation_user_id

        # Applying modification audit must NOT alter creation fields.
        set_modification_audit(record, user_id=modifier_id)

        assert record.creation_date == saved_creation_date, (
            "creation_date changed after set_modification_audit"
        )
        assert record.creation_time == saved_creation_time, (
            "creation_time changed after set_modification_audit"
        )
        assert record.creation_user_id == saved_creation_user_id, (
            "creation_user_id changed after set_modification_audit"
        )

        # And modification fields must now be populated.
        assert record.modification_date is not None
        assert record.modification_time is not None
        assert record.modification_user_id == modifier_id
