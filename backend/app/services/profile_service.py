"""
ProfileService — manages user profile assignment and permission resolution.

A Profile is a named permission set that lists which application screens
a User-role account may access.  Admin-role accounts bypass profile checks
entirely and are granted full access (returned as ["*"]).

Requirements: 3.1–3.7
"""

from sqlalchemy.orm import Session

from app.models import Profile, User, UserProfile
from app.utils.audit_columns import set_creation_audit, set_modification_audit


class ProfileService:
    """Encapsulates all profile / permission logic."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_user_permissions(self, user_id: int) -> list[str]:
        """Return the list of permitted screen keys for *user_id*.

        Admin-role accounts receive ``["*"]`` (full access) without
        consulting the ``user_profiles`` table — this mirrors the hardcoded
        bypass described in the design.

        For User-role accounts the method joins ``user_profiles`` →
        ``profiles`` and returns ``profiles.permitted_screens`` (a JSON
        array stored as JSONB).  If the user has no profile assignment the
        method returns an empty list (no screens permitted).

        :param user_id: PK of the user whose permissions are requested.
        :returns: A list of screen-key strings, e.g.
            ``["credentials", "credentials.new"]``, or ``["*"]`` for admins.
        :raises ValueError: If no user with *user_id* exists.
        """
        user: User | None = (
            self._db.query(User).filter(User.user_id == user_id).first()
        )
        if user is None:
            raise ValueError(f"User {user_id} not found.")

        # Admin role: unconditional full access (Requirement 3.5)
        if user.role == "Admin":
            return ["*"]

        # User role: derive permissions from assigned profile (Requirement 3.4)
        user_profile: UserProfile | None = (
            self._db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        if user_profile is None:
            # No profile assigned — no screens permitted
            return []

        profile: Profile | None = (
            self._db.query(Profile)
            .filter(Profile.profile_id == user_profile.profile_id)
            .first()
        )
        if profile is None:
            return []

        # permitted_screens is stored as JSONB (a Python list after ORM load)
        screens = profile.permitted_screens
        if screens is None:
            return []
        return list(screens)

    def assign_profile(
        self, admin_id: int, user_id: int, profile_id: int
    ) -> UserProfile:
        """Assign (or update) the profile for *user_id*.

        If a ``user_profiles`` row already exists for *user_id*, the
        ``profile_id`` is updated and the modification audit columns are set
        via :func:`~app.utils.audit_columns.set_modification_audit`.

        If no row exists yet, a new one is inserted and the creation audit
        columns are set via :func:`~app.utils.audit_columns.set_creation_audit`.

        In both cases the change is committed synchronously before returning.

        :param admin_id: PK of the Admin user performing the assignment
            (used for audit columns).
        :param user_id: PK of the User whose profile is being assigned.
        :param profile_id: PK of the Profile to assign.
        :returns: The persisted :class:`~app.models.UserProfile` ORM instance.
        """
        existing: UserProfile | None = (
            self._db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )

        if existing is not None:
            # Update existing assignment
            existing.profile_id = profile_id
            set_modification_audit(existing, user_id=admin_id)
            self._db.commit()
            self._db.refresh(existing)
            return existing

        # Insert new assignment
        record = UserProfile(
            user_id=user_id,
            profile_id=profile_id,
        )
        set_creation_audit(record, user_id=admin_id)
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record
