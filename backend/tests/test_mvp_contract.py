"""
Frontend ↔ backend contract tests (Phase 1 / MVP unblock, tasks 30.x).

These exercise the endpoints and claims the React app relies on, against a
full schema with the default profiles seeded — the setup earlier tests
skipped by promoting every test user to Admin.
"""

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_JWT_SECRET = "test-mvp-contract-secret"
_TEST_JWT_ALGORITHM = "HS256"

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["FERNET_KEY"] = _TEST_FERNET_KEY
os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
os.environ["JWT_ALGORITHM"] = _TEST_JWT_ALGORITHM
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import jwt  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from tests.conftest import make_test_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Credential, Profile, RefreshToken, User, UserProfile  # noqa: E402
from app.seed import seed_default_profiles  # noqa: E402

_ENGINE = make_test_engine()  # PostgreSQL when TEST_DATABASE_URL is set
_Session = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def _override_get_db():
    db: Session = _Session()
    try:
        yield db
    finally:
        db.close()


_client = TestClient(app)

_PW = "Str0ngPassw0rd!"


@pytest.fixture(autouse=True)
def _clean_db():
    with _Session() as db:
        # Children first: PostgreSQL enforces the foreign keys.
        for model in (RefreshToken, AuditLog, Credential, UserProfile, Profile, User):
            db.query(model).delete()
        db.commit()
        seed_default_profiles(db)
    yield


def _register(username: str) -> int:
    r = _client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": _PW,
            "password_confirmation": _PW,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def _login(username: str) -> dict:
    r = _client.post("/api/auth/login", json={"username": username, "password": _PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_admin(username: str) -> None:
    with _Session() as db:
        db.query(User).filter(User.username == username).update({"role": "Admin"})
        db.commit()


# ── B1: JWT carries every claim AuthContext.decodeJwtPayload requires ───────


def test_jwt_contains_claims_required_by_frontend():
    user_id = _register("alice")
    token = _login("alice")["Authorization"].split(" ", 1)[1]
    claims = jwt.decode(token, _TEST_JWT_SECRET, algorithms=[_TEST_JWT_ALGORITHM])
    assert claims["user_id"] == user_id
    assert claims["username"] == "alice"
    assert claims["role"] == "User"
    assert "exp" in claims


# ── B5: seed + default profile on sign-up ────────────────────────────────────


def test_default_profiles_are_seeded_idempotently():
    with _Session() as db:
        seed_default_profiles(db)  # second run must not duplicate
        names = sorted(p.profile_name for p in db.query(Profile).all())
    assert names == ["Basic", "Full"]


def test_new_user_gets_full_profile_and_can_use_credentials():
    _register("bob")
    headers = _login("bob")
    r = _client.get("/api/profile/permissions", headers=headers)
    assert r.status_code == 200
    assert set(r.json()["permissions"]) == {
        "credentials",
        "credentials.new",
        "credentials.edit",
        "credentials.delete",
    }
    assert _client.get("/api/credentials", headers=headers).status_code == 200


# ── B2: GET /api/profile/permissions ─────────────────────────────────────────


def test_profile_permissions_requires_auth():
    assert _client.get("/api/profile/permissions").status_code == 401


def test_profile_permissions_admin_is_wildcard():
    _register("root")
    _make_admin("root")
    r = _client.get("/api/profile/permissions", headers=_login("root"))
    assert r.status_code == 200
    assert r.json() == {"role": "Admin", "permissions": ["*"]}


# ── B3: GET /api/credentials/{id} ────────────────────────────────────────────


def _create_credential(headers: dict, site: str = "GitHub") -> int:
    r = _client.post(
        "/api/credentials",
        headers=headers,
        json={
            "website_name": site,
            "email_or_username": "carol@example.com",
            "is_username_login": False,
            "password": "s3cret-site-pw",
            "account_password": _PW,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["credential_id"]


def test_get_single_credential_never_returns_password():
    _register("carol")
    headers = _login("carol")
    cred_id = _create_credential(headers)
    r = _client.get(f"/api/credentials/{cred_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["website_name"] == "GitHub"
    assert body["email_or_username"] == "carol@example.com"
    assert body["password"] is None


def test_get_single_credential_enforces_ownership():
    _register("carol")
    _register("dave")
    cred_id = _create_credential(_login("carol"))
    r = _client.get(f"/api/credentials/{cred_id}", headers=_login("dave"))
    assert r.status_code == 403
    assert _client.get("/api/credentials/99999", headers=_login("dave")).status_code == 404


# ── B4 + Property 7: admin endpoints are Admin-role only ─────────────────────


def test_admin_lists_profiles_with_screens():
    _register("root")
    _make_admin("root")
    r = _client.get("/api/admin/profiles", headers=_login("root"))
    assert r.status_code == 200
    by_name = {p["profile_name"]: p for p in r.json()}
    assert by_name["Basic"]["permitted_screens"] == ["credentials"]
    assert "credentials.delete" in by_name["Full"]["permitted_screens"]


def test_user_cannot_reach_admin_even_with_admin_screen_in_profile():
    _register("eve")
    with _Session() as db:
        full = db.query(Profile).filter(Profile.profile_name == "Full").one()
        full.permitted_screens = list(full.permitted_screens) + ["admin.users"]
        db.commit()
    headers = _login("eve")
    assert _client.get("/api/admin/users", headers=headers).status_code == 403
    assert _client.get("/api/admin/profiles", headers=headers).status_code == 403


def test_admin_reassigns_profile_and_permissions_follow():
    uid = _register("frank")
    _register("root")
    _make_admin("root")
    admin = _login("root")
    profiles = {p["profile_name"]: p["profile_id"] for p in _client.get("/api/admin/profiles", headers=admin).json()}
    r = _client.put(f"/api/admin/users/{uid}/profile", headers=admin, json={"profile_id": profiles["Basic"]})
    assert r.status_code == 200
    frank = _login("frank")
    assert _client.get("/api/profile/permissions", headers=frank).json()["permissions"] == ["credentials"]
    assert _client.get("/api/credentials", headers=frank).status_code == 200
    r = _client.post(
        "/api/credentials",
        headers=frank,
        json={
            "website_name": "X",
            "email_or_username": "frank@example.com",
            "password": "pw",
            "account_password": _PW,
        },
    )
    assert r.status_code == 403


# ── B6 contract: wrong account password keeps the documented detail ─────────


def test_wrong_account_password_detail_matches_frontend_constant():
    _register("gina")
    headers = _login("gina")
    cred_id = _create_credential(headers)
    r = _client.post(
        f"/api/credentials/{cred_id}/reveal",
        headers=headers,
        json={"account_password": "wrong"},
    )
    assert r.status_code == 401
    # Must equal ACCOUNT_PASSWORD_ERROR in frontend/src/api/apiClient.ts so
    # the interceptor does not log the user out on a typo.
    assert r.json() == {"detail": "Account password verification failed."}


# ── Task 32.4: search treats LIKE wildcards literally ───────────────────────


def test_search_escapes_like_wildcards():
    _register("hugo")
    headers = _login("hugo")
    _create_credential(headers, site="GitHub")
    _create_credential(headers, site="50%_off_store")

    def sites(q: str) -> list[str]:
        r = _client.get("/api/credentials", headers=headers, params={"q": q})
        assert r.status_code == 200
        return sorted(c["website_name"] for c in r.json())

    assert sites("%") == ["50%_off_store"]
    assert sites("_") == ["50%_off_store"]
    assert sites("0%_o") == ["50%_off_store"]
    assert sites("git") == ["GitHub"]  # case-insensitive partial match still works
    assert sites("\\") == []


def test_health_endpoint(monkeypatch):
    from app import database

    monkeypatch.setattr(database, "SessionLocal", _Session)
    assert _client.get("/api/health").json() == {"status": "ok"}
