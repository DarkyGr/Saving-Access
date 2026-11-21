"""Trusted devices that may skip the two-step code (Requirement 21).

Revision ID: 0014_trusted_devices
Revises: 0013_account_deletion
Create Date: 2026-11-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_trusted_devices"
down_revision: Union[str, None] = "0013_account_deletion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trusted_devices",
        sa.Column("trusted_device_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("trusted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.create_index("idx_trusted_devices_user_id", "trusted_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
