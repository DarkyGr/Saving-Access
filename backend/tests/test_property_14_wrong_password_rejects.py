"""
Property-based tests for Property 14: Wrong Account Password Rejects Sensitive Operations.

Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops

For any sensitive operation (save, reveal, edit, delete) submitted with an
incorrect account password, the backend SHALL return HTTP 401 and SHALL NOT
perform the requested mutation or decryption.

Validates: Requirements 4.9, 6.6, 7.5
"""

import os
from datetime import date, datetime, timezone, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from jose import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# ---------------------------------------------------------------------------
# Environment defaults — must be set before importing app modules that read them
# ---------------------------------------------------------------------------

_TEST_JWT_SECRET = "prop14-test-jwt-secret"
_TEST_BCRYPT_ROUNDS = "4"  # low rounds for test speed
_TEST_FERNET_KEY = Fernet.generate_key().decode()

os.environ.setdefault("JWT_SECRET", _TEST_JWT_SECRET)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "15")
os.environ.setdefault("BCRYPT_ROUNDS", _TEST_BCRYPT_ROUNDS)
os.environ.setdefault("FERNET_KEY", _TEST_FERNET_KEY)
# Override DATABASE_URL to prevent app.database from crashing at import time
# (it raises KeyError if DATABASE_URL is unset — we override get_db below).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Base, Credential, Profile, User, UserProfile  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.utils.audit_columns import set_creation_audit  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory SQLite test database helpers
# ---------------------------------------------------------------------------
# JSONB (PostgreSQL-only) is used by the `profiles` table.
# We create all tables except `profiles` and `user_profiles` because the
# credentials and auth tests only need `users`, `credentials`, and `audit_log`.
# The permission middleware queries `user_profiles` + `profiles` for User-role
# accounts; we sidestep that by giving our test user the "Admin" role so the
# middleware grants access unconditionally, without touching those tables.
# ---------------------------------------------------------------------------

def _make_test_engine():
    """Create a fresh in-memory SQLite engine with the required tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Disable FK enforcement so we can insert rows without satisfying every FK.
    @event.listens_for(engine, "connect")
    def _disable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    # Create only the tables needed for these tests (skip profiles/user_profiles
    # which use JSONB — a PostgreSQL-only type that SQLite cannot parse).
    User.__table__.create(bind=engine, checkfirst=True)
    Credential.__table__.create(bind=engine, checkfirst=True)
    AuditLog.__table__.create(bind=engine, checkfirst=True)

    return engine


def _make_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# JWT factory
# ---------------------------------------------------------------------------

def _issue_jwt(user_id: int, role: str = "Admin") -> str:
    """Issue a valid JWT for use in Authorization headers."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(
        payload,
        os.environ.get("JWT_SECRET", _TEST_JWT_SECRET),
        algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
    )


# ---------------------------------------------------------------------------
# Test fixture builder: creates a fresh DB + client for each Hypothesis call
# ---------------------------------------------------------------------------

class _TestFixture:
    """
    Encapsulates a fresh in-memory SQLite DB + registered user + TestClient
    for one Hypothesis iteration.

    Using Admin role so the permission middleware grants access without
    consulting the `profiles`/`user_profiles` tables (which use JSONB and
    cannot be created in SQLite).
    """

    CORRECT_PASSWORD = "CorrectPwd1@xyz"
    _CREDENTIAL_PASSWORD = "CredentialPassword1@"

    def __init__(self):
        # Fresh engine and session factory
        self._engine = _make_test_engine()
        self._SessionFactory = _make_session_factory(self._engine)
        self._db: Session = self._SessionFactory()

        # Register the user in the test DB
        auth_svc = AuthService(self._db)
        self._user: User = auth_svc.register({
            "username": "prop14user",
            "email": "prop14user@example.com",
            "password": self.CORRECT_PASSWORD,
            "password_confirmation": self.CORRECT_PASSWORD,
        })

        # Override the user's role to Admin so the middleware allows access
        # without needing a profile row (avoids JSONB table issue on SQLite).
        self._user.role = "Admin"
        self._db.commit()
        self._db.refresh(self._user)

        # Build the TestClient, overriding get_db to use our in-memory DB.
        db_ref = self._db

        def _override_get_db():
            try:
                yield db_ref
            finally:
                pass  # session managed externally

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=True)
        self.user_id = self._user.user_id
        self.token = _issue_jwt(self.user_id, role="Admin")
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

    def create_credential(self) -> int:
        """Insert a credential directly via the DB and return its id."""
        from app.services.encryptor_service import EncryptorService
        enc = EncryptorService()
        encrypted = enc.encrypt(self._CREDENTIAL_PASSWORD)

        cred = Credential(
            user_id=self.user_id,
            website_name="TestSite",
            email_or_username="user@testsite.com",
            is_username_login=False,
            encrypted_password=encrypted,
        )
        set_creation_audit(cred, user_id=self.user_id)
        self._db.add(cred)
        self._db.commit()
        self._db.refresh(cred)
        return cred.credential_id

    def credential_count(self) -> int:
        return self._db.query(Credential).filter(
            Credential.user_id == self.user_id
        ).count()

    def get_credential(self, credential_id: int) -> Credential | None:
        return self._db.query(Credential).filter(
            Credential.credential_id == credential_id
        ).first()

    def select_audit_entries(self, credential_id: int) -> list[AuditLog]:
        """Return all SELECT audit_log entries for a given credential."""
        return self._db.query(AuditLog).filter(
            AuditLog.operation == "SELECT",
            AuditLog.affected_record_id == credential_id,
            AuditLog.user_id == self.user_id,
        ).all()

    def teardown(self):
        app.dependency_overrides.clear()
        self._db.close()
        self._engine.dispose()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A "wrong" password: any non-empty string ≠ the user's correct password.
_wrong_password = st.text(min_size=1, max_size=32).filter(
    lambda s: s != _TestFixture.CORRECT_PASSWORD
)


# ---------------------------------------------------------------------------
# Property 14: Wrong Account Password Rejects Sensitive Operations
# Validates: Requirements 4.9, 6.6, 7.5
# ---------------------------------------------------------------------------


class TestWrongPasswordRejectsSensitiveOps:
    """
    Property 14: Wrong Account Password Rejects Sensitive Operations

    For any sensitive operation (save, reveal, edit, delete) submitted with
    an incorrect account password, the backend SHALL:
      1. Return HTTP 401 with detail "Account password verification failed."
      2. NOT perform the requested mutation or decryption.

    After a failed operation the database state is verified directly to
    confirm no change occurred.

    Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops
    Validates: Requirements 4.9, 6.6, 7.5
    """

    # ------------------------------------------------------------------
    # Sub-test A: POST /api/credentials with wrong account_password
    # ------------------------------------------------------------------

    @given(wrong_pwd=_wrong_password)
    @settings(max_examples=100, deadline=None)
    def test_save_with_wrong_password_returns_401_no_credential_created(
        self, wrong_pwd: str
    ):
        """
        POST /api/credentials with a wrong account_password must return 401
        and must NOT create a new credential record.

        Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops
        Validates: Requirements 4.9
        """
        fx = _TestFixture()
        try:
            before_count = fx.credential_count()

            response = fx.client.post(
                "/api/credentials",
                json={
                    "website_name": "EvilSite",
                    "email_or_username": "hacker@evilsite.com",
                    "is_username_login": False,
                    "password": "SomePassword1@",
                    "account_password": wrong_pwd,
                },
                headers=fx.auth_headers,
            )

            # Must return 401
            assert response.status_code == 401, (
                f"Expected 401 but got {response.status_code} for "
                f"wrong_pwd={wrong_pwd!r}. Body: {response.text}"
            )
            assert response.json().get("detail") == "Account password verification failed.", (
                f"Unexpected detail: {response.json()}"
            )

            # No new credential must have been created
            after_count = fx.credential_count()
            assert after_count == before_count, (
                f"Credential was created despite wrong password! "
                f"Before={before_count}, After={after_count}, "
                f"wrong_pwd={wrong_pwd!r}"
            )
        finally:
            fx.teardown()

    # ------------------------------------------------------------------
    # Sub-test B: POST /api/credentials/{id}/reveal with wrong account_password
    # ------------------------------------------------------------------

    @given(wrong_pwd=_wrong_password)
    @settings(max_examples=100, deadline=None)
    def test_reveal_with_wrong_password_returns_401_no_audit_log(
        self, wrong_pwd: str
    ):
        """
        POST /api/credentials/{id}/reveal with a wrong account_password must
        return 401 and must NOT write a SELECT entry to the audit_log.

        Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops
        Validates: Requirements 4.9, 6.6
        """
        fx = _TestFixture()
        try:
            cred_id = fx.create_credential()

            # Confirm no SELECT entries exist before the attempt
            select_entries_before = fx.select_audit_entries(cred_id)
            assert len(select_entries_before) == 0

            response = fx.client.post(
                f"/api/credentials/{cred_id}/reveal",
                json={"account_password": wrong_pwd},
                headers=fx.auth_headers,
            )

            # Must return 401
            assert response.status_code == 401, (
                f"Expected 401 but got {response.status_code} for "
                f"wrong_pwd={wrong_pwd!r}. Body: {response.text}"
            )
            assert response.json().get("detail") == "Account password verification failed.", (
                f"Unexpected detail: {response.json()}"
            )

            # No SELECT audit entry must have been written
            select_entries_after = fx.select_audit_entries(cred_id)
            assert len(select_entries_after) == 0, (
                f"SELECT audit entry was written despite wrong password! "
                f"Entries: {select_entries_after}, wrong_pwd={wrong_pwd!r}"
            )

            # The plaintext password must NOT appear in the response body
            assert "password" not in response.json() or response.json().get("password") is None, (
                "Response body contains a password field despite returning 401!"
            )
        finally:
            fx.teardown()

    # ------------------------------------------------------------------
    # Sub-test C: PUT /api/credentials/{id} with wrong account_password
    # ------------------------------------------------------------------

    @given(wrong_pwd=_wrong_password)
    @settings(max_examples=100, deadline=None)
    def test_edit_with_wrong_password_returns_401_credential_unchanged(
        self, wrong_pwd: str
    ):
        """
        PUT /api/credentials/{id} with a wrong account_password must return
        401 and must NOT modify the existing credential record.

        Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops
        Validates: Requirements 6.6
        """
        fx = _TestFixture()
        try:
            cred_id = fx.create_credential()

            # Capture original state
            original = fx.get_credential(cred_id)
            assert original is not None
            original_website = original.website_name
            original_email = original.email_or_username
            original_encrypted = bytes(original.encrypted_password)

            response = fx.client.put(
                f"/api/credentials/{cred_id}",
                json={
                    "website_name": "ChangedSite",
                    "email_or_username": "changed@site.com",
                    "is_username_login": True,
                    "password": "NewPassword1@",
                    "account_password": wrong_pwd,
                },
                headers=fx.auth_headers,
            )

            # Must return 401
            assert response.status_code == 401, (
                f"Expected 401 but got {response.status_code} for "
                f"wrong_pwd={wrong_pwd!r}. Body: {response.text}"
            )
            assert response.json().get("detail") == "Account password verification failed.", (
                f"Unexpected detail: {response.json()}"
            )

            # Credential must be unchanged — reload from DB
            fx._db.expire_all()
            after = fx.get_credential(cred_id)
            assert after is not None, "Credential was deleted despite wrong password!"

            assert after.website_name == original_website, (
                f"website_name changed despite wrong password! "
                f"Before={original_website!r}, After={after.website_name!r}, "
                f"wrong_pwd={wrong_pwd!r}"
            )
            assert after.email_or_username == original_email, (
                f"email_or_username changed despite wrong password! "
                f"Before={original_email!r}, After={after.email_or_username!r}, "
                f"wrong_pwd={wrong_pwd!r}"
            )
            assert bytes(after.encrypted_password) == original_encrypted, (
                "encrypted_password changed despite wrong password!"
            )
        finally:
            fx.teardown()

    # ------------------------------------------------------------------
    # Sub-test D: DELETE /api/credentials/{id} with wrong account_password
    # ------------------------------------------------------------------

    @given(wrong_pwd=_wrong_password)
    @settings(max_examples=100, deadline=None)
    def test_delete_with_wrong_password_returns_401_credential_still_exists(
        self, wrong_pwd: str
    ):
        """
        DELETE /api/credentials/{id} with a wrong account_password must return
        401 and must NOT delete the credential record.

        Feature: password-manager-website, Property 14: wrong-password-rejects-sensitive-ops
        Validates: Requirements 7.5
        """
        fx = _TestFixture()
        try:
            cred_id = fx.create_credential()

            import json as _json
            response = fx.client.request(
                "DELETE",
                f"/api/credentials/{cred_id}",
                content=_json.dumps({"account_password": wrong_pwd}).encode(),
                headers={**fx.auth_headers, "Content-Type": "application/json"},
            )

            # Must return 401
            assert response.status_code == 401, (
                f"Expected 401 but got {response.status_code} for "
                f"wrong_pwd={wrong_pwd!r}. Body: {response.text}"
            )
            assert response.json().get("detail") == "Account password verification failed.", (
                f"Unexpected detail: {response.json()}"
            )

            # Credential must still exist
            fx._db.expire_all()
            still_there = fx.get_credential(cred_id)
            assert still_there is not None, (
                f"Credential was deleted despite wrong password! "
                f"credential_id={cred_id}, wrong_pwd={wrong_pwd!r}"
            )
        finally:
            fx.teardown()
