"""
Property-based tests for the credentials list/search endpoint.

Feature: password-manager-website

Properties tested:
  Property 11: Search Filter Correctness
               — Validates: Requirements 5.2

For any search query string Q and any set of credentials belonging to the
authenticated user, every credential returned by GET /api/credentials?q=Q
SHALL contain Q as a case-insensitive substring in either website_name or
email_or_username.

Additionally, every credential that DOES contain Q (case-insensitively) in
either field SHALL appear in the results — the filter must not be
over-restrictive.
"""

import os
import string
from datetime import date, datetime, timezone, timedelta
from typing import Generator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st
from jose import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Environment defaults — must be set before importing app modules
# ---------------------------------------------------------------------------

os.environ.setdefault("JWT_SECRET", "test-search-filter-secret-11")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "15")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

# Generate a Fernet key for the test session (EncryptorService requires it)
_TEST_FERNET_KEY = Fernet.generate_key().decode()
os.environ.setdefault("FERNET_KEY", _TEST_FERNET_KEY)

# Set a dummy DATABASE_URL so database.py can be imported without raising
# KeyError; the actual DB connection is overridden via dependency injection.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# ---------------------------------------------------------------------------
# App and ORM imports — placed after env setup
# ---------------------------------------------------------------------------

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Credential, User  # noqa: E402
from app.services.encryptor_service import EncryptorService  # noqa: E402
from app.utils.audit_columns import set_creation_audit  # noqa: E402

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe alphabet: uppercase letters, lowercase letters, and digits.
# Avoids characters that SQLite ILIKE / Python str.lower() behave
# ambiguously with (e.g., certain Unicode accents).
_SAFE_ALPHABET = string.ascii_letters + string.digits

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=20,
)

# Strategy for a list of (website_name, email_or_username) credential pairs.
_credential_pair = st.tuples(_safe_text, _safe_text)
_credential_list = st.lists(_credential_pair, min_size=1, max_size=8)

# ---------------------------------------------------------------------------
# In-memory SQLite helpers
# ---------------------------------------------------------------------------
# The `profiles` table uses JSONB (PostgreSQL-only).  We create only the
# tables that are actually needed: users, credentials, and audit_log.
# Foreign-key enforcement is disabled so we can insert credentials without
# needing fully populated FK chains.
# ---------------------------------------------------------------------------

def _make_test_engine():
    """Create a fresh in-memory SQLite engine with only the required tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _disable_fk(dbapi_conn, _record):
        # Disable FK enforcement so we can skip profile-related tables.
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    # Only create the tables we actually need.
    User.__table__.create(bind=engine, checkfirst=True)
    Credential.__table__.create(bind=engine, checkfirst=True)

    return engine


# ---------------------------------------------------------------------------
# TestClient factory — builds a fresh app client per test invocation
# ---------------------------------------------------------------------------

def _make_client_and_session():
    """
    Return a (TestClient, Session) pair backed by a fresh in-memory SQLite DB.

    The ``get_db`` FastAPI dependency is overridden so that the app uses this
    in-memory session for the duration of the test.
    """
    engine = _make_test_engine()
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db: Session = TestingSession()

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db
        finally:
            pass  # keep session open; caller closes it

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=True)
    return client, db


def _cleanup(db: Session) -> None:
    """Close the session and remove the dependency override."""
    db.close()
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _create_test_user(db: Session, suffix: str = "") -> User:
    """Insert a User row directly (bypass HTTP layer to keep tests fast)."""
    from passlib.hash import bcrypt as bcrypt_hasher

    rounds = int(os.environ.get("BCRYPT_ROUNDS", "4"))
    password_hash = bcrypt_hasher.using(rounds=rounds).hash("TestPass1@xyz")
    now_date = date.today()
    now_time = datetime.now(timezone.utc).time().replace(tzinfo=None)

    username = f"search_user_{suffix}"
    email = f"search_user_{suffix}@example.com"

    # Avoid duplicate username collisions across Hypothesis examples
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return existing

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role="Admin",  # Admin bypasses profile permission check
        email_verified=False,
        creation_date=now_date,
        creation_time=now_time,
        creation_user_id=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Back-fill self-referential creation_user_id
    user.creation_user_id = user.user_id
    db.commit()
    db.refresh(user)
    return user


def _issue_jwt(user: User) -> str:
    """Issue a signed JWT for the given user (mirrors AuthService.login)."""
    secret = os.environ.get("JWT_SECRET", "test-search-filter-secret-11")
    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    expire_minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "15"))

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expire_minutes)
    payload = {
        "user_id": user.user_id,
        "role": user.role,
        "exp": exp,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def _seed_credentials(
    db: Session,
    user_id: int,
    credential_pairs: list[tuple[str, str]],
) -> list[Credential]:
    """Insert Credential rows for *user_id* directly, bypassing the HTTP layer."""
    encryptor = EncryptorService()
    now_date = date.today()
    now_time = datetime.now(timezone.utc).time().replace(tzinfo=None)

    rows: list[Credential] = []
    for website_name, email_or_username in credential_pairs:
        cred = Credential(
            user_id=user_id,
            website_name=website_name,
            email_or_username=email_or_username,
            is_username_login=False,
            encrypted_password=encryptor.encrypt("DummyPass1@"),
            creation_date=now_date,
            creation_time=now_time,
            creation_user_id=user_id,
        )
        db.add(cred)
        rows.append(cred)

    db.commit()
    for row in rows:
        db.refresh(row)

    return rows


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestSearchFilterUnit:
    """Concrete examples verifying basic search filter behaviour."""

    def test_no_query_returns_all_credentials(self):
        """GET /api/credentials with no q returns all user credentials."""
        client, db = _make_client_and_session()
        try:
            user = _create_test_user(db, suffix="noquery")
            token = _issue_jwt(user)
            _seed_credentials(db, user.user_id, [
                ("GitHub", "alice@example.com"),
                ("Gmail", "alice@gmail.com"),
            ])

            response = client.get(
                "/api/credentials",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
        finally:
            _cleanup(db)

    def test_query_matches_website_name_case_insensitive(self):
        """Querying 'git' returns credentials whose website_name contains 'git'."""
        client, db = _make_client_and_session()
        try:
            user = _create_test_user(db, suffix="gitcase")
            token = _issue_jwt(user)
            _seed_credentials(db, user.user_id, [
                ("GitHub", "alice@example.com"),
                ("GitLab", "bob@example.com"),
                ("Bitbucket", "charlie@example.com"),
            ])

            response = client.get(
                "/api/credentials?q=git",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            names = {item["website_name"] for item in data}
            assert names == {"GitHub", "GitLab"}
        finally:
            _cleanup(db)

    def test_query_matches_email_or_username_case_insensitive(self):
        """Querying 'alice' returns credentials whose email_or_username contains 'alice'."""
        client, db = _make_client_and_session()
        try:
            user = _create_test_user(db, suffix="aliceemail")
            token = _issue_jwt(user)
            _seed_credentials(db, user.user_id, [
                ("GitHub", "alice@example.com"),
                ("Gmail", "bob@example.com"),
            ])

            response = client.get(
                "/api/credentials?q=ALICE",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["email_or_username"] == "alice@example.com"
        finally:
            _cleanup(db)

    def test_query_with_no_match_returns_empty_list(self):
        """A query that matches nothing returns an empty list."""
        client, db = _make_client_and_session()
        try:
            user = _create_test_user(db, suffix="nomatch")
            token = _issue_jwt(user)
            _seed_credentials(db, user.user_id, [
                ("GitHub", "alice@example.com"),
            ])

            response = client.get(
                "/api/credentials?q=ZZZNOMATCH99",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            _cleanup(db)

    def test_password_field_is_always_null_in_list_response(self):
        """The password field is always null — never exposed in list results."""
        client, db = _make_client_and_session()
        try:
            user = _create_test_user(db, suffix="nullpass")
            token = _issue_jwt(user)
            _seed_credentials(db, user.user_id, [
                ("GitHub", "alice@example.com"),
            ])

            response = client.get(
                "/api/credentials",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            for item in response.json():
                assert item["password"] is None
        finally:
            _cleanup(db)

    def test_unauthenticated_request_returns_401(self):
        """Requests without a Bearer token receive 401."""
        client, db = _make_client_and_session()
        try:
            response = client.get("/api/credentials")
            assert response.status_code == 401
        finally:
            _cleanup(db)


# ---------------------------------------------------------------------------
# Property 11: Search Filter Correctness
# Validates: Requirements 5.2
# ---------------------------------------------------------------------------

class TestSearchFilterCorrectness:
    """
    Property 11: Search Filter Correctness

    For any search query string Q and any set of credentials belonging to the
    authenticated user:

      (a) Every credential returned by GET /api/credentials?q=Q contains Q
          as a case-insensitive substring in either website_name OR
          email_or_username  (no false positives).

      (b) Every credential that DOES contain Q (case-insensitively) in at
          least one of those two fields appears in the results
          (no false negatives / filter is not over-restrictive).

    Feature: password-manager-website, Property 11: search-filter-correctness
    Validates: Requirements 5.2
    """

    @given(
        credential_pairs=_credential_list,
        query=_safe_text,
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_no_false_positives_and_no_false_negatives(
        self,
        credential_pairs: list[tuple[str, str]],
        query: str,
    ) -> None:
        """
        Feature: password-manager-website, Property 11: search-filter-correctness
        Validates: Requirements 5.2

        Part A (no false positives): every item in the response contains
        ``query`` (case-insensitive) in website_name OR email_or_username.

        Part B (no false negatives): every seeded credential that contains
        ``query`` (case-insensitive) in website_name OR email_or_username
        appears in the response.
        """
        client, db = _make_client_and_session()
        try:
            # Use a unique suffix derived from the generated query to avoid
            # username collisions between Hypothesis examples.
            import hashlib
            suffix = hashlib.md5(
                (query + str(credential_pairs)).encode(), usedforsecurity=False
            ).hexdigest()[:8]

            user = _create_test_user(db, suffix=suffix)
            token = _issue_jwt(user)

            seeded = _seed_credentials(db, user.user_id, credential_pairs)

            # Compute the ground-truth expected set using Python's own
            # case-insensitive substring check (the oracle).
            q_lower = query.lower()
            expected_ids = {
                cred.credential_id
                for cred in seeded
                if q_lower in cred.website_name.lower()
                or q_lower in cred.email_or_username.lower()
            }

            response = client.get(
                f"/api/credentials?q={query}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}. Body: {response.text}"
            )

            results = response.json()

            # ---------------------------------------------------------------
            # Part A: No false positives
            # Every returned credential must match the query.
            # ---------------------------------------------------------------
            for item in results:
                website = item["website_name"]
                email_user = item["email_or_username"]
                matches = (
                    q_lower in website.lower()
                    or q_lower in email_user.lower()
                )
                assert matches, (
                    f"False positive: credential_id={item['credential_id']} "
                    f"website_name={website!r}, email_or_username={email_user!r} "
                    f"was returned but does NOT contain query={query!r} "
                    f"(case-insensitive)."
                )

            # ---------------------------------------------------------------
            # Part B: No false negatives
            # Every credential that matches must be in the response.
            # ---------------------------------------------------------------
            returned_ids = {item["credential_id"] for item in results}
            missing_ids = expected_ids - returned_ids

            assert not missing_ids, (
                f"False negatives detected: {len(missing_ids)} credential(s) "
                f"containing query={query!r} were NOT returned. "
                f"Missing credential_ids: {missing_ids}. "
                f"Returned ids: {returned_ids}. "
                f"All seeded credentials: "
                + str([
                    (c.credential_id, c.website_name, c.email_or_username)
                    for c in seeded
                ])
            )

        finally:
            _cleanup(db)

    @given(
        credential_pairs=_credential_list,
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_empty_query_returns_all_credentials(
        self,
        credential_pairs: list[tuple[str, str]],
    ) -> None:
        """
        Feature: password-manager-website, Property 11: search-filter-correctness
        Validates: Requirements 5.2

        When no query parameter is provided (or q is empty), the endpoint
        returns ALL credentials belonging to the authenticated user — no
        records are filtered out.
        """
        client, db = _make_client_and_session()
        try:
            import hashlib
            suffix = hashlib.md5(
                str(credential_pairs).encode(), usedforsecurity=False
            ).hexdigest()[:8]

            user = _create_test_user(db, suffix=f"nq{suffix}")
            token = _issue_jwt(user)
            seeded = _seed_credentials(db, user.user_id, credential_pairs)

            response = client.get(
                "/api/credentials",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}. Body: {response.text}"
            )

            results = response.json()
            returned_ids = {item["credential_id"] for item in results}
            seeded_ids = {c.credential_id for c in seeded}

            assert returned_ids == seeded_ids, (
                f"With no query, expected all {len(seeded_ids)} credentials "
                f"to be returned, but got {len(returned_ids)}. "
                f"Missing: {seeded_ids - returned_ids}. "
                f"Unexpected: {returned_ids - seeded_ids}."
            )

        finally:
            _cleanup(db)

    @given(
        base_name=_safe_text,
        num_matching=st.integers(min_value=1, max_value=4),
        num_non_matching=st.integers(min_value=1, max_value=4),
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_only_matching_credentials_are_returned(
        self,
        base_name: str,
        num_matching: int,
        num_non_matching: int,
    ) -> None:
        """
        Feature: password-manager-website, Property 11: search-filter-correctness
        Validates: Requirements 5.2

        Seeds a controlled mix of credentials:
          - ``num_matching`` credentials whose website_name contains the query
          - ``num_non_matching`` credentials whose website_name and
            email_or_username do NOT contain the query

        The response must contain exactly the matching ones and none of the
        non-matching ones.
        """
        # The query is base_name itself; non-matching credentials use a name
        # that has a guaranteed prefix difference ('ZZZ').
        query = base_name
        q_lower = query.lower()

        # Non-matching website name: build by replacing any char that appears
        # in q_lower with 'A', then prefix 'ZZZ'.  This guarantees q_lower
        # cannot be a substring of non_match_name.
        non_match_name = "ZZZ" + "".join(
            "A" if c.lower() in q_lower else c
            for c in "XNOMATCH"
        )
        # Non-matching email: same sanitisation — replace any q_lower chars.
        non_match_email_prefix = "nm" + "".join(
            "B" if c.lower() in q_lower else c
            for c in "nomatch"
        )
        non_match_email = f"{non_match_email_prefix}@test.io"

        # Guarantee no accidental overlap for either field
        assume(q_lower not in non_match_name.lower())
        assume(q_lower not in non_match_email.lower())

        client, db = _make_client_and_session()
        try:
            import hashlib
            suffix = hashlib.md5(
                (base_name + str(num_matching) + str(num_non_matching)).encode(),
                usedforsecurity=False,
            ).hexdigest()[:8]

            user = _create_test_user(db, suffix=f"ctrl{suffix}")
            token = _issue_jwt(user)

            # Build the credential list: matching first, then non-matching.
            matching_pairs = [
                (base_name, f"user{i}@example.com")
                for i in range(num_matching)
            ]
            non_matching_pairs = [
                (non_match_name, non_match_email)
                for i in range(num_non_matching)
            ]
            all_pairs = matching_pairs + non_matching_pairs

            seeded = _seed_credentials(db, user.user_id, all_pairs)
            # The first num_matching rows are the matching ones
            matching_ids = {seeded[i].credential_id for i in range(num_matching)}
            non_matching_ids = {
                seeded[num_matching + i].credential_id
                for i in range(num_non_matching)
            }

            response = client.get(
                f"/api/credentials?q={query}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}. Body: {response.text}"
            )

            results = response.json()
            returned_ids = {item["credential_id"] for item in results}

            # All matching credentials must be in the response
            assert matching_ids.issubset(returned_ids), (
                f"Some matching credentials were not returned. "
                f"Expected {matching_ids} ⊆ {returned_ids}. "
                f"Query={query!r}"
            )

            # No non-matching credentials must appear
            spurious = non_matching_ids & returned_ids
            assert not spurious, (
                f"Non-matching credentials appeared in the response: {spurious}. "
                f"Query={query!r}, non_match_name={non_match_name!r}"
            )

        finally:
            _cleanup(db)
