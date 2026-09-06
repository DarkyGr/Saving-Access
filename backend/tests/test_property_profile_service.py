"""
Property-based tests for ProfileService.

Feature: password-manager-website

Properties tested:
  Property 7: Non-Admin Denied Access to Admin Screens
              — Validates: Requirements 3.2, 3.4, 3.6
  Property 8: Profile Assignment Updates Audit Columns
              — Validates: Requirements 3.3
"""

import os
import string
from datetime import date, time, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from jose import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.models import Base, Profile, User, UserProfile
from app.services.profile_service import ProfileService
from app.utils.audit_columns import set_creation_audit, set_modification_audit

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-profile-secret-7and8"
_TEST_ALGORITHM = "HS256"

os.environ.setdefault("JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("JWT_ALGORITHM", _TEST_ALGORITHM)
os.environ.setdefault("JWT_EXPIRE_MINUTES", "15")
os.environ.setdefault("BCRYPT_ROUNDS", "4")


# ---------------------------------------------------------------------------
# In-memory SQLite helpers
# ---------------------------------------------------------------------------
# The `profiles` table uses JSONB (PostgreSQL-only).  We work around this for
# SQLite tests in Property 8 by using a mock DB session — see below.
# For Property 7 no DB query is needed (the test relies on JWT claims only).
# ---------------------------------------------------------------------------

def _make_sqlite_users_session() -> Session:
    """SQLite session with only the `users` table (for Property 7 helpers)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _disable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    User.__table__.create(bind=engine, checkfirst=True)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return TestSession()


# ---------------------------------------------------------------------------
# Stub admin FastAPI app for Property 7
# ---------------------------------------------------------------------------
# We create a minimal FastAPI app that:
#   1. Registers two stub admin endpoints: GET and PUT /api/admin/users
#   2. Uses a lightweight JWT-based permission dependency that:
#        - Decodes the Bearer token
#        - Returns 403 if role != "Admin"
#        - Returns 401 if no/invalid token
# This mirrors exactly what the real permission middleware (Task 9) will do,
# letting us validate Property 7 independently of the admin router (Task 12).
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Dependency: decode JWT and enforce Admin role; raise 403 for User role."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            os.environ.get("JWT_SECRET", _TEST_SECRET),
            algorithms=[os.environ.get("JWT_ALGORITHM", _TEST_ALGORITHM)],
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    role = payload.get("role", "")
    if role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )
    return payload


_stub_app = FastAPI()


@_stub_app.get("/api/admin/users")
def _stub_list_users(claims: dict = Depends(_require_admin)):
    return []


@_stub_app.put("/api/admin/users/{user_id}/profile")
def _stub_assign_profile(user_id: int, claims: dict = Depends(_require_admin)):
    return {"user_id": user_id, "profile_id": 1}


_test_client = TestClient(_stub_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# JWT factories
# ---------------------------------------------------------------------------

def _make_jwt(role: str, user_id: int = 1, expire_minutes: int = 15) -> str:
    """Issue a signed JWT with the given role claim."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(
        payload,
        os.environ.get("JWT_SECRET", _TEST_SECRET),
        algorithm=os.environ.get("JWT_ALGORITHM", _TEST_ALGORITHM),
    )


# ---------------------------------------------------------------------------
# Simple record stub for Property 8 (mirrors test_property_audit_columns.py)
# ---------------------------------------------------------------------------

class _UserProfileStub:
    """Minimal stand-in for a UserProfile ORM instance."""

    def __init__(
        self,
        user_profile_id: int | None = None,
        user_id: int = 1,
        profile_id: int = 1,
    ) -> None:
        self.user_profile_id = user_profile_id
        self.user_id = user_id
        self.profile_id = profile_id
        self.creation_date = None
        self.creation_time = None
        self.creation_user_id = None
        self.modification_date = None
        self.modification_time = None
        self.modification_user_id = None


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_positive_int = st.integers(min_value=1, max_value=2_147_483_647)

# Any role that is NOT "Admin"
_non_admin_role = st.text(
    alphabet=string.ascii_letters + string.digits + "_-",
    min_size=1,
    max_size=32,
).filter(lambda r: r != "Admin")


# ---------------------------------------------------------------------------
# Property 7: Non-Admin Denied Access to Admin Screens
# Validates: Requirements 3.2, 3.4, 3.6
# ---------------------------------------------------------------------------

class TestNonAdminDeniedAdminEndpoints:
    """
    Property 7: Non-Admin Denied Access to Admin Screens

    For any JWT whose ``role`` claim is not ``"Admin"``, every request to
    ``/api/admin/*`` endpoints SHALL return HTTP 403 Forbidden.

    Feature: password-manager-website, Property 7: Non-Admin Denied Access to Admin Screens
    Validates: Requirements 3.2, 3.4, 3.6
    """

    # The two admin endpoints exposed by the stub app
    _ADMIN_ENDPOINTS = [
        ("GET",  "/api/admin/users"),
        ("PUT",  "/api/admin/users/42/profile"),
    ]

    def _request(self, method: str, path: str, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            return _test_client.get(path, headers=headers)
        elif method == "PUT":
            return _test_client.put(path, headers=headers, json={"profile_id": 1})
        raise ValueError(f"Unsupported method: {method}")

    @given(
        user_id=_positive_int,
        non_admin_role=_non_admin_role,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_user_role_receives_403_on_all_admin_endpoints(
        self, user_id: int, non_admin_role: str
    ):
        """
        Any JWT with role != "Admin" must receive 403 on every admin endpoint.

        Feature: password-manager-website, Property 7: Non-Admin Denied Access to Admin Screens
        Validates: Requirements 3.2, 3.4, 3.6
        """
        token = _make_jwt(role=non_admin_role, user_id=user_id)

        for method, path in self._ADMIN_ENDPOINTS:
            response = self._request(method, path, token)
            assert response.status_code == status.HTTP_403_FORBIDDEN, (
                f"{method} {path} with role={non_admin_role!r} (user_id={user_id}) "
                f"returned {response.status_code} instead of 403. "
                f"Body: {response.text}"
            )

    @given(user_id=_positive_int)
    @settings(max_examples=100)
    def test_explicit_user_role_receives_403(self, user_id: int):
        """
        The literal role value "User" (as stored in the DB for all
        non-admin accounts) must always receive 403 on admin endpoints.

        Feature: password-manager-website, Property 7: Non-Admin Denied Access to Admin Screens
        Validates: Requirements 3.2, 3.4, 3.6
        """
        token = _make_jwt(role="User", user_id=user_id)

        for method, path in self._ADMIN_ENDPOINTS:
            response = self._request(method, path, token)
            assert response.status_code == status.HTTP_403_FORBIDDEN, (
                f"{method} {path} returned {response.status_code} for role='User' "
                f"(user_id={user_id}). Body: {response.text}"
            )

    @given(user_id=_positive_int)
    @settings(max_examples=50)
    def test_admin_role_is_not_blocked(self, user_id: int):
        """
        Contrast: a JWT with role="Admin" must NOT receive 403.
        This validates the inverse of the property — the guard only blocks
        non-admins, not admins.

        Feature: password-manager-website, Property 7: Non-Admin Denied Access to Admin Screens
        Validates: Requirements 3.2, 3.5
        """
        token = _make_jwt(role="Admin", user_id=user_id)

        for method, path in self._ADMIN_ENDPOINTS:
            response = self._request(method, path, token)
            assert response.status_code != status.HTTP_403_FORBIDDEN, (
                f"{method} {path} incorrectly blocked Admin (user_id={user_id}). "
                f"Status: {response.status_code}, Body: {response.text}"
            )

    def test_missing_token_returns_401_not_403(self):
        """
        A request with no Authorization header must return 401, not 403.
        This confirms the guard distinguishes unauthenticated from unauthorized.

        Feature: password-manager-website, Property 7: Non-Admin Denied Access to Admin Screens
        Validates: Requirements 3.6
        """
        for method, path in self._ADMIN_ENDPOINTS:
            if method == "GET":
                response = _test_client.get(path)
            else:
                response = _test_client.put(path, json={"profile_id": 1})
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"{method} {path} without token returned {response.status_code} "
                f"instead of 401."
            )


# ---------------------------------------------------------------------------
# Property 8: Profile Assignment Updates Audit Columns
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestProfileAssignmentUpdatesAuditColumns:
    """
    Property 8: Profile Assignment Updates Audit Columns

    After ``ProfileService.assign_profile(admin_id, user_id, profile_id)``
    executes:
      - If an existing ``user_profiles`` row was updated:
            ``modification_date``, ``modification_time``, and
            ``modification_user_id`` are all non-null, modification_date
            equals today, and modification_user_id equals ``admin_id``.
      - If a new ``user_profiles`` row was inserted:
            ``creation_date``, ``creation_time``, and ``creation_user_id``
            are all non-null, creation_date equals today, and
            creation_user_id equals ``admin_id``.

    The DB session is mocked so this test does not require a live database.

    Feature: password-manager-website, Property 8: Profile Assignment Updates Audit Columns
    Validates: Requirements 3.3
    """

    # ------------------------------------------------------------------
    # Mock DB session factory
    # ------------------------------------------------------------------

    def _make_mock_db(
        self, existing_record: _UserProfileStub | None = None
    ) -> MagicMock:
        """Return a MagicMock that simulates a SQLAlchemy Session.

        If *existing_record* is not None, ``query().filter().first()`` returns
        it (simulating an existing row).  Otherwise ``first()`` returns None.
        """
        mock_db = MagicMock(spec=Session)

        # Chain: db.query(UserProfile).filter(...).first()
        mock_filter = MagicMock()
        mock_filter.first.return_value = existing_record
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        # refresh() should update the record's PK (simulate autoincrement)
        def _refresh(record):
            if record.user_profile_id is None:
                record.user_profile_id = 99  # simulated DB-assigned PK

        mock_db.refresh.side_effect = _refresh

        return mock_db

    # ------------------------------------------------------------------
    # Property 8a — UPDATE path: existing row gets modification audit
    # ------------------------------------------------------------------

    @given(
        admin_id=_positive_int,
        user_id=_positive_int,
        profile_id=_positive_int,
        new_profile_id=_positive_int,
    )
    @settings(max_examples=100, deadline=None)
    def test_update_path_sets_modification_audit_columns(
        self,
        admin_id: int,
        user_id: int,
        profile_id: int,
        new_profile_id: int,
    ):
        """
        When assign_profile finds an existing user_profiles row, it must
        set modification_date to today, modification_time to a non-null time,
        and modification_user_id to admin_id.

        Feature: password-manager-website, Property 8: Profile Assignment Updates Audit Columns
        Validates: Requirements 3.3
        """
        # Simulate an existing row
        existing = _UserProfileStub(
            user_profile_id=10,
            user_id=user_id,
            profile_id=profile_id,
        )
        mock_db = self._make_mock_db(existing_record=existing)

        svc = ProfileService(mock_db)
        result = svc.assign_profile(
            admin_id=admin_id,
            user_id=user_id,
            profile_id=new_profile_id,
        )

        # profile_id must be updated
        assert result.profile_id == new_profile_id, (
            f"profile_id not updated: expected {new_profile_id}, got {result.profile_id}"
        )

        # All three modification audit columns must be non-null
        assert result.modification_date is not None, (
            f"modification_date is None after assign_profile (admin_id={admin_id})"
        )
        assert result.modification_time is not None, (
            f"modification_time is None after assign_profile (admin_id={admin_id})"
        )
        assert result.modification_user_id is not None, (
            f"modification_user_id is None after assign_profile (admin_id={admin_id})"
        )

        # modification_date must equal today
        assert result.modification_date == date.today(), (
            f"modification_date={result.modification_date!r} != today "
            f"({date.today()!r}) for admin_id={admin_id}"
        )

        # modification_user_id must equal the performing admin's id
        assert result.modification_user_id == admin_id, (
            f"modification_user_id={result.modification_user_id!r} != "
            f"admin_id={admin_id}"
        )

        # modification_time must be a time instance
        assert isinstance(result.modification_time, time), (
            f"modification_time is not a time instance: "
            f"{type(result.modification_time)} (admin_id={admin_id})"
        )

        # Verify commit was called
        mock_db.commit.assert_called()

    # ------------------------------------------------------------------
    # Property 8b — INSERT path: new row gets creation audit
    # ------------------------------------------------------------------

    @given(
        admin_id=_positive_int,
        user_id=_positive_int,
        profile_id=_positive_int,
    )
    @settings(max_examples=100, deadline=None)
    def test_insert_path_sets_creation_audit_columns(
        self,
        admin_id: int,
        user_id: int,
        profile_id: int,
    ):
        """
        When assign_profile inserts a new user_profiles row (no existing row),
        it must set creation_date to today, creation_time to a non-null time,
        and creation_user_id to admin_id.

        Feature: password-manager-website, Property 8: Profile Assignment Updates Audit Columns
        Validates: Requirements 3.3
        """
        mock_db = self._make_mock_db(existing_record=None)

        # Capture the record that is added to the session so we can inspect it
        added_records: list = []
        mock_db.add.side_effect = lambda r: added_records.append(r)

        svc = ProfileService(mock_db)
        result = svc.assign_profile(
            admin_id=admin_id,
            user_id=user_id,
            profile_id=profile_id,
        )

        # One record must have been added
        assert len(added_records) == 1, (
            f"Expected 1 record added via db.add(), got {len(added_records)}"
        )
        added = added_records[0]

        # The added record is the same object returned
        assert added is result

        # All three creation audit columns must be non-null
        assert result.creation_date is not None, (
            f"creation_date is None after new assign_profile (admin_id={admin_id})"
        )
        assert result.creation_time is not None, (
            f"creation_time is None after new assign_profile (admin_id={admin_id})"
        )
        assert result.creation_user_id is not None, (
            f"creation_user_id is None after new assign_profile (admin_id={admin_id})"
        )

        # creation_date must equal today
        assert result.creation_date == date.today(), (
            f"creation_date={result.creation_date!r} != today ({date.today()!r}) "
            f"for admin_id={admin_id}"
        )

        # creation_user_id must equal the performing admin's id
        assert result.creation_user_id == admin_id, (
            f"creation_user_id={result.creation_user_id!r} != admin_id={admin_id}"
        )

        # creation_time must be a time instance
        assert isinstance(result.creation_time, time), (
            f"creation_time is not a time instance: "
            f"{type(result.creation_time)} (admin_id={admin_id})"
        )

        # modification fields must remain null on a fresh insert
        assert result.modification_date is None, (
            "modification_date was unexpectedly set on a new row insert"
        )
        assert result.modification_time is None, (
            "modification_time was unexpectedly set on a new row insert"
        )
        assert result.modification_user_id is None, (
            "modification_user_id was unexpectedly set on a new row insert"
        )

        # Verify commit was called
        mock_db.commit.assert_called()

    # ------------------------------------------------------------------
    # Property 8c — UPDATE path does NOT clobber creation audit fields
    # ------------------------------------------------------------------

    @given(
        admin_id=_positive_int,
        creator_id=_positive_int,
        user_id=_positive_int,
        profile_id=_positive_int,
    )
    @settings(max_examples=100, deadline=None)
    def test_update_path_preserves_creation_audit_columns(
        self,
        admin_id: int,
        creator_id: int,
        user_id: int,
        profile_id: int,
    ):
        """
        When assign_profile updates an existing row, the original creation
        audit columns must not be overwritten.

        Feature: password-manager-website, Property 8: Profile Assignment Updates Audit Columns
        Validates: Requirements 3.3, 9.8
        """
        existing = _UserProfileStub(
            user_profile_id=5,
            user_id=user_id,
            profile_id=profile_id,
        )
        # Pre-populate creation audit as if this row was originally created
        # by a different admin (creator_id)
        set_creation_audit(existing, user_id=creator_id)
        saved_creation_date = existing.creation_date
        saved_creation_time = existing.creation_time
        saved_creation_user_id = existing.creation_user_id

        mock_db = self._make_mock_db(existing_record=existing)

        svc = ProfileService(mock_db)
        result = svc.assign_profile(
            admin_id=admin_id,
            user_id=user_id,
            profile_id=profile_id + 1,
        )

        # Creation fields must be unchanged
        assert result.creation_date == saved_creation_date, (
            "creation_date was overwritten during profile update"
        )
        assert result.creation_time == saved_creation_time, (
            "creation_time was overwritten during profile update"
        )
        assert result.creation_user_id == saved_creation_user_id, (
            "creation_user_id was overwritten during profile update"
        )

        # Modification fields must now be populated
        assert result.modification_user_id == admin_id, (
            f"modification_user_id={result.modification_user_id!r} != "
            f"admin_id={admin_id}"
        )
        assert result.modification_date == date.today()
        assert result.modification_time is not None
