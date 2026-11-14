"""
Administrative command-line tasks.

Usage (from backend/ or inside the backend container), after
``alembic upgrade head``::

    python -m app.cli seed
    python -m app.cli create-admin --username admin --email admin@example.com
    python -m app.cli promote --username alice
    python -m app.cli rotate-fernet-key [--dry-run]

``create-admin`` reads the password from the ``ADMIN_PASSWORD`` env var, or
prompts for it (twice) when the variable is not set.  The password must meet
the same strength rules as sign-up (Requirement 1.5).
"""

import argparse
import getpass
import os
import sys

from app.database import SessionLocal
from app.models import User
from app.security import hash_password
from app.seed import seed_default_profiles
from app.services.auth_service import validate_password_strength
from app.utils.audit_columns import utc_date_time
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
        now_date, now_time = utc_date_time()
        user = User(
            username=args.username,
            email=args.email,
            password_hash=hash_password(password),
            role="Admin",
            email_verified=True,
            creation_date=now_date,
            creation_time=now_time,
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


def cmd_rotate_fernet_key(args: argparse.Namespace) -> None:
    """Re-encrypt every saved credential with the first key in FERNET_KEY.

    Run with FERNET_KEY="<new>,<old>" (see EncryptorService). All rows are
    updated in one transaction: either every credential is re-encrypted or
    none is. Rows already using the new key are re-encrypted too (harmless).
    """
    from cryptography.fernet import InvalidToken

    from app.models import Credential
    from app.services.encryptor_service import EncryptorService, load_fernet_keys

    if len(load_fernet_keys()) < 2:
        sys.exit('FERNET_KEY must list the new key first and the old key(s) after it: "<new>,<old>".')

    encryptor = EncryptorService()
    with SessionLocal() as db:
        rows = db.query(Credential).all()
        try:
            for row in rows:
                row.encrypted_password = encryptor.rotate(row.encrypted_password)
        except InvalidToken:
            db.rollback()
            sys.exit(
                f"Credential {row.credential_id} cannot be decrypted with any key in "
                "FERNET_KEY. Nothing was changed."
            )
        if args.dry_run:
            db.rollback()
            print(f"Dry run: {len(rows)} credential(s) can be re-encrypted. Nothing was changed.")
            return
        db.commit()
    print(f"Re-encrypted {len(rows)} credential(s) with the new key. "
          'Now set FERNET_KEY="<new>" and restart.')


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

    p_rotate = sub.add_parser(
        "rotate-fernet-key",
        help='Re-encrypt all credentials with the first key of FERNET_KEY="<new>,<old>"',
    )
    p_rotate.add_argument("--dry-run", action="store_true", help="Check every row decrypts; change nothing")
    p_rotate.set_defaults(func=cmd_rotate_fernet_key)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
