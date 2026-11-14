"""
Administrative command-line tasks.

Usage (from backend/ or inside the backend container), after
``alembic upgrade head``::

    python -m app.cli seed
    python -m app.cli create-admin --username admin --email admin@example.com
    python -m app.cli promote --username alice

``create-admin`` reads the password from the ``ADMIN_PASSWORD`` env var, or
prompts for it (twice) when the variable is not set.  The password must meet
the same strength rules as sign-up (Requirement 1.5).
"""

import argparse
import getpass
import os
import sys
from datetime import date, datetime, timezone

from app.database import SessionLocal
from app.models import User
from app.security import hash_password
from app.seed import seed_default_profiles
from app.services.auth_service import validate_password_strength
from app.utils.email_validator import validate_email


def _read_password() -> str:
    env_pw = os.environ.get("ADMIN_PASSWORD")
    if env_pw:
        return env_pw
    first = getpass.getpass("Admin password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        sys.exit("Passwords do not match.")
    return first


def cmd_seed(_args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        seed_default_profiles(db)
    print("Default profiles are in place.")


def cmd_create_admin(args: argparse.Namespace) -> None:
    if not validate_email(args.email):
        sys.exit("Invalid email address.")
    password = _read_password()
    errors = validate_password_strength(password)
    if errors:
        sys.exit("Password rejected:\n  - " + "\n  - ".join(errors))

    with SessionLocal() as db:
        seed_default_profiles(db)
        clash = (
            db.query(User)
            .filter((User.username == args.username) | (User.email == args.email))
            .first()
        )
        if clash:
            sys.exit("A user with that username or email already exists. Use 'promote'.")
        user = User(
            username=args.username,
            email=args.email,
            password_hash=hash_password(password),
            role="Admin",
            email_verified=True,
            creation_date=date.today(),
            creation_time=datetime.now(timezone.utc).time().replace(tzinfo=None),
        )
        db.add(user)
        db.commit()
        user.creation_user_id = user.user_id
        db.commit()
        print(f"Admin '{user.username}' created (user_id={user.user_id}).")


def cmd_promote(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            sys.exit(f"User '{args.username}' not found.")
        user.role = "Admin"
        db.commit()
        print(f"'{user.username}' is now Admin.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="Create the default profiles (run alembic upgrade head first)").set_defaults(func=cmd_seed)

    p_admin = sub.add_parser("create-admin", help="Create an Admin account")
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--email", required=True)
    p_admin.set_defaults(func=cmd_create_admin)

    p_promote = sub.add_parser("promote", help="Give an existing user the Admin role")
    p_promote.add_argument("--username", required=True)
    p_promote.set_defaults(func=cmd_promote)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
