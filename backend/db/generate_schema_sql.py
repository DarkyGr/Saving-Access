"""Regenerate db/schema.sql from the Alembic migrations (PostgreSQL DDL).

    cd backend && python db/generate_schema_sql.py

schema.sql is a generated reference/DBA artifact; the migrations are the
source of truth (task 31.6). The app_user role section is appended verbatim.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent

ROLE_SQL = """
-- =============================================================
-- Application database role (Requirement 9.9) — run as superuser
-- after the tables exist. Replace the password before use.
-- =============================================================
CREATE ROLE app_user LOGIN PASSWORD 'change-me';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- No SUPERUSER, no schema ownership.
"""


def main() -> None:
    env = dict(os.environ, DATABASE_URL="postgresql://offline/savepass")
    ddl = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    header = (
        "-- GENERATED FILE — do not edit by hand.\n"
        "-- Source: backend/migrations (Alembic). Regenerate with:\n"
        "--   cd backend && python db/generate_schema_sql.py\n\n"
    )
    (HERE / "schema.sql").write_text(header + ddl + ROLE_SQL, encoding="utf-8")
    print("db/schema.sql regenerated.")


if __name__ == "__main__":
    main()
