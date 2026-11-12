"""
Integration tests for the full credential lifecycle.

Feature: password-manager-website

Test: test_full_credential_lifecycle
  Exercises every credential endpoint end-to-end against an in-memory SQLite
  database, using FastAPI's TestClient and an overridden get_db dependency.

  Steps covered:
    1. POST /api/auth/register              → 201
    2. POST /api/auth/login                 → 200 + JWT
    3. POST /api/credentials               → 201 (INSERT audit row)
    4. GET  /api/credentials               → 200 (list, password null)
    5. POST /api/credentials/{id}/reveal   → 200 (SELECT audit row)
    6. PUT  /api/credentials/{id}          → 200 (UPDATE audit row)
    7. DELETE /api/credentials/{id}        → 204 (DELETE audit row)

  After steps 3–7 (every mutation / reveal), the test queries audit_log
  directly and asserts a row exists with the correct operation, user_id,
  and affected_record_id.

Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7
"""

import os

from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Environment variables must be set BEFORE importing any app modules so that
# database.py, auth_service.py, and encryptor_service.py all pick them up at
# import time.
# ---------------------------------------------------------------------------

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-integration-lifecycle-secret"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["JWT_EXPIRE_MINUTES"] = "15"
# Low bcrypt cost for fast tests
os.environ["BCRYPT_ROUNDS"] = "4"
# Prevent the startup event from calling Base.metadata.create_all on the
# real Postgres engine referenced by DATABASE_URL.
os.environ["ENVIRONMENT"] = "test"

# ---------------------------------------------------------------------------
# Imports — after env vars
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker, Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, User  # noqa: E402

# ---------------------------------------------------------------------------
# In-memory SQLite engine shared across the whole module
#
# StaticPool: every session reuses the identical underlying SQLite connection
# so that:
#   - Tables created at module-setup time are visible to TestClient requests.
#   - Data written by the test is visible to route handlers and vice versa.
#
# check_same_thread=False: TestClient can call route handlers on worker threads.
# FK enforcement is disabled so AuditLog rows referencing user_ids in test
# data survive without cascading FK errors during table setup.
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_ENGINE, "connect")
def _disable_fk(dbapi_conn, _record):  # pragma: no cover
    dbapi_conn.execute("PRAGMA foreign_keys = OFF")


# Create only the tables this integration test actually touches.
# Profile and UserProfile are JSONB-backed (PostgreSQL-only) and are
# deliberately excluded.  The test uses an Admin-role JWT so the
# permissions middleware bypasses the profile lookup entirely.
User.__table__.create(bind=_ENGINE, checkfirst=True)
Credential.__table__.create(bind=_ENGINE, checkfirst=True)
AuditLog.__table__.create(bind=_ENGINE, checkfirst=True)

_TestingSessionLocal = sessionmaker(
    bind=_ENGINE,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# get_db override — routes all FastAPI sessions to the shared engine
# ---------------------------------------------------------------------------


def _override_get_db():
    """FastAPI dependency override that yields a session on the shared engine."""
    db: Session = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

# Single TestClient shared across all tests in this module.
_client = TestClient(app, raise_server_exceptions=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A valid password that satisfies AuthService's strength rules:
#   length ≥ 12, uppercase, lowercase, digit, symbol from {@, $, !}
_STRONG_PASSWORD = "Integration1@Test"


def _latest_audit_row(db: Session) -> AuditLog | None:
    """Return the most recently inserted audit_log row (highest log_id)."""
    return (
        db.query(AuditLog)
        .order_by(AuditLog.log_id.desc())
        .first()
    )


def _assert_audit_row(
    db: Session,
    operation: str,
    user_id: int,
    affected_record_id: int | None,
) -> None:
    """Assert that the most recent audit row matches the expected values."""
    # Expire cached ORM state so we see the latest committed rows.
    db.expire_all()

    row = _latest_audit_row(db)
    assert row is not None, (
        f"Expected an audit_log row for operation={operation!r} "
        f"but no rows exist."
    )
    assert row.operation == operation, (
        f"audit_log.operation: expected {operation!r}, got {row.operation!r}"
    )
    assert row.user_id == user_id, (
        f"audit_log.user_id: expected {user_id}, got {row.user_id}"
    )
    assert row.affected_record_id == affected_record_id, (
        f"audit_log.affected_record_id: expected {affected_record_id!r}, "
        f"got {row.affected_record_id!r}"
    )


# ---------------------------------------------------------------------------
# Integration test: full credential lifecycle
# Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7
# ---------------------------------------------------------------------------


class TestFullCredentialLifecycle:
    """
    End-to-end integration test that walks through the complete credential
    lifecycle and verifies every audit_log entry.

    The test is structured as a single linear method so that each step
    depends on the state produced by the previous step (a real user is
    registered, logs in, creates a credential, etc.).  Assertions are
    inline after every HTTP call.
    """

    def test_full_credential_lifecycle(self) -> None:
        """
        Execute the full credential lifecycle and assert correctness at
        every step, including audit_log entries after each mutation.

        Steps:
          1. Register a new user account.
          2. Log in and obtain a JWT.
          3. Save a new credential (POST) → assert INSERT audit row.
          4. List credentials (GET) → assert password is null.
          5. Reveal the credential password (POST /reveal) → assert SELECT audit row.
          6. Update the credential (PUT) → assert UPDATE audit row.
          7. Delete the credential (DELETE) → assert DELETE audit row.

        Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7
        """
        # Obtain a direct DB session for audit_log assertions.
        db: Session = _TestingSessionLocal()

        try:
            # ------------------------------------------------------------------
            # Step 1: Register a new user
            # ------------------------------------------------------------------
            register_resp = _client.post(
                "/api/auth/register",
                json={
                    "username": "lifecycle_user",
                    "email": "lifecycle@example.com",
                    "password": _STRONG_PASSWORD,
                    "password_confirmation": _STRONG_PASSWORD,
                },
            )
            assert register_resp.status_code == 201, (
                f"Register failed: {register_resp.status_code} {register_resp.text}"
            )
            register_body = register_resp.json()
            assert register_body["username"] == "lifecycle_user"
            assert register_body["role"] == "User"
            registered_user_id: int = register_body["user_id"]

            # Promote the user to Admin so the permissions middleware skips the
            # JSONB-backed Profile/UserProfile tables (which are not created in
            # the SQLite in-memory schema).
            user_row = db.query(User).filter(User.user_id == registered_user_id).first()
            assert user_row is not None
            user_row.role = "Admin"
            db.commit()

            # ------------------------------------------------------------------
            # Step 2: Log in and obtain a JWT
            # ------------------------------------------------------------------
            login_resp = _client.post(
                "/api/auth/login",
                json={
                    "username": "lifecycle_user",
                    "password": _STRONG_PASSWORD,
                },
            )
            assert login_resp.status_code == 200, (
                f"Login failed: {login_resp.status_code} {login_resp.text}"
            )
            login_body = login_resp.json()
            assert "access_token" in login_body
            assert login_body["token_type"] == "bearer"
            assert login_body["expires_in"] == 900  # 15 min × 60

            access_token: str = login_body["access_token"]
            auth_headers = {"Authorization": f"Bearer {access_token}"}

            # ------------------------------------------------------------------
            # Step 3: Save a new credential
            # POST /api/credentials → 201
            # Expect: INSERT row in audit_log
            # ------------------------------------------------------------------
            create_resp = _client.post(
                "/api/credentials",
                json={
                    "website_name": "github.com",
                    "email_or_username": "lifecycle@example.com",
                    "is_username_login": False,
                    "password": "GitHubPass1@",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=auth_headers,
            )
            assert create_resp.status_code == 201, (
                f"Create credential failed: {create_resp.status_code} {create_resp.text}"
            )
            create_body = create_resp.json()
            assert create_body["website_name"] == "github.com"
            credential_id: int = create_body["credential_id"]

            # Assert audit_log has an INSERT row for this credential
            _assert_audit_row(
                db,
                operation="INSERT",
                user_id=registered_user_id,
                affected_record_id=credential_id,
            )

            # ------------------------------------------------------------------
            # Step 4: List credentials
            # GET /api/credentials → 200
            # Credential must appear; password must be null
            # ------------------------------------------------------------------
            list_resp = _client.get("/api/credentials", headers=auth_headers)
            assert list_resp.status_code == 200, (
                f"List credentials failed: {list_resp.status_code} {list_resp.text}"
            )
            items = list_resp.json()
            assert isinstance(items, list)
            assert len(items) >= 1

            # Find the credential we just created
            matching = [c for c in items if c["credential_id"] == credential_id]
            assert len(matching) == 1, (
                f"Credential {credential_id} not found in list response. "
                f"Items: {items}"
            )
            cred_item = matching[0]
            assert cred_item["website_name"] == "github.com"
            assert cred_item["email_or_username"] == "lifecycle@example.com"
            assert cred_item["is_username_login"] is False
            # Requirement 5.4 — password is always null in list responses
            assert cred_item["password"] is None, (
                f"password should be null in list response, got {cred_item['password']!r}"
            )

            # List does not emit an audit_log row (SELECT is only logged on reveal)
            # so we do NOT assert an audit row here.

            # ------------------------------------------------------------------
            # Step 5: Reveal the credential password
            # POST /api/credentials/{id}/reveal → 200
            # Expect: SELECT row in audit_log
            # ------------------------------------------------------------------
            reveal_resp = _client.post(
                f"/api/credentials/{credential_id}/reveal",
                json={"account_password": _STRONG_PASSWORD},
                headers=auth_headers,
            )
            assert reveal_resp.status_code == 200, (
                f"Reveal failed: {reveal_resp.status_code} {reveal_resp.text}"
            )
            reveal_body = reveal_resp.json()
            assert "password" in reveal_body
            assert reveal_body["password"] == "GitHubPass1@", (
                f"Decrypted password mismatch: {reveal_body['password']!r}"
            )

            # Assert audit_log has a SELECT row for this credential
            _assert_audit_row(
                db,
                operation="SELECT",
                user_id=registered_user_id,
                affected_record_id=credential_id,
            )

            # ------------------------------------------------------------------
            # Step 6: Update the credential
            # PUT /api/credentials/{id} → 200
            # Expect: UPDATE row in audit_log
            # ------------------------------------------------------------------
            update_resp = _client.put(
                f"/api/credentials/{credential_id}",
                json={
                    "website_name": "github.com",
                    "email_or_username": "new_lifecycle@example.com",
                    "is_username_login": False,
                    "password": "NewGitHubPass1!",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=auth_headers,
            )
            assert update_resp.status_code == 200, (
                f"Update credential failed: {update_resp.status_code} {update_resp.text}"
            )
            update_body = update_resp.json()
            assert update_body["credential_id"] == credential_id

            # Assert audit_log has an UPDATE row for this credential
            _assert_audit_row(
                db,
                operation="UPDATE",
                user_id=registered_user_id,
                affected_record_id=credential_id,
            )

            # Verify the update actually persisted: reveal the new password
            reveal_after_update = _client.post(
                f"/api/credentials/{credential_id}/reveal",
                json={"account_password": _STRONG_PASSWORD},
                headers=auth_headers,
            )
            assert reveal_after_update.status_code == 200
            assert reveal_after_update.json()["password"] == "NewGitHubPass1!"

            # ------------------------------------------------------------------
            # Step 7: Delete the credential
            # DELETE /api/credentials/{id} → 204
            # Expect: DELETE row in audit_log
            # ------------------------------------------------------------------
            delete_resp = _client.request(
                "DELETE",
                f"/api/credentials/{credential_id}",
                json={"account_password": _STRONG_PASSWORD},
                headers=auth_headers,
            )
            assert delete_resp.status_code == 204, (
                f"Delete credential failed: {delete_resp.status_code} {delete_resp.text}"
            )

            # Assert audit_log has a DELETE row for this credential
            _assert_audit_row(
                db,
                operation="DELETE",
                user_id=registered_user_id,
                affected_record_id=credential_id,
            )

            # Confirm the credential is truly gone — reveal must return 404
            gone_resp = _client.post(
                f"/api/credentials/{credential_id}/reveal",
                json={"account_password": _STRONG_PASSWORD},
                headers=auth_headers,
            )
            assert gone_resp.status_code == 404, (
                f"Expected 404 after delete but got {gone_resp.status_code}"
            )

        finally:
            db.close()

    def test_list_search_filters_by_query(self) -> None:
        """
        GET /api/credentials?q= with a partial match returns only matching
        credentials; a non-matching query returns an empty list.

        Validates: Requirement 5.2
        """
        db: Session = _TestingSessionLocal()
        try:
            # Clean slate for this test
            db.query(AuditLog).delete()
            db.query(Credential).delete()
            db.query(User).delete()
            db.commit()

            # Register and promote to Admin
            reg = _client.post(
                "/api/auth/register",
                json={
                    "username": "search_user",
                    "email": "search@example.com",
                    "password": _STRONG_PASSWORD,
                    "password_confirmation": _STRONG_PASSWORD,
                },
            )
            assert reg.status_code == 201
            user_id = reg.json()["user_id"]
            user_row = db.query(User).filter(User.user_id == user_id).first()
            user_row.role = "Admin"
            db.commit()

            login = _client.post(
                "/api/auth/login",
                json={"username": "search_user", "password": _STRONG_PASSWORD},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create two credentials with different website names
            for site in ["github.com", "gitlab.com", "bitbucket.org"]:
                r = _client.post(
                    "/api/credentials",
                    json={
                        "website_name": site,
                        "email_or_username": f"user@{site}",
                        "is_username_login": False,
                        "password": "GitLabPass1@",
                        "account_password": _STRONG_PASSWORD,
                    },
                    headers=headers,
                )
                assert r.status_code == 201, f"Failed to create credential for {site}: {r.text}"

            # Search for "git" — should match github and gitlab but not bitbucket
            search_resp = _client.get("/api/credentials?q=git", headers=headers)
            assert search_resp.status_code == 200
            items = search_resp.json()
            websites = [c["website_name"] for c in items]
            assert "github.com" in websites
            assert "gitlab.com" in websites
            assert "bitbucket.org" not in websites, (
                f"'bitbucket.org' should not appear in results for q='git', got: {websites}"
            )

            # Search for a non-existent term — should return empty list
            empty_resp = _client.get("/api/credentials?q=zzznomatch", headers=headers)
            assert empty_resp.status_code == 200
            assert empty_resp.json() == [], (
                f"Expected empty list for non-matching query, got: {empty_resp.json()}"
            )

        finally:
            db.close()

    def test_wrong_account_password_rejects_sensitive_operations(self) -> None:
        """
        Sensitive operations (create, reveal, update, delete) with an incorrect
        account_password must return 401 and leave audit_log unchanged.

        Validates: Requirements 4.9, 6.6, 7.5
        """
        db: Session = _TestingSessionLocal()
        try:
            # Clean slate
            db.query(AuditLog).delete()
            db.query(Credential).delete()
            db.query(User).delete()
            db.commit()

            # Register and promote to Admin
            reg = _client.post(
                "/api/auth/register",
                json={
                    "username": "wrongpw_user",
                    "email": "wrongpw@example.com",
                    "password": _STRONG_PASSWORD,
                    "password_confirmation": _STRONG_PASSWORD,
                },
            )
            assert reg.status_code == 201
            user_id = reg.json()["user_id"]
            user_row = db.query(User).filter(User.user_id == user_id).first()
            user_row.role = "Admin"
            db.commit()

            login = _client.post(
                "/api/auth/login",
                json={"username": "wrongpw_user", "password": _STRONG_PASSWORD},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # First create a credential with the CORRECT password
            create_r = _client.post(
                "/api/credentials",
                json={
                    "website_name": "example.com",
                    "email_or_username": "u@example.com",
                    "is_username_login": False,
                    "password": "ExamplePass1@",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=headers,
            )
            assert create_r.status_code == 201
            cred_id = create_r.json()["credential_id"]

            audit_count_after_create = db.query(AuditLog).count()

            wrong_pw = "WrongPassword9!"

            # Reveal with wrong password → 401, no new audit row
            r = _client.post(
                f"/api/credentials/{cred_id}/reveal",
                json={"account_password": wrong_pw},
                headers=headers,
            )
            assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
            db.expire_all()
            assert db.query(AuditLog).count() == audit_count_after_create, (
                "audit_log should not grow when reveal is rejected"
            )

            # Update with wrong password → 401, no new audit row
            r = _client.put(
                f"/api/credentials/{cred_id}",
                json={
                    "website_name": "example.com",
                    "email_or_username": "u@example.com",
                    "is_username_login": False,
                    "password": "NewExamplePass1@",
                    "account_password": wrong_pw,
                },
                headers=headers,
            )
            assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
            db.expire_all()
            assert db.query(AuditLog).count() == audit_count_after_create, (
                "audit_log should not grow when update is rejected"
            )

            # Delete with wrong password → 401, no new audit row
            r = _client.request(
                "DELETE",
                f"/api/credentials/{cred_id}",
                json={"account_password": wrong_pw},
                headers=headers,
            )
            assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
            db.expire_all()
            assert db.query(AuditLog).count() == audit_count_after_create, (
                "audit_log should not grow when delete is rejected"
            )

        finally:
            db.close()


# ---------------------------------------------------------------------------
# Task 27.2 — Admin profile assignment end-to-end integration test
#
# This test class uses its own isolated in-memory SQLite engine so that the
# JSONB-backed ``profiles`` and ``user_profiles`` tables can be created with
# a TEXT column (SQLite's dialect cannot render PostgreSQL's JSONB).  The raw
# SQL tables are schema-compatible with the ORM models: ProfileService and the
# permissions middleware both issue standard SELECT queries that SQLite handles
# transparently, and ``permitted_screens`` is serialised / deserialised as
# JSON text.
#
# Requirements: 3.1–3.7
# ---------------------------------------------------------------------------

import json as _json

from sqlalchemy import create_engine as _create_engine, text as _text
from sqlalchemy.orm import sessionmaker as _sessionmaker
from sqlalchemy.pool import StaticPool as _StaticPool

from app.models import (  # noqa: E402  (models already imported above)
    AuditLog as _AuditLog2,
    Credential as _Credential2,
    User as _User2,
)

# ---------------------------------------------------------------------------
# Dedicated engine for the admin-profile test class.
# A separate engine avoids table-creation conflicts with the engine used in
# TestFullCredentialLifecycle (which intentionally omits Profile/UserProfile).
# ---------------------------------------------------------------------------

_ADMIN_ENGINE = _create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=_StaticPool,
)


@event.listens_for(_ADMIN_ENGINE, "connect")
def _disable_fk_admin(dbapi_conn, _record):  # pragma: no cover
    dbapi_conn.execute("PRAGMA foreign_keys = OFF")


# Create the standard ORM-mapped tables (no JSONB).
_User2.__table__.create(bind=_ADMIN_ENGINE, checkfirst=True)
_Credential2.__table__.create(bind=_ADMIN_ENGINE, checkfirst=True)
_AuditLog2.__table__.create(bind=_ADMIN_ENGINE, checkfirst=True)

# Create ``profiles`` and ``user_profiles`` with TEXT instead of JSONB so
# that SQLAlchemy's SQLite dialect can render them without errors.
with _ADMIN_ENGINE.connect() as _conn:
    _conn.execute(_text(
        "CREATE TABLE IF NOT EXISTS profiles ("
        "profile_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "profile_name VARCHAR(64) NOT NULL UNIQUE, "
        "permitted_screens TEXT NOT NULL DEFAULT '[]', "
        "creation_date DATE NOT NULL, "
        "creation_time TIME NOT NULL, "
        "creation_user_id INTEGER, "
        "modification_date DATE, "
        "modification_time TIME, "
        "modification_user_id INTEGER)"
    ))
    _conn.execute(_text(
        "CREATE TABLE IF NOT EXISTS user_profiles ("
        "user_profile_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER NOT NULL, "
        "profile_id INTEGER NOT NULL, "
        "creation_date DATE NOT NULL, "
        "creation_time TIME NOT NULL, "
        "creation_user_id INTEGER, "
        "modification_date DATE, "
        "modification_time TIME, "
        "modification_user_id INTEGER)"
    ))
    _conn.commit()

_AdminTestingSessionLocal = _sessionmaker(
    bind=_ADMIN_ENGINE,
    autocommit=False,
    autoflush=False,
)


def _override_get_db_admin():
    """FastAPI dependency override pointing to the admin-test engine."""
    db: Session = _AdminTestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dedicated TestClient for the admin-profile tests.
# We swap get_db to the admin engine before instantiating the client and
# restore it afterwards in the class tear-down so the two test classes do not
# interfere with each other.
# ---------------------------------------------------------------------------

app.dependency_overrides[get_db] = _override_get_db_admin
_admin_client = TestClient(app, raise_server_exceptions=True)
# Restore the original override so other test classes keep using the first engine.
app.dependency_overrides[get_db] = _override_get_db


class TestAdminProfileAssignment:
    """
    End-to-end integration test for the admin profile assignment flow.

    Scenario
    --------
    1. Register an Admin user and a regular User.
    2. Admin logs in; seeds a Profile with a limited ``permitted_screens`` list
       (``["credentials", "credentials.new"]``) directly into the SQLite DB.
    3. Admin calls ``PUT /api/admin/users/{user_id}/profile`` → 200.
    4. User logs in and exercises every credential endpoint:
         - ``GET  /api/credentials``              → 200  (in profile)
         - ``POST /api/credentials``              → 201  (in profile)
         - ``PUT  /api/credentials/{id}``         → 403  (NOT in profile)
         - ``DELETE /api/credentials/{id}``       → 403  (NOT in profile)
         - ``POST /api/credentials/{id}/reveal``  → 200  (in profile — "credentials")

    Requirements: 3.1–3.7
    """

    def setup_method(self) -> None:
        """Point get_db at the admin engine before each test method."""
        app.dependency_overrides[get_db] = _override_get_db_admin

    def teardown_method(self) -> None:
        """Restore the original get_db override after each test method."""
        app.dependency_overrides[get_db] = _override_get_db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _seed_profile(db: Session, name: str, screens: list[str]) -> int:
        """Insert a profile row via raw SQL and return its profile_id."""
        from datetime import date, datetime, timezone

        now_date = str(date.today())
        now_time = str(datetime.now(timezone.utc).time().replace(tzinfo=None))
        db.execute(
            _text(
                "INSERT INTO profiles "
                "(profile_name, permitted_screens, creation_date, creation_time) "
                "VALUES (:n, :s, :d, :t)"
            ),
            {
                "n": name,
                "s": _json.dumps(screens),
                "d": now_date,
                "t": now_time,
            },
        )
        db.commit()
        row = db.execute(
            _text("SELECT profile_id FROM profiles WHERE profile_name = :n"),
            {"n": name},
        ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Test
    # ------------------------------------------------------------------

    def test_admin_assigns_profile_and_user_respects_permissions(self) -> None:
        """
        Full admin-profile-assignment end-to-end scenario.

        Validates: Requirements 3.1–3.7
        """
        db: Session = _AdminTestingSessionLocal()

        try:
            # Clean slate for this test
            db.execute(_text("DELETE FROM user_profiles"))
            db.execute(_text("DELETE FROM profiles"))
            db.query(_AuditLog2).delete()
            db.query(_Credential2).delete()
            db.query(_User2).delete()
            db.commit()

            # ----------------------------------------------------------
            # Step 1: Register Admin user
            # ----------------------------------------------------------
            admin_reg = _admin_client.post(
                "/api/auth/register",
                json={
                    "username": "profile_admin",
                    "email": "profile_admin@example.com",
                    "password": _STRONG_PASSWORD,
                    "password_confirmation": _STRONG_PASSWORD,
                },
            )
            assert admin_reg.status_code == 201, (
                f"Admin register failed: {admin_reg.status_code} {admin_reg.text}"
            )
            admin_id: int = admin_reg.json()["user_id"]

            # Promote to Admin role
            admin_row = db.query(_User2).filter(_User2.user_id == admin_id).first()
            assert admin_row is not None
            admin_row.role = "Admin"
            db.commit()

            # ----------------------------------------------------------
            # Step 2: Register regular User
            # ----------------------------------------------------------
            user_reg = _admin_client.post(
                "/api/auth/register",
                json={
                    "username": "profile_user",
                    "email": "profile_user@example.com",
                    "password": _STRONG_PASSWORD,
                    "password_confirmation": _STRONG_PASSWORD,
                },
            )
            assert user_reg.status_code == 201, (
                f"User register failed: {user_reg.status_code} {user_reg.text}"
            )
            regular_user_id: int = user_reg.json()["user_id"]
            assert user_reg.json()["role"] == "User", (
                "Newly registered user should have role='User' (Requirement 3.1)"
            )

            # ----------------------------------------------------------
            # Step 3: Admin logs in
            # ----------------------------------------------------------
            admin_login = _admin_client.post(
                "/api/auth/login",
                json={"username": "profile_admin", "password": _STRONG_PASSWORD},
            )
            assert admin_login.status_code == 200, (
                f"Admin login failed: {admin_login.status_code} {admin_login.text}"
            )
            admin_token: str = admin_login.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}

            # ----------------------------------------------------------
            # Step 4: Seed a Profile with limited permitted screens.
            # Only "credentials" and "credentials.new" are permitted;
            # "credentials.edit" and "credentials.delete" are excluded.
            # ----------------------------------------------------------
            permitted: list[str] = ["credentials", "credentials.new"]
            profile_id: int = self._seed_profile(db, "LimitedAccess", permitted)
            assert profile_id > 0

            # ----------------------------------------------------------
            # Step 5: Admin assigns the profile to the regular user.
            # Requirement 3.2 — Admin can call PUT /api/admin/users/{id}/profile.
            # Requirement 3.3 — Assignment is persisted with audit columns.
            # Requirement 3.7 — Response contains {user_id, profile_id}.
            # ----------------------------------------------------------
            assign_resp = _admin_client.put(
                f"/api/admin/users/{regular_user_id}/profile",
                json={"profile_id": profile_id},
                headers=admin_headers,
            )
            assert assign_resp.status_code == 200, (
                f"Profile assignment failed: {assign_resp.status_code} {assign_resp.text}"
            )
            assign_body = assign_resp.json()
            assert assign_body["user_id"] == regular_user_id, (
                "Response user_id must match the target user (Requirement 3.7)"
            )
            assert assign_body["profile_id"] == profile_id, (
                "Response profile_id must match the assigned profile (Requirement 3.7)"
            )

            # Verify the user_profiles row was actually persisted (Requirement 3.3)
            db.expire_all()
            up_row = db.execute(
                _text(
                    "SELECT user_id, profile_id FROM user_profiles "
                    "WHERE user_id = :uid"
                ),
                {"uid": regular_user_id},
            ).fetchone()
            assert up_row is not None, (
                "user_profiles row must exist after assignment (Requirement 3.3)"
            )
            assert up_row[1] == profile_id

            # ----------------------------------------------------------
            # Step 6: Regular user logs in
            # ----------------------------------------------------------
            user_login = _admin_client.post(
                "/api/auth/login",
                json={"username": "profile_user", "password": _STRONG_PASSWORD},
            )
            assert user_login.status_code == 200, (
                f"User login failed: {user_login.status_code} {user_login.text}"
            )
            user_token: str = user_login.json()["access_token"]
            user_headers = {"Authorization": f"Bearer {user_token}"}

            # ----------------------------------------------------------
            # Step 7: Permitted routes — must return success (200 / 201)
            # Requirement 3.4 — User may access only screens in their profile.
            # ----------------------------------------------------------

            # GET /api/credentials is permitted ("credentials" in profile)
            list_resp = _admin_client.get("/api/credentials", headers=user_headers)
            assert list_resp.status_code == 200, (
                f"GET /api/credentials should be 200 for a user with 'credentials' "
                f"permission, got {list_resp.status_code}: {list_resp.text}"
            )

            # POST /api/credentials is permitted ("credentials.new" in profile)
            create_resp = _admin_client.post(
                "/api/credentials",
                json={
                    "website_name": "permitted-site.com",
                    "email_or_username": "user@permitted-site.com",
                    "is_username_login": False,
                    "password": "SitePass1@Test",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=user_headers,
            )
            assert create_resp.status_code == 201, (
                f"POST /api/credentials should be 201 for a user with 'credentials.new' "
                f"permission, got {create_resp.status_code}: {create_resp.text}"
            )
            created_cred_id: int = create_resp.json()["credential_id"]

            # POST /api/credentials/{id}/reveal is permitted ("credentials" in profile)
            reveal_resp = _admin_client.post(
                f"/api/credentials/{created_cred_id}/reveal",
                json={"account_password": _STRONG_PASSWORD},
                headers=user_headers,
            )
            assert reveal_resp.status_code == 200, (
                f"POST /api/credentials/reveal should be 200 for 'credentials' "
                f"permission, got {reveal_resp.status_code}: {reveal_resp.text}"
            )
            assert reveal_resp.json()["password"] == "SitePass1@Test"

            # ----------------------------------------------------------
            # Step 8: Forbidden routes — must return 403
            # Requirement 3.4 — screens not in profile are blocked.
            # Requirement 3.6 — forbidden access returns 403 {"detail": "Access denied."}.
            # ----------------------------------------------------------

            # PUT /api/credentials/{id} requires "credentials.edit" — NOT in profile
            update_resp = _admin_client.put(
                f"/api/credentials/{created_cred_id}",
                json={
                    "website_name": "permitted-site.com",
                    "email_or_username": "user@permitted-site.com",
                    "is_username_login": False,
                    "password": "NewSitePass1@Test",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=user_headers,
            )
            assert update_resp.status_code == 403, (
                f"PUT /api/credentials should be 403 when 'credentials.edit' is "
                f"not in the profile, got {update_resp.status_code}: {update_resp.text}"
            )
            assert update_resp.json()["detail"] == "Access denied.", (
                "403 response detail must be 'Access denied.' (Requirement 3.6)"
            )

            # DELETE /api/credentials/{id} requires "credentials.delete" — NOT in profile
            delete_resp = _admin_client.request(
                "DELETE",
                f"/api/credentials/{created_cred_id}",
                json={"account_password": _STRONG_PASSWORD},
                headers=user_headers,
            )
            assert delete_resp.status_code == 403, (
                f"DELETE /api/credentials should be 403 when 'credentials.delete' "
                f"is not in the profile, got {delete_resp.status_code}: {delete_resp.text}"
            )
            assert delete_resp.json()["detail"] == "Access denied.", (
                "403 response detail must be 'Access denied.' (Requirement 3.6)"
            )

            # GET /api/admin/users requires "admin.users" — NOT in profile
            # (Requirement 3.5 — admin.users is Admin-only in practice, but the
            # middleware 403s a User JWT regardless of route handler intent)
            admin_users_resp = _admin_client.get(
                "/api/admin/users",
                headers=user_headers,
            )
            assert admin_users_resp.status_code == 403, (
                f"GET /api/admin/users should be 403 for a non-admin user, "
                f"got {admin_users_resp.status_code}: {admin_users_resp.text}"
            )
            assert admin_users_resp.json()["detail"] == "Access denied.", (
                "403 response detail must be 'Access denied.' (Requirement 3.6)"
            )

            # ----------------------------------------------------------
            # Step 9: Re-assignment — Admin updates the profile to include
            # "credentials.edit".  Verify that PUT is now allowed.
            # Requirement 3.3 — re-assignment updates existing user_profiles row.
            # ----------------------------------------------------------
            expanded_screens = [
                "credentials",
                "credentials.new",
                "credentials.edit",
            ]
            expanded_profile_id: int = self._seed_profile(
                db, "ExpandedAccess", expanded_screens
            )

            reassign_resp = _admin_client.put(
                f"/api/admin/users/{regular_user_id}/profile",
                json={"profile_id": expanded_profile_id},
                headers=admin_headers,
            )
            assert reassign_resp.status_code == 200, (
                f"Re-assignment failed: {reassign_resp.status_code} {reassign_resp.text}"
            )

            # Verify there is still only ONE user_profiles row for this user
            # (upsert behaviour — Requirement 3.3).
            db.expire_all()
            row_count = db.execute(
                _text(
                    "SELECT COUNT(*) FROM user_profiles WHERE user_id = :uid"
                ),
                {"uid": regular_user_id},
            ).scalar()
            assert row_count == 1, (
                f"Expected exactly 1 user_profiles row after re-assignment, "
                f"got {row_count} (Requirement 3.3)"
            )

            # User must now be able to call PUT /api/credentials/{id}
            # (need a fresh login to get a JWT that picks up the new profile)
            user_login2 = _admin_client.post(
                "/api/auth/login",
                json={"username": "profile_user", "password": _STRONG_PASSWORD},
            )
            assert user_login2.status_code == 200
            user_token2: str = user_login2.json()["access_token"]
            user_headers2 = {"Authorization": f"Bearer {user_token2}"}

            update_after_reassign = _admin_client.put(
                f"/api/credentials/{created_cred_id}",
                json={
                    "website_name": "permitted-site.com",
                    "email_or_username": "user@permitted-site.com",
                    "is_username_login": False,
                    "password": "UpdatedPass1@",
                    "account_password": _STRONG_PASSWORD,
                },
                headers=user_headers2,
            )
            assert update_after_reassign.status_code == 200, (
                f"PUT /api/credentials should be 200 after expanding the profile to "
                f"include 'credentials.edit', got "
                f"{update_after_reassign.status_code}: {update_after_reassign.text}"
            )

        finally:
            db.close()
