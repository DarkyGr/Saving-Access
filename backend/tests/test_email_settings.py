"""
Email settings in System parameters (task 37.5, Requirement 16.8): sign-up
email verification on/off and outgoing SMTP with a write-only password and a
test button.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-email-settings-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

from unittest.mock import MagicMock, patch  # noqa: E402

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
from app.services import system_settings  # noqa: E402
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
SMTP = {"host": "mail.example.com", "port": 465, "security": "ssl", "username": "vault", "from_address": "vault@example.com"}


def _wipe():
    with _Session() as db:
        for model in (
            EmailVerificationToken, RecoveryCode, SystemSetting, AccountToken,
            UserPreference, RefreshToken, AuditLog, Credential, User,
        ):
            db.query(model).delete()
        db.commit()
        system_settings.refresh_cache(db, force=True)


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    monkeypatch.delenv("EMAIL_VERIFICATION_ENABLED", raising=False)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    _wipe()
    yield
    _wipe()  # never leave settings cached for other test modules


@pytest.fixture()
def admin():
    c = TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})
    r = c.post(
        "/api/auth/register",
        json={"username": "boss", "email": "boss@example.com", "password": _PW, "password_confirmation": _PW},
    )
    with _Session() as db:
        db.get(User, r.json()["user_id"]).role = "Admin"
        db.commit()
    token = c.post("/api/auth/login", json={"username": "boss", "password": _PW}).json()["access_token"]
    return c, {"Authorization": f"Bearer {token}"}


def test_defaults_follow_the_environment(admin):
    c, h = admin
    body = c.get("/api/admin/settings/email", headers=h).json()
    assert body["email_verification"] is False
    assert body["smtp"]["configured"] is False and body["smtp"]["has_password"] is False
    assert body["environment_backend"] == "console"


def test_the_smtp_password_is_encrypted_and_never_shown(admin):
    c, h = admin
    r = c.put("/api/admin/settings/email", json={"smtp": {**SMTP, "password": "Sm7pSecret!"}}, headers=h)
    assert r.status_code == 200
    assert "Sm7pSecret" not in r.text
    assert r.json()["smtp"] == {**SMTP, "has_password": True, "configured": True}
    with _Session() as db:
        stored = db.get(SystemSetting, "smtp").value
        assert "Sm7pSecret" not in stored

    # Saving again without a password keeps it; clear_password removes it.
    r = c.put("/api/admin/settings/email", json={"smtp": {**SMTP, "port": 587, "security": "starttls"}}, headers=h)
    assert r.json()["smtp"]["has_password"] is True and r.json()["smtp"]["port"] == 587
    r = c.put("/api/admin/settings/email", json={"smtp": {**SMTP, "clear_password": True}}, headers=h)
    assert r.json()["smtp"]["has_password"] is False

    # An empty host removes the SMTP: the environment decides again.
    r = c.put("/api/admin/settings/email", json={"smtp": {"host": ""}}, headers=h)
    assert r.json()["smtp"]["configured"] is False


def test_bad_values_are_refused(admin):
    c, h = admin
    no_sender = {**SMTP, "from_address": ""}
    assert c.put("/api/admin/settings/email", json={"smtp": no_sender}, headers=h).status_code == 422
    bad_port = {**SMTP, "port": 70000}
    assert c.put("/api/admin/settings/email", json={"smtp": bad_port}, headers=h).status_code == 422
    bad_security = {**SMTP, "security": "tls9"}
    assert c.put("/api/admin/settings/email", json={"smtp": bad_security}, headers=h).status_code == 422


def test_verification_needs_the_public_address_and_then_applies(admin, monkeypatch):
    c, h = admin
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    r = c.put("/api/admin/settings/email", json={"email_verification": True}, headers=h)
    assert r.status_code == 422 and r.json()["detail"] == "APP_BASE_URL is not set on the server."

    monkeypatch.setenv("APP_BASE_URL", "https://vault.example.com")
    r = c.put("/api/admin/settings/email", json={"email_verification": True}, headers=h)
    assert r.status_code == 200 and r.json()["email_verification"] is True
    assert c.get("/api/auth/config").json()["email_verification"] is True

    # New sign-ups now get a verification link.
    with patch("app.routers.auth_router.send_email") as send:
        c.post(
            "/api/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": _PW, "password_confirmation": _PW},
        )
    assert "/verify-email?token=" in send.call_args.args[0].body
    audit = c.get("/api/admin/audit", params={"action": "settings.update"}, headers=h).json()["items"]
    assert audit[0]["detail"] == "email_verification"


def test_the_test_button_uses_the_saved_smtp(admin):
    c, h = admin
    c.put("/api/admin/settings/email", json={"smtp": {**SMTP, "password": "Sm7pSecret!"}}, headers=h)
    server = MagicMock()
    server.__enter__.return_value = server
    with patch("app.services.email_sender.smtplib.SMTP_SSL", return_value=server) as smtp_ssl:
        r = c.post("/api/admin/settings/email/test", json={}, headers=h)
    assert r.json() == {"ok": True, "backend": "smtp", "error": None}
    assert smtp_ssl.call_args.args[:2] == ("mail.example.com", 465)
    server.login.assert_called_once_with("vault", "Sm7pSecret!")
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == "boss@example.com" and sent["From"] == "vault@example.com"


def test_the_test_button_reports_a_failure(admin):
    c, h = admin
    c.put("/api/admin/settings/email", json={"smtp": {**SMTP, "port": 2525, "security": "none"}}, headers=h)
    with patch("app.services.email_sender.smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
        r = c.post("/api/admin/settings/email/test", json={"to": "someone@example.com"}, headers=h)
    assert r.json()["ok"] is False and r.json()["error"].startswith("ConnectionRefusedError")


def test_only_the_admin(admin):
    c, _ = admin
    c.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": _PW, "password_confirmation": _PW},
    )
    token = c.post("/api/auth/login", json={"username": "alice", "password": _PW}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert c.get("/api/admin/settings/email", headers=h).status_code == 403
    assert c.post("/api/admin/settings/email/test", json={}, headers=h).status_code == 403
