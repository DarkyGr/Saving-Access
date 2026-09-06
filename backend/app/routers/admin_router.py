"""
Admin router — user management and profile assignment endpoints.

Endpoints:
  GET /api/admin/users                         → list all users with their assigned profile
  PUT /api/admin/users/{user_id}/profile       → assign a profile to a user

Both endpoints require ``require_permission("admin.users")``.  Because Admin role
bypasses the profile check unconditionally (Requirement 3.5), only Admin-role
tokens can reach these handlers in practice; any User-role JWT receives a 403
from the middleware before the handler is invoked.

Security notes:
  - Ownership check is not applicable here (Admin has full access — Requirement 3.5).
  - All profile assignments are recorded in audit columns via ProfileService
    (Requirement 3.3).
  - User passwords are never returned in any response.

Requirements: 3.2, 3.3, 3.5, 3.7
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import require_permission
from app.models import Profile, User, UserProfile
from app.services.profile_service import ProfileService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------


class ProfileSummary(BaseModel):
    """Embedded profile info returned alongside each user."""

    profile_id: int
    profile_name: str

    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """Single user entry returned by GET /api/admin/users.

    The ``profile`` field is ``None`` when the user has no profile assigned.
    The password hash is never included (Requirement 8.5).
    """

    user_id: int
    username: str
    email: str
    role: str
    profile: Optional[ProfileSummary] = None

    class Config:
        from_attributes = True


class AssignProfileRequest(BaseModel):
    """Request body for PUT /api/admin/users/{user_id}/profile."""

    profile_id: int


class AssignProfileResponse(BaseModel):
    """Response body for PUT /api/admin/users/{user_id}/profile (200)."""

    user_id: int
    profile_id: int


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=list[UserListItem],
    status_code=status.HTTP_200_OK,
    summary="List all users with their assigned profile",
)
def list_users(
    claims: dict = Depends(require_permission("admin.users")),
    db: Session = Depends(get_db),
) -> list[UserListItem]:
    """Return every user in the system together with their assigned profile.

    - All user records are returned regardless of role (Requirement 3.7).
    - Password hashes are never included in the response (Requirement 8.5).
    - Users without a profile assignment have ``profile: null``.

    The query performs a left-join via Python after two separate ORM queries
    (users + a map of user_id → profile) to avoid complex join syntax while
    still using ORM parameterized queries (Requirement 8.6).
    """
    # Fetch all users
    users: list[User] = db.query(User).order_by(User.user_id).all()

    # Fetch all user_profile assignments and build a quick lookup map
    user_profile_rows: list[UserProfile] = db.query(UserProfile).all()
    profile_ids_by_user: dict[int, int] = {
        row.user_id: row.profile_id for row in user_profile_rows
    }

    # Fetch all profiles and build a lookup map
    all_profiles: list[Profile] = db.query(Profile).all()
    profiles_by_id: dict[int, Profile] = {p.profile_id: p for p in all_profiles}

    result: list[UserListItem] = []
    for user in users:
        profile_id = profile_ids_by_user.get(user.user_id)
        profile_summary: Optional[ProfileSummary] = None

        if profile_id is not None:
            profile = profiles_by_id.get(profile_id)
            if profile is not None:
                profile_summary = ProfileSummary(
                    profile_id=profile.profile_id,
                    profile_name=profile.profile_name,
                )

        result.append(
            UserListItem(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                role=user.role,
                profile=profile_summary,
            )
        )

    return result


# ---------------------------------------------------------------------------
# PUT /api/admin/users/{user_id}/profile
# ---------------------------------------------------------------------------


@router.put(
    "/users/{user_id}/profile",
    response_model=AssignProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign a profile to a user",
)
def assign_user_profile(
    user_id: int,
    body: AssignProfileRequest,
    claims: dict = Depends(require_permission("admin.users")),
    db: Session = Depends(get_db),
) -> AssignProfileResponse:
    """Assign (or update) the profile for the given user.

    Steps:
      1. Verify the target user exists → 404 if not.
      2. Verify the requested profile exists → 404 if not.
      3. Call ``ProfileService.assign_profile`` to upsert the
         ``user_profiles`` row and record modification audit columns
         (Requirement 3.3).
      4. Return ``{user_id, profile_id}`` (Requirement 3.7).

    :param user_id: PK of the user whose profile is being assigned.
    :param body:    Request body containing the new ``profile_id``.
    :param claims:  Decoded JWT payload injected by ``require_permission``.
    :param db:      Database session injected by ``get_db``.
    """
    admin_id: int = claims["user_id"]

    # 1. Verify target user exists
    target_user: User | None = (
        db.query(User).filter(User.user_id == user_id).first()
    )
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    # 2. Verify requested profile exists
    target_profile: Profile | None = (
        db.query(Profile).filter(Profile.profile_id == body.profile_id).first()
    )
    if target_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    # 3. Upsert the user_profiles row via ProfileService (sets audit columns)
    profile_svc = ProfileService(db)
    profile_svc.assign_profile(
        admin_id=admin_id,
        user_id=user_id,
        profile_id=body.profile_id,
    )

    # 4. Return confirmation
    return AssignProfileResponse(user_id=user_id, profile_id=body.profile_id)
