"""Two-factor authentication: TOTP secret and recovery codes (task 37.5).

Revision ID: 0011_two_factor
Revises: 0010_lockout_settings
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_two_factor"
down_revision: Union[str, None] = "0010_lockout_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("totp_secret", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("totp_pending_secret", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("totp_enabled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("totp_last_step", sa.Integer(), nullable=True))

    op.create_table(
        "recovery_codes",
        sa.Column("recovery_code_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("creation_time", sa.Time(), nullable=False),
        sa.Column("creation_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("modification_time", sa.Time(), nullable=True),
        sa.Column("modification_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.create_index("idx_recovery_codes_user_id", "recovery_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    with op.batch_alter_table("users") as batch:
        for column in ("totp_last_step", "totp_enabled_at", "totp_pending_secret", "totp_secret"):
            batch.drop_column(column)
