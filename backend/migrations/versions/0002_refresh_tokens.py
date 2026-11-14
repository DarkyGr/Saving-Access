"""Add refresh_tokens for the httpOnly session cookie (task 31.5).

Revision ID: 0002_refresh_tokens
Revises: 0001_baseline
Create Date: 2026-11-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_refresh_tokens"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("refresh_token_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("family_id", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
