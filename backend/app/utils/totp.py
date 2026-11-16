"""
Time-based one-time passwords (RFC 6238 / RFC 4226), task 37.5.

SHA-1, 6 digits, 30-second steps: what every authenticator app expects from
an ``otpauth://totp`` link. Written with the standard library only, so the
second factor adds no dependency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
# One step either side absorbs clock drift between the phone and the server.
WINDOW = 1


def new_secret() -> str:
    """160 random bits in base32 (RFC 4226 recommends at least 128)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def matching_step(secret: str, code: str, *, after: int | None, now: float | None = None) -> int | None:
    """The time step *code* belongs to, or None.

    Only steps later than *after* (the last one accepted) count, so a code
    can never be used twice (RFC 6238 §5.2).
    """
    code = "".join(code.split())
    if len(code) != DIGITS or not code.isdigit():
        return None
    centre = current_step(now)
    found = None
    for step in range(centre - WINDOW, centre + WINDOW + 1):
        # Compare every candidate so the time taken does not depend on which matched.
        if hmac.compare_digest(code_at(secret, step), code) and (after is None or step > after):
            found = step
    return found


def otpauth_uri(secret: str, account: str, issuer: str = "Save-Pass") -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"
