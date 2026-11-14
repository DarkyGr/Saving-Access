"""Add email_verification_tokens (task 33.2, Requirements 1.10, 2.8).

Revision ID: 0004_email_verification
Revises: 0003_search_trgm
Create Date: 2026-11-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_email_verification"
down_revision: Union[str, None] = "0003_search_trgm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("email_verification_token_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.create_index(
        "idx_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
