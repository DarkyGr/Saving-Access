"""
Spec Phase 2 settings: email verification, account deactivation and CAPTCHA
(Requirements 1.9, 1.10, 2.6–2.9; task 33).

Both features are off unless configured, so existing deployments keep their
behaviour until the operator opts in.

Environment:
  EMAIL_VERIFICATION_ENABLED  "true" / "false" (default). When on, new
                              accounts get a deactivation deadline 30 days
                              after creation and a verification email.
  APP_BASE_URL                Public URL of the frontend, used to build the
                              verification link (required when enabled).
  VERIFICATION_TOKEN_HOURS    Lifetime of a verification link (default 48).
  VERIFICATION_REMINDER_DAYS  Days before the deadline at which unverified
                              users get a reminder with a new link
                              (default "7,1"; empty = no reminders).
  EMAIL_BACKEND               "console" (default, prints the email), "file"
                              (one JSON file per email in EMAIL_OUTBOX_DIR)
                              or "smtp" (SMTP_* variables).
  HCAPTCHA_SITE_KEY,
  HCAPTCHA_SECRET             Both set → the login form requires an hCaptcha
                              challenge. Setting only one is a startup error.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from app.models import User

DEACTIVATION_DAYS = 30  # Requirement 1.9 — fixed by the spec
_EMAIL_BACKENDS = {"console", "file", "smtp"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def email_verification_enabled() -> bool:
    """The Admin's choice in System parameters (task 37.5), else the
    EMAIL_VERIFICATION_ENABLED environment variable."""
    from app.services.system_settings import cached  # local: system_settings imports models

    chosen = cached("email_verification")
    if chosen is not None:
        return bool(chosen)
    return _flag("EMAIL_VERIFICATION_ENABLED")


def captcha_site_key() -> str | None:
    if not captcha_enabled():
        return None
    return os.environ["HCAPTCHA_SITE_KEY"].strip()


def captcha_enabled() -> bool:
    return bool(
        os.environ.get("HCAPTCHA_SITE_KEY", "").strip()
        and os.environ.get("HCAPTCHA_SECRET", "").strip()
    )


def app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", "").strip().rstrip("/")


def verification_token_lifetime() -> timedelta:
    return timedelta(hours=float(os.environ.get("VERIFICATION_TOKEN_HOURS", "48")))


def reminder_days() -> list[int]:
    """Reminder thresholds, largest first (e.g. [7, 1])."""
    raw = os.environ.get("VERIFICATION_REMINDER_DAYS", "7,1")
    days = {int(part) for part in raw.split(",") if part.strip()}
    return sorted((d for d in days if 0 <= d < DEACTIVATION_DAYS), reverse=True)


def normalize_language(language: str | None) -> str | None:
    """Map a UI language tag ("es-ES", "en") to a supported one, or None."""
    if not language:
        return None
    return "es" if language.strip().lower().startswith("es") else "en"


def deactivation_deadline_for(created: date) -> date:
    return created + timedelta(days=DEACTIVATION_DAYS)


def verification_required(user: User) -> bool:
    """True when the user must still verify their email (feature on)."""
    return email_verification_enabled() and not user.email_verified


def is_deactivated(user: User, today: date) -> bool:
    """Deactivated by the Admin (task 37.4), or Requirement 2.9: unverified
    and past the deadline.

    Accounts without a deadline (created before the feature was enabled, or
    by the admin CLI) are never deactivated automatically.
    """
    return user.deactivated_at is not None or deadline_passed(user, today)


def deadline_passed(user: User, today: date) -> bool:
    """Requirement 2.9 only: still unverified after the deadline."""
    return (
        verification_required(user)
        and user.deactivation_deadline is not None
        and today > user.deactivation_deadline
    )


def settings_problems() -> list[str]:
    """Configuration errors for validate_settings()."""
    problems: list[str] = []
    site = os.environ.get("HCAPTCHA_SITE_KEY", "").strip()
    secret = os.environ.get("HCAPTCHA_SECRET", "").strip()
    if bool(site) != bool(secret):
        problems.append("Set both HCAPTCHA_SITE_KEY and HCAPTCHA_SECRET, or neither.")

    # Task 37.5: the second factor is mandatory wherever real people sign in.
    required = os.environ.get("TWO_FACTOR_REQUIRED", "true").strip().lower()
    if os.environ.get("ENVIRONMENT", "development") == "production" and required in {"0", "false", "no", "off"}:
        problems.append("TWO_FACTOR_REQUIRED cannot be false in production.")

    if not email_verification_enabled():
        return problems

    if not app_base_url().startswith(("https://", "http://")):
        problems.append(
            "APP_BASE_URL (e.g. https://vault.example.com) is required when "
            "EMAIL_VERIFICATION_ENABLED is on."
        )
    backend = os.environ.get("EMAIL_BACKEND", "console").strip().lower()
    if backend not in _EMAIL_BACKENDS:
        problems.append(f"EMAIL_BACKEND must be one of {sorted(_EMAIL_BACKENDS)}.")
    elif backend == "smtp":
        for name in ("SMTP_HOST", "SMTP_FROM"):
            if not os.environ.get(name, "").strip():
                problems.append(f"{name} is required when EMAIL_BACKEND=smtp.")
        if os.environ.get("SMTP_SECURITY", "starttls").strip().lower() not in {"starttls", "ssl", "none"}:
            problems.append("SMTP_SECURITY must be starttls, ssl or none.")
    elif backend == "file" and not os.environ.get("EMAIL_OUTBOX_DIR", "").strip():
        problems.append("EMAIL_OUTBOX_DIR is required when EMAIL_BACKEND=file.")
    try:
        reminder_days()
    except ValueError:
        problems.append('VERIFICATION_REMINDER_DAYS must be comma-separated days, e.g. "7,1".')
    return problems
