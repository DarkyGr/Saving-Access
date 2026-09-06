"""
Database engine and session factory for the password manager application.

Reads DATABASE_URL from the environment (via .env file through python-dotenv)
and exposes:
  - engine       — the SQLAlchemy Engine instance
  - SessionLocal — the sessionmaker factory
  - get_db()     — FastAPI dependency that yields a session and closes it on exit

Requirements 9.1–9.8, 8.6 (ORM + parameterized queries; no raw string interpolation).
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load variables from a .env file in the project root (if present).
# In production, env vars are expected to be set externally; load_dotenv is
# a no-op when the variables are already in the environment.
load_dotenv()

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ["DATABASE_URL"]
# Raises KeyError immediately at import time if DATABASE_URL is not set,
# making misconfiguration visible during startup rather than at first request.

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# pool_pre_ping=True verifies connections before handing them out from the pool,
# preventing stale-connection errors after a database restart or network blip.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

# autocommit=False and autoflush=False are SQLAlchemy defaults; stated explicitly
# to make the transactional intent clear.  Callers must commit explicitly.
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_db():
    """
    FastAPI dependency that yields a database session for the duration of a
    single request and closes it in the finally block.

    Usage::

        from app.database import get_db
        from sqlalchemy.orm import Session
        from fastapi import Depends

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
