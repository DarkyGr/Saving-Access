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
    """A DB created before Alembic (the baseline schema, never stamped) is
    stamped at baseline and upgraded.

    The pre-Alembic create_all produced exactly the 0001 baseline schema
    (users, profiles, user_profiles, credentials, audit_log). It is rebuilt
    here from that migration with the version table removed, because today's
    models no longer describe it (task 37.1 dropped profiles, 37.3 added
    columns to users).
    """
    from sqlalchemy import create_engine, inspect, text

    assert _alembic(db_url, "upgrade", "0001_baseline").returncode == 0
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(
            text(
                "INSERT INTO users (username, email, password_hash, role, email_verified, "
                "creation_date, creation_time) VALUES ('old', 'old@example.com', 'x', 'User', 1, "
                "'2026-01-01', '00:00:00')"
            )
        )
    engine.dispose()

    assert _alembic(db_url, "stamp", "0001_baseline").returncode == 0
    up = _alembic(db_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    engine = create_engine(db_url)
    tables = inspect(engine).get_table_names()
    assert "refresh_tokens" in tables and "email_verification_tokens" in tables
    assert "profiles" not in tables and "user_profiles" not in tables
    with engine.connect() as conn:
        # 0008 gave the existing account its immutable code.
        code = conn.execute(text("SELECT user_code FROM users WHERE username = 'old'")).scalar_one()
    assert code.startswith("SP-") and len(code) == 9
    engine.dispose()


def test_downgrade_from_0006_restores_profiles_for_existing_users(db_url):
    """Going back below 0006 gives every User the Full profile they had."""
    from sqlalchemy import create_engine, text

    assert _alembic(db_url, "upgrade", "head").returncode == 0
    engine = create_engine(db_url)
    with engine.begin() as conn:
        for name, role, code in (("u1", "User", "SP-AAAAAA"), ("a1", "Admin", "SP-BBBBBB")):
            conn.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, role, email_verified, "
                    "creation_date, creation_time, user_code) "
                    "VALUES (:n, :e, 'x', :r, 1, '2026-11-16', '00:00:00', :c)"
                ),
                {"n": name, "e": f"{name}@example.com", "r": role, "c": code},
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
