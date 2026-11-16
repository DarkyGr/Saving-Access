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
    later = {"refresh_tokens", "email_verification_tokens", "user_preferences"}  # 0002 / 0004 / 0007
    old_tables = [t for name, t in Base.metadata.tables.items() if name not in later]
    Base.metadata.create_all(bind=engine, tables=old_tables)
    # The pre-Alembic schema had no trigram indexes (added in 0003).
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX idx_credentials_website_name_trgm")
        conn.exec_driver_sql("DROP INDEX idx_credentials_email_username_trgm")
        # Nor the reminder columns (added in 0005).
        conn.exec_driver_sql("ALTER TABLE users DROP COLUMN preferred_language")
        conn.exec_driver_sql("ALTER TABLE users DROP COLUMN last_verification_reminder_days")
        # It still had the profile tables (dropped by 0006, task 37.1).
        conn.exec_driver_sql(
            "CREATE TABLE profiles (profile_id INTEGER PRIMARY KEY, profile_name VARCHAR(64), "
            "permitted_screens TEXT, creation_date DATE, creation_time TIME, creation_user_id INTEGER, "
            "modification_date DATE, modification_time TIME, modification_user_id INTEGER)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE user_profiles (user_profile_id INTEGER PRIMARY KEY, user_id INTEGER, "
            "profile_id INTEGER, creation_date DATE, creation_time TIME, creation_user_id INTEGER, "
            "modification_date DATE, modification_time TIME, modification_user_id INTEGER)"
        )
    engine.dispose()

    assert _alembic(db_url, "stamp", "0001_baseline").returncode == 0
    up = _alembic(db_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    engine = create_engine(db_url)
    tables = inspect(engine).get_table_names()
    assert "refresh_tokens" in tables and "email_verification_tokens" in tables
    assert "profiles" not in tables and "user_profiles" not in tables
    engine.dispose()


def test_downgrade_from_0006_restores_profiles_for_existing_users(db_url):
    """Going back below 0006 gives every User the Full profile they had."""
    from sqlalchemy import create_engine, text

    assert _alembic(db_url, "upgrade", "head").returncode == 0
    engine = create_engine(db_url)
    with engine.begin() as conn:
        for name, role in (("u1", "User"), ("a1", "Admin")):
            conn.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, role, email_verified, "
                    "creation_date, creation_time) VALUES (:n, :e, 'x', :r, 1, '2026-11-16', '00:00:00')"
                ),
                {"n": name, "e": f"{name}@example.com", "r": role},
            )
    engine.dispose()

    down = _alembic(db_url, "downgrade", "0005_verification_reminders")
    assert down.returncode == 0, down.stderr
    engine = create_engine(db_url)
    with engine.connect() as conn:
        names = [r[0] for r in conn.execute(text("SELECT profile_name FROM profiles ORDER BY profile_id"))]
        links = conn.execute(
            text("SELECT u.username, p.profile_name FROM user_profiles up "
                 "JOIN users u ON u.user_id = up.user_id JOIN profiles p ON p.profile_id = up.profile_id")
        ).all()
    engine.dispose()
    assert names == ["Basic", "Full"]
    assert [tuple(r) for r in links] == [("u1", "Full")]
