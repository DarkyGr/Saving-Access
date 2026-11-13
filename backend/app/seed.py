"""
Idempotent seed data required for the application to be usable.

- Default profiles ("Basic", "Full") so the permission system has something
  to assign (Requirement 3.2).
- ``assign_default_profile`` gives every newly registered User the profile
  named by ``DEFAULT_PROFILE`` (default "Full"); without it a new account
  could not open any screen.
"""

import os

from sqlalchemy.orm import Session

from app.models import Profile, UserProfile
from app.utils.audit_columns import set_creation_audit

# Screen keys must match the frontend router's ProtectedRoute screens and the
# backend require_permission() keys.
DEFAULT_PROFILES: dict[str, list[str]] = {
    "Basic": ["credentials"],
    "Full": [
        "credentials",
        "credentials.new",
        "credentials.edit",
        "credentials.delete",
    ],
}


def seed_default_profiles(db: Session) -> None:
    """Create any missing default profile. Never modifies existing ones."""
    existing = {name for (name,) in db.query(Profile.profile_name).all()}
    created = False
    for name, screens in DEFAULT_PROFILES.items():
        if name in existing:
            continue
        profile = Profile(profile_name=name, permitted_screens=screens)
        set_creation_audit(profile, user_id=None)
        db.add(profile)
        created = True
    if created:
        db.commit()


def assign_default_profile(db: Session, user_id: int) -> None:
    """Link *user_id* to the configured default profile, if it exists.

    The caller is responsible for committing.
    """
    name = os.environ.get("DEFAULT_PROFILE", "Full")
    if not name:
        return
    profile = db.query(Profile).filter(Profile.profile_name == name).first()
    if profile is None:
        return
    link = UserProfile(user_id=user_id, profile_id=profile.profile_id)
    set_creation_audit(link, user_id=user_id)
    db.add(link)
