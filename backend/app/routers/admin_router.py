"""
Admin router — user listing and role change (Requirement 3.6, 3.7).

Endpoints:
  GET /api/admin/users                 → every user with their role
  PUT /api/admin/users/{user_id}/role  → change another user's role

Both need ``users.manage``, which only the Admin role grants. Nothing here
returns password hashes or touches anyone's credentials.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import require_permission
from app.models import User
from app.utils.audit_columns import set_modification_audit

router = APIRouter()


class UserListItem(BaseModel):
    """Single user entry returned by GET /api/admin/users (no password hash)."""

    user_id: int
    username: str
    email: str
    role: str
    email_verified: bool

    model_config = ConfigDict(from_attributes=True)


class ChangeRoleRequest(BaseModel):
    role: Literal["User", "Admin"]


class ChangeRoleResponse(BaseModel):
    user_id: int
    role: str


@router.get(
    "/users",
    response_model=list[UserListItem],
    status_code=status.HTTP_200_OK,
    summary="List all users with their role",
)
def list_users(
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> list[User]:
    return db.query(User).order_by(User.user_id).all()


@router.put(
    "/users/{user_id}/role",
    response_model=ChangeRoleResponse,
    status_code=status.HTTP_200_OK,
    summary="Change another user's role",
)
def change_user_role(
    user_id: int,
    body: ChangeRoleRequest,
    claims: dict = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> ChangeRoleResponse:
    """Set *user_id*'s role and its modification Audit_Columns (Property 8).

    An Admin cannot change their own role, so at least one Admin always
    remains (Requirement 3.7).
    """
    admin_id: int = claims["user_id"]
    if user_id == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role.",
        )
    target: User | None = db.query(User).filter(User.user_id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    if target.role != body.role:
        target.role = body.role
        set_modification_audit(target, user_id=admin_id)
        db.commit()
    return ChangeRoleResponse(user_id=target.user_id, role=target.role)
