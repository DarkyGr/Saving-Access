"""
Phase 2 security hardening tests (tasks 31.1–31.5).
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-security-hardening-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

from datetime import datetime, timedelta, timezone  # noqa: E402
from unittest.mock import patch  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import security  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Base, Credential, Profile, RefreshToken, User, UserProfile  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.seed import seed_default_profiles  # noqa: E402
from app.services.audit_service import AuditService  # noqa: E402

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_ENGINE)
_Session = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def _override_get_db():
    db: Session = _Session()
    try:
        yield db
    finally:
        db.close()


_PW = "Str0ngPassw0rd!"


@pytest.fixture()
def client():
    # base_url https so the Secure refresh cookie is stored and sent back.
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        for model in (RefreshToken, AuditLog, Credential, UserProfile, Profile, User):
            db.query(model).delete()
        db.commit()
        seed_default_profiles(db)
    yield


def _register_and_login(client: TestClient, username: str = "alice") -> dict:
    r = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": _PW,
            "password_confirmation": _PW,
        },
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"username": username, "password": _PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── 31.1 Settings validation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "secret, key, fragment",
    [
        ("", _TEST_FERNET_KEY, "JWT_SECRET is not set"),
        ("changeme", _TEST_FERNET_KEY, "at least 32"),
        ("short-secret", _TEST_FERNET_KEY, "at least 32"),
        ("x" * 40, "", "FERNET_KEY is not set"),
        ("x" * 40, "not-a-fernet-key", "not a valid Fernet key"),
    ],
)
def test_validate_settings_rejects_unsafe_config(monkeypatch, secret, key, fragment):
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("FERNET_KEY", key)
    with pytest.raises(security.SettingsError, match=fragment):
        security.validate_settings()


def test_validate_settings_accepts_safe_config(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "a" * 48)
    monkeypatch.setenv("FERNET_KEY", _TEST_FERNET_KEY)
    security.validate_settings()


def test_app_refuses_to_start_with_weak_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "changeme")
    with pytest.raises(security.SettingsError):
        with TestClient(app):
            pass


def test_no_default_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(security.SettingsError):
        security.encode_token({"user_id": 1, "exp": datetime.now(timezone.utc)})


# ── 31.2 Hashing and tokens ──────────────────────────────────────────────────

# Generated with passlib 1.7.4: bcrypt.using(rounds=4).hash("Legacy!Passw0rd")
_PASSLIB_HASH = "$2b$04$8KiAY2uTY6vJnp3QrKei2.9Jsxm1sywu84pZQrezHjmTx7AX.cxAa"


def test_hashes_created_by_passlib_still_verify():
    assert security.verify_password("Legacy!Passw0rd", _PASSLIB_HASH)
    assert not security.verify_password("wrong", _PASSLIB_HASH)


def test_hash_is_bcrypt_and_never_plaintext():
    h = security.hash_password(_PW)
    assert h.startswith("$2b$") and _PW not in h
    assert security.verify_password(_PW, h)


def test_verify_password_never_raises_on_garbage_hash():
    assert security.verify_password("x", "not-a-hash") is False


def test_long_passwords_keep_passlib_truncation_semantics():
    long_pw = "A1!" + "x" * 100
    h = security.hash_password(long_pw)
    assert security.verify_password(long_pw, h)


def test_login_of_unknown_user_still_runs_bcrypt(client):
    with patch("app.services.auth_service.burn_password_check") as burn:
        r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid credentials."}
    burn.assert_called_once_with("x")


def test_access_token_requires_exp(client):
    _register_and_login(client)
    token = jwt.encode({"user_id": 1, "role": "Admin"}, _TEST_JWT_SECRET, algorithm="HS256")
    r = client.get("/api/profile/permissions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_non_access_token_type_is_rejected(client):
    token = jwt.encode(
        {
            "user_id": 1,
            "role": "Admin",
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        _TEST_JWT_SECRET,
        algorithm="HS256",
    )
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_none_algorithm_token_is_rejected(client):
    token = jwt.encode(
        {"user_id": 1, "role": "Admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        None,
        algorithm="none",
    )
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ── 31.3 Rate limiting ───────────────────────────────────────────────────────


@pytest.fixture()
def rate_limited():
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


def test_login_is_rate_limited_per_ip(client, rate_limited):
    codes = [
        client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_account_password_checks_are_rate_limited_per_user(client, rate_limited):
    limiter.enabled = False
    headers = _register_and_login(client, "bob")
    other = _register_and_login(client, "carol")
    limiter.enabled = True
    for _ in range(10):
        r = client.post("/api/credentials/1/reveal", headers=headers, json={"account_password": "bad"})
        assert r.status_code in (401, 403, 404)
    r = client.post("/api/credentials/1/reveal", headers=headers, json={"account_password": "bad"})
    assert r.status_code == 429
    assert "Too many attempts" in r.json()["detail"]
    # Another user's quota is independent.
    r = client.post("/api/credentials/1/reveal", headers=other, json={"account_password": "bad"})
    assert r.status_code != 429


# ── 31.4 Atomic audit ────────────────────────────────────────────────────────


def test_credential_insert_rolls_back_when_audit_write_fails(client):
    headers = _register_and_login(client)
    body = {
        "website_name": "GitHub",
        "email_or_username": "alice@example.com",
        "password": "site-pw",
        "account_password": _PW,
    }
    original = AuditService.log

    def failing_log(self, *args, **kwargs):
        raise RuntimeError("audit store unavailable")

    AuditService.log = failing_log
    try:
        with pytest.raises(RuntimeError):
            TestClient(app, base_url="https://testserver").post(
                "/api/credentials", headers=headers, json=body
            )
    finally:
        AuditService.log = original

    with _Session() as db:
        assert db.query(Credential).count() == 0

    r = client.post("/api/credentials", headers=headers, json=body)
    assert r.status_code == 201
    with _Session() as db:
        assert db.query(Credential).count() == 1
        assert db.query(AuditLog).filter(AuditLog.operation == "INSERT").count() == 1


# ── 31.5 Refresh token cookie ────────────────────────────────────────────────


def test_login_sets_httponly_strict_refresh_cookie(client):
    client.post(
        "/api/auth/register",
        json={"username": "dan", "email": "dan@example.com", "password": _PW, "password_confirmation": _PW},
    )
    r = client.post("/api/auth/login", json={"username": "dan", "password": _PW})
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("sp_refresh=")
    for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api/auth"):
        assert attr.lower() in cookie.lower()
    # Only a hash is stored server-side.
    raw = cookie.split(";", 1)[0].split("=", 1)[1]
    with _Session() as db:
        row = db.query(RefreshToken).one()
        assert row.token_hash != raw and len(row.token_hash) == 64


def test_refresh_returns_new_access_token_and_rotates_cookie(client):
    _register_and_login(client, "erin")
    first = client.cookies.get("sp_refresh")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    claims = jwt.decode(r.json()["access_token"], _TEST_JWT_SECRET, algorithms=["HS256"])
    assert claims["username"] == "erin" and claims["type"] == "access"
    second = client.cookies.get("sp_refresh")
    assert second and second != first


def test_refresh_without_cookie_is_401(client):
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
    assert r.json() == {"detail": "Session expired."}


def test_reusing_a_rotated_refresh_token_revokes_the_family(client):
    _register_and_login(client, "fay")
    stolen = client.cookies.get("sp_refresh")
    assert client.post("/api/auth/refresh").status_code == 200
    current = client.cookies.get("sp_refresh")

    attacker = TestClient(app, base_url="https://testserver")
    attacker.cookies.set("sp_refresh", stolen, path="/api/auth")
    assert attacker.post("/api/auth/refresh").status_code == 401

    # The legitimate session in the same family is revoked too.
    client.cookies.clear()
    client.cookies.set("sp_refresh", current, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_expired_refresh_token_is_rejected(client):
    _register_and_login(client, "gus")
    with _Session() as db:
        row = db.query(RefreshToken).one()
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token_and_clears_cookie(client):
    _register_and_login(client, "hal")
    token = client.cookies.get("sp_refresh")
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert "sp_refresh=" in r.headers["set-cookie"] and "max-age=0" in r.headers["set-cookie"].lower()

    replay = TestClient(app, base_url="https://testserver")
    replay.cookies.set("sp_refresh", token, path="/api/auth")
    assert replay.post("/api/auth/refresh").status_code == 401
