"""
Two-factor authentication (task 37.5, Requirement 16.1–16.2, 16.7): TOTP,
recovery codes, the mandatory setup at sign-in, lockout by wrong codes,
settings and the Admin's reset.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-two-factor-secret-0123456789abcdef-xyz"
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
    User,
    UserPreference,
)
from app.security import SettingsError, validate_settings  # noqa: E402
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
        for model in (RecoveryCode, SystemSetting, AccountToken, UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


class Clock:
    """Moves TOTP time forward so each test code is a new step."""

    def __init__(self):
        self.now = time.time()

    def tick(self):
        self.now += totp.STEP_SECONDS
        return self.now


@pytest.fixture()
def clock():
    c = Clock()
    with patch("app.utils.totp.time.time", lambda: c.now):
        yield c


def _device() -> TestClient:
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})


def _register(client: TestClient, username: str = "alice") -> int:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": _PW, "password_confirmation": _PW},
    )
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def _password(client: TestClient, username: str = "alice", password: str = _PW):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _enroll(client: TestClient, clock: Clock, username: str = "alice") -> tuple[str, list[str], dict]:
    """First sign-in: set 2FA up. Returns (secret, recovery codes, auth headers)."""
    first = _password(client, username).json()
    assert first["mfa"] == "setup" and first["access_token"] is None
    setup = client.post("/api/auth/2fa/setup", json={"mfa_token": first["mfa_token"]}).json()
    code = totp.code_at(setup["secret"], totp.current_step(clock.now))
    with patch("app.routers.auth_router.send_email"):
        done = client.post("/api/auth/2fa/confirm", json={"mfa_token": first["mfa_token"], "code": code})
    assert done.status_code == 200, done.text
    body = done.json()
    return setup["secret"], body["recovery_codes"], {"Authorization": f"Bearer {body['access_token']}"}


def _code(secret: str, clock: Clock) -> str:
    return totp.code_at(secret, totp.current_step(clock.tick()))


# ── TOTP itself ───────────────────────────────────────────────────────────


def test_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.code_at(secret, 1234567890 // 30) == "005924"


def test_codes_are_accepted_once_and_within_one_step():
    secret = totp.new_secret()
    now = 1_700_000_000.0
    step = totp.current_step(now)
    assert totp.matching_step(secret, totp.code_at(secret, step - 1), after=None, now=now) == step - 1
    assert totp.matching_step(secret, totp.code_at(secret, step - 2), after=None, now=now) is None
    assert totp.matching_step(secret, totp.code_at(secret, step), after=step, now=now) is None
    assert totp.matching_step(secret, "12345", after=None, now=now) is None


# ── Mandatory setup at sign-in ────────────────────────────────────────────


def test_first_sign_in_sets_two_factor_up(clock):
    c = _device()
    _register(c)
    first = _password(c).json()
    assert first["mfa"] == "setup"
    assert "sp_refresh" not in c.cookies
    # The challenge is not an access token.
    assert c.get("/api/credentials", headers={"Authorization": f"Bearer {first['mfa_token']}"}).status_code == 401

    setup = c.post("/api/auth/2fa/setup", json={"mfa_token": first["mfa_token"]}).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/Save-Pass%3Aalice?secret=")
    wrong = c.post("/api/auth/2fa/confirm", json={"mfa_token": first["mfa_token"], "code": "000000"})
    assert wrong.status_code == 400

    code = totp.code_at(setup["secret"], totp.current_step(clock.now))
    with patch("app.routers.auth_router.send_email") as send:
        done = c.post("/api/auth/2fa/confirm", json={"mfa_token": first["mfa_token"], "code": code})
    body = done.json()
    assert done.status_code == 200 and body["access_token"]
    assert len(body["recovery_codes"]) == 10 and len(set(body["recovery_codes"])) == 10
    assert all(len(code) == 11 and code[5] == "-" for code in body["recovery_codes"])
    assert "sp_refresh" in c.cookies
    assert "two-step" in send.call_args.args[0].subject.lower()

    with _Session() as db:
        user = db.query(User).one()
        # Encrypted at rest: the plain secret is not in the column.
        assert setup["secret"].encode() not in user.totp_secret
        assert db.query(RecoveryCode).count() == 10
        assert not any(c.encode() in r.code_hash.encode() for r in db.query(RecoveryCode) for c in body["recovery_codes"])

    me = c.get("/api/profile/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me["two_factor"]["enabled"] is True and me["two_factor"]["recovery_codes_left"] == 10


def test_sign_in_asks_for_a_code_and_rejects_a_replay(clock):
    c = _device()
    _register(c)
    secret, _, _ = _enroll(c, clock)

    challenge = _password(c).json()
    assert challenge["mfa"] == "code"
    code = _code(secret, clock)
    ok = c.post("/api/auth/login/verify", json={"mfa_token": challenge["mfa_token"], "code": code})
    assert ok.status_code == 200 and ok.json()["access_token"]
    again = c.post("/api/auth/login/verify", json={"mfa_token": challenge["mfa_token"], "code": code})
    assert again.status_code == 401 and again.json()["detail"] == "Invalid code."

    # A wrong password never reaches the second step.
    assert _password(c, password="Wr0ngPassword!").status_code == 401


def test_a_recovery_code_works_once_and_says_how_many_are_left(clock):
    c = _device()
    _register(c)
    _, codes, _ = _enroll(c, clock)

    token = _password(c).json()["mfa_token"]
    r = c.post("/api/auth/login/verify", json={"mfa_token": token, "code": codes[0].lower().replace("-", " ")})
    assert r.status_code == 200 and r.json()["recovery_codes_left"] == 9
    token = _password(c).json()["mfa_token"]
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": codes[0]}).status_code == 401


def test_wrong_codes_lock_and_a_valid_code_unlocks(clock):
    c = _device()
    uid = _register(c)
    secret, _, _ = _enroll(c, clock)

    token = _password(c).json()["mfa_token"]
    sent = []
    with patch("app.routers.auth_router.send_email", side_effect=lambda m: sent.append(m) or True):
        for _ in range(5):
            assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": "000000"}).status_code == 401
    assert len(sent) == 1 and "/unlock?token=" in sent[0].body
    with _Session() as db:
        assert db.get(User, uid).locked_at is not None

    # Locked, the right password still opens the code step; a valid code unlocks.
    token = _password(c).json()["mfa_token"]
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": _code(secret, clock)}).status_code == 200
    with _Session() as db:
        user = db.get(User, uid)
        assert user.locked_at is None and user.failed_attempts == 0


# ── Settings ──────────────────────────────────────────────────────────────


def test_new_recovery_codes_need_password_and_a_current_code(clock):
    c = _device()
    _register(c)
    secret, old, headers = _enroll(c, clock)

    bad = c.post("/api/profile/2fa/recovery-codes", json={"account_password": "Wr0ngPassword!", "code": _code(secret, clock)}, headers=headers)
    assert bad.status_code == 401
    # A recovery code is not accepted here (and is not used up).
    rec = c.post("/api/profile/2fa/recovery-codes", json={"account_password": _PW, "code": old[0]}, headers=headers)
    assert rec.status_code == 400
    with patch("app.routers.profile_router.send_email") as send:
        r = c.post("/api/profile/2fa/recovery-codes", json={"account_password": _PW, "code": _code(secret, clock)}, headers=headers)
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
    assert send.call_args.args[0].subject == "Save-Pass: new recovery codes"

    token = _password(c).json()["mfa_token"]
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": old[1]}).status_code == 401
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": r.json()["recovery_codes"][0]}).status_code == 200


def test_a_new_device_replaces_the_old_one_only_when_confirmed(clock):
    c = _device()
    _register(c)
    old_secret, _, headers = _enroll(c, clock)

    start = c.post("/api/profile/2fa/setup", json={"account_password": _PW}, headers=headers)
    assert start.status_code == 200
    new_secret = start.json()["secret"]
    # Not confirmed yet: the old device still signs in.
    token = _password(c).json()["mfa_token"]
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": _code(old_secret, clock)}).status_code == 200

    with patch("app.routers.profile_router.send_email"):
        done = c.post("/api/profile/2fa/confirm", json={"code": _code(new_secret, clock)}, headers=headers)
    assert done.status_code == 200
    token = _password(c).json()["mfa_token"]
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": _code(old_secret, clock)}).status_code == 401
    assert c.post("/api/auth/login/verify", json={"mfa_token": token, "code": _code(new_secret, clock)}).status_code == 200


# ── Admin reset ───────────────────────────────────────────────────────────


def test_the_admin_resets_two_factor(clock):
    admin_device = _device()
    admin_id = _register(admin_device, "boss")
    with _Session() as db:
        db.get(User, admin_id).role = "Admin"
        db.commit()
    _, _, admin_headers = _enroll(admin_device, clock, "boss")

    c = _device()
    uid = _register(c)
    _, _, headers = _enroll(c, clock)
    rows = admin_device.get("/api/admin/users", headers=admin_headers).json()
    assert next(r for r in rows if r["username"] == "alice")["two_factor"] is True

    with patch("app.routers.admin_router.send_email") as send:
        r = admin_device.post(f"/api/admin/users/{uid}/reset-2fa", headers=admin_headers)
    assert r.status_code == 200 and r.json()["two_factor"] is False
    assert send.call_args.args[0].to == "alice@example.com"
    # Sessions end; the next sign-in sets it up again.
    assert c.get("/api/credentials", headers=headers).status_code == 401
    assert _password(c).json()["mfa"] == "setup"
    assert admin_device.post(f"/api/admin/users/{uid}/reset-2fa", headers=admin_headers).status_code == 409


def test_production_refuses_to_turn_the_second_factor_off(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TWO_FACTOR_REQUIRED", "false")
    with pytest.raises(SettingsError, match="TWO_FACTOR_REQUIRED"):
        validate_settings()


def test_cli_resets_two_factor_for_a_lost_phone(clock, capsys):
    from argparse import Namespace

    from app import cli

    c = _device()
    uid = _register(c)
    _enroll(c, clock)
    with _Session() as db:
        db.get(User, uid).locked_at = datetime(2026, 1, 1)
        db.commit()
    with patch.object(cli, "SessionLocal", _Session):
        cli.cmd_reset_two_factor(Namespace(username="alice"))
    assert "was reset" in capsys.readouterr().out
    with _Session() as db:
        user = db.get(User, uid)
        assert user.totp_secret is None and user.locked_at is None
        assert db.query(RecoveryCode).filter(RecoveryCode.user_id == uid).count() == 0
    assert _password(c).json()["mfa"] == "setup"

