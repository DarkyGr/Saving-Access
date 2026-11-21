"""
Trusted devices: "don't ask for a code on this device for N days"
(Requirement 21).
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-trusted-devices-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import time  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AccountToken,
    AuditLog,
    Credential,
    RecoveryCode,
    RefreshToken,
    SystemSetting,
    TrustedDevice,
    User,
    UserPreference,
)
from app.utils import totp  # noqa: E402
from tests.conftest import make_test_engine  # noqa: E402

_ENGINE = make_test_engine()
_Session = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def _override_get_db():
    db: Session = _Session()
    try:
        yield db
    finally:
        db.close()


_PW = "Str0ngPassw0rd!"


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_REQUIRED", "true")
    with _Session() as db:
        for model in (TrustedDevice, RecoveryCode, SystemSetting, AccountToken, UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


class Clock:
    def __init__(self):
        self.now = time.time()

    def code(self, secret: str) -> str:
        self.now += totp.STEP_SECONDS
        return totp.code_at(secret, totp.current_step(self.now))


@pytest.fixture()
def clock():
    c = Clock()
    with patch("app.utils.totp.time.time", lambda: c.now):
        yield c


def _device(agent: str = "Mozilla/5.0 (Windows NT 10.0) Firefox/140.0") -> TestClient:
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": agent})


def _password(c: TestClient):
    return c.post("/api/auth/login", json={"username": "alice", "password": _PW}).json()


def _enrolled(clock) -> tuple[TestClient, str]:
    c = _device()
    c.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": _PW, "password_confirmation": _PW},
    )
    token = _password(c)["mfa_token"]
    secret = c.post("/api/auth/2fa/setup", json={"mfa_token": token}).json()["secret"]
    with patch("app.routers.auth_router.send_email"):
        c.post("/api/auth/2fa/confirm", json={"mfa_token": token, "code": totp.code_at(secret, totp.current_step(clock.now))})
    return c, secret


def _verify(c: TestClient, secret: str, clock, remember: bool):
    first = _password(c)
    assert first["mfa"] == "code"
    with patch("app.routers.auth_router.send_email") as send:
        r = c.post(
            "/api/auth/login/verify",
            json={"mfa_token": first["mfa_token"], "code": clock.code(secret), "remember_device": remember},
        )
    assert r.status_code == 200, r.text
    return r, send


def test_the_code_step_offers_the_configured_days(clock):
    c, _ = _enrolled(clock)
    assert _password(c)["trusted_device_days"] == 30


def test_a_remembered_browser_skips_the_code_but_not_the_password(clock):
    c, secret = _enrolled(clock)
    r, send = _verify(c, secret, clock, remember=True)
    cookie = r.headers["set-cookie"]
    assert "sp_device=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/auth" in cookie and "Max-Age=2592000" in cookie
    assert "skip the two-step code for 30 days" in send.call_args.args[0].body
    with _Session() as db:
        row = db.query(TrustedDevice).one()
        assert c.cookies["sp_device"] not in row.token_hash  # only the hash is stored

    skipped = _password(c)
    assert skipped["access_token"] and skipped["mfa"] is None
    # The password is still checked.
    assert c.post("/api/auth/login", json={"username": "alice", "password": "Wr0ngPassword!"}).status_code == 401


def test_without_remember_the_code_is_asked_again_and_other_browsers_ask(clock):
    c, secret = _enrolled(clock)
    _verify(c, secret, clock, remember=False)
    assert _password(c)["mfa"] == "code"

    _verify(c, secret, clock, remember=True)
    other = _device("Other browser")
    other.post("/api/auth/register", json={"username": "bob", "email": "bob@example.com", "password": _PW, "password_confirmation": _PW})
    assert _password(other)["mfa"] == "code"
    # Alice's cookie never helps another account.
    stolen = _device()
    stolen.cookies.set("sp_device", c.cookies["sp_device"], domain="testserver", path="/api/auth")
    bob = stolen.post("/api/auth/login", json={"username": "bob", "password": _PW}).json()
    assert bob["mfa"] == "setup"


def test_expired_locked_and_zero_days_ask_for_the_code(clock):
    c, secret = _enrolled(clock)
    _verify(c, secret, clock, remember=True)
    with _Session() as db:
        db.query(TrustedDevice).update({"expires_at": datetime(2020, 1, 1)})
        db.commit()
    assert _password(c)["mfa"] == "code"

    _verify(c, secret, clock, remember=True)
    with _Session() as db:
        db.query(User).update({"locked_at": datetime(2026, 1, 1)})
        db.commit()
    assert _password(c)["mfa"] == "code"
    with _Session() as db:
        db.query(User).update({"locked_at": None})
        db.add(SystemSetting(key="trusted_device_days", value="0", creation_date=datetime.now().date(), creation_time=datetime.now().time()))
        db.commit()
    body = _password(c)
    assert body["mfa"] == "code" and body["trusted_device_days"] == 0


def test_settings_list_and_forget(clock):
    c, secret = _enrolled(clock)
    r, _ = _verify(c, secret, clock, remember=True)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    devices = c.get("/api/profile/trusted-devices", headers=h).json()
    assert len(devices) == 1 and "Firefox" in devices[0]["user_agent"]
    assert devices[0]["expires_at"].endswith("Z")

    assert c.delete(f"/api/profile/trusted-devices/{devices[0]['device_id']}", headers=h).status_code == 204
    assert _password(c)["mfa"] == "code"
    assert c.delete("/api/profile/trusted-devices/9999", headers=h).status_code == 404


def test_a_password_change_forgets_every_device(clock):
    c, secret = _enrolled(clock)
    r, _ = _verify(c, secret, clock, remember=True)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with patch("app.routers.profile_router.send_email"):
        changed = c.post(
            "/api/profile/password",
            json={"current_password": _PW, "new_password": "N3wStr0ngPass!", "new_password_confirmation": "N3wStr0ngPass!"},
            headers=h,
        )
    assert changed.status_code == 204
    with _Session() as db:
        assert db.query(TrustedDevice).count() == 0
        assert db.query(AuditLog).filter(AuditLog.action == "account.trust_device").count() == 1
