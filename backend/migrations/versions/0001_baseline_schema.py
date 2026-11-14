"""Baseline schema (tasks 2–3): users, profiles, user_profiles, credentials, audit_log.

Matches what ``Base.metadata.create_all`` produced before Alembic was
introduced. An existing database created that way is adopted with::

    alembic stamp 0001_baseline
    alembic upgrade head

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    """The six audit columns required on every table (Requirement 9.8)."""
    return [
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deactivation_deadline", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("role IN ('User', 'Admin')", name="ck_users_role"),
    )

    op.create_table(
        "profiles",
        sa.Column("profile_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_name", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "permitted_screens",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        *_audit_columns(),
    )

    op.create_table(
        "user_profiles",
        sa.Column("user_profile_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("profiles.profile_id", ondelete="CASCADE"), nullable=False),
        *_audit_columns(),
    )

    op.create_table(
        "credentials",
        sa.Column("credential_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("website_name", sa.String(256), nullable=False),
        sa.Column("email_or_username", sa.String(254), nullable=False),
        sa.Column("is_username_login", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("encrypted_password", sa.LargeBinary(), nullable=False),
        *_audit_columns(),
    )
    op.create_index("idx_credentials_user_id", "credentials", ["user_id"])
    op.create_index("idx_credentials_website_name", "credentials", ["website_name"])
    op.create_index("idx_credentials_email_username", "credentials", ["email_or_username"])

    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("affected_record_id", sa.Integer(), nullable=True),
        sa.Column("operation_date", sa.Date(), nullable=False),
        sa.Column("operation_time", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')",
            name="ck_audit_log_operation",
        ),
    )
    op.create_index("idx_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("idx_credentials_email_username", table_name="credentials")
    op.drop_index("idx_credentials_website_name", table_name="credentials")
    op.drop_index("idx_credentials_user_id", table_name="credentials")
    op.drop_table("credentials")
    op.drop_table("user_profiles")
    op.drop_table("profiles")
    op.drop_table("users")
