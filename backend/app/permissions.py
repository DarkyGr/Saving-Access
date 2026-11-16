"""
Per-action permissions and the two fixed roles (Requirement 3, task 37.1).

Every non-public endpoint asks for one of these names through
``require_permission``; whatever a role does not list is denied. There is no
role bypass: Admin passes a check only because its set names the permission.

Credentials stay private to their owner for every role: these permissions say
what a user may do with *their own* vault, never with someone else's.
"""

from __future__ import annotations

PERMISSIONS: tuple[str, ...] = (
    "credentials.view",
    "credentials.create",
    "credentials.edit",
    "credentials.delete",
    "credentials.reveal",
    "users.manage",
)

ROLES: tuple[str, ...] = ("User", "Admin")

_VAULT = frozenset(p for p in PERMISSIONS if p.startswith("credentials."))

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "User": _VAULT,
    "Admin": _VAULT | {"users.manage"},
}


def permissions_for(role: str | None) -> frozenset[str]:
    """The permissions of *role*; an unknown role gets none (deny by default)."""
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def check_known(permission: str) -> str:
    """Return *permission*, or fail at import time on a typo."""
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission!r}")
    return permission
