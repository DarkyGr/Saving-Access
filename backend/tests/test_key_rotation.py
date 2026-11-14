"""
Fernet key rotation (task 32.5): multi-key FERNET_KEY + rotate-fernet-key CLI.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import cli  # noqa: E402
from app.models import Credential, User  # noqa: E402
from app.security import SettingsError, validate_settings  # noqa: E402
from app.services.encryptor_service import EncryptorService  # noqa: E402
from app.utils.audit_columns import set_creation_audit  # noqa: E402
from tests.conftest import make_test_engine  # noqa: E402

OLD = Fernet.generate_key().decode()
NEW = Fernet.generate_key().decode()


@pytest.fixture()
def session_factory(monkeypatch):
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _seed_credentials(factory, monkeypatch, plaintexts: list[str]) -> None:
    monkeypatch.setenv("FERNET_KEY", OLD)
    enc = EncryptorService()
    with factory() as db:
        user = User(username="u", email="u@example.com", password_hash="x", role="User")
        set_creation_audit(user, user_id=None)
        db.add(user)
        db.flush()
        for p in plaintexts:
            c = Credential(
                user_id=user.user_id,
                website_name="site",
                email_or_username="u@example.com",
                encrypted_password=enc.encrypt(p),
            )
            set_creation_audit(c, user_id=user.user_id)
            db.add(c)
        db.commit()


def _ciphertexts(factory) -> list[bytes]:
    with factory() as db:
        return [c.encrypted_password for c in db.query(Credential).order_by(Credential.credential_id)]


def test_multi_key_encrypts_with_first_and_decrypts_with_any(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", OLD)
    old_token = EncryptorService().encrypt("secret")

    monkeypatch.setenv("FERNET_KEY", f"{NEW},{OLD}")
    enc = EncryptorService()
    assert enc.decrypt(old_token) == "secret"
    new_token = enc.encrypt("secret")
    assert Fernet(NEW.encode()).decrypt(new_token) == b"secret"


def test_validate_settings_accepts_key_list_and_rejects_bad_member(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    monkeypatch.setenv("FERNET_KEY", f"{NEW}, {OLD}")
    validate_settings()
    monkeypatch.setenv("FERNET_KEY", f"{NEW},not-a-key")
    with pytest.raises(SettingsError, match="not a valid Fernet key"):
        validate_settings()


def test_rotation_reencrypts_every_row_with_the_new_key(session_factory, monkeypatch, capsys):
    _seed_credentials(session_factory, monkeypatch, ["alpha", "beta", "gamma"])

    monkeypatch.setenv("FERNET_KEY", f"{NEW},{OLD}")
    cli.main(["rotate-fernet-key"])
    assert "Re-encrypted 3 credential(s)" in capsys.readouterr().out

    new_only = Fernet(NEW.encode())
    assert [new_only.decrypt(t).decode() for t in _ciphertexts(session_factory)] == ["alpha", "beta", "gamma"]
    with pytest.raises(InvalidToken):
        Fernet(OLD.encode()).decrypt(_ciphertexts(session_factory)[0])

    # After dropping the old key the app still reads everything.
    monkeypatch.setenv("FERNET_KEY", NEW)
    assert EncryptorService().decrypt(_ciphertexts(session_factory)[1]) == "beta"


def test_dry_run_changes_nothing(session_factory, monkeypatch, capsys):
    _seed_credentials(session_factory, monkeypatch, ["alpha"])
    before = _ciphertexts(session_factory)
    monkeypatch.setenv("FERNET_KEY", f"{NEW},{OLD}")
    cli.main(["rotate-fernet-key", "--dry-run"])
    assert "Dry run: 1 credential(s)" in capsys.readouterr().out
    assert _ciphertexts(session_factory) == before


def test_rotation_requires_old_key_listed(session_factory, monkeypatch):
    _seed_credentials(session_factory, monkeypatch, ["alpha"])
    monkeypatch.setenv("FERNET_KEY", NEW)
    with pytest.raises(SystemExit, match="new key first"):
        cli.main(["rotate-fernet-key"])


def test_rotation_is_all_or_nothing_when_a_row_cannot_be_decrypted(session_factory, monkeypatch):
    _seed_credentials(session_factory, monkeypatch, ["alpha", "beta"])
    stranger = Fernet.generate_key().decode()
    with session_factory() as db:
        last = db.query(Credential).order_by(Credential.credential_id.desc()).first()
        last.encrypted_password = Fernet(stranger.encode()).encrypt(b"unknown key")
        db.commit()
    before = _ciphertexts(session_factory)

    monkeypatch.setenv("FERNET_KEY", f"{NEW},{OLD}")
    with pytest.raises(SystemExit, match="cannot be decrypted"):
        cli.main(["rotate-fernet-key"])
    assert _ciphertexts(session_factory) == before
