"""
User administration and audit view (task 37.4, Requirement 15): account
status, deactivation with a reason, reactivation and the audit view.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-user-admin-secret-0123456789abcdef-xyz"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

from datetime import timedelta  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, RefreshToken, User, UserPreference  # noqa: E402
from app.utils.audit_columns import utc_date_time  # noqa: E402
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
        for model in (UserPreference, RefreshToken, AuditLog, Credential, User):
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


def _login(client: TestClient, username: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": _PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _set(user_id: int, **values) -> None:
    with _Session() as db:
        user = db.get(User, user_id)
        for key, value in values.items():
            setattr(user, key, value)
        db.commit()


@pytest.fixture()
def accounts():
    """An Admin and a User, each signed in on their own device."""
    admin_device, user_device = _device(), _device()
    admin_id = _register(admin_device, "boss")
    user_id = _register(user_device, "alice")
    _set(admin_id, role="Admin", email_verified=True)
    _set(user_id, email_verified=True)
    return {
        "admin": admin_device,
        "admin_h": _login(admin_device, "boss"),
        "admin_id": admin_id,
        "user": user_device,
        "user_h": _login(user_device, "alice"),
        "user_id": user_id,
    }


def _deactivate(a, reason="Left the company"):
    with patch("app.routers.admin_router.send_email") as send:
        r = a["admin"].post(f"/api/admin/users/{a['user_id']}/deactivate", json={"reason": reason}, headers=a["admin_h"])
    return r, send


# ── Users list ────────────────────────────────────────────────────────────


def test_list_shows_code_status_and_never_the_password_hash(accounts):
    rows = accounts["admin"].get("/api/admin/users", headers=accounts["admin_h"]).json()
    alice = next(r for r in rows if r["username"] == "alice")
    assert alice["user_code"].startswith("SP-")
    assert alice["status"] == "active" and alice["deactivated_by"] is None
    assert alice["created"].endswith("Z")
    assert "password_hash" not in alice


def test_user_role_cannot_use_admin_endpoints(accounts):
    a = accounts
    assert a["user"].get("/api/admin/users", headers=a["user_h"]).status_code == 403
    assert a["user"].get("/api/admin/audit", headers=a["user_h"]).status_code == 403
    r = a["user"].post(f"/api/admin/users/{a['admin_id']}/deactivate", json={"reason": "nope"}, headers=a["user_h"])
    assert r.status_code == 403


# ── Deactivate / reactivate ───────────────────────────────────────────────


def test_deactivate_ends_sessions_blocks_login_and_emails_the_reason(accounts):
    a = accounts
    r, send = _deactivate(a, "  Left   the company ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "deactivated" and body["deactivated_by"] == "admin"
    assert body["deactivation_reason"] == "Left the company"

    # The open session stops at once: access token and refresh cookie.
    assert a["user"].get("/api/credentials", headers=a["user_h"]).status_code == 401
    assert a["user"].post("/api/auth/refresh").status_code == 401
    # Signing in again is refused (after the password matched).
    login = a["user"].post("/api/auth/login", json={"username": "alice", "password": _PW})
    assert login.status_code == 403 and login.json()["detail"] == "Account deactivated."

    email = send.call_args.args[0]
    assert email.to == "alice@example.com" and "Left the company" in email.body


def test_deactivate_needs_a_reason_and_never_the_own_account(accounts):
    a = accounts
    r, _ = _deactivate(a, "  x ")
    assert r.status_code == 422
    own = a["admin"].post(f"/api/admin/users/{a['admin_id']}/deactivate", json={"reason": "testing"}, headers=a["admin_h"])
    assert own.status_code == 400
    missing = a["admin"].post("/api/admin/users/99999/deactivate", json={"reason": "testing"}, headers=a["admin_h"])
    assert missing.status_code == 404
    assert _deactivate(a)[0].status_code == 200
    assert _deactivate(a)[0].status_code == 409


def test_reactivate_lets_the_account_sign_in_again(accounts):
    a = accounts
    _deactivate(a)
    with patch("app.routers.admin_router.send_email") as send:
        r = a["admin"].post(f"/api/admin/users/{a['user_id']}/reactivate", headers=a["admin_h"])
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert r.json()["deactivation_reason"] is None
    assert send.call_args.args[0].to == "alice@example.com"
    _login(a["user"], "alice")
    again = a["admin"].post(f"/api/admin/users/{a['user_id']}/reactivate", headers=a["admin_h"])
    assert again.status_code == 409


def test_reactivating_an_expired_unverified_account_gives_a_new_deadline(accounts, monkeypatch):
    a = accounts
    monkeypatch.setenv("EMAIL_VERIFICATION_ENABLED", "true")
    today = utc_date_time()[0]
    _set(a["user_id"], email_verified=False, deactivation_deadline=today - timedelta(days=1))
    rows = a["admin"].get("/api/admin/users", headers=a["admin_h"]).json()
    alice = next(r for r in rows if r["username"] == "alice")
    assert alice["status"] == "deactivated" and alice["deactivated_by"] == "deadline"

    with patch("app.routers.admin_router.send_email"):
        r = a["admin"].post(f"/api/admin/users/{a['user_id']}/reactivate", headers=a["admin_h"])
    assert r.status_code == 200 and r.json()["status"] == "unverified"
    with _Session() as db:
        user = db.get(User, a["user_id"])
        assert user.deactivation_deadline > today and user.email_verified is False


# ── Audit view ────────────────────────────────────────────────────────────


def _audit(a, **params):
    r = a["admin"].get("/api/admin/audit", params=params, headers=a["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


def test_audit_records_account_admin_and_credential_events(accounts):
    a = accounts
    created = a["user"].post(
        "/api/credentials",
        json={
            "website_name": "Secret Bank",
            "email_or_username": "alice-at-bank",
            "is_username_login": True,
            "password": "Sup3rS3cret!",
            "account_password": _PW,
        },
        headers=a["user_h"],
    )
    assert created.status_code == 201, created.text
    a["admin"].put(f"/api/admin/users/{a['user_id']}/role", json={"role": "Admin"}, headers=a["admin_h"])
    _deactivate(a)

    data = _audit(a)
    actions = [row["action"] for row in data["items"]]
    for expected in ("account.register", "account.login", "credential.create", "user.role", "user.deactivate"):
        assert expected in actions
    assert data["truncated"] is False
    # Newest first.
    assert actions[0] == "user.deactivate"

    role = next(row for row in data["items"] if row["action"] == "user.role")
    assert role["actor"]["username"] == "boss" and role["target"]["username"] == "alice"
    assert role["detail"] == "User→Admin"

    cred = next(row for row in data["items"] if row["action"] == "credential.create")
    assert cred["record_id"] == created.json()["credential_id"]
    # Never the credential's contents.
    text = str(data)
    assert "Secret Bank" not in text and "alice-at-bank" not in text and "Sup3rS3cret" not in text


def test_audit_filters_by_action_person_and_date(accounts):
    a = accounts
    _deactivate(a)
    only = _audit(a, action="user.deactivate")["items"]
    assert [row["action"] for row in only] == ["user.deactivate"]

    # A person matches whoever did it or whoever it was done to.
    alice = _audit(a, q="ALICE")["items"]
    assert alice and all("alice" in (row["actor"]["username"], (row["target"] or {}).get("username")) for row in alice)
    code = next(r for r in a["admin"].get("/api/admin/users", headers=a["admin_h"]).json() if r["username"] == "boss")
    assert all(row["actor"]["username"] == "boss" or (row["target"] or {}).get("username") == "boss"
               for row in _audit(a, q=code["user_code"])["items"])
    # Wildcards are literal.
    assert _audit(a, q="%")["items"] == []

    tomorrow = (utc_date_time()[0] + timedelta(days=1)).isoformat()
    assert _audit(a, date_from=tomorrow)["items"] == []
    assert _audit(a, date_to=tomorrow)["items"]

    bad = a["admin"].get("/api/admin/audit", params={"action": "drop.tables"}, headers=a["admin_h"])
    assert bad.status_code == 422


def test_password_change_is_audited(accounts):
    a = accounts
    with patch("app.routers.profile_router.send_email"):
        r = a["user"].post(
            "/api/profile/password",
            json={"current_password": _PW, "new_password": "N3wStr0ngPass!", "new_password_confirmation": "N3wStr0ngPass!"},
            headers=a["user_h"],
        )
    assert r.status_code == 204
    rows = _audit(a, action="account.password")["items"]
    assert len(rows) == 1 and rows[0]["actor"]["username"] == "alice"
