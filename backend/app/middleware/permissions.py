"""
Permission middleware for the password manager application.

Exposes ``require_permission(screen: str)`` — a FastAPI dependency factory
that enforces role-based and profile-based access control on a per-endpoint
basis.

Flow (Requirement 3.2, 3.4, 3.5, 3.6):
  1. Extract the Bearer token from the ``Authorization`` header.
     → 401 if absent or malformed.
  2. Decode and validate the JWT via ``AuthService.verify_token``.
     → 401 on expiry or invalid signature (raised by AuthService).
  3. If ``role == "Admin"`` → allow unconditionally (Requirement 3.5).
  4. Otherwise fetch the user's permitted screens via
     ``ProfileService.get_user_permissions``.
  5. If ``screen`` is found in the permission list → allow.
  6. Otherwise → 403 ``{"detail": "Access denied."}`` (Requirement 3.6).

Error shapes match the design's Error Handling table:
  - Missing / invalid token  → 401 ``{"detail": "Not authenticated."}``
  - Expired token            → 401 ``{"detail": "Token expired."}``
  - Missing screen permission → 403 ``{"detail": "Access denied."}``
"""

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService

# HTTPBearer extracts the token from ``Authorization: Bearer <token>``.
# ``auto_error=False`` lets us raise a custom 401 instead of the default
# FastAPI 403 when the header is missing.
_bearer = HTTPBearer(auto_error=False)


def require_permission(screen: str) -> Callable:
    """Return a FastAPI dependency that enforces access to *screen*.

    Usage::

        from app.middleware.permissions import require_permission

        @router.get("/api/credentials")
        def list_credentials(
            claims: dict = Depends(require_permission("credentials")),
            db: Session = Depends(get_db),
        ):
            ...

    :param screen: The screen key to check, e.g. ``"credentials"``,
        ``"credentials.new"``, ``"admin.users"``.
    :returns: A FastAPI dependency callable that yields the decoded JWT
        payload on success, or raises ``HTTPException`` on failure.
    """

    def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> dict:
        """Inner dependency resolved by FastAPI's DI container.

        :raises HTTPException 401: If the ``Authorization`` header is absent,
            the token is malformed, or the token is expired.
        :raises HTTPException 403: If the user's profile does not include
            *screen* in its permitted screens.
        :returns: The decoded JWT payload dict (``user_id``, ``role``, ``exp``).
        """
        # Step 1: ensure the header is present
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
            )

        # Step 2: decode and validate the JWT
        # AuthService.verify_token raises HTTPException(401) on expiry or bad sig.
        auth_svc = AuthService(db)
        payload = auth_svc.verify_token(credentials.credentials)

        user_id: int = payload["user_id"]
        role: str = payload.get("role", "")

        # Step 3: Admin bypasses profile check (Requirement 3.5)
        if role == "Admin":
            return payload

        # Step 4: fetch permissions for User role
        profile_svc = ProfileService(db)
        try:
            permissions = profile_svc.get_user_permissions(user_id)
        except ValueError:
            # User not found in the DB (deleted between token issuance and now)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
            )

        # Step 5: check if the requested screen is permitted
        if screen in permissions:
            return payload

        # Step 6: screen not permitted → 403 (Requirement 3.6)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    return _dependency
