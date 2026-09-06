"""
EncryptorService — wraps Fernet symmetric encryption for credential passwords.

The Fernet key is a 32-byte URL-safe base64 value read from the FERNET_KEY
environment variable at instantiation time.  The key is never logged or
included in any API response.
"""

import os

from cryptography.fernet import Fernet


class EncryptorService:
    """Provides encrypt/decrypt operations for credential passwords."""

    def __init__(self) -> None:
        key = os.environ.get("FERNET_KEY")
        if not key:
            raise ValueError(
                "FERNET_KEY environment variable is not set. "
                "Generate a key with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        # Accept both str and bytes; Fernet requires bytes.
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

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
