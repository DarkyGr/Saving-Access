"""Account lockout, one-time account links and system parameters (task 37.5).

Revision ID: 0010_lockout_settings
Revises: 0009_user_admin
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_lockout_settings"
down_revision: Union[str, None] = "0009_user_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    ]


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("failed_attempts", sa.SmallInteger(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("locked_at", sa.DateTime(), nullable=True))

    op.create_table(
        "account_tokens",
        sa.Column("account_token_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("purpose IN ('unlock', 'reset')", name="ck_account_tokens_purpose"),
    )
    op.create_index("idx_account_tokens_user_id", "account_tokens", ["user_id"])

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(2000), nullable=False),
        *_audit_columns(),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("idx_account_tokens_user_id", table_name="account_tokens")
    op.drop_table("account_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locked_at")
        batch.drop_column("failed_attempts")
