"""
Export my data and delete my account (task 35.8, Requirement 19).
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-account-data-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import csv  # noqa: E402
import io  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AccountToken,
    AuditLog,
    Credential,
    EmailVerificationToken,
    RecoveryCode,
    RefreshToken,
    SystemSetting,
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
def _clean_db():
    with _Session() as db:
        for model in (
            EmailVerificationToken, RecoveryCode, SystemSetting, AccountToken,
            UserPreference, RefreshToken, AuditLog, Credential, User,
        ):
            db.query(model).delete()
        db.commit()
    yield


def _signed_in(username: str = "alice", role: str = "User"):
    c = TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})
    r = c.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": _PW, "password_confirmation": _PW},
    )
    uid = r.json()["user_id"]
    with _Session() as db:
        db.get(User, uid).role = role
        db.commit()
    token = c.post("/api/auth/login", json={"username": username, "password": _PW}).json()["access_token"]
    return c, {"Authorization": f"Bearer {token}"}, uid


def _save(c, h, site, login, password):
    r = c.post(
        "/api/credentials",
        json={"website_name": site, "email_or_username": login, "is_username_login": "@" not in login,
              "password": password, "account_password": _PW},
        headers=h,
    )
    assert r.status_code == 201, r.text


def _export(c, h, **body):
    with patch("app.routers.profile_router.send_email") as send:
        r = c.post("/api/profile/export", json={"account_password": _PW, **body}, headers=h)
    return r, send


# ── Export ────────────────────────────────────────────────────────────────


def test_export_csv_has_every_credential_and_is_audited():
    c, h, uid = _signed_in()
    _save(c, h, "GitHub", "alice@example.com", "gh-Secret!1")
    _save(c, h, "=HYPERLINK(\"x\")", "alice", "=starts-with-equals")
    r, send = _export(c, h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0] == ["website_name", "email_or_username", "is_username_login", "password", "last_changed"]
    by_site = {row[0]: row for row in rows[1:]}
    assert by_site["GitHub"][1:4] == ["alice@example.com", "no", "gh-Secret!1"]
    # Names cannot run as formulas; the password stays exactly as saved.
    formula = by_site["'=HYPERLINK(\"x\")"]
    assert formula[3] == "=starts-with-equals"
    assert send.call_args.args[0].subject == "Save-Pass: your passwords were exported"
    with _Session() as db:
        row = db.query(AuditLog).filter(AuditLog.action == "account.export").one()
        assert row.user_id == uid and row.detail == "2 csv"


def test_export_json():
    c, h, _ = _signed_in()
    _save(c, h, "Bank", "alice", "B4nk-Secret!")
    r, _ = _export(c, h, format="json")
    body = r.json()
    assert body["credentials"][0]["password"] == "B4nk-Secret!"
    assert body["credentials"][0]["is_username_login"] is True


def test_export_needs_the_password_and_the_code_when_2fa_is_on():
    c, h, uid = _signed_in()
    assert c.post("/api/profile/export", json={"account_password": "Wr0ngPassword!"}, headers=h).status_code == 401
    # Turn 2FA on for this account.
    secret = c.post("/api/profile/2fa/setup", json={"account_password": _PW}, headers=h).json()["secret"]
    with patch("app.routers.profile_router.send_email"):
        c.post("/api/profile/2fa/confirm", json={"code": totp.code_at(secret, totp.current_step())}, headers=h)
    assert _export(c, h)[0].status_code == 400
    code = totp.code_at(secret, totp.current_step() + 1)
    with patch("app.utils.totp.time.time", return_value=(totp.current_step() + 1) * 30 + 1):
        assert _export(c, h, code=code)[0].status_code == 200


# ── Delete ────────────────────────────────────────────────────────────────


def _delete(c, h, **body):
    with patch("app.routers.profile_router.send_email") as send:
        r = c.post("/api/profile/account/delete", json={"account_password": _PW, **body}, headers=h)
    return r, send


def test_delete_erases_personal_data_and_keeps_an_anonymous_row():
    c, h, uid = _signed_in()
    _save(c, h, "GitHub", "alice@example.com", "gh-Secret!1")
    assert _delete(c, h, confirm_username="Alice")[0].status_code == 400
    r, send = _delete(c, h, confirm_username="alice")
    assert r.status_code == 204
    assert send.call_args.args[0].to == "alice@example.com"

    with _Session() as db:
        user = db.get(User, uid)
        assert user.deleted_at is not None
        assert user.username.startswith("deleted-SP-") and "alice" not in user.email
        assert db.query(Credential).filter(Credential.user_id == uid).count() == 0
        assert db.query(RefreshToken).filter(RefreshToken.user_id == uid).count() == 0
        actions = [a.action for a in db.query(AuditLog).filter(AuditLog.user_id == uid)]
        assert "credential.create" in actions and "account.delete" in actions

    # Signed out at once, cannot sign in, and the name and email are free again.
    assert c.get("/api/credentials", headers=h).status_code == 401
    assert c.post("/api/auth/login", json={"username": "alice", "password": _PW}).status_code == 401
    again = c.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": _PW, "password_confirmation": _PW},
    )
    assert again.status_code == 201


def test_the_admin_list_hides_deleted_accounts_and_the_last_admin_stays():
    admin, ah, admin_id = _signed_in("boss", "Admin")
    c, h, uid = _signed_in("alice")
    _delete(c, h, confirm_username="alice")
    names = [u["username"] for u in admin.get("/api/admin/users", headers=ah).json()]
    assert names == ["boss"]
    assert admin.post(f"/api/admin/users/{uid}/unlock", headers=ah).status_code == 404

    r, _ = _delete(admin, ah, confirm_username="boss")
    assert r.status_code == 409 and r.json()["detail"] == "The last Admin cannot delete their account."
