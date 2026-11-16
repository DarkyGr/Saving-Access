"""
Role permissions (Requirement 3, task 37.1; replaces the ProfileService tests).

Property 7: Non-Admin Denied Access to Admin Screens — Validates 3.2, 3.3, 3.5
Property 8 (role change audit columns) is covered end to end in
``test_integration.py::TestAdminRoleChange``.
"""

import os

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-permissions-secret-at-least-32-chars")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from app.main import app  # noqa: E402
from app.middleware.permissions import get_current_claims, require_permission  # noqa: E402
from app.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES, permissions_for  # noqa: E402

_VAULT = {
    "credentials.view",
    "credentials.create",
    "credentials.edit",
    "credentials.delete",
    "credentials.reveal",
}


def test_user_role_has_exactly_the_vault():
    assert permissions_for("User") == _VAULT


def test_admin_role_adds_administration_only():
    assert permissions_for("Admin") == _VAULT | {"users.manage", "audit.view", "settings.manage"}


def test_roles_only_grant_known_permissions():
    assert set(ROLES) == set(ROLE_PERMISSIONS)
    for granted in ROLE_PERMISSIONS.values():
        assert granted <= set(PERMISSIONS)


@settings(max_examples=100)
@given(st.text(max_size=20).filter(lambda r: r not in ROLES))
def test_property_7_unknown_roles_get_nothing(role):
    """Deny by default: any role that is not defined grants no permission."""
    assert permissions_for(role) == frozenset()


@settings(max_examples=100)
@given(st.sampled_from([r for r in ROLES if r != "Admin"]))
def test_property_7_no_non_admin_role_manages_users(role):
    assert "users.manage" not in permissions_for(role)
    assert "audit.view" not in permissions_for(role)
    assert "settings.manage" not in permissions_for(role)


def test_unknown_permission_fails_when_declared():
    with pytest.raises(ValueError):
        require_permission("credentials.export")


# Endpoints anyone may call: sign-up, sign-in, session refresh, Phase 2
# configuration and links, health.
_PUBLIC = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/config",
    "/api/auth/verify-email",
    "/api/auth/unlock",
    "/api/health",
}


def _calls(dependant) -> list:
    found = [dependant.call]
    for sub in dependant.dependencies:
        found.extend(_calls(sub))
    return found


def _permission_of(route: APIRoute) -> str | None:
    """The permission a route asks for, from the closure of require_permission."""
    for call in _calls(route.dependant):
        cells = getattr(call, "__closure__", None) or ()
        if getattr(call, "__qualname__", "").startswith("require_permission."):
            for cell in cells:
                if isinstance(cell.cell_contents, str):
                    return cell.cell_contents
    return None


def _api_routes() -> list[tuple[str, APIRoute]]:
    """(full path, route) for every API route.

    FastAPI 0.16x keeps included routers as wrappers (``include_context``
    holds the prefix) instead of copying their routes into ``app.routes``.
    """
    found: list[tuple[str, APIRoute]] = []
    for item in app.routes:
        if isinstance(item, APIRoute):
            found.append((item.path, item))
        elif hasattr(item, "original_router") and hasattr(item, "include_context"):
            prefix = item.include_context.prefix or ""
            found.extend(
                (prefix + r.path, r) for r in item.original_router.routes if isinstance(r, APIRoute)
            )
    return [(path, r) for path, r in found if path.startswith("/api")]


def test_route_discovery_sees_the_routers():
    paths = {path for path, _ in _api_routes()}
    assert {"/api/auth/login", "/api/credentials", "/api/admin/users"} <= paths


def test_every_non_public_endpoint_requires_authentication():
    for path, route in _api_routes():
        if path in _PUBLIC:
            continue
        assert get_current_claims in _calls(route.dependant), path


def test_credential_and_admin_endpoints_name_their_permission():
    expected = {
        ("GET", "/api/credentials"): "credentials.view",
        ("GET", "/api/credentials/{credential_id}"): "credentials.view",
        ("POST", "/api/credentials"): "credentials.create",
        ("PUT", "/api/credentials/{credential_id}"): "credentials.edit",
        ("DELETE", "/api/credentials/{credential_id}"): "credentials.delete",
        ("POST", "/api/credentials/{credential_id}/reveal"): "credentials.reveal",
        ("GET", "/api/admin/users"): "users.manage",
        ("PUT", "/api/admin/users/{user_id}/role"): "users.manage",
        ("POST", "/api/admin/users/{user_id}/deactivate"): "users.manage",
        ("POST", "/api/admin/users/{user_id}/reactivate"): "users.manage",
        ("GET", "/api/admin/audit"): "audit.view",
        ("POST", "/api/admin/users/{user_id}/unlock"): "users.manage",
        ("GET", "/api/admin/settings"): "settings.manage",
        ("PUT", "/api/admin/settings"): "settings.manage",
    }
    seen = {}
    for path, route in _api_routes():
        if path.startswith(("/api/credentials", "/api/admin")):
            for method in route.methods:
                seen[(method, path.rstrip("/") if path != "/" else path)] = _permission_of(route)
    assert seen == expected
