"""
Permission checks for the API (Requirement 3, task 37.1).

``require_permission(permission)`` is a FastAPI dependency factory:

  1. Read the Bearer token from ``Authorization``   → 401 if absent.
  2. Validate it with ``AuthService.verify_token``  → 401 if expired / invalid.
  3. Load the user from the database                → 401 if it no longer exists.
  4. Allow only if the user's *current* role grants the permission
     (``app.permissions``); otherwise 403 ``Access denied.``.

There is no role bypass, and the role comes from the database rather than the
token, so a role change applies to the next request.

Error shapes match the design's Error Handling table:
  - Missing / invalid token  → 401 ``{"detail": "Not authenticated."}``
  - Expired token            → 401 ``{"detail": "Token expired."}``
  - Missing permission       → 403 ``{"detail": "Access denied."}``
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import check_known, permissions_for
from app.services.auth_service import AuthService
from app.services.refresh_token_service import RefreshTokenService

# ``auto_error=False`` lets us raise our own 401 instead of FastAPI's 403
# when the header is missing.
_bearer = HTTPBearer(auto_error=False)


def get_current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency: any authenticated user. Returns the decoded JWT payload.

    :raises HTTPException 401: If the header is absent or the token invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    claims = AuthService(db).verify_token(credentials.credentials)
    # Task 37.3: a token bound to a session dies with it (logout, "end
    # session", password change), not 15 minutes later.
    sid = claims.get("sid")
    if sid and not RefreshTokenService(db).is_active(sid, claims["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired.",
        )
    return claims


def require_permission(permission: str) -> Callable:
    """Return a dependency that allows the request only with *permission*.

    The yielded claims carry ``role`` as stored in the database now.

    :raises ValueError: At import time, for a permission that does not exist.
    """
    check_known(permission)

    def _dependency(
        claims: dict = Depends(get_current_claims),
        db: Session = Depends(get_db),
    ) -> dict:
        user = db.query(User.role).filter(User.user_id == claims["user_id"]).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
            )
        if permission not in permissions_for(user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )
        return {**claims, "role": user.role}

    return _dependency
