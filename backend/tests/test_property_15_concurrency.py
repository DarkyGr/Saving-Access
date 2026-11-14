"""
Property-based tests for Property 15: Concurrent Operations Preserve Per-User Isolation.

Feature: password-manager-website, Property 15: Concurrent Operations Preserve Per-User Isolation

For any set of simultaneous credential operations by distinct users, no user's
operation SHALL read, modify, or delete another user's credentials; each user's
final data state SHALL reflect only their own operations.

Validates: Requirements 8.7

Implementation notes
--------------------
*  Concurrency is simulated via ``asyncio.gather`` dispatching requests to the
   FastAPI ASGI app through ``httpx.AsyncClient(transport=ASGITransport(...))``.
   The requests are interleaved cooperatively in one event loop, exercising
   application-level per-user isolation logic.

*  A temporary file-based SQLite database with ``NullPool`` is used so that
   each SQLAlchemy session opens its own connection.  This avoids the
   ``InterfaceError: bad parameter or other API misuse`` that occurs when two
   coroutines' sessions compete on a single ``StaticPool`` connection.  SQLite
   serializes concurrent writes at the file level, so isolation is preserved.

*  ``is_username_login=True`` is used for all credentials in these tests so
   that the email-format validator is not invoked (it only runs when
   ``is_username_login=False``).  The property under test is about per-user
   data isolation, not email validation.

*  The temporary file is created once at module level and reused across all
   Hypothesis iterations; it is removed by an ``atexit`` handler.
"""

import asyncio
import atexit
import os
import string
import tempfile
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient
import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Environment variables must be set BEFORE importing any app modules.
# ---------------------------------------------------------------------------

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "prop15-concurrency-isolation-secret"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ.setdefault("JWT_EXPIRE_MINUTES", "15")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# Prevent startup event from touching the real PostgreSQL engine.
os.environ["ENVIRONMENT"] = "test"

# ---------------------------------------------------------------------------
# Imports — after env vars
# ---------------------------------------------------------------------------

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, User  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.encryptor_service import EncryptorService  # noqa: E402
from app.utils.audit_columns import set_creation_audit  # noqa: E402

# ---------------------------------------------------------------------------
# Temporary file-based SQLite engine with NullPool
#
# A file-based SQLite database allows multiple independent sessions (each with
# their own connection) to co-exist without interfering — unlike an in-memory
# StaticPool setup where all sessions share one connection.
#
# NullPool: connections are closed immediately after use and never reused,
# so there is no pool contention between concurrent async coroutines.
#
# The temp file is cleaned up via atexit when the Python process exits.
# ---------------------------------------------------------------------------

_DB_FILE = tempfile.mktemp(suffix="_prop15_test.db")


@atexit.register
def _cleanup_db_file():  # pragma: no cover
    """Remove the temporary SQLite file when the test process exits."""
    try:
        if os.path.exists(_DB_FILE):
            os.unlink(_DB_FILE)
    except OSError:
        pass


_ENGINE = create_engine(
    f"sqlite:///{_DB_FILE}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)


@event.listens_for(_ENGINE, "connect")
def _disable_fk(dbapi_conn, _record):  # pragma: no cover
    dbapi_conn.execute("PRAGMA foreign_keys = OFF")


# Create only the tables this test needs.  Profile/UserProfile use JSONB
# (PostgreSQL-only) and are excluded; we use Admin-role JWTs so the
# permissions middleware bypasses the profile lookup entirely.
User.__table__.create(bind=_ENGINE, checkfirst=True)
Credential.__table__.create(bind=_ENGINE, checkfirst=True)
AuditLog.__table__.create(bind=_ENGINE, checkfirst=True)
from app.models import Profile as _Pf, UserProfile as _UPf  # noqa: E402
_Pf.__table__.create(bind=_ENGINE, checkfirst=True)
_UPf.__table__.create(bind=_ENGINE, checkfirst=True)
from app.models import RefreshToken as _RT  # noqa: E402
_RT.__table__.create(bind=_ENGINE, checkfirst=True)

_TestingSessionLocal = sessionmaker(
    bind=_ENGINE,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency override — points all request sessions at the shared DB
# ---------------------------------------------------------------------------


def _override_get_db():
    """Yield a fresh session on the shared file-based engine."""
    db: Session = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STRONG_PASSWORD = "Concurr1@TestPw"
_CRED_PASSWORD_A = "CredentialA1@pw"
_CRED_PASSWORD_B = "CredentialB1@pw"


def _make_jwt(user_id: int, role: str = "Admin") -> str:
    """Issue a signed Admin JWT for the given user_id."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm=_TEST_JWT_ALGORITHM)


def _auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {_make_jwt(user_id)}"}


def _make_session() -> Session:
    """Open a fresh session on the shared engine."""
    return _TestingSessionLocal()


def _reset_db() -> None:
    """Delete all rows between Hypothesis iterations."""
    db = _make_session()
    try:
        db.query(AuditLog).delete()
        db.query(Credential).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()


def _create_admin_user(username: str, email: str) -> int:
    """Register a user via AuthService, then promote to Admin.

    Returns ``user_id`` as a plain int to avoid cross-session ORM issues.
    """
    db = _make_session()
    try:
        auth_svc = AuthService(db)
        user: User = auth_svc.register(
            {
                "username": username,
                "email": email,
                "password": _STRONG_PASSWORD,
                "password_confirmation": _STRONG_PASSWORD,
            }
        )
        user.role = "Admin"
        db.commit()
        return user.user_id
    finally:
        db.close()


def _insert_credential(user_id: int, website: str, password: str) -> int:
    """Insert an encrypted Credential row directly into the DB.

    Returns ``credential_id`` as a plain int to avoid cross-session ORM issues.
    """
    db = _make_session()
    try:
        enc = EncryptorService()
        cred = Credential(
            user_id=user_id,
            website_name=website,
            # Use username login (not email) to bypass the email validator.
            email_or_username=f"user{user_id}",
            is_username_login=True,
            encrypted_password=enc.encrypt(password),
        )
        set_creation_audit(cred, user_id=user_id)
        db.add(cred)
        db.commit()
        return cred.credential_id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Async helper: runs a coroutine in a fresh event loop from sync test code.
# ---------------------------------------------------------------------------


def _run(coro):
    """Execute a coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_safe_alpha = st.text(
    alphabet=string.ascii_lowercase + string.digits,
    min_size=5,
    max_size=10,
)

_website_name = st.text(
    alphabet=string.ascii_letters + string.digits + "-",
    min_size=3,
    max_size=24,
)


# ---------------------------------------------------------------------------
# Property 15: Concurrent Operations Preserve Per-User Isolation
# Validates: Requirements 8.7
# ---------------------------------------------------------------------------


class TestConcurrentOperationsPerUserIsolation:
    """
    Property 15: Concurrent Operations Preserve Per-User Isolation

    Simultaneous credential operations by two distinct users (A and B) must
    never cross-contaminate data: each user's list/reveal responses must
    contain only their own records, regardless of the interleaving order.

    Feature: password-manager-website, Property 15: Concurrent Operations Preserve Per-User Isolation
    Validates: Requirements 8.7
    """

    # ------------------------------------------------------------------
    # Property 15a: Concurrent saves — each user's list contains only
    # their own credentials after parallel POST operations.
    # ------------------------------------------------------------------

    @given(
        suffix_a=_safe_alpha,
        suffix_b=_safe_alpha,
        site_a=_website_name,
        site_b=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_concurrent_saves_do_not_cross_contaminate_lists(
        self,
        suffix_a: str,
        suffix_b: str,
        site_a: str,
        site_b: str,
    ) -> None:
        """
        When users A and B concurrently POST /api/credentials, the subsequent
        GET /api/credentials for each user must contain only that user's own
        credentials — never the other user's.

        Feature: password-manager-website, Property 15: Concurrent Operations Preserve Per-User Isolation
        Validates: Requirements 8.7
        """
        assume(suffix_a != suffix_b)

        _reset_db()
        uid_a = _create_admin_user(
            username=f"a_{suffix_a[:8]}",
            email=f"a_{suffix_a[:8]}@test.example",
        )
        uid_b = _create_admin_user(
            username=f"b_{suffix_b[:8]}",
            email=f"b_{suffix_b[:8]}@test.example",
        )

        headers_a = _auth_headers(uid_a)
        headers_b = _auth_headers(uid_b)

        async def _do():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # Concurrent saves for both users
                resp_a, resp_b = await asyncio.gather(
                    ac.post(
                        "/api/credentials",
                        json={
                            "website_name": site_a[:256],
                            "email_or_username": f"usera_{suffix_a[:8]}",
                            "is_username_login": True,
                            "password": _CRED_PASSWORD_A,
                            "account_password": _STRONG_PASSWORD,
                        },
                        headers=headers_a,
                    ),
                    ac.post(
                        "/api/credentials",
                        json={
                            "website_name": site_b[:256],
                            "email_or_username": f"userb_{suffix_b[:8]}",
                            "is_username_login": True,
                            "password": _CRED_PASSWORD_B,
                            "account_password": _STRONG_PASSWORD,
                        },
                        headers=headers_b,
                    ),
                )

                # Concurrent list requests for both users
                list_a, list_b = await asyncio.gather(
                    ac.get("/api/credentials", headers=headers_a),
                    ac.get("/api/credentials", headers=headers_b),
                )
            return resp_a, resp_b, list_a, list_b

        resp_a, resp_b, list_a, list_b = _run(_do())

        assert resp_a.status_code == 201, (
            f"User A's save failed: {resp_a.status_code} {resp_a.text}"
        )
        assert resp_b.status_code == 201, (
            f"User B's save failed: {resp_b.status_code} {resp_b.text}"
        )
        cred_id_a = resp_a.json()["credential_id"]
        cred_id_b = resp_b.json()["credential_id"]

        assert list_a.status_code == 200, (
            f"User A's list failed: {list_a.status_code} {list_a.text}"
        )
        assert list_b.status_code == 200, (
            f"User B's list failed: {list_b.status_code} {list_b.text}"
        )

        ids_a = {item["credential_id"] for item in list_a.json()}
        ids_b = {item["credential_id"] for item in list_b.json()}

        # Each user must see their own credential.
        assert cred_id_a in ids_a, (
            f"User A (uid={uid_a}) did not see their own credential "
            f"{cred_id_a} in list. ids_a={ids_a}"
        )
        assert cred_id_b in ids_b, (
            f"User B (uid={uid_b}) did not see their own credential "
            f"{cred_id_b} in list. ids_b={ids_b}"
        )

        # Cross-contamination check: neither user must see the other's credential.
        assert cred_id_b not in ids_a, (
            f"User A's list contains User B's credential {cred_id_b}! "
            f"Cross-contamination detected. ids_a={ids_a}"
        )
        assert cred_id_a not in ids_b, (
            f"User B's list contains User A's credential {cred_id_a}! "
            f"Cross-contamination detected. ids_b={ids_b}"
        )

    # ------------------------------------------------------------------
    # Property 15b: Concurrent reveals — each user's reveal returns only
    # their own plaintext password.
    # ------------------------------------------------------------------

    @given(
        suffix_a=_safe_alpha,
        suffix_b=_safe_alpha,
        site_a=_website_name,
        site_b=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_concurrent_reveals_return_correct_plaintexts(
        self,
        suffix_a: str,
        suffix_b: str,
        site_a: str,
        site_b: str,
    ) -> None:
        """
        When users A and B concurrently POST /api/credentials/{id}/reveal,
        each response must contain that user's own plaintext password, never
        the other user's.

        Feature: password-manager-website, Property 15: Concurrent Operations Preserve Per-User Isolation
        Validates: Requirements 8.7
        """
        assume(suffix_a != suffix_b)

        _reset_db()
        uid_a = _create_admin_user(
            username=f"a_{suffix_a[:8]}",
            email=f"a_{suffix_a[:8]}@test.example",
        )
        uid_b = _create_admin_user(
            username=f"b_{suffix_b[:8]}",
            email=f"b_{suffix_b[:8]}@test.example",
        )

        cred_id_a = _insert_credential(uid_a, site_a[:100], _CRED_PASSWORD_A)
        cred_id_b = _insert_credential(uid_b, site_b[:100], _CRED_PASSWORD_B)

        headers_a = _auth_headers(uid_a)
        headers_b = _auth_headers(uid_b)

        async def _do():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                reveal_a, reveal_b = await asyncio.gather(
                    ac.post(
                        f"/api/credentials/{cred_id_a}/reveal",
                        json={"account_password": _STRONG_PASSWORD},
                        headers=headers_a,
                    ),
                    ac.post(
                        f"/api/credentials/{cred_id_b}/reveal",
                        json={"account_password": _STRONG_PASSWORD},
                        headers=headers_b,
                    ),
                )
            return reveal_a, reveal_b

        reveal_a, reveal_b = _run(_do())

        assert reveal_a.status_code == 200, (
            f"User A's reveal failed: {reveal_a.status_code} {reveal_a.text}"
        )
        assert reveal_b.status_code == 200, (
            f"User B's reveal failed: {reveal_b.status_code} {reveal_b.text}"
        )

        plaintext_a = reveal_a.json()["password"]
        plaintext_b = reveal_b.json()["password"]

        # Each user gets their own plaintext — never the other's.
        assert plaintext_a == _CRED_PASSWORD_A, (
            f"User A received wrong plaintext. "
            f"Expected {_CRED_PASSWORD_A!r}, got {plaintext_a!r}. "
            f"Cross-contamination with B's password ({_CRED_PASSWORD_B!r})?"
        )
        assert plaintext_b == _CRED_PASSWORD_B, (
            f"User B received wrong plaintext. "
            f"Expected {_CRED_PASSWORD_B!r}, got {plaintext_b!r}. "
            f"Cross-contamination with A's password ({_CRED_PASSWORD_A!r})?"
        )

    # ------------------------------------------------------------------
    # Property 15c: Concurrent mixed operations — save + list + reveal
    # all issued simultaneously across two users produce no cross-user data.
    # ------------------------------------------------------------------

    @given(
        suffix_a=_safe_alpha,
        suffix_b=_safe_alpha,
        site_a=_website_name,
        site_b=_website_name,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_concurrent_mixed_operations_preserve_isolation(
        self,
        suffix_a: str,
        suffix_b: str,
        site_a: str,
        site_b: str,
    ) -> None:
        """
        Mixed concurrent scenario: user A saves a new credential while user B
        lists their credentials and reveals an existing one — all gathered
        concurrently via ``asyncio.gather``.  Assertions:

        1. User A's save → 201; the new credential appears in A's list only.
        2. User B's list → 200; does NOT contain user A's new credential.
        3. User B's reveal → 200; returns B's own plaintext password.
        4. No cross-user credential IDs appear in any list response.

        Feature: password-manager-website, Property 15: Concurrent Operations Preserve Per-User Isolation
        Validates: Requirements 8.7
        """
        assume(suffix_a != suffix_b)

        _reset_db()
        uid_a = _create_admin_user(
            username=f"a_{suffix_a[:8]}",
            email=f"a_{suffix_a[:8]}@test.example",
        )
        uid_b = _create_admin_user(
            username=f"b_{suffix_b[:8]}",
            email=f"b_{suffix_b[:8]}@test.example",
        )

        # Pre-seed a credential for B so B can reveal it concurrently.
        cred_id_b = _insert_credential(uid_b, site_b[:100], _CRED_PASSWORD_B)

        headers_a = _auth_headers(uid_a)
        headers_b = _auth_headers(uid_b)

        async def _do():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # Gather: A saves, B lists, B reveals — all concurrent.
                save_a, list_b, reveal_b = await asyncio.gather(
                    ac.post(
                        "/api/credentials",
                        json={
                            "website_name": site_a[:256],
                            "email_or_username": f"usera_{suffix_a[:8]}",
                            "is_username_login": True,
                            "password": _CRED_PASSWORD_A,
                            "account_password": _STRONG_PASSWORD,
                        },
                        headers=headers_a,
                    ),
                    ac.get("/api/credentials", headers=headers_b),
                    ac.post(
                        f"/api/credentials/{cred_id_b}/reveal",
                        json={"account_password": _STRONG_PASSWORD},
                        headers=headers_b,
                    ),
                )
                # After saves settle, list A's credentials too.
                list_a = await ac.get("/api/credentials", headers=headers_a)
            return save_a, list_b, reveal_b, list_a

        save_a, list_b, reveal_b, list_a = _run(_do())

        # 1. A's save succeeded.
        assert save_a.status_code == 201, (
            f"User A's save failed: {save_a.status_code} {save_a.text}"
        )
        new_cred_id_a = save_a.json()["credential_id"]

        # 2. B's list must not include A's new credential.
        assert list_b.status_code == 200, (
            f"User B's list failed: {list_b.status_code} {list_b.text}"
        )
        ids_in_b_list = {item["credential_id"] for item in list_b.json()}
        assert new_cred_id_a not in ids_in_b_list, (
            f"User B's list contains User A's new credential {new_cred_id_a}! "
            f"Cross-contamination detected. B's ids={ids_in_b_list}"
        )

        # 3. B's reveal returns B's own plaintext.
        assert reveal_b.status_code == 200, (
            f"User B's reveal failed: {reveal_b.status_code} {reveal_b.text}"
        )
        assert reveal_b.json()["password"] == _CRED_PASSWORD_B, (
            f"User B received wrong plaintext. "
            f"Expected {_CRED_PASSWORD_B!r}, got {reveal_b.json()['password']!r}."
        )

        # 4. A's list must include A's new credential and must NOT include B's.
        assert list_a.status_code == 200, (
            f"User A's list failed: {list_a.status_code} {list_a.text}"
        )
        ids_in_a_list = {item["credential_id"] for item in list_a.json()}
        assert new_cred_id_a in ids_in_a_list, (
            f"User A's list does not contain their own new credential {new_cred_id_a}. "
            f"A's ids={ids_in_a_list}"
        )
        assert cred_id_b not in ids_in_a_list, (
            f"User A's list contains User B's credential {cred_id_b}! "
            f"Cross-contamination detected. A's ids={ids_in_a_list}"
        )
