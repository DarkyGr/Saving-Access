"""Session limits and the administration re-authentication window (task 37.5).

Revision ID: 0012_session_limits
Revises: 0011_two_factor
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_session_limits"
down_revision: Union[str, None] = "0011_two_factor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.add_column(sa.Column("session_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_activity_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("reauth_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_column("reauth_at")
        batch.drop_column("last_activity_at")
        batch.drop_column("session_expires_at")
