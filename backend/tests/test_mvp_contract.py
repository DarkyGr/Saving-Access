"""
Frontend ↔ backend contract tests (Phase 1 / MVP unblock, tasks 30.x).

These exercise the endpoints and claims the React app relies on, against a
full schema (task 37.1: permissions come from the role, no seed data).
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
from app.models import AuditLog, Credential, RefreshToken, User, UserPreference  # noqa: E402

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
        for model in (UserPreference, RefreshToken, AuditLog, Credential, User):
            db.query(model).delete()
        db.commit()
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


# ── B5 / task 37.1: a new sign-up is a User with the whole vault ─────────────

_VAULT = [
    "credentials.create",
    "credentials.delete",
    "credentials.edit",
    "credentials.reveal",
    "credentials.view",
]


def test_new_user_gets_the_vault_permissions_and_can_use_credentials():
    _register("bob")
    headers = _login("bob")
    r = _client.get("/api/profile/permissions", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"role": "User", "permissions": _VAULT}
    assert _client.get("/api/credentials", headers=headers).status_code == 200


# ── B2: GET /api/profile/permissions ─────────────────────────────────────────


def test_profile_permissions_requires_auth():
    assert _client.get("/api/profile/permissions").status_code == 401


def test_profile_permissions_admin_is_an_explicit_list():
    _register("root")
    _make_admin("root")
    r = _client.get("/api/profile/permissions", headers=_login("root"))
    assert r.status_code == 200
    assert r.json() == {"role": "Admin", "permissions": sorted(_VAULT + ["users.manage", "audit.view", "settings.manage"])}


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


def test_admin_lists_users_with_their_role():
    _register("eve")
    _register("root")
    _make_admin("root")
    r = _client.get("/api/admin/users", headers=_login("root"))
    assert r.status_code == 200
    roles = {u["username"]: u["role"] for u in r.json()}
    assert roles == {"eve": "User", "root": "Admin"}
    assert {"user_id", "username", "email", "role", "email_verified", "user_code", "status"} <= set(r.json()[0])
    assert "password_hash" not in r.json()[0]


def test_user_cannot_reach_admin_endpoints():
    uid = _register("eve")
    headers = _login("eve")
    assert _client.get("/api/admin/users", headers=headers).status_code == 403
    r = _client.put(f"/api/admin/users/{uid}/role", headers=headers, json={"role": "Admin"})
    assert r.status_code == 403
    assert r.json() == {"detail": "Access denied."}


def test_role_change_applies_to_the_next_request_with_the_same_token():
    uid = _register("frank")
    _register("root")
    _make_admin("root")
    admin = _login("root")
    frank = _login("frank")
    assert _client.put(f"/api/admin/users/{uid}/role", headers=admin, json={"role": "Admin"}).status_code == 200
    assert _client.get("/api/admin/users", headers=frank).status_code == 200
    assert _client.put(f"/api/admin/users/{uid}/role", headers=admin, json={"role": "User"}).status_code == 200
    assert _client.get("/api/admin/users", headers=frank).status_code == 403
    assert _client.get("/api/credentials", headers=frank).status_code == 200


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


# ── Task 37.2: Home data and account preferences ────────────────────────────


def test_list_carries_the_last_change():
    _register("ivy")
    headers = _login("ivy")
    _create_credential(headers, site="Zeta")
    first = _create_credential(headers, site="alpha")
    rows = _client.get("/api/credentials", headers=headers).json()
    assert {r["website_name"] for r in rows} == {"Zeta", "alpha"}
    created = {r["credential_id"]: r["last_changed"] for r in rows}[first]
    assert created.endswith("Z") and "T" in created

    r = _client.put(
        f"/api/credentials/{first}",
        headers=headers,
        json={
            "website_name": "alpha",
            "email_or_username": "ivy@example.com",
            "is_username_login": False,
            "password": "new-pw",
            "account_password": _PW,
        },
    )
    assert r.status_code == 200
    single = _client.get(f"/api/credentials/{first}", headers=headers).json()
    assert single["last_changed"] >= created


def test_preferences_start_empty_and_save_list_views():
    _register("jack")
    headers = _login("jack")
    assert _client.get("/api/profile/preferences").status_code == 401
    assert _client.get("/api/profile/preferences", headers=headers).json()["list_views"] == {}

    r = _client.put("/api/profile/preferences/list-view", headers=headers, json={"key": "credentials", "view": "grid"})
    assert r.status_code == 200 and r.json()["list_views"] == {"credentials": "grid"}
    r = _client.put("/api/profile/preferences/list-view", headers=headers, json={"key": "users", "view": "list"})
    assert r.json()["list_views"] == {"credentials": "grid", "users": "list"}
    r = _client.put("/api/profile/preferences/list-view", headers=headers, json={"key": "credentials", "view": "list"})
    assert r.json()["list_views"] == {"credentials": "list", "users": "list"}
    assert _client.get("/api/profile/preferences", headers=headers).json() == r.json()

    for bad in ({"key": "other", "view": "grid"}, {"key": "credentials", "view": "table"}):
        assert _client.put("/api/profile/preferences/list-view", headers=headers, json=bad).status_code == 422


def test_preferences_are_per_account():
    _register("kate")
    _register("liam")
    _client.put(
        "/api/profile/preferences/list-view", headers=_login("kate"), json={"key": "credentials", "view": "grid"}
    )
    assert _client.get("/api/profile/preferences", headers=_login("liam")).json()["list_views"] == {}
