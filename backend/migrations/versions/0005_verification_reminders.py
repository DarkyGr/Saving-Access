"""Deadline reminders: users.preferred_language, last_verification_reminder_days (task 34.4).

Revision ID: 0005_verification_reminders
Revises: 0004_email_verification
Create Date: 2026-11-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_verification_reminders"
down_revision: Union[str, None] = "0004_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("preferred_language", sa.String(8), nullable=True))
        batch.add_column(sa.Column("last_verification_reminder_days", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_verification_reminder_days")
        batch.drop_column("preferred_language")
