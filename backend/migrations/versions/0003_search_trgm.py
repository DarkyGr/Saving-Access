"""Trigram indexes for credential search (task 32.4).

``GET /api/credentials?q=`` filters with ``ILIKE '%q%'``, which B-tree
indexes cannot serve. On PostgreSQL this adds the ``pg_trgm`` extension
(trusted since PG 13, so the database owner can create it) and GIN trigram
indexes. On SQLite the same indexes are plain ones, keeping the schema
identical to the ORM models.

Revision ID: 0003_search_trgm
Revises: 0002_refresh_tokens
Create Date: 2026-11-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_search_trgm"
down_revision: Union[str, None] = "0002_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = {
    "idx_credentials_website_name_trgm": "website_name",
    "idx_credentials_email_username_trgm": "email_or_username",
}


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, column in _INDEXES.items():
        op.create_index(
            name,
            "credentials",
            [column],
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    for name in _INDEXES:
        op.drop_index(name, table_name="credentials")
    # The extension is left in place: other objects may depend on it.
