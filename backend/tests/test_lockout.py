"""
Account lockout and system parameters (task 37.5, Requirements 16.2, 16.8).
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-lockout-secret-0123456789abcdef-xyz"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import re  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AccountToken,
    AuditLog,
    Credential,
    RefreshToken,
    SystemSetting,
    User,
    UserPreference,
)
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
def _clean_db():
    with _Session() as db:
        for model in (SystemSetting, AccountToken, UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


def _device() -> TestClient:
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})


def _register(client: TestClient, username: str) -> int:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": _PW, "password_confirmation": _PW},
    )
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def _login(client: TestClient, username: str, password: str = _PW):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _user(user_id: int) -> User:
    with _Session() as db:
        return db.get(User, user_id)


def _fail(client: TestClient, username: str, times: int):
    sent = []
    with patch("app.routers.auth_router.send_email", side_effect=lambda m: sent.append(m) or True):
        for _ in range(times):
            r = _login(client, username, "Wr0ngPassword!")
            assert r.status_code == 401
            assert r.json()["detail"] == "Invalid credentials."
    return sent


@pytest.fixture()
def admin():
    device = _device()
    admin_id = _register(device, "boss")
    with _Session() as db:
        db.get(User, admin_id).role = "Admin"
        db.commit()
    r = _login(device, "boss")
    return device, {"Authorization": f"Bearer {r.json()['access_token']}"}, admin_id


def test_five_wrong_passwords_lock_the_account_and_email_a_link():
    c = _device()
    uid = _register(c, "alice")
    assert _fail(c, "alice", 4) == []
    assert _user(uid).locked_at is None and _user(uid).failed_attempts == 4

    sent = _fail(c, "alice", 1)
    assert len(sent) == 1 and sent[0].to == "alice@example.com"
    assert re.search(r"/unlock\?token=\S+", sent[0].body)
    assert _user(uid).locked_at is not None

    # The right password now says locked; more wrong ones send nothing more.
    r = _login(c, "alice")
    assert r.status_code == 423 and r.json()["detail"] == "Account locked."
    assert _fail(c, "alice", 3) == []


def test_a_right_password_resets_the_count():
    c = _device()
    uid = _register(c, "alice")
    _fail(c, "alice", 4)
    assert _login(c, "alice").status_code == 200
    _fail(c, "alice", 4)
    assert _user(uid).locked_at is None


def test_the_unlock_link_works_once():
    c = _device()
    uid = _register(c, "alice")
    sent = _fail(c, "alice", 5)
    token = re.search(r"/unlock\?token=(\S+)", sent[0].body).group(1)

    assert c.post("/api/auth/unlock", json={"token": token}).status_code == 200
    assert _user(uid).locked_at is None and _user(uid).failed_attempts == 0
    assert _login(c, "alice").status_code == 200
    assert c.post("/api/auth/unlock", json={"token": token}).status_code == 400
    assert c.post("/api/auth/unlock", json={"token": "made-up"}).status_code == 400


def test_the_admin_unlocks_and_sees_the_status(admin):
    device, headers, _ = admin
    c = _device()
    uid = _register(c, "alice")
    _fail(c, "alice", 5)

    rows = device.get("/api/admin/users", headers=headers).json()
    assert next(r for r in rows if r["username"] == "alice")["status"] == "locked"

    r = device.post(f"/api/admin/users/{uid}/unlock", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["locked_at"] is None
    assert _login(c, "alice").status_code == 200
    assert device.post(f"/api/admin/users/{uid}/unlock", headers=headers).status_code == 409
    actions = [row["action"] for row in device.get("/api/admin/audit", headers=headers).json()["items"]]
    assert "user.unlock" in actions


# ── System parameters ─────────────────────────────────────────────────────


def test_parameters_have_defaults_ranges_and_change_the_lockout(admin):
    device, headers, _ = admin
    params = {p["key"]: p for p in device.get("/api/admin/settings", headers=headers).json()}
    assert params["lockout_attempts"] == {
        "key": "lockout_attempts", "group": "security", "value": 5, "default": 5, "minimum": 3, "maximum": 20,
    }
    assert params["admin_reauth_minutes"]["value"] == 5

    r = device.put("/api/admin/settings", json={"lockout_attempts": 3}, headers=headers)
    assert r.status_code == 200
    assert next(p for p in r.json() if p["key"] == "lockout_attempts")["value"] == 3

    c = _device()
    uid = _register(c, "alice")
    assert len(_fail(c, "alice", 3)) == 1
    assert _user(uid).locked_at is not None

    audit = device.get("/api/admin/audit", params={"action": "settings.update"}, headers=headers).json()["items"]
    assert len(audit) == 1 and audit[0]["detail"] == "lockout_attempts"


def test_parameters_are_checked_before_any_is_saved(admin):
    device, headers, _ = admin
    for body in ({"lockout_attempts": 2}, {"lockout_attempts": 21}, {"nope": 5}, {"lockout_attempts": True}):
        r = device.put("/api/admin/settings", json={"session_idle_minutes": 30, **body}, headers=headers)
        assert r.status_code == 422, body
    values = {p["key"]: p["value"] for p in device.get("/api/admin/settings", headers=headers).json()}
    assert values["session_idle_minutes"] == 15


def test_only_the_admin_reads_or_changes_parameters():
    c = _device()
    _register(c, "alice")
    h = {"Authorization": f"Bearer {_login(c, 'alice').json()['access_token']}"}
    assert c.get("/api/admin/settings", headers=h).status_code == 403
    assert c.put("/api/admin/settings", json={"lockout_attempts": 3}, headers=h).status_code == 403
