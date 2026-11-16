"""
SQLAlchemy ORM models for the password manager application.

Maps every table and column defined in the ERD:
  - users
  - credentials
  - audit_log

Audit columns (creation_date, creation_time, creation_user_id,
modification_date, modification_time, modification_user_id) are present
on all tables except audit_log, as specified in Requirement 9.8.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy import false as sa_false
from sqlalchemy.orm import DeclarativeBase, relationship

from app.utils.user_code import new_user_code


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Mixin: the six audit columns shared by users,
# and credentials (Requirement 9.8)
# ---------------------------------------------------------------------------

class AuditColumnsMixin:
    """
    Six standard audit columns required on every application table:
      creation_date, creation_time, creation_user_id,
      modification_date, modification_time, modification_user_id
    """

    creation_date = Column(Date, nullable=False)
    creation_time = Column(Time, nullable=False)
    # Self-referential FK is resolved as a string to avoid forward-reference issues.
    creation_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    modification_date = Column(Date, nullable=True)
    modification_time = Column(Time, nullable=True)
    modification_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class User(AuditColumnsMixin, Base):
    """
    Stores registered user accounts.
    Requirement 9.1 — columns: user_id, username, email, password_hash,
    role, email_verified, deactivation_deadline + Audit_Columns.
    """

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    email = Column(String(254), nullable=False, unique=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(
        String(16),
        nullable=False,
        # Requirement 3.1 — only two roles are supported.
        # CHECK constraint mirrors the DDL in design.md.
    )
    email_verified = Column(Boolean, nullable=False, default=False)
    # nullable — only relevant in Phase 2 (Requirement 1.9)
    deactivation_deadline = Column(Date, nullable=True)
    # UI language at sign-up / last resend ("en" | "es"), for emails sent
    # later without a request (deadline reminders, task 34.4).
    preferred_language = Column(String(8), nullable=True)
    # Days-before-deadline of the last reminder sent (e.g. 7, then 1).
    last_verification_reminder_days = Column(SmallInteger, nullable=True)
    # Task 37.3: public immutable ID (SP-XXXXXX) and the name shown in the app.
    user_code = Column(String(9), nullable=False, default=new_user_code)
    display_name = Column(String(60), nullable=True)
    # Task 37.4: set by the Admin (with the reason shown to the user); NULL = active.
    deactivated_at = Column(DateTime, nullable=True)
    deactivation_reason = Column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('User', 'Admin')", name="ck_users_role"),
        UniqueConstraint("user_code", name="uq_users_user_code"),
    )

    # Relationships
    credentials = relationship(
        "Credential",
        back_populates="user",
        foreign_keys="Credential.user_id",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship(
        "AuditLog",
        back_populates="user",
        foreign_keys="AuditLog.user_id",
    )


# ---------------------------------------------------------------------------
# user_preferences (task 37.2)
# ---------------------------------------------------------------------------

class UserPreference(AuditColumnsMixin, Base):
    """
    Per-account interface choices (Requirement 13.4; 14.x adds more).
    One row per user, created on the first change.
    """

    __tablename__ = "user_preferences"

    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # {"credentials": "grid", "users": "list"} — list or grid per listing.
    list_views = Column(JSON, nullable=False, default=dict)
    # Task 37.3 (Requirement 14): appearance and behaviour.
    theme = Column(String(8), nullable=False, default="system", server_default="system")
    accent = Column(String(10), nullable=False, default="indigo", server_default="indigo")
    start_page = Column(String(16), nullable=False, default="home", server_default="home")
    private_mode = Column(Boolean, nullable=False, default=False, server_default=sa_false())
    # One of the built-in icons, or a picture (validated, at most 256 KB).
    avatar_preset = Column(String(16), nullable=True)
    avatar_image = Column(LargeBinary, nullable=True)
    avatar_mime = Column(String(16), nullable=True)


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------

class Credential(AuditColumnsMixin, Base):
    """
    Stores encrypted user credentials (website + login + encrypted password).
    Requirement 9.4 — columns: credential_id, user_id FK, website_name,
    email_or_username, is_username_login, encrypted_password + Audit_Columns.
    Requirement 9.7 — indexes on user_id, website_name, email_or_username.
    """

    __tablename__ = "credentials"

    credential_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    website_name = Column(String(256), nullable=False)
    email_or_username = Column(String(254), nullable=False)
    is_username_login = Column(Boolean, nullable=False, default=False)
    # BYTEA — stores the raw Fernet-encrypted bytes (Requirement 8.1)
    encrypted_password = Column(LargeBinary, nullable=False)

    __table_args__ = (
        # Requirement 9.7 — indexes to support efficient queries under load
        Index("idx_credentials_user_id", "user_id"),
        Index("idx_credentials_website_name", "website_name"),
        Index("idx_credentials_email_username", "email_or_username"),
        # Trigram GIN indexes let PostgreSQL serve ILIKE '%q%' searches
        # (Requirement 5.2) from an index. Plain indexes on SQLite.
        Index(
            "idx_credentials_website_name_trgm",
            "website_name",
            postgresql_using="gin",
            postgresql_ops={"website_name": "gin_trgm_ops"},
        ),
        Index(
            "idx_credentials_email_username_trgm",
            "email_or_username",
            postgresql_using="gin",
            postgresql_ops={"email_or_username": "gin_trgm_ops"},
        ),
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="credentials",
        foreign_keys=[user_id],
    )


# ---------------------------------------------------------------------------
# audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """
    Immutable record of every user-initiated data operation.
    Requirement 9.5 — columns: log_id, user_id FK, operation, affected_record_id,
    operation_date, operation_time.
    Note: audit_log intentionally does NOT carry the six Audit_Columns (Requirement 9.8
    applies to 'every table' — audit_log is an append-only log, not a mutable table,
    so it has only its own operation timestamp columns).
    Requirement 9.7 — index on user_id.
    """

    __tablename__ = "audit_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False,
    )
    operation = Column(String(16), nullable=False)
    # NULL when the operation is not tied to a specific record
    affected_record_id = Column(Integer, nullable=True)
    operation_date = Column(Date, nullable=False)
    operation_time = Column(Time, nullable=False)
    # Task 37.4: what happened (e.g. "credential.reveal", "user.deactivate"),
    # the account it was done to and a short non-secret detail ("User→Admin").
    action = Column(String(32), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    detail = Column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "operation IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')",
            name="ck_audit_log_operation",
        ),
        # Requirement 9.7 — index on audit_log.user_id
        Index("idx_audit_log_user_id", "user_id"),
        # Task 37.4: the audit view lists newest first and filters by date.
        Index("idx_audit_log_date", "operation_date", "operation_time"),
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="audit_logs",
        foreign_keys=[user_id],
    )


# ---------------------------------------------------------------------------
# refresh_tokens (task 31.5)
# ---------------------------------------------------------------------------

class RefreshToken(AuditColumnsMixin, Base):
    """
    Server-side record of an issued refresh token.

    Only the SHA-256 of the opaque token is stored, so a database leak does
    not expose usable tokens. Rows are rotated on every refresh; ``revoked_at``
    is set on logout or rotation. Reusing a revoked token revokes the whole
    ``family_id`` (stolen-token detection).
    """

    __tablename__ = "refresh_tokens"

    refresh_token_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    family_id = Column(String(32), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    # Task 37.3 — shown in "Active sessions" (device and last activity).
    user_agent = Column(String(256), nullable=True)
    client_ip = Column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_family_id", "family_id"),
    )


# ---------------------------------------------------------------------------
# email_verification_tokens  (task 33.2)
# ---------------------------------------------------------------------------

class EmailVerificationToken(AuditColumnsMixin, Base):
    """
    One-time email verification link (Requirements 1.10, 2.8).

    Only the SHA-256 of the token travels to the database. ``used_at`` is set
    when the link is consumed; links also expire at ``expires_at``.
    """

    __tablename__ = "email_verification_tokens"

    email_verification_token_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_email_verification_tokens_user_id", "user_id"),
    )
