"""
Session limits and the administration re-authentication window (task 37.5,
Requirements 16.4–16.5).
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-session-limits-secret-0123456789abcdef"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

from datetime import UTC, datetime, timedelta  # noqa: E402

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


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        for model in (RecoveryCode, SystemSetting, AccountToken, UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _device() -> TestClient:
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": "pytest"})


def _signed_in(username: str = "alice", role: str = "User") -> tuple[TestClient, dict, int]:
    c = _device()
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


def _session(uid: int, **values) -> None:
    with _Session() as db:
        for row in db.query(RefreshToken).filter(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None)):
            for key, value in values.items():
                setattr(row, key, value)
        db.commit()


def test_a_new_session_reports_its_limits():
    c, h, _ = _signed_in()
    limits = c.get("/api/profile/session", headers=h).json()
    assert limits["idle_seconds"] == 15 * 60
    assert 480 * 60 - 5 <= limits["expires_in_seconds"] <= 480 * 60
    assert limits["extend_minutes"] == 30 and limits["reauth_minutes"] == 5


def test_an_idle_session_ends_and_activity_keeps_it_open():
    c, h, uid = _signed_in()
    _session(uid, last_activity_at=_now() - timedelta(minutes=12))
    assert c.post("/api/profile/session/ping", headers=h).status_code == 204
    assert c.get("/api/credentials", headers=h).status_code == 200

    _session(uid, last_activity_at=_now() - timedelta(minutes=17))
    r = c.get("/api/credentials", headers=h)
    assert r.status_code == 401 and r.json()["detail"] == "Session expired."
    assert c.post("/api/auth/refresh").status_code == 401


def test_the_maximum_length_ends_the_session_unless_extended():
    c, h, uid = _signed_in()
    _session(uid, session_expires_at=_now() + timedelta(seconds=40))
    extended = c.post("/api/profile/session/extend", headers=h).json()
    assert 30 * 60 <= extended["expires_in_seconds"] <= 31 * 60
    # Limits travel with the rotated refresh token.
    assert c.post("/api/auth/refresh").status_code == 200
    with _Session() as db:
        live = db.query(RefreshToken).filter(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None)).one()
        assert live.session_expires_at > _now() + timedelta(minutes=29)

    _session(uid, session_expires_at=_now() - timedelta(seconds=1))
    assert c.get("/api/credentials", headers=h).status_code == 401
    assert c.post("/api/auth/refresh").status_code == 401


def test_parameters_change_new_sessions():
    with _Session() as db:
        db.add_all([SystemSetting(key="session_max_minutes", value="60", creation_date=_now().date(), creation_time=_now().time())])
        db.commit()
    c, h, _ = _signed_in()
    assert c.get("/api/profile/session", headers=h).json()["expires_in_seconds"] <= 60 * 60


def test_administration_asks_for_the_password_again_after_the_window():
    admin, h, _ = _signed_in("boss", "Admin")
    _, _, uid = _signed_in("alice")
    role = f"/api/admin/users/{uid}/role"
    # Signing in counts as a fresh check.
    assert admin.put(role, json={"role": "Admin"}, headers=h).status_code == 200

    with _Session() as db:
        admin_id = db.query(User).filter(User.username == "boss").one().user_id
    _session(admin_id, reauth_at=_now() - timedelta(minutes=6))
    r = admin.put(role, json={"role": "User"}, headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "Re-authentication required."
    # Reading is not an action.
    assert admin.get("/api/admin/users", headers=h).status_code == 200

    wrong = admin.post("/api/profile/session/reauth", json={"account_password": "Wr0ngPassword!"}, headers=h)
    assert wrong.status_code == 401
    assert admin.post("/api/profile/session/reauth", json={"account_password": _PW}, headers=h).status_code == 204
    assert admin.put(role, json={"role": "User"}, headers=h).status_code == 200


def test_a_zero_window_asks_every_time():
    admin, h, _ = _signed_in("boss", "Admin")
    _, _, uid = _signed_in("alice")
    assert admin.put("/api/admin/settings", json={"admin_reauth_minutes": 0}, headers=h).status_code == 200
    role = f"/api/admin/users/{uid}/role"
    # The password typed at sign-in counts once; then each action asks.
    assert admin.put(role, json={"role": "Admin"}, headers=h).status_code == 200
    assert admin.put(role, json={"role": "User"}, headers=h).status_code == 403
    admin.post("/api/profile/session/reauth", json={"account_password": _PW}, headers=h)
    assert admin.put(role, json={"role": "User"}, headers=h).status_code == 200
    assert admin.put(role, json={"role": "Admin"}, headers=h).status_code == 403
