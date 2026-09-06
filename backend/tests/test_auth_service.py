"""
Property-based tests for AuthService.

Feature: password-manager-website

Properties tested:
  Property 1: Password Confirmation Match        — Validates: Requirements 1.3, 1.4
  Property 2: Password Strength Validation       — Validates: Requirements 1.5, 1.6
  Property 3: Account Password Hashing           — Validates: Requirements 1.7, 8.5
  Property 5: Generic Error on Invalid Login     — Validates: Requirements 2.3
  Property 6: JWT Issued on Successful Login     — Validates: Requirements 2.4
"""

import os
import string
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from jose import jwt
from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models import Base, User
from app.services.auth_service import AuthService, validate_password_strength

# ---------------------------------------------------------------------------
# Env setup for tests — set defaults that all tests can rely on
# ---------------------------------------------------------------------------

os.environ.setdefault("JWT_SECRET", "test-secret-default")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "15")
# Use low bcrypt rounds in tests to keep runtime manageable.
# Production code reads this env var and defaults to 12 when not set.
os.environ.setdefault("BCRYPT_ROUNDS", "4")


# ---------------------------------------------------------------------------
# In-memory SQLite test database helpers
# ---------------------------------------------------------------------------
# We create only the `users` table because:
#  - Other tables use JSONB (PostgreSQL-only) which SQLite doesn't support.
#  - AuthService only touches the `users` table.
# ---------------------------------------------------------------------------

def _make_sqlite_session() -> Session:
    """Create a fresh in-memory SQLite engine + session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    User.__table__.create(bind=engine, checkfirst=True)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return TestSession()


@pytest.fixture(scope="session")
def sqlite_engine():
    """Session-scoped SQLite in-memory engine (only users table)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    User.__table__.create(bind=engine, checkfirst=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(sqlite_engine) -> Session:
    """Function-scoped transactional session that rolls back after each test."""
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSession()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def auth_service(db_session) -> AuthService:
    """AuthService bound to the test DB session."""
    return AuthService(db_session)


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# A "valid" password that satisfies all 5 strength rules.
_VALID_BASE = "ValidPass1@"  # 11 chars — padded to ≥ 12 via suffix


def _make_valid_password(suffix: str = "X") -> str:
    """Return a password that always passes all strength rules."""
    candidate = _VALID_BASE + suffix
    if len(candidate) < 12:
        candidate = candidate + "A" * (12 - len(candidate))
    return candidate


# Strategy: short alphanumeric strings as username/email suffixes.
_safe_text = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=4,
    max_size=16,
)


# ---------------------------------------------------------------------------
# Unit tests — specific examples (not property-based)
# ---------------------------------------------------------------------------

class TestPasswordStrengthUnit:
    def test_valid_password_passes(self):
        assert validate_password_strength("Abcdefgh1@34") == []

    def test_too_short_fails(self):
        errors = validate_password_strength("Ab1@xxxxx")  # 9 chars
        assert any("12 characters" in e for e in errors)

    def test_no_uppercase_fails(self):
        errors = validate_password_strength("abcdefgh1@34")
        assert any("uppercase" in e for e in errors)

    def test_no_lowercase_fails(self):
        errors = validate_password_strength("ABCDEFGH1@34")
        assert any("lowercase" in e for e in errors)

    def test_no_digit_fails(self):
        errors = validate_password_strength("Abcdefghij@x")
        assert any("digit" in e for e in errors)

    def test_no_symbol_fails(self):
        errors = validate_password_strength("Abcdefgh1234")
        assert any("symbol" in e for e in errors)


class TestAuthServiceUnit:
    def test_register_creates_user(self, auth_service):
        user = auth_service.register({
            "username": "alice_unit",
            "email": "alice_unit@example.com",
            "password": "AlicePass1@34",
            "password_confirmation": "AlicePass1@34",
        })
        assert user.user_id is not None
        assert user.username == "alice_unit"
        assert user.password_hash != "AlicePass1@34"

    def test_register_duplicate_username_raises(self, auth_service):
        auth_service.register({
            "username": "bob_dup",
            "email": "bob_dup@example.com",
            "password": "BobPass1@3456",
            "password_confirmation": "BobPass1@3456",
        })
        with pytest.raises(HTTPException) as exc_info:
            auth_service.register({
                "username": "bob_dup",
                "email": "bob_dup2@example.com",
                "password": "BobPass1@3456",
                "password_confirmation": "BobPass1@3456",
            })
        assert exc_info.value.status_code == 400

    def test_login_success(self, auth_service):
        auth_service.register({
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "Charlie1@pass",
            "password_confirmation": "Charlie1@pass",
        })
        result = auth_service.login({"username": "charlie", "password": "Charlie1@pass"})
        assert "access_token" in result
        assert result["token_type"] == "bearer"

    def test_login_wrong_password_raises_401(self, auth_service):
        auth_service.register({
            "username": "dave",
            "email": "dave@example.com",
            "password": "DavePass1@xyz",
            "password_confirmation": "DavePass1@xyz",
        })
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login({"username": "dave", "password": "wrongpassword"})
        assert exc_info.value.status_code == 401

    def test_login_nonexistent_user_raises_401(self, auth_service):
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login({"username": "nobody", "password": "anything"})
        assert exc_info.value.status_code == 401

    def test_check_account_password_correct(self, auth_service):
        user = auth_service.register({
            "username": "eve_check",
            "email": "eve_check@example.com",
            "password": "EvePass1@2024",
            "password_confirmation": "EvePass1@2024",
        })
        assert auth_service.check_account_password(user.user_id, "EvePass1@2024") is True

    def test_check_account_password_wrong(self, auth_service):
        user = auth_service.register({
            "username": "frank_check",
            "email": "frank_check@example.com",
            "password": "FrankPass1@24",
            "password_confirmation": "FrankPass1@24",
        })
        assert auth_service.check_account_password(user.user_id, "wrong") is False


# ---------------------------------------------------------------------------
# Property 1: Password Confirmation Match
# Validates: Requirements 1.3, 1.4
# ---------------------------------------------------------------------------

class TestPasswordConfirmationMatch:
    """
    Property 1: Password Confirmation Match

    For any pair of strings (password, confirmation), register accepts the
    submission if and only if password == confirmation.

    Feature: password-manager-website, Property 1: Password Confirmation Match
    Validates: Requirements 1.3, 1.4
    """

    @given(
        password=st.text(min_size=1, max_size=64),
        confirmation=st.text(min_size=1, max_size=64),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_confirmation_match_accepted_rejected(self, password, confirmation):
        """
        Feature: password-manager-website, Property 1: Password Confirmation Match
        Validates: Requirements 1.3, 1.4
        """
        db = _make_sqlite_session()
        svc = AuthService(db)

        payload = {
            "username": "prop1user",
            "email": "prop1user@example.com",
            "password": password,
            "password_confirmation": confirmation,
        }

        if password == confirmation:
            # When confirmation matches, any failure must NOT be about mismatch.
            try:
                svc.register(payload)
            except HTTPException as exc:
                assert "do not match" not in str(exc.detail), (
                    f"Mismatch error raised even though password == confirmation. "
                    f"password={password!r}"
                )
        else:
            # When confirmation differs, must raise 400 with mismatch detail.
            with pytest.raises(HTTPException) as exc_info:
                svc.register(payload)
            assert exc_info.value.status_code == 400
            assert "do not match" in str(exc_info.value.detail), (
                f"Expected mismatch error but got: {exc_info.value.detail!r}"
            )

        db.close()


# ---------------------------------------------------------------------------
# Property 2: Password Strength Validation
# Validates: Requirements 1.5, 1.6
# ---------------------------------------------------------------------------

class TestPasswordStrengthValidation:
    """
    Property 2: Password Strength Validation

    The validator rejects a password iff at least one rule is unmet:
      - length < 12
      - no uppercase letter
      - no lowercase letter
      - no digit
      - no symbol from {@, $, !}

    Feature: password-manager-website, Property 2: Password Strength Validation
    Validates: Requirements 1.5, 1.6
    """

    def _is_valid_password(self, pwd: str) -> bool:
        """Reference oracle: independently compute whether a password is valid."""
        if len(pwd) < 12:
            return False
        if not any(c.isupper() for c in pwd):
            return False
        if not any(c.islower() for c in pwd):
            return False
        if not any(c.isdigit() for c in pwd):
            return False
        if not any(c in "@$!" for c in pwd):
            return False
        return True

    @given(password=st.text(min_size=0, max_size=128))
    @settings(max_examples=200)
    def test_strength_validator_matches_oracle(self, password):
        """
        Feature: password-manager-website, Property 2: Password Strength Validation
        Validates: Requirements 1.5, 1.6
        """
        errors = validate_password_strength(password)
        expected_valid = self._is_valid_password(password)

        if expected_valid:
            assert errors == [], (
                f"Oracle says password is valid but validator returned errors: "
                f"password={password!r}, errors={errors}"
            )
        else:
            assert len(errors) > 0, (
                f"Oracle says password is INVALID but validator returned no errors: "
                f"password={password!r}"
            )

    @given(
        # Passwords with lowercase + digits only: no uppercase, no @$! symbol
        password=st.text(
            alphabet=string.ascii_lowercase + string.digits,
            min_size=12,
            max_size=32,
        )
    )
    @settings(max_examples=200)
    def test_missing_uppercase_or_symbol_always_rejected(self, password):
        """
        Feature: password-manager-website, Property 2: Password Strength Validation
        Validates: Requirements 1.5, 1.6
        """
        errors = validate_password_strength(password)
        rule_violations = [e for e in errors if "uppercase" in e or "symbol" in e]
        assert len(rule_violations) > 0, (
            f"Expected uppercase/symbol error for password without them: {password!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Account Password Hashing
# Validates: Requirements 1.7, 8.5
# ---------------------------------------------------------------------------

class TestAccountPasswordHashing:
    """
    Property 3: Account Password Hashing

    For any valid registration payload, stored password_hash is a valid bcrypt
    hash AND differs from the plaintext password.

    Feature: password-manager-website, Property 3: Account Password Hashing
    Validates: Requirements 1.7, 8.5
    """

    @given(suffix=_safe_text)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,  # bcrypt with rounds=12 is intentionally slow (~300-400 ms)
    )
    def test_stored_hash_is_bcrypt_and_differs_from_plaintext(self, suffix):
        """
        Feature: password-manager-website, Property 3: Account Password Hashing
        Validates: Requirements 1.7, 8.5
        """
        db = _make_sqlite_session()
        svc = AuthService(db)
        password = _make_valid_password(suffix[:8])

        user = svc.register({
            "username": f"hashuser_{suffix[:8]}",
            "email": f"hashuser_{suffix[:8]}@example.com",
            "password": password,
            "password_confirmation": password,
        })

        # 1. Hash must start with bcrypt identifier ($2b$)
        assert user.password_hash.startswith("$2b$"), (
            f"Stored hash does not look like bcrypt: {user.password_hash!r}"
        )

        # 2. Hash must NOT equal the plaintext
        assert user.password_hash != password, (
            "Stored password_hash equals plaintext — password stored unencrypted!"
        )

        # 3. bcrypt.verify must confirm the hash matches the original plaintext
        assert bcrypt_hasher.verify(password, user.password_hash), (
            "bcrypt.verify failed — the stored hash does not match the plaintext."
        )

        db.close()


# ---------------------------------------------------------------------------
# Property 5: Generic Error on Invalid Login
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------

class TestGenericErrorOnInvalidLogin:
    """
    Property 5: Generic Error on Invalid Login

    For any failed login attempt (wrong username, wrong password, or
    non-existent user) the response always contains the same generic error
    detail — never revealing which field was wrong.

    Feature: password-manager-website, Property 5: Generic Error on Invalid Login
    Validates: Requirements 2.3
    """

    _GENERIC_DETAIL = "Invalid credentials."

    @given(
        username=st.text(min_size=1, max_size=64),
        password=st.text(min_size=1, max_size=64),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_nonexistent_user_always_returns_generic_error(self, username, password):
        """
        Login with any username/password pair that doesn't exist must always
        return the same generic 401 with "Invalid credentials."

        Feature: password-manager-website, Property 5: Generic Error on Invalid Login
        Validates: Requirements 2.3
        """
        db = _make_sqlite_session()
        svc = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            svc.login({"username": username, "password": password})

        exc = exc_info.value
        assert exc.status_code == 401, (
            f"Expected 401 but got {exc.status_code} for username={username!r}"
        )
        assert exc.detail == self._GENERIC_DETAIL, (
            f"Expected generic detail {self._GENERIC_DETAIL!r} but got {exc.detail!r} "
            f"for username={username!r}"
        )

        db.close()

    @given(wrong_password=st.text(min_size=1, max_size=64))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,  # bcrypt verify is intentionally slow (~300 ms)
    )
    def test_wrong_password_returns_generic_error(self, wrong_password):
        """
        Login with an existing username but the wrong password must return the
        same generic 401.

        Feature: password-manager-website, Property 5: Generic Error on Invalid Login
        Validates: Requirements 2.3
        """
        correct_password = "CorrectPwd1@xyz"
        assume(wrong_password != correct_password)

        db = _make_sqlite_session()
        svc = AuthService(db)

        svc.register({
            "username": "wrongpwd_user",
            "email": "wrongpwd_user@example.com",
            "password": correct_password,
            "password_confirmation": correct_password,
        })

        with pytest.raises(HTTPException) as exc_info:
            svc.login({"username": "wrongpwd_user", "password": wrong_password})

        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == self._GENERIC_DETAIL, (
            f"Expected {self._GENERIC_DETAIL!r} but got {exc.detail!r} "
            f"for wrong_password={wrong_password!r}"
        )

        db.close()


# ---------------------------------------------------------------------------
# Property 6: JWT Issued on Successful Login
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

class TestJWTIssuedOnSuccessfulLogin:
    """
    Property 6: JWT Issued on Successful Login

    For any successful login, the response contains an access_token that is
    a structurally valid JWT with user_id, role, and exp claims where exp is
    within 15 minutes of issue time.

    Feature: password-manager-website, Property 6: JWT Issued on Successful Login
    Validates: Requirements 2.4
    """

    _SECRET = "prop6-test-secret"

    @given(suffix=_safe_text)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,  # bcrypt with rounds=12 is intentionally slow (~300-400 ms)
    )
    def test_jwt_contains_required_claims_within_15min(self, suffix):
        """
        Feature: password-manager-website, Property 6: JWT Issued on Successful Login
        Validates: Requirements 2.4
        """
        # Set env vars before creating the service instance
        os.environ["JWT_SECRET"] = self._SECRET
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_EXPIRE_MINUTES"] = "15"

        db = _make_sqlite_session()
        svc = AuthService(db)

        password = _make_valid_password(suffix[:8])
        username = f"jwtuser_{suffix[:8]}"
        email = f"jwtuser_{suffix[:8]}@example.com"

        user = svc.register({
            "username": username,
            "email": email,
            "password": password,
            "password_confirmation": password,
        })

        before_login = datetime.now(timezone.utc)
        result = svc.login({"username": username, "password": password})
        after_login = datetime.now(timezone.utc)

        # 1. Response structure
        assert "access_token" in result, "Response missing 'access_token'"
        assert result["token_type"] == "bearer", (
            f"Expected token_type='bearer', got {result['token_type']!r}"
        )
        assert result["expires_in"] == 900, (
            f"Expected expires_in=900, got {result['expires_in']}"
        )

        # 2. Decode the JWT and verify claims
        token = result["access_token"]
        decoded = jwt.decode(token, self._SECRET, algorithms=["HS256"])

        assert "user_id" in decoded, "JWT missing 'user_id' claim"
        assert "role" in decoded, "JWT missing 'role' claim"
        assert "exp" in decoded, "JWT missing 'exp' claim"

        assert decoded["user_id"] == user.user_id, (
            f"JWT user_id {decoded['user_id']} != registered user_id {user.user_id}"
        )
        assert decoded["role"] == "User", (
            f"JWT role {decoded['role']!r} != expected 'User'"
        )

        # 3. Expiry must be within 15 minutes (+ 2 s buffer for test overhead)
        exp_dt = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        max_exp = after_login + timedelta(minutes=15, seconds=2)
        min_exp = before_login + timedelta(minutes=14, seconds=58)

        assert exp_dt <= max_exp, (
            f"exp {exp_dt} is more than 15 min after login time {after_login}"
        )
        assert exp_dt >= min_exp, (
            f"exp {exp_dt} is less than 15 min after login time {before_login}"
        )

        db.close()
