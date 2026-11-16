"""Retire per-user screen profiles: drop user_profiles and profiles (task 37.1).

Permissions now come from the account's role (``app/permissions.py``). The
downgrade recreates both tables with the old seed (Basic, Full) and links every
User to Full, which is what each sign-up used to get.

Revision ID: 0006_retire_profiles
Revises: 0005_verification_reminders
Create Date: 2026-11-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_retire_profiles"
down_revision: Union[str, None] = "0005_verification_reminders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("user_profiles")
    op.drop_table("profiles")


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    ]


def downgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "profiles",
        sa.Column("profile_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_name", sa.String(64), nullable=False, unique=True),
        sa.Column("permitted_screens", json_type, nullable=False, server_default=sa.text("'[]'")),
        *_audit_columns(),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_profile_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("profiles.profile_id", ondelete="CASCADE"), nullable=False),
        *_audit_columns(),
    )
    op.execute(
        "INSERT INTO profiles (profile_id, profile_name, permitted_screens, creation_date, creation_time) VALUES "
        "(1, 'Basic', '[\"credentials\"]', CURRENT_DATE, CURRENT_TIME), "
        "(2, 'Full', '[\"credentials\", \"credentials.new\", \"credentials.edit\", \"credentials.delete\"]', "
        "CURRENT_DATE, CURRENT_TIME)"
    )
    op.execute(
        "INSERT INTO user_profiles (user_id, profile_id, creation_date, creation_time) "
        "SELECT user_id, 2, CURRENT_DATE, CURRENT_TIME FROM users WHERE role = 'User'"
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('profiles', 'profile_id'), 2)")
