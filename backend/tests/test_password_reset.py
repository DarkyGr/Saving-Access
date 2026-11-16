"""
Forgot password (task 37.5, Requirement 16.3): a one-time emailed link that
sets a new password, ends every session, lifts a lock and does not skip the
second step.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-password-reset-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import re  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
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
_NEW = "N3wStr0ngPass!"


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        for model in (RecoveryCode, SystemSetting, AccountToken, UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


def _device() -> TestClient:
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})


def _register(c: TestClient, username: str = "alice") -> int:
    r = c.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@Example.com", "password": _PW, "password_confirmation": _PW},
    )
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def _forgot(c: TestClient, account: str) -> list:
    sent = []
    with patch("app.routers.auth_router.send_email", side_effect=lambda m: sent.append(m) or True):
        r = c.post("/api/auth/forgot-password", json={"account": account})
    assert r.status_code == 202
    assert r.json() == {"detail": "If the account exists, a link was emailed."}
    return sent


def _token(email) -> str:
    return re.search(r"/reset-password\?token=(\S+)", email.body).group(1)


def _reset(c: TestClient, token: str, password: str = _NEW, confirm: str | None = None):
    with patch("app.routers.auth_router.send_email") as send:
        r = c.post(
            "/api/auth/reset-password",
            json={"token": token, "password": password, "password_confirmation": confirm or password},
        )
    return r, send


def test_the_answer_never_reveals_whether_the_account_exists():
    c = _device()
    _register(c)
    assert _forgot(c, "nobody") == []
    assert _forgot(c, "nobody@example.com") == []
    # Username or email (any case) both work.
    assert len(_forgot(c, "alice")) == 1
    assert len(_forgot(c, "ALICE@example.COM")) == 1


def test_the_link_sets_a_new_password_once_and_ends_every_session():
    c = _device()
    uid = _register(c)
    login = c.post("/api/auth/login", json={"username": "alice", "password": _PW})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    email = _forgot(c, "alice")[0]
    assert "1 hour" in email.body
    r, send = _reset(c, _token(email))
    assert r.status_code == 200
    assert send.call_args.args[0].subject == "Save-Pass: your password was changed"

    # No session is opened by the reset, and the old one is gone.
    assert c.get("/api/credentials", headers=headers).status_code == 401
    assert c.post("/api/auth/login", json={"username": "alice", "password": _PW}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "alice", "password": _NEW}).status_code == 200
    # Used once.
    assert _reset(c, _token(email), "An0therStr0ng!")[0].status_code == 400
    with _Session() as db:
        actions = [a.action for a in db.query(AuditLog).filter(AuditLog.user_id == uid)]
        assert "account.password_reset" in actions


def test_the_new_password_follows_the_rules_and_a_bad_try_keeps_the_link():
    c = _device()
    _register(c)
    token = _token(_forgot(c, "alice")[0])
    weak, _ = _reset(c, token, "short")
    assert weak.status_code == 400 and "password_errors" in weak.json()["detail"]
    mismatch, _ = _reset(c, token, _NEW, "N3wStr0ngPass?")
    assert mismatch.status_code == 400
    assert _reset(c, token)[0].status_code == 200


def test_expired_and_older_links_do_not_work():
    c = _device()
    _register(c)
    first = _token(_forgot(c, "alice")[0])
    second = _token(_forgot(c, "alice")[0])
    assert _reset(c, first)[0].status_code == 400  # a newer link retires it
    with _Session() as db:
        for row in db.query(AccountToken):
            row.expires_at = datetime(2020, 1, 1)
        db.commit()
    assert _reset(c, second)[0].status_code == 400


def test_a_reset_lifts_a_lock_but_not_a_deactivation():
    c = _device()
    uid = _register(c)
    with _Session() as db:
        db.get(User, uid).locked_at = datetime(2026, 1, 1)
        db.commit()
    assert _reset(c, _token(_forgot(c, "alice")[0]))[0].status_code == 200
    assert c.post("/api/auth/login", json={"username": "alice", "password": _NEW}).status_code == 200

    with _Session() as db:
        db.get(User, uid).deactivated_at = datetime(2026, 1, 1) + timedelta(days=1)
        db.commit()
    assert _forgot(c, "alice") == []


def test_the_second_step_is_still_needed(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_REQUIRED", "true")
    c = _device()
    _register(c)
    assert _reset(c, _token(_forgot(c, "alice")[0]))[0].status_code == 200
    r = c.post("/api/auth/login", json={"username": "alice", "password": _NEW})
    assert r.json()["mfa"] == "setup" and r.json()["access_token"] is None
