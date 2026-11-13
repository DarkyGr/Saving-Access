"""
Profile router — exposes the current user's permitted screens.

Endpoints:
  GET /api/profile/permissions → 200 {"role": str, "permissions": list[str]}

Used by the frontend ``ProtectedRoute`` and navigation header to decide which
screens a User-role account may open (Requirements 3.4, 3.6).  Admin accounts
receive ``["*"]``.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import get_current_claims
from app.services.profile_service import ProfileService

router = APIRouter()


class PermissionsResponse(BaseModel):
    role: str
    permissions: list[str]


@router.get(
    "/permissions",
    response_model=PermissionsResponse,
    summary="List the screens the current user may access",
)
def get_my_permissions(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> PermissionsResponse:
    try:
        permissions = ProfileService(db).get_user_permissions(claims["user_id"])
    except ValueError:
        # User deleted after the token was issued.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return PermissionsResponse(role=claims.get("role", ""), permissions=permissions)
