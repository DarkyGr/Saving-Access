"""
Spec Phase 2 (task 33): email verification, 30-day deactivation and CAPTCHA.

Requirements 1.9, 1.10, 2.6–2.9.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-phase2-verification-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import cli, security  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    Credential,
    EmailVerificationToken,
    RefreshToken,
    User,
)
from app.rate_limit import limiter  # noqa: E402
from app.services import captcha_service, email_sender  # noqa: E402
from app.services.email_sender import OutgoingEmail  # noqa: E402
from tests.conftest import make_test_engine  # noqa: E402

_ENGINE = make_test_engine()
_Session = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)

def utc_today():
    """Today as the app records it: UTC (task 32.3), not the machine's local date."""
    from app.utils.audit_columns import utc_date_time

    return utc_date_time()[0]


def _override_get_db():
    db: Session = _Session()
    try:
        yield db
    finally:
        db.close()


_PW = "Str0ngPassw0rd!"
_BASE = "https://vault.example.test"


@pytest.fixture()
def client():
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        for model in (
            EmailVerificationToken,
            RefreshToken,
            AuditLog,
            Credential,
            User,
        ):
            db.query(model).delete()
        db.commit()
    yield


@pytest.fixture()
def outbox(monkeypatch, tmp_path) -> Path:
    """Email verification on, emails written as JSON files to *tmp_path*."""
    monkeypatch.setenv("EMAIL_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("APP_BASE_URL", _BASE + "/")
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("EMAIL_OUTBOX_DIR", str(tmp_path))
    return tmp_path


def _emails(outbox: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(outbox.glob("*.json"))]


def _token_from(email: dict) -> str:
    match = re.search(re.escape(_BASE) + r"/verify-email\?token=([\w-]+)", email["body"])
    assert match, email["body"]
    return match.group(1)


def _register(client: TestClient, username: str = "alice", **extra) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": _PW,
            "password_confirmation": _PW,
            **extra,
        },
    )
    assert r.status_code == 201, r.text


def _login(client: TestClient, username: str = "alice", password: str = _PW, **extra):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password, **extra}
    )


def _auth(client: TestClient, username: str = "alice") -> dict:
    r = _login(client, username)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _user(username: str = "alice") -> User:
    with _Session() as db:
        user = db.query(User).filter(User.username == username).one()
        db.expunge(user)
        return user


def _set_deadline(deadline: date | None, username: str = "alice") -> None:
    with _Session() as db:
        db.query(User).filter(User.username == username).update(
            {User.deactivation_deadline: deadline}
        )
        db.commit()


# ── Feature off (default) ────────────────────────────────────────────────────


def test_config_defaults_to_everything_off(client):
    r = client.get("/api/auth/config")
    assert r.status_code == 200
    assert r.json() == {"captcha_site_key": None, "email_verification": False}


def test_disabled_keeps_mvp_behaviour(client, tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("EMAIL_OUTBOX_DIR", str(tmp_path))
    _register(client)
    assert _user().deactivation_deadline is None
    assert _emails(tmp_path) == []

    r = _login(client)
    assert r.status_code == 200
    assert r.json()["email_verification_required"] is False
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.post("/api/auth/verify-email", json={"token": "x"}).status_code == 404
    assert client.post("/api/profile/verification-email", headers=headers).status_code == 404


def test_old_deadline_is_ignored_while_disabled(client):
    _register(client)
    _set_deadline(utc_today() - timedelta(days=5))
    assert _login(client).status_code == 200


# ── 1.9 / 1.10 Sign-up ───────────────────────────────────────────────────────


def test_signup_sets_deadline_and_sends_email(client, outbox):
    _register(client)
    user = _user()
    assert user.email_verified is False
    assert user.deactivation_deadline == user.creation_date + timedelta(days=30)

    emails = _emails(outbox)
    assert len(emails) == 1
    assert emails[0]["to"] == "alice@example.com"
    assert "Verify" in emails[0]["subject"]
    assert user.deactivation_deadline.isoformat() in emails[0]["body"]
    _token_from(emails[0])

    with _Session() as db:
        row = db.query(EmailVerificationToken).one()
        # Only the hash is stored.
        assert row.token_hash != _token_from(emails[0])
        assert len(row.token_hash) == 64


def test_signup_email_follows_ui_language(client, outbox):
    _register(client, language="es")
    assert _emails(outbox)[0]["subject"].startswith("Verifica")


def test_signup_succeeds_when_email_delivery_fails(client, outbox, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.invalid")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    with patch.object(email_sender, "_send_smtp", side_effect=OSError("down")):
        _register(client)
    assert _user().email_verified is False


def test_config_reports_verification_on(client, outbox):
    assert client.get("/api/auth/config").json()["email_verification"] is True


# ── 2.7 Login of an unverified account ───────────────────────────────────────


def test_unverified_login_is_allowed_and_flagged(client, outbox):
    _register(client)
    r = _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["email_verification_required"] is True
    assert body["deactivation_deadline"] == _user().deactivation_deadline.isoformat()


def test_verification_link_verifies_once(client, outbox):
    _register(client)
    token = _token_from(_emails(outbox)[0])

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert _user().email_verified is True
    assert _login(client).json()["email_verification_required"] is False

    again = client.post("/api/auth/verify-email", json={"token": token})
    assert again.status_code == 400
    assert again.json()["detail"] == "Invalid or expired verification link."


def test_unknown_and_expired_links_are_rejected(client, outbox):
    _register(client)
    token = _token_from(_emails(outbox)[0])
    assert client.post("/api/auth/verify-email", json={"token": "nope"}).status_code == 400

    with _Session() as db:
        row = db.query(EmailVerificationToken).one()
        row.expires_at = row.expires_at - timedelta(days=3)
        db.commit()
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400
    assert _user().email_verified is False


# ── 2.8 Resend ───────────────────────────────────────────────────────────────


def test_resend_sends_new_link_and_keeps_deadline(client, outbox):
    _register(client)
    deadline = _user().deactivation_deadline
    headers = _auth(client)

    r = client.post(
        "/api/profile/verification-email", json={"language": "es"}, headers=headers
    )
    assert r.status_code == 202, r.text
    emails = _emails(outbox)
    assert len(emails) == 2
    assert emails[1]["subject"].startswith("Verifica")
    assert _user().deactivation_deadline == deadline

    first, second = _token_from(emails[0]), _token_from(emails[1])
    assert first != second
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200
    assert _user().deactivation_deadline == deadline


def test_resend_without_body_and_when_already_verified(client, outbox):
    _register(client)
    headers = _auth(client)
    assert client.post("/api/profile/verification-email", headers=headers).status_code == 202
    client.post("/api/auth/verify-email", json={"token": _token_from(_emails(outbox)[0])})
    r = client.post("/api/profile/verification-email", headers=headers)
    assert r.status_code == 409


def test_resend_requires_authentication(client, outbox):
    assert client.post("/api/profile/verification-email").status_code == 401


def test_resend_is_rate_limited_per_user(client, outbox):
    _register(client)
    headers = _auth(client)
    limiter.reset()
    limiter.enabled = True
    try:
        codes = [
            client.post("/api/profile/verification-email", headers=headers).status_code
            for _ in range(4)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes == [202, 202, 202, 429]


# ── 2.9 Deactivation ─────────────────────────────────────────────────────────


def test_deadline_day_itself_is_still_active(client, outbox):
    _register(client)
    _set_deadline(utc_today())
    assert _login(client).status_code == 200


def test_unverified_past_deadline_cannot_log_in(client, outbox):
    _register(client)
    _set_deadline(utc_today() - timedelta(days=1))

    r = _login(client)
    assert r.status_code == 403
    assert r.json()["detail"] == "Account deactivated."
    # A wrong password still gets the generic error: no account-state leak.
    wrong = _login(client, password="Wr0ngPassword!")
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid credentials."


def test_deactivated_account_cannot_use_old_link(client, outbox):
    _register(client)
    token = _token_from(_emails(outbox)[0])
    _set_deadline(utc_today() - timedelta(days=1))
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 403
    assert _user().email_verified is False


def test_open_session_ends_when_deadline_passes(client, outbox):
    _register(client)
    headers = _auth(client)
    assert client.post("/api/auth/refresh").status_code == 200

    _set_deadline(utc_today() - timedelta(days=1))
    assert client.post("/api/auth/refresh").status_code == 401
    assert client.post("/api/profile/verification-email", headers=headers).status_code == 403


def test_verified_account_is_never_deactivated(client, outbox):
    _register(client)
    client.post("/api/auth/verify-email", json={"token": _token_from(_emails(outbox)[0])})
    _set_deadline(utc_today() - timedelta(days=100))
    assert _login(client).status_code == 200


def test_cli_verify_email_reactivates(client, outbox, capsys):
    _register(client)
    _set_deadline(utc_today() - timedelta(days=1))
    with patch.object(cli, "SessionLocal", _Session):
        cli.cmd_verify_email(argparse.Namespace(username="alice"))
    assert "verified" in capsys.readouterr().out
    user = _user()
    assert user.email_verified is True
    assert user.modification_user_id == user.user_id
    assert _login(client).status_code == 200


def test_cli_verify_email_unknown_user(outbox):
    with patch.object(cli, "SessionLocal", _Session), pytest.raises(SystemExit):
        cli.cmd_verify_email(argparse.Namespace(username="ghost"))


# ── 2.6 CAPTCHA ──────────────────────────────────────────────────────────────


@pytest.fixture()
def captcha(monkeypatch):
    monkeypatch.setenv("HCAPTCHA_SITE_KEY", "site-key-123")
    monkeypatch.setenv("HCAPTCHA_SECRET", "secret-456")


def test_config_exposes_site_key_only(client, captcha):
    body = client.get("/api/auth/config").json()
    assert body["captcha_site_key"] == "site-key-123"
    assert "secret-456" not in json.dumps(body)


def test_login_requires_captcha_when_configured(client, captcha):
    _register(client)
    r = _login(client)  # no token: rejected without calling hCaptcha
    assert r.status_code == 400
    assert r.json()["detail"] == "CAPTCHA verification failed."

    with patch("app.routers.auth_router.verify_captcha", return_value=False) as check:
        assert _login(client, captcha_token="bad").status_code == 400
    check.assert_called_once()
    assert check.call_args.args[0] == "bad"

    with patch("app.routers.auth_router.verify_captcha", return_value=True):
        assert _login(client, captcha_token="good").status_code == 200


def test_captcha_runs_before_password_check(client, captcha):
    with (
        patch("app.routers.auth_router.verify_captcha", return_value=False),
        patch("app.services.auth_service.AuthService.login") as login,
    ):
        assert _login(client, captcha_token="x").status_code == 400
    login.assert_not_called()


def test_login_without_captcha_config_ignores_token(client):
    _register(client)
    assert _login(client, captcha_token="anything").status_code == 200


def _fake_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


def test_verify_captcha_calls_hcaptcha(captcha):
    with patch.object(
        captcha_service.urllib.request, "urlopen", return_value=_fake_response({"success": True})
    ) as urlopen:
        assert captcha_service.verify_captcha("tok", "203.0.113.9") is True
    url = urlopen.call_args.args[0]
    data = urlopen.call_args.kwargs["data"].decode()
    assert url == "https://api.hcaptcha.com/siteverify"
    assert "secret=secret-456" in data and "response=tok" in data and "remoteip=203.0.113.9" in data


@pytest.mark.parametrize(
    "outcome",
    [{"success": False}, {"success": "true"}, {}, OSError("timeout"), ValueError("bad json")],
)
def test_verify_captcha_fails_closed(captcha, outcome):
    kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {
        "return_value": _fake_response(outcome)
    }
    with patch.object(captcha_service.urllib.request, "urlopen", **kwargs):
        assert captcha_service.verify_captcha("tok") is False


def test_verify_captcha_without_token_skips_network(captcha):
    with patch.object(captcha_service.urllib.request, "urlopen") as urlopen:
        assert captcha_service.verify_captcha(None) is False
        assert captcha_service.verify_captcha("") is False
    urlopen.assert_not_called()


# ── Settings validation ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "env, fragment",
    [
        ({"HCAPTCHA_SITE_KEY": "only-site"}, "HCAPTCHA_SECRET"),
        ({"HCAPTCHA_SECRET": "only-secret"}, "HCAPTCHA_SECRET"),
        ({"EMAIL_VERIFICATION_ENABLED": "true"}, "APP_BASE_URL"),
        (
            {"EMAIL_VERIFICATION_ENABLED": "true", "APP_BASE_URL": _BASE, "EMAIL_BACKEND": "pigeon"},
            "EMAIL_BACKEND",
        ),
        (
            {"EMAIL_VERIFICATION_ENABLED": "true", "APP_BASE_URL": _BASE, "EMAIL_BACKEND": "smtp"},
            "SMTP_HOST",
        ),
        (
            {"EMAIL_VERIFICATION_ENABLED": "true", "APP_BASE_URL": _BASE, "EMAIL_BACKEND": "file"},
            "EMAIL_OUTBOX_DIR",
        ),
    ],
)
def test_validate_settings_rejects_incomplete_phase2_config(monkeypatch, env, fragment):
    for name in (
        "HCAPTCHA_SITE_KEY", "HCAPTCHA_SECRET", "EMAIL_VERIFICATION_ENABLED",
        "APP_BASE_URL", "EMAIL_BACKEND", "SMTP_HOST", "SMTP_FROM", "EMAIL_OUTBOX_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(security.SettingsError, match=fragment):
        security.validate_settings()


def test_validate_settings_accepts_complete_phase2_config(monkeypatch):
    monkeypatch.setenv("HCAPTCHA_SITE_KEY", "s")
    monkeypatch.setenv("HCAPTCHA_SECRET", "t")
    monkeypatch.setenv("EMAIL_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("APP_BASE_URL", _BASE)
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    security.validate_settings()


# ── SMTP backend ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("security_mode", ["starttls", "ssl", "none"])
def test_smtp_backend(monkeypatch, security_mode):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM", "Save-Pass <noreply@example.test>")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("SMTP_SECURITY", security_mode)
    target = "SMTP_SSL" if security_mode == "ssl" else "SMTP"
    with patch.object(email_sender.smtplib, target) as smtp_cls:
        ok = email_sender.send_email(OutgoingEmail("bob@example.com", "Hi", "Body"))
    assert ok is True
    server = smtp_cls.return_value
    assert smtp_cls.call_args.args[:2] == ("smtp.example.test", 2525)
    assert server.starttls.called is (security_mode == "starttls")
    server.login.assert_called_once_with("mailer", "pw")
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == "bob@example.com" and sent["Subject"] == "Hi"


def test_console_backend_prints(monkeypatch, capsys):
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    assert email_sender.send_email(OutgoingEmail("bob@example.com", "Hi", "Body")) is True
    assert "bob@example.com" in capsys.readouterr().out


# ── 34.4 Deadline reminders ──────────────────────────────────────────────────

from app.services.email_verification_service import EmailVerificationService  # noqa: E402


def _remind(today: date | None = None, **kwargs) -> list[str]:
    with _Session() as db:
        return EmailVerificationService(db).send_due_reminders(today or utc_today(), **kwargs)


def test_signup_and_resend_store_the_ui_language(client, outbox):
    _register(client, language="es-ES")
    assert _user().preferred_language == "es"
    client.post("/api/profile/verification-email", json={"language": "en"}, headers=_auth(client))
    assert _user().preferred_language == "en"


def test_reminders_at_seven_and_one_day_once_each(client, outbox):
    _register(client, language="es")
    deadline = _user().deactivation_deadline
    sent = len(_emails(outbox))

    assert _remind(deadline - timedelta(days=8)) == []
    assert _remind(deadline - timedelta(days=7)) == ["alice"]
    assert _user().last_verification_reminder_days == 7
    assert _remind(deadline - timedelta(days=6)) == []  # same stage: once
    assert _remind(deadline - timedelta(days=1)) == ["alice"]
    assert _remind(deadline) == []
    assert _user().last_verification_reminder_days == 1

    reminders = _emails(outbox)[sent:]
    assert len(reminders) == 2
    assert all(e["subject"].startswith("Recordatorio") for e in reminders)
    assert deadline.isoformat() in reminders[0]["body"]
    # Each reminder carries a working link, and the deadline never moves.
    assert client.post("/api/auth/verify-email", json={"token": _token_from(reminders[1])}).status_code == 200
    assert _user().deactivation_deadline == deadline


def test_missed_stage_sends_only_the_latest(client, outbox):
    _register(client)
    deadline = _user().deactivation_deadline
    assert _remind(deadline) == ["alice"]  # job did not run at 7 days
    assert _user().last_verification_reminder_days == 1
    assert _emails(outbox)[-1]["subject"].startswith("Reminder")


def test_no_reminders_for_verified_deactivated_or_grandfathered(client, outbox):
    for name in ("verified", "expired", "legacy"):
        _register(client, name)
    client.post("/api/auth/verify-email", json={"token": _token_from(_emails(outbox)[0])})
    _set_deadline(utc_today() - timedelta(days=1), "expired")
    _set_deadline(None, "legacy")
    _set_deadline(utc_today() + timedelta(days=1), "verified")
    assert _remind() == []


def test_dry_run_sends_and_changes_nothing(client, outbox):
    _register(client)
    _set_deadline(utc_today() + timedelta(days=3))
    sent = len(_emails(outbox))
    assert _remind(dry_run=True) == ["alice"]
    assert len(_emails(outbox)) == sent
    assert _user().last_verification_reminder_days is None


def test_failed_reminder_is_retried(client, outbox):
    _register(client)
    _set_deadline(utc_today() + timedelta(days=3))
    with patch("app.services.email_verification_service.send_email", return_value=False):
        assert _remind() == []
    assert _user().last_verification_reminder_days is None
    assert _remind() == ["alice"]


def test_reminders_off(client, outbox, monkeypatch):
    _register(client)
    _set_deadline(utc_today() + timedelta(days=1))
    monkeypatch.setenv("VERIFICATION_REMINDER_DAYS", "")
    assert _remind() == []
    monkeypatch.setenv("VERIFICATION_REMINDER_DAYS", "7,1")
    monkeypatch.setenv("EMAIL_VERIFICATION_ENABLED", "false")
    assert _remind() == []


def test_invalid_reminder_days_stop_startup(monkeypatch, outbox):
    monkeypatch.setenv("VERIFICATION_REMINDER_DAYS", "seven")
    with pytest.raises(security.SettingsError, match="VERIFICATION_REMINDER_DAYS"):
        security.validate_settings()


def test_cli_send_verification_reminders(client, outbox, capsys):
    _register(client)
    _set_deadline(utc_today() + timedelta(days=1))
    with patch.object(cli, "SessionLocal", _Session):
        cli.cmd_send_verification_reminders(argparse.Namespace(dry_run=True))
        assert "Would remind 1 user(s): alice" in capsys.readouterr().out
        cli.cmd_send_verification_reminders(argparse.Namespace(dry_run=False))
        assert "Reminded 1 user(s): alice" in capsys.readouterr().out
        cli.cmd_send_verification_reminders(argparse.Namespace(dry_run=False))
        assert "Reminded 0 user(s)." in capsys.readouterr().out


def test_cli_reminders_when_disabled(capsys):
    cli.cmd_send_verification_reminders(argparse.Namespace(dry_run=False))
    assert "off" in capsys.readouterr().out
