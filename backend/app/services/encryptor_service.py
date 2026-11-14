"""
EncryptorService — wraps Fernet symmetric encryption for credential passwords.

FERNET_KEY holds one key, or several comma-separated keys during a key
rotation (task 32.5): new data is encrypted with the FIRST key, and any of
the keys can decrypt. Keys are never logged or included in any API response.

Zero-downtime rotation:
  1. FERNET_KEY="<new>,<old>"  and restart
  2. python -m app.cli rotate-fernet-key   (re-encrypts every row with <new>)
  3. FERNET_KEY="<new>"         and restart
"""

import os

from cryptography.fernet import Fernet, MultiFernet


def load_fernet_keys() -> list[Fernet]:
    """Parse FERNET_KEY into Fernet instances (primary first).

    :raises ValueError: if the variable is empty or any key is invalid.
    """
    raw = os.environ.get("FERNET_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ValueError(
            "FERNET_KEY environment variable is not set. "
            "Generate a key with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return [Fernet(k.encode()) for k in keys]


class EncryptorService:
    """Provides encrypt/decrypt operations for credential passwords."""

    def __init__(self) -> None:
        self._fernet = MultiFernet(load_fernet_keys())

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt *plaintext* and return the Fernet token as bytes.

        The returned value is a valid Fernet token that can later be passed to
        :meth:`decrypt` to recover the original string.

        :param plaintext: The credential password to encrypt.  Must be a
            non-empty string.
        :returns: Encrypted bytes (Fernet token).
        """
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a Fernet token and return the plaintext string.

        :param ciphertext: Bytes previously produced by :meth:`encrypt`.
        :returns: The original plaintext password as a ``str``.
        :raises cryptography.fernet.InvalidToken: If *ciphertext* is not a
            valid Fernet token or was encrypted with a different key.
        """
        return self._fernet.decrypt(ciphertext).decode("utf-8")

    def rotate(self, ciphertext: bytes) -> bytes:
        """Re-encrypt *ciphertext* with the primary key (any configured key may decrypt it)."""
        return self._fernet.rotate(ciphertext)
