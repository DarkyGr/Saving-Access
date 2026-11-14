"""
Alembic migrations are the single source of truth for the schema (task 31.6).

- ``upgrade head`` on an empty database succeeds;
- the result matches the ORM models (no pending autogenerate diff), so a
  model change without a migration fails CI;
- ``downgrade base`` works.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, DATABASE_URL=db_url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'migrations.sqlite3').as_posix()}"


def test_upgrade_matches_models_and_downgrades(db_url):
    up = _alembic(db_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    check = _alembic(db_url, "check")
    assert check.returncode == 0, (
        "ORM models and migrations differ — run "
        "'alembic revision --autogenerate -m ...':\n" + check.stdout + check.stderr
    )

    down = _alembic(db_url, "downgrade", "base")
    assert down.returncode == 0, down.stderr


def test_existing_create_all_database_can_be_adopted(db_url):
    """A DB created by the old create_all (no refresh_tokens) is stamped at baseline."""
    from sqlalchemy import create_engine, inspect

    from app.models import Base

    engine = create_engine(db_url)
    old_tables = [t for name, t in Base.metadata.tables.items() if name != "refresh_tokens"]
    Base.metadata.create_all(bind=engine, tables=old_tables)
    engine.dispose()

    assert _alembic(db_url, "stamp", "0001_baseline").returncode == 0
    up = _alembic(db_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    engine = create_engine(db_url)
    assert "refresh_tokens" in inspect(engine).get_table_names()
    engine.dispose()
