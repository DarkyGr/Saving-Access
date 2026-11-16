"""Personal settings (task 37.3): user code and display name, appearance
preferences and avatar, device of each session.

Revision ID: 0008_settings
Revises: 0007_user_preferences
Create Date: 2026-11-16
"""

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_settings"
down_revision: Union[str, None] = "0007_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def new_user_code() -> str:
    # Same rule as app/utils/user_code.py, copied so the migration never
    # changes when the application code does.
    return "SP-" + "".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(6))

def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("user_code", sa.String(9), nullable=True))
        batch.add_column(sa.Column("display_name", sa.String(60), nullable=True))

    # Every existing account gets its immutable code once. Offline (--sql,
    # used to generate db/schema.sql for an empty database) there are no rows.
    if op.get_context().as_sql:
        rows = []
    else:
        rows = op.get_bind().execute(sa.text("SELECT user_id FROM users ORDER BY user_id")).all()
    conn = op.get_bind()
    taken: set[str] = set()
    for (user_id,) in rows:
        code = new_user_code()
        while code in taken:
            code = new_user_code()
        taken.add(code)
        conn.execute(sa.text("UPDATE users SET user_code = :c WHERE user_id = :u"), {"c": code, "u": user_id})

    with op.batch_alter_table("users") as batch:
        batch.alter_column("user_code", existing_type=sa.String(9), nullable=False)
        batch.create_unique_constraint("uq_users_user_code", ["user_code"])

    with op.batch_alter_table("user_preferences") as batch:
        batch.add_column(sa.Column("theme", sa.String(8), nullable=False, server_default="system"))
        batch.add_column(sa.Column("accent", sa.String(10), nullable=False, server_default="indigo"))
        batch.add_column(sa.Column("start_page", sa.String(16), nullable=False, server_default="home"))
        batch.add_column(sa.Column("private_mode", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("avatar_preset", sa.String(16), nullable=True))
        batch.add_column(sa.Column("avatar_image", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("avatar_mime", sa.String(16), nullable=True))

    with op.batch_alter_table("refresh_tokens") as batch:
        batch.add_column(sa.Column("user_agent", sa.String(256), nullable=True))
        batch.add_column(sa.Column("client_ip", sa.String(45), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_column("client_ip")
        batch.drop_column("user_agent")
    with op.batch_alter_table("user_preferences") as batch:
        for column in ("avatar_mime", "avatar_image", "avatar_preset", "private_mode", "start_page", "accent", "theme"):
            batch.drop_column(column)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_user_code", type_="unique")
        batch.drop_column("display_name")
        batch.drop_column("user_code")
