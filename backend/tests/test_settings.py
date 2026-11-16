"""
Personal settings (task 37.3, Requirement 14): profile and user code,
preferences, avatar, password change, active sessions and session-bound
access tokens.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-settings-secret-0123456789abcdef-xyz"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import re  # noqa: E402
from unittest.mock import patch  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, RefreshToken, User, UserPreference  # noqa: E402
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
_NEW_PW = "N3wStr0ngPass!"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        for model in (UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
    yield


def _device(agent: str = "pytest-device") -> TestClient:
    # https so the Secure refresh cookie is kept; one client = one device.
    return TestClient(app, base_url="https://testserver", headers={"User-Agent": agent})


def _register(client: TestClient, username: str = "alice") -> None:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": _PW, "password_confirmation": _PW},
    )
    assert r.status_code == 201, r.text


def _login(client: TestClient, username: str = "alice", password: str = _PW) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Profile and user code ─────────────────────────────────────────────────


def test_me_has_an_immutable_user_code_and_display_name():
    c = _device()
    _register(c)
    h = _login(c)
    me = c.get("/api/profile/me", headers=h).json()
    assert re.fullmatch(r"SP-[23456789A-HJ-NP-Z]{6}", me["user_code"])
    assert me["username"] == "alice" and me["display_name"] is None and me["role"] == "User"

    r = c.put("/api/profile/me", headers=h, json={"display_name": "  Alicia Pérez "})
    assert r.status_code == 200 and r.json()["display_name"] == "Alicia Pérez"
    assert r.json()["user_code"] == me["user_code"]

    for bad in ("A", "<script>", "x" * 61, "Ana{1}"):
        assert c.put("/api/profile/me", headers=h, json={"display_name": bad}).status_code == 422
    assert c.put("/api/profile/me", headers=h, json={"display_name": ""}).json()["display_name"] is None


def test_codes_differ_between_accounts():
    c = _device()
    _register(c, "a1")
    _register(c, "a2")
    codes = {c.get("/api/profile/me", headers=_login(c, name)).json()["user_code"] for name in ("a1", "a2")}
    assert len(codes) == 2


# ── Preferences ───────────────────────────────────────────────────────────


def test_preferences_defaults_partial_update_and_validation():
    c = _device()
    _register(c)
    h = _login(c)
    p = c.get("/api/profile/preferences", headers=h).json()
    assert p | {"language": None} == {
        "list_views": {}, "theme": "system", "accent": "indigo", "start_page": "home",
        "private_mode": False, "language": None, "avatar_preset": None, "has_avatar_image": False,
    }
    r = c.put("/api/profile/preferences", headers=h, json={"theme": "dark", "private_mode": True})
    assert r.status_code == 200
    assert (r.json()["theme"], r.json()["private_mode"], r.json()["accent"]) == ("dark", True, "indigo")
    r = c.put("/api/profile/preferences", headers=h, json={"accent": "rose", "start_page": "credentials", "language": "es"})
    body = r.json()
    assert (body["theme"], body["accent"], body["start_page"], body["language"]) == ("dark", "rose", "credentials", "es")
    for bad in ({"theme": "pink"}, {"accent": "black"}, {"start_page": "admin-users"}, {"language": "fr"}):
        assert c.put("/api/profile/preferences", headers=h, json=bad).status_code == 422


# ── Avatar ────────────────────────────────────────────────────────────────


def test_avatar_preset_picture_and_initials():
    c = _device()
    _register(c)
    h = _login(c)
    assert c.put("/api/profile/avatar/preset", headers=h, json={"preset": "skull"}).status_code == 422
    r = c.put("/api/profile/avatar/preset", headers=h, json={"preset": "rocket"})
    assert r.json()["avatar_preset"] == "rocket" and r.json()["has_avatar_image"] is False

    r = c.put("/api/profile/avatar/image", headers={**h, "Content-Type": "image/png"}, content=PNG)
    assert r.status_code == 200 and r.json()["has_avatar_image"] is True and r.json()["avatar_preset"] is None
    pic = c.get("/api/profile/avatar/image", headers=h)
    assert pic.content == PNG and pic.headers["content-type"] == "image/png"
    assert pic.headers["x-content-type-options"] == "nosniff"
    assert pic.headers["content-security-policy"] == "default-src 'none'"

    # The real format is read from the bytes, not from the declared type.
    r = c.put("/api/profile/avatar/image", headers={**h, "Content-Type": "image/png"}, content=WEBP)
    assert r.status_code == 200
    assert c.get("/api/profile/avatar/image", headers=h).headers["content-type"] == "image/webp"
    for bad, code in ((b"<svg onload=alert(1)>", 415), (b"GIF89a" + b"\x00" * 20, 415), (PNG + b"\x00" * 300_000, 413), (b"", 413)):
        assert c.put("/api/profile/avatar/image", headers={**h, "Content-Type": "image/png"}, content=bad).status_code == code

    r = c.delete("/api/profile/avatar", headers=h)
    assert r.json()["has_avatar_image"] is False and r.json()["avatar_preset"] is None
    assert c.get("/api/profile/avatar/image", headers=h).status_code == 404


def test_avatar_is_private_to_its_owner():
    c = _device()
    _register(c, "ana")
    _register(c, "ben")
    c.put("/api/profile/avatar/image", headers={**_login(c, "ana"), "Content-Type": "image/png"}, content=PNG)
    assert c.get("/api/profile/avatar/image", headers=_login(c, "ben")).status_code == 404
    assert c.get("/api/profile/avatar/image").status_code == 401


# ── Sessions ──────────────────────────────────────────────────────────────


def test_access_token_carries_the_session_and_dies_with_logout():
    c = _device()
    _register(c)
    h = _login(c)
    claims = jwt.decode(h["Authorization"][7:], _TEST_JWT_SECRET, algorithms=[_TEST_JWT_ALGORITHM])
    assert len(claims["sid"]) == 32
    assert c.get("/api/profile/me", headers=h).status_code == 200
    assert c.post("/api/auth/logout").status_code == 204
    r = c.get("/api/profile/me", headers=h)
    assert r.status_code == 401 and r.json() == {"detail": "Session expired."}


def test_refresh_keeps_the_same_session():
    c = _device()
    _register(c)
    sid = jwt.decode(_login(c)["Authorization"][7:], _TEST_JWT_SECRET, algorithms=["HS256"])["sid"]
    r = c.post("/api/auth/refresh")
    assert r.status_code == 200
    assert jwt.decode(r.json()["access_token"], _TEST_JWT_SECRET, algorithms=["HS256"])["sid"] == sid
    assert c.get("/api/profile/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_sessions_list_and_end_another_device():
    laptop, phone = _device("Laptop Browser"), _device("Phone Browser")
    _register(laptop)
    h_laptop = _login(laptop)
    h_phone = _login(phone)

    sessions = laptop.get("/api/profile/sessions", headers=h_laptop).json()
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1 and current[0]["user_agent"] == "Laptop Browser"
    other = next(s for s in sessions if not s["current"])
    assert other["user_agent"] == "Phone Browser" and other["last_active"].endswith("Z")

    assert laptop.delete(f"/api/profile/sessions/{current[0]['session_id']}", headers=h_laptop).status_code == 400
    assert laptop.delete("/api/profile/sessions/ffffffffffffffffffffffffffffffff", headers=h_laptop).status_code == 404
    assert laptop.delete(f"/api/profile/sessions/{other['session_id']}", headers=h_laptop).status_code == 204

    # The phone is signed out at once: access token and refresh both fail.
    assert phone.get("/api/profile/me", headers=h_phone).status_code == 401
    assert phone.post("/api/auth/refresh").status_code == 401
    assert [s["current"] for s in laptop.get("/api/profile/sessions", headers=h_laptop).json()] == [True]


def test_cannot_end_someone_elses_session():
    a, b = _device(), _device()
    _register(a, "ana")
    _register(b, "ben")
    h_a = _login(a, "ana")
    h_b = _login(b, "ben")
    ben_session = b.get("/api/profile/sessions", headers=h_b).json()[0]["session_id"]
    assert a.delete(f"/api/profile/sessions/{ben_session}", headers=h_a).status_code == 404
    assert b.get("/api/profile/me", headers=h_b).status_code == 200


# ── Password change ───────────────────────────────────────────────────────


def _change(client, headers, current=_PW, new=_NEW_PW, confirm=None):
    return client.post(
        "/api/profile/password",
        headers=headers,
        json={"current_password": current, "new_password": new, "new_password_confirmation": confirm or new},
    )


def test_password_change_rules():
    c = _device()
    _register(c)
    h = _login(c)
    r = _change(c, h, current="wrong")
    assert r.status_code == 401 and r.json() == {"detail": "Account password verification failed."}
    assert _change(c, h, confirm="Different1!xyz").status_code == 400
    weak = _change(c, h, new="short")
    assert weak.status_code == 400 and weak.json()["detail"]["password_errors"]
    assert _change(c, h, new=_PW).json() == {"detail": "The new password must be different."}


def test_password_change_ends_other_sessions_keeps_this_one_and_notifies():
    laptop, phone = _device(), _device()
    _register(laptop)
    h_laptop = _login(laptop)
    h_phone = _login(phone)
    with patch("app.routers.profile_router.send_email") as send:
        assert _change(laptop, h_laptop).status_code == 204
    send.assert_called_once()
    notice = send.call_args.args[0]
    assert notice.to == "alice@example.com" and "password" in notice.subject.lower()

    assert laptop.get("/api/profile/me", headers=h_laptop).status_code == 200
    assert phone.get("/api/profile/me", headers=h_phone).status_code == 401
    assert phone.post("/api/auth/refresh").status_code == 401

    other = _device()
    assert other.post("/api/auth/login", json={"username": "alice", "password": _PW}).status_code == 401
    _login(other, password=_NEW_PW)


def test_password_notice_follows_the_language():
    c = _device()
    _register(c)
    h = _login(c)
    c.put("/api/profile/preferences", headers=h, json={"language": "es"})
    with patch("app.routers.profile_router.send_email") as send:
        _change(c, h)
    assert "contraseña" in send.call_args.args[0].subject
