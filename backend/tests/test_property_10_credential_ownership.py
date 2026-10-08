"""
Property-based tests for credential ownership isolation.

Feature: password-manager-website

Properties tested:
  Property 10: Credential Ownership Isolation
               — Validates: Requirements 5.3, 8.2

For any two distinct authenticated users U and V, user U SHALL be denied
access to any credential owned by user V via every credential endpoint:
  - GET  /api/credentials?q=   (list — V's credential must never appear)
  - POST /api/credentials/{id}/reveal
  - PUT  /api/credentials/{id}
  - DELETE /api/credentials/{id}

The reveal, edit, and delete operations must return 403 (owned by another
user) or 404 (not found), never 200/204.
"""

import os
import string
from datetime import date, datetime, timezone, timedelta

from cryptography.fernet import Fernet
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from jose import jwt

# ---------------------------------------------------------------------------
# Environment defaults — must be set before importing any app modules.
# DATABASE_URL must be set so app.database doesn't raise KeyError at import.
# We point it at the same SQLite shared-pool engine we configure below so
# that get_db (when overridden) uses the same connection as the test setup.
# ---------------------------------------------------------------------------

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-ownership-isolation-secret-p10"
_TEST_JWT_ALGORITHM = "HS256"

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["JWT_EXPIRE_MINUTES"] = "15"
os.environ["BCRYPT_ROUNDS"] = "4"
# "test" environment prevents the startup event from running
# Base.metadata.create_all on the real app.database.engine.
os.environ["ENVIRONMENT"] = "test"

# Import app modules after env vars are set.
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker, Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, User  # noqa: E402
from app.services.encryptor_service import EncryptorService  # noqa: E402
from app.utils.audit_columns import set_creation_audit  # noqa: E402


# ---------------------------------------------------------------------------
# Shared SQLite engine with StaticPool
#
# StaticPool ensures every SQLAlchemy session — whether opened by the test
# setup code OR by the FastAPI request handler via _override_get_db — reuses
# the exact same underlying SQLite connection.  This means:
#   - The in-memory database is never garbage-collected between sessions.
#   - Tables created at module setup time are visible to all sessions.
#   - Data written by the test setup is immediately visible to the request.
#
# check_same_thread=False is required because FastAPI runs route handlers in
# worker threads while setup code runs on the main thread.
#
# FK enforcement is disabled so AuditLog rows can reference user_ids that
# exist in the test setup without cascading FK errors during cleanup.
# ---------------------------------------------------------------------------

_SQLITE_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_SQLITE_ENGINE, "connect")
def _disable_fk(dbapi_conn, _record):
    dbapi_conn.execute("PRAGMA foreign_keys = OFF")


# Create only the tables used by this test.  Profile/UserProfile use JSONB
# (PostgreSQL-only) and are deliberately excluded.
User.__table__.create(bind=_SQLITE_ENGINE, checkfirst=True)
Credential.__table__.create(bind=_SQLITE_ENGINE, checkfirst=True)
AuditLog.__table__.create(bind=_SQLITE_ENGINE, checkfirst=True)

_TestingSessionLocal = sessionmaker(
    bind=_SQLITE_ENGINE,
    autocommit=False,
    autoflush=False,
)

# Module-level session reused across all Hypothesis iterations to avoid
# open/close churn.  StaticPool guarantees it uses the same connection.
_DB: Session = _TestingSessionLocal()


# ---------------------------------------------------------------------------
# Override get_db so FastAPI request handlers use the same shared engine.
# ---------------------------------------------------------------------------

def _override_get_db():
    """FastAPI dependency override — yields a fresh session on the shared engine."""
    db: Session = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

# Single TestClient instance shared across all iterations.
_client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _make_jwt(user_id: int, role: str = "Admin") -> str:
    """Issue a signed JWT for the given user_id and role.

    Reads JWT_SECRET and JWT_ALGORITHM from os.environ at call time so that
    the token is always signed with the same secret that AuthService.verify_token
    will use — even when another test file changes JWT_SECRET between test runs.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(minutes=15),
    }
    secret = os.environ.get("JWT_SECRET", _TEST_JWT_SECRET)
    algorithm = os.environ.get("JWT_ALGORITHM", _TEST_JWT_ALGORITHM)
    # Restore the known test secret so AuthService decodes with the same key.
    os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
    os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
    return jwt.encode(
        payload,
        _TEST_JWT_SECRET,
        algorithm=_TEST_JWT_ALGORITHM,
    )


def _auth_headers(user_id: int, role: str = "Admin") -> dict:
    """Return Authorization headers for user_id."""
    return {"Authorization": f"Bearer {_make_jwt(user_id, role)}"}


def _create_user(username: str, email: str) -> User:
    """Insert a minimal Admin User row into the shared database.

    Using role="Admin" means the permissions middleware never queries the
    JSONB-backed profiles or user_profiles tables.
    """
    now_date = date.today()
    now_time = datetime.now(timezone.utc).time().replace(tzinfo=None)
    # A static bcrypt hash (rounds=4) avoids live hashing overhead.
    # This hash was pre-computed for "TestPass1@2024" at rounds=4.
    password_hash = (
        "$2b$04$LI9MsKSCF9DuOmEWEjHmguSmFNjX05KMcgqQXoT7rFVsS3UMPjkLu"
    )
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role="Admin",
        email_verified=True,
        creation_date=now_date,
        creation_time=now_time,
        creation_user_id=None,
    )
    _DB.add(user)
    _DB.commit()
    _DB.refresh(user)
    # Back-fill self-referential FK (nullable in schema)
    user.creation_user_id = user.user_id
    _DB.commit()
    _DB.refresh(user)
    return user


def _create_credential(owner_id: int, website: str) -> Credential:
    """Insert a Credential row owned by owner_id."""
    encryptor = EncryptorService()
    encrypted = encryptor.encrypt("SomePassword1!")
    cred = Credential(
        user_id=owner_id,
        website_name=website[:256],  # honour VARCHAR(256) column limit
        email_or_username="owner@example.com",
        is_username_login=False,
        encrypted_password=encrypted,
    )
    set_creation_audit(cred, user_id=owner_id)
    _DB.add(cred)
    _DB.commit()
    _DB.refresh(cred)
    return cred


def _reset_db() -> None:
    """Delete all rows from test tables to reset state between iterations."""
    _DB.query(AuditLog).delete()
    _DB.query(Credential).delete()
    _DB.query(User).delete()
    _DB.commit()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Safe alphanumeric strings for username suffixes.
_safe_alpha = st.text(
    alphabet=string.ascii_lowercase + string.digits,
    min_size=4,
    max_size=12,
)

# Website name strings — printable ASCII, non-empty, within column limit.
_website_name = st.text(
    alphabet=string.ascii_letters + string.digits + ".-_",
    min_size=1,
    max_size=32,
)


# ---------------------------------------------------------------------------
# Property 10: Credential Ownership Isolation
# Validates: Requirements 5.3, 8.2
# ---------------------------------------------------------------------------


class TestCredentialOwnershipIsolation:
    """
    Property 10: Credential Ownership Isolation

    For any pair of distinct users U and V, user U's requests to all
    credential endpoints that target a credential owned by V MUST be denied
    (403 Forbidden or 404 Not Found — never 200 OK or 204 No Content).

    Additionally, the credential list endpoint (GET /api/credentials) for
    user U must never include a credential whose credential_id belongs to V.

    Feature: password-manager-website, Property 10: credential-ownership-isolation
    Validates: Requirements 5.3, 8.2
    """

    # ------------------------------------------------------------------
    # Shared setup helper
    # ------------------------------------------------------------------

    def _setup(self, suffix_u: str, suffix_v: str, website: str):
        """Reset DB, create users U and V, and a credential owned by V.

        Returns (user_u, user_v, credential_v).
        """
        _reset_db()
        user_u = _create_user(
            username=f"u_{suffix_u[:10]}",
            email=f"u_{suffix_u[:10]}@test.example",
        )
        user_v = _create_user(
            username=f"v_{suffix_v[:10]}",
            email=f"v_{suffix_v[:10]}@test.example",
        )
        cred_v = _create_credential(owner_id=user_v.user_id, website=website)
        return user_u, user_v, cred_v

    # ------------------------------------------------------------------
    # Property 10a: Reveal endpoint denies cross-user access
    # ------------------------------------------------------------------

    @given(
        suffix_u=_safe_alpha,
        suffix_v=_safe_alpha,
        website=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_reveal_denies_access_to_other_users_credential(
        self, suffix_u: str, suffix_v: str, website: str
    ) -> None:
        """
        POST /api/credentials/{id}/reveal with user U's JWT and V's
        credential_id must return 403 or 404, never 200.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        assume(suffix_u != suffix_v)

        user_u, _user_v, cred_v = self._setup(suffix_u, suffix_v, website)

        response = _client.post(
            f"/api/credentials/{cred_v.credential_id}/reveal",
            json={"account_password": "anything"},
            headers=_auth_headers(user_u.user_id),
        )

        assert response.status_code in (403, 404), (
            f"Expected 403 or 404 when user U (id={user_u.user_id}) "
            f"attempts to reveal credential {cred_v.credential_id} "
            f"owned by user V. Got {response.status_code}. "
            f"Body: {response.text}"
        )

    # ------------------------------------------------------------------
    # Property 10b: Edit endpoint denies cross-user access
    # ------------------------------------------------------------------

    @given(
        suffix_u=_safe_alpha,
        suffix_v=_safe_alpha,
        website=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_edit_denies_access_to_other_users_credential(
        self, suffix_u: str, suffix_v: str, website: str
    ) -> None:
        """
        PUT /api/credentials/{id} with user U's JWT and V's credential_id
        must return 403 or 404, never 200.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        assume(suffix_u != suffix_v)

        user_u, _user_v, cred_v = self._setup(suffix_u, suffix_v, website)

        response = _client.put(
            f"/api/credentials/{cred_v.credential_id}",
            json={
                "website_name": "hacked.example.com",
                "email_or_username": "hacker@evil.com",
                "is_username_login": False,
                "password": "HackedPass1@",
                "account_password": "anything",
            },
            headers=_auth_headers(user_u.user_id),
        )

        assert response.status_code in (403, 404), (
            f"Expected 403 or 404 when user U (id={user_u.user_id}) "
            f"attempts to edit credential {cred_v.credential_id} "
            f"owned by user V. Got {response.status_code}. "
            f"Body: {response.text}"
        )

    # ------------------------------------------------------------------
    # Property 10c: Delete endpoint denies cross-user access
    # ------------------------------------------------------------------

    @given(
        suffix_u=_safe_alpha,
        suffix_v=_safe_alpha,
        website=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_delete_denies_access_to_other_users_credential(
        self, suffix_u: str, suffix_v: str, website: str
    ) -> None:
        """
        DELETE /api/credentials/{id} with user U's JWT and V's
        credential_id must return 403 or 404, never 204.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        assume(suffix_u != suffix_v)

        user_u, _user_v, cred_v = self._setup(suffix_u, suffix_v, website)

        response = _client.request(
            "DELETE",
            f"/api/credentials/{cred_v.credential_id}",
            json={"account_password": "anything"},
            headers=_auth_headers(user_u.user_id),
        )

        assert response.status_code in (403, 404), (
            f"Expected 403 or 404 when user U (id={user_u.user_id}) "
            f"attempts to delete credential {cred_v.credential_id} "
            f"owned by user V. Got {response.status_code}. "
            f"Body: {response.text}"
        )

    # ------------------------------------------------------------------
    # Property 10d: List endpoint never leaks other users' credentials
    # ------------------------------------------------------------------

    @given(
        suffix_u=_safe_alpha,
        suffix_v=_safe_alpha,
        website=_website_name,
        search_q=st.one_of(st.none(), _website_name),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_list_never_returns_other_users_credentials(
        self,
        suffix_u: str,
        suffix_v: str,
        website: str,
        search_q: str | None,
    ) -> None:
        """
        GET /api/credentials (with and without ?q=) for user U must never
        include a credential whose credential_id belongs to user V.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        assume(suffix_u != suffix_v)

        user_u, user_v, cred_v = self._setup(suffix_u, suffix_v, website)

        url = "/api/credentials"
        if search_q is not None:
            url = f"{url}?q={search_q}"

        response = _client.get(url, headers=_auth_headers(user_u.user_id))

        assert response.status_code == 200, (
            f"GET /api/credentials returned {response.status_code} "
            f"for user U (id={user_u.user_id}). Body: {response.text}"
        )

        items = response.json()
        returned_ids = {item["credential_id"] for item in items}

        assert cred_v.credential_id not in returned_ids, (
            f"User U (id={user_u.user_id}) received credential "
            f"{cred_v.credential_id} which is owned by user V "
            f"(id={user_v.user_id}) in the list response. "
            f"Returned IDs: {returned_ids}"
        )

    # ------------------------------------------------------------------
    # Property 10e: Isolation holds after V's credential is updated
    # ------------------------------------------------------------------

    @given(
        suffix_u=_safe_alpha,
        suffix_v=_safe_alpha,
        website_original=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_isolation_holds_after_owner_modifies_credential(
        self,
        suffix_u: str,
        suffix_v: str,
        website_original: str,
    ) -> None:
        """
        Even after user V successfully updates their own credential, user U
        must still be denied access via reveal, edit, and delete endpoints.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        assume(suffix_u != suffix_v)

        user_u, user_v, cred_v = self._setup(suffix_u, suffix_v, website_original)

        # V updates the credential via a direct DB write — simulates a
        # legitimate owner modification without needing bcrypt verification.
        encryptor = EncryptorService()
        cred_v.website_name = "updated.example.com"
        cred_v.encrypted_password = encryptor.encrypt("UpdatedPass1@")
        _DB.commit()

        for method, path, body in [
            (
                "POST",
                f"/api/credentials/{cred_v.credential_id}/reveal",
                {"account_password": "anything"},
            ),
            (
                "PUT",
                f"/api/credentials/{cred_v.credential_id}",
                {
                    "website_name": "attack.example.com",
                    "email_or_username": "u@u.com",
                    "is_username_login": False,
                    "password": "Attack1@pass",
                    "account_password": "anything",
                },
            ),
            (
                "DELETE",
                f"/api/credentials/{cred_v.credential_id}",
                {"account_password": "anything"},
            ),
        ]:
            if method == "POST":
                resp = _client.post(
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )
            elif method == "PUT":
                resp = _client.put(
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )
            else:
                resp = _client.request(
                    "DELETE",
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )

            assert resp.status_code in (403, 404), (
                f"{method} {path}: expected 403 or 404 for user U "
                f"(id={user_u.user_id}) after V updated the credential. "
                f"Got {resp.status_code}. Body: {resp.text}"
            )

    # ------------------------------------------------------------------
    # Unit test: Owner CAN see their own credential in the list
    # ------------------------------------------------------------------

    def test_owner_can_see_their_own_credential_in_list(self) -> None:
        """
        Sanity check: the ownership filter must allow V to see V's own
        credential in the list.  This confirms the isolation is one-directional
        and the filter does not over-restrict.

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        _reset_db()
        user_v = _create_user(
            username="v_owner_sanity",
            email="v_owner_sanity@test.example",
        )
        cred_v = _create_credential(
            owner_id=user_v.user_id,
            website="sanity.example.com",
        )

        resp = _client.get(
            "/api/credentials",
            headers=_auth_headers(user_v.user_id),
        )
        assert resp.status_code == 200
        ids = {item["credential_id"] for item in resp.json()}
        assert cred_v.credential_id in ids, (
            f"Owner V (id={user_v.user_id}) did not see their own "
            f"credential {cred_v.credential_id} in the list. IDs: {ids}"
        )

    # ------------------------------------------------------------------
    # Unit test: Non-existent credential returns 404
    # ------------------------------------------------------------------

    def test_nonexistent_credential_returns_404(self) -> None:
        """
        Requesting a credential_id that does not exist must return 404.
        This verifies the guard returns the correct status for IDs that never
        existed (as opposed to IDs belonging to another user → 403).

        Feature: password-manager-website, Property 10: credential-ownership-isolation
        Validates: Requirements 5.3, 8.2
        """
        _reset_db()
        user_u = _create_user(
            username="u_404_test",
            email="u_404_test@test.example",
        )

        nonexistent_id = 999_999

        for method, path, body in [
            (
                "POST",
                f"/api/credentials/{nonexistent_id}/reveal",
                {"account_password": "anything"},
            ),
            (
                "PUT",
                f"/api/credentials/{nonexistent_id}",
                {
                    "website_name": "x.com",
                    "email_or_username": "x@x.com",
                    "is_username_login": False,
                    "password": "TestPass1@",
                    "account_password": "anything",
                },
            ),
            (
                "DELETE",
                f"/api/credentials/{nonexistent_id}",
                {"account_password": "anything"},
            ),
        ]:
            if method == "POST":
                resp = _client.post(
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )
            elif method == "PUT":
                resp = _client.put(
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )
            else:
                resp = _client.request(
                    "DELETE",
                    path,
                    json=body,
                    headers=_auth_headers(user_u.user_id),
                )

            assert resp.status_code == 404, (
                f"{method} {path}: expected 404 for non-existent credential. "
                f"Got {resp.status_code}. Body: {resp.text}"
            )
