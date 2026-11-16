"""User administration and audit view (task 37.4): deactivation by the Admin
with a reason, and what each audit row was about.

Revision ID: 0009_user_admin
Revises: 0008_settings
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_user_admin"
down_revision: Union[str, None] = "0008_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("deactivated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("deactivation_reason", sa.String(500), nullable=True))

    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("action", sa.String(32), nullable=True))
        batch.add_column(sa.Column("target_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("detail", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_audit_log_target_user_id", "users", ["target_user_id"], ["user_id"])
        batch.create_index("idx_audit_log_date", ["operation_date", "operation_time"])

    # Until now only credentials were audited: name what each row was.
    op.execute(
        "UPDATE audit_log SET action = CASE operation "
        "WHEN 'INSERT' THEN 'credential.create' "
        "WHEN 'UPDATE' THEN 'credential.edit' "
        "WHEN 'DELETE' THEN 'credential.delete' "
        "ELSE 'credential.reveal' END"
    )


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("idx_audit_log_date")
        batch.drop_constraint("fk_audit_log_target_user_id", type_="foreignkey")
        batch.drop_column("detail")
        batch.drop_column("target_user_id")
        batch.drop_column("action")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("deactivation_reason")
        batch.drop_column("deactivated_at")
