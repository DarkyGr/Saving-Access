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

def utc_today():
    """Today as the app records it: UTC (task 32.3), not the machine's local date."""
    from app.utils.audit_columns import utc_date_time

    return utc_date_time()[0]


@event.listens_for(_ENGINE, "connect")
def _disable_fk(dbapi_conn, _record):  # pragma: no cover
    dbapi_conn.execute("PRAGMA foreign_keys = OFF")


# Create only the tables this integration test actually touches.
User.__table__.create(bind=_ENGINE, checkfirst=True)
Credential.__table__.create(bind=_ENGINE, checkfirst=True)
AuditLog.__table__.create(bind=_ENGINE, checkfirst=True)
from app.models import RefreshToken as _RT  # noqa: E402
_RT.__table__.create(bind=_ENGINE, checkfirst=True)
from app.models import SystemSetting as _SS  # noqa: E402  (task 37.5 parameters)
_SS.__table__.create(bind=_ENGINE, checkfirst=True)

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

            # The User role alone grants the vault permissions (task 37.1).
            user_row = db.query(User).filter(User.user_id == registered_user_id).first()
            assert user_row is not None and user_row.role == "User"

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
# Task 27.2, revised by task 37.1 — Admin role change end-to-end
#
# Kiro's version assigned screen profiles; profiles were retired and the role
# alone now decides the permissions (Requirements 3.1–3.7, Property 8).
# ---------------------------------------------------------------------------


class TestAdminRoleChange:
    """
    1. Register two accounts; make the first an Admin directly in the DB
       (as ``python -m app.cli create-admin`` / ``promote`` would).
    2. The User reaches the vault but not the admin endpoints.
    3. The Admin promotes the User; the *same* token now reaches the admin
       endpoints (the role is read from the database on each request).
    4. The Admin cannot change their own role; the role change sets the
       target's modification Audit_Columns.
    5. Demoted again, the User is denied the admin endpoints but keeps the vault.
    """

    def _register_and_login(self, name: str) -> tuple[int, dict]:
        r = _client.post(
            "/api/auth/register",
            json={
                "username": name,
                "email": f"{name}@example.com",
                "password": _STRONG_PASSWORD,
                "password_confirmation": _STRONG_PASSWORD,
            },
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["user_id"]
        return user_id, self._login(name)

    @staticmethod
    def _login(name: str) -> dict:
        r = _client.post("/api/auth/login", json={"username": name, "password": _STRONG_PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_admin_changes_roles_and_permissions_follow(self) -> None:
        db: Session = _TestingSessionLocal()
        try:
            admin_id, _ = self._register_and_login("role_admin")
            user_id, user_headers = self._register_and_login("role_user")
            db.query(User).filter(User.user_id == admin_id).update({"role": "Admin"})
            db.commit()
            admin_headers = self._login("role_admin")

            # 2. A User has the vault, not the administration.
            assert _client.get("/api/credentials", headers=user_headers).status_code == 200
            assert _client.get("/api/admin/users", headers=user_headers).status_code == 403
            assert _client.put(
                f"/api/admin/users/{admin_id}/role", json={"role": "User"}, headers=user_headers
            ).status_code == 403

            listed = _client.get("/api/admin/users", headers=admin_headers)
            assert listed.status_code == 200
            roles = {u["username"]: u["role"] for u in listed.json()}
            assert roles["role_admin"] == "Admin" and roles["role_user"] == "User"
            assert all("password_hash" not in u for u in listed.json())

            # 4. Never on yourself, so one Admin always remains.
            own = _client.put(
                f"/api/admin/users/{admin_id}/role", json={"role": "User"}, headers=admin_headers
            )
            assert own.status_code == 400
            assert own.json() == {"detail": "You cannot change your own role."}
            assert _client.put(
                "/api/admin/users/999999/role", json={"role": "Admin"}, headers=admin_headers
            ).status_code == 404
            assert _client.put(
                f"/api/admin/users/{user_id}/role", json={"role": "Root"}, headers=admin_headers
            ).status_code == 422

            # 3. Promote: the same token reaches the admin endpoints at once.
            promoted = _client.put(
                f"/api/admin/users/{user_id}/role", json={"role": "Admin"}, headers=admin_headers
            )
            assert promoted.status_code == 200
            assert promoted.json() == {"user_id": user_id, "role": "Admin"}
            assert _client.get("/api/admin/users", headers=user_headers).status_code == 200
            perms = _client.get("/api/profile/permissions", headers=user_headers).json()
            assert perms["role"] == "Admin" and "users.manage" in perms["permissions"]

            # Property 8: the role change is recorded in the Audit_Columns.
            db.expire_all()
            row = db.query(User).filter(User.user_id == user_id).one()
            assert row.modification_user_id == admin_id
            assert row.modification_date == utc_today()
            assert row.modification_time is not None

            # 5. Demote: administration denied again, vault kept.
            assert _client.put(
                f"/api/admin/users/{user_id}/role", json={"role": "User"}, headers=admin_headers
            ).status_code == 200
            assert _client.get("/api/admin/users", headers=user_headers).status_code == 403
            assert _client.get("/api/credentials", headers=user_headers).status_code == 200
        finally:
            db.query(User).filter(User.username.in_(["role_admin", "role_user"])).delete()
            db.commit()
            db.close()
