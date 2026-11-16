"""
Administrative command-line tasks.

Usage (from backend/ or inside the backend container), after
``alembic upgrade head``::

    python -m app.cli create-admin --username admin --email admin@example.com
    python -m app.cli promote --username alice
    python -m app.cli verify-email --username alice
    python -m app.cli reset-2fa --username alice   # also unlocks
    python -m app.cli send-verification-reminders [--dry-run]
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


def cmd_create_admin(args: argparse.Namespace) -> None:
    if not validate_email(args.email):
        sys.exit("Invalid email address.")
    password = _read_password()
    errors = validate_password_strength(password)
    if errors:
        sys.exit("Password rejected:\n  - " + "\n  - ".join(errors))

    with SessionLocal() as db:
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


def cmd_verify_email(args: argparse.Namespace) -> None:
    """Mark a user's email as verified (support / reactivating a deactivated account)."""
    from app.utils.audit_columns import set_modification_audit

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            sys.exit(f"User '{args.username}' not found.")
        user.email_verified = True
        set_modification_audit(user, user_id=user.user_id)
        db.commit()
        print(f"'{user.username}' email marked as verified; the account is active.")


def cmd_reset_two_factor(args: argparse.Namespace) -> None:
    """Task 37.5: for the Admin who lost their phone and recovery codes (no
    other Admin can reset it from the app). Ends every session, removes the
    second factor and unlocks the account; the next sign-in sets it up."""
    from app.services.audit_service import AuditService
    from app.services.refresh_token_service import RefreshTokenService
    from app.services.two_factor import TwoFactorService
    from app.utils.audit_columns import set_modification_audit

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            sys.exit(f"User '{args.username}' not found.")
        TwoFactorService(db).reset(user)
        user.locked_at = None
        user.failed_attempts = 0
        set_modification_audit(user, user_id=user.user_id)
        RefreshTokenService(db).revoke_all(user.user_id)
        AuditService(db).log(
            user.user_id, "UPDATE", user.user_id, commit=False,
            action="user.reset_2fa", target_user_id=user.user_id, detail="cli",
        )
        db.commit()
        print(f"Two-step verification of '{user.username}' was reset; it is set up again at the next sign-in.")


def cmd_send_verification_reminders(args: argparse.Namespace) -> None:
    """Email deadline reminders to unverified users (task 34.4). Idempotent."""
    from app.phase2 import email_verification_enabled
    from app.services.email_verification_service import EmailVerificationService
    from app.utils.audit_columns import utc_date_time

    if not email_verification_enabled():
        print("Email verification is off; nothing to do.")
        return
    with SessionLocal() as db:
        names = EmailVerificationService(db).send_due_reminders(
            utc_date_time()[0], dry_run=args.dry_run
        )
    verb = "Would remind" if args.dry_run else "Reminded"
    print(f"{verb} {len(names)} user(s)" + (": " + ", ".join(names) if names else "."))


def cmd_rotate_fernet_key(args: argparse.Namespace) -> None:
    """Re-encrypt every saved credential with the first key in FERNET_KEY.

    Run with FERNET_KEY="<new>,<old>" (see EncryptorService). All rows are
    updated in one transaction: either every credential is re-encrypted or
    none is. Rows already using the new key are re-encrypted too (harmless).
    """
    from cryptography.fernet import InvalidToken

    from app.models import Credential, User
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
        # Task 37.5: two-factor secrets use the same key.
        secrets_done = 0
        for user in db.query(User).filter(
            (User.totp_secret.is_not(None)) | (User.totp_pending_secret.is_not(None))
        ).all():
            try:
                if user.totp_secret is not None:
                    user.totp_secret = encryptor.rotate(user.totp_secret)
                if user.totp_pending_secret is not None:
                    user.totp_pending_secret = encryptor.rotate(user.totp_pending_secret)
            except InvalidToken:
                db.rollback()
                sys.exit(f"The two-factor secret of user {user.user_id} cannot be decrypted. Nothing was changed.")
            secrets_done += 1
        if args.dry_run:
            db.rollback()
            print(
                f"Dry run: {len(rows)} credential(s) and {secrets_done} two-factor secret(s) "
                "can be re-encrypted. Nothing was changed."
            )
            return
        db.commit()
    print(f"Re-encrypted {len(rows)} credential(s) and {secrets_done} two-factor secret(s) with the new key. "
          'Now set FERNET_KEY="<new>" and restart.')


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Create an Admin account")
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--email", required=True)
    p_admin.set_defaults(func=cmd_create_admin)

    p_promote = sub.add_parser("promote", help="Give an existing user the Admin role")
    p_promote.add_argument("--username", required=True)
    p_promote.set_defaults(func=cmd_promote)

    p_verify = sub.add_parser(
        "verify-email", help="Mark a user's email as verified (also reactivates the account)"
    )
    p_verify.add_argument("--username", required=True)
    p_verify.set_defaults(func=cmd_verify_email)

    p_reset = sub.add_parser(
        "reset-2fa", help="Remove a user's two-step verification and unlock them (lost phone and codes)"
    )
    p_reset.add_argument("--username", required=True)
    p_reset.set_defaults(func=cmd_reset_two_factor)

    p_remind = sub.add_parser(
        "send-verification-reminders",
        help="Email unverified users whose deactivation deadline is near",
    )
    p_remind.add_argument("--dry-run", action="store_true", help="List users, send nothing")
    p_remind.set_defaults(func=cmd_send_verification_reminders)

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
