"""
Property-based tests for EncryptorService.

Feature: password-manager-website, Property 9: Credential Encryption Invariant

Validates: Requirements 4.10, 6.7, 8.1, 8.2, 8.3
"""

import os

import pytest
from cryptography.fernet import Fernet
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.encryptor_service import EncryptorService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_fernet_key(monkeypatch):
    """Set a freshly generated FERNET_KEY for every test.

    Using a fresh key for each test run keeps the tests self-contained and
    independent of any key that may (or may not) be set in the real
    environment.
    """
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", key)
    yield


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestEncryptorServiceUnit:
    """Concrete examples that verify basic contract of EncryptorService."""

    def test_encrypt_returns_bytes(self):
        svc = EncryptorService()
        result = svc.encrypt("hello")
        assert isinstance(result, bytes)

    def test_decrypt_round_trip(self):
        svc = EncryptorService()
        plaintext = "S3cur3P@ssword!"
        assert svc.decrypt(svc.encrypt(plaintext)) == plaintext

    def test_encrypted_differs_from_plaintext(self):
        svc = EncryptorService()
        plaintext = "password123"
        assert svc.encrypt(plaintext) != plaintext.encode()

    def test_missing_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("FERNET_KEY", raising=False)
        with pytest.raises(ValueError, match="FERNET_KEY"):
            EncryptorService()

    def test_empty_key_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", "")
        with pytest.raises(ValueError, match="FERNET_KEY"):
            EncryptorService()

    def test_encrypt_unicode_password(self):
        svc = EncryptorService()
        plaintext = "contraseña@2024!"
        assert svc.decrypt(svc.encrypt(plaintext)) == plaintext

    def test_each_encrypt_call_produces_different_token(self):
        """Fernet uses a random IV — two encryptions of the same plaintext
        must NOT produce the same ciphertext."""
        svc = EncryptorService()
        plaintext = "same_password"
        token_a = svc.encrypt(plaintext)
        token_b = svc.encrypt(plaintext)
        assert token_a != token_b


# ---------------------------------------------------------------------------
# Property 9: Credential Encryption Invariant
# ---------------------------------------------------------------------------

class TestCredentialEncryptionInvariant:
    """
    Property 9: Credential Encryption Invariant

    For any credential password string `p` (non-empty):
    1. encrypt(p) is a valid Fernet token that decrypts back to `p`.
    2. encrypt(p) never equals the encoded bytes of `p` (i.e., the ciphertext
       differs from the plaintext).

    Feature: password-manager-website, Property 9: Credential Encryption Invariant
    Validates: Requirements 4.10, 6.7, 8.1
    """

    @given(plaintext=st.text(min_size=1))
    @settings(max_examples=200)
    def test_encryption_invariant(self, plaintext: str):
        """encrypt(p) decrypts back to p and is never equal to p.

        Feature: password-manager-website, Property 9: Credential Encryption Invariant
        Validates: Requirements 4.10, 6.7, 8.1
        """
        svc = EncryptorService()

        ciphertext = svc.encrypt(plaintext)

        # 1. The ciphertext must be bytes (a valid Fernet token structure).
        assert isinstance(ciphertext, bytes), (
            f"Expected bytes, got {type(ciphertext)}"
        )

        # 2. The ciphertext must decrypt back to the original plaintext.
        recovered = svc.decrypt(ciphertext)
        assert recovered == plaintext, (
            f"Round-trip failed: encrypt then decrypt did not recover original. "
            f"Original={plaintext!r}, Recovered={recovered!r}"
        )

        # 3. The ciphertext must never equal the plaintext encoded as bytes
        #    (i.e., raw storage is always encrypted, never cleartext).
        assert ciphertext != plaintext.encode("utf-8"), (
            f"Ciphertext equals plaintext bytes for input {plaintext!r} — "
            "credential is being stored unencrypted!"
        )
