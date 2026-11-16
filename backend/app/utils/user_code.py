"""
Public, immutable user ID such as ``SP-7K3M9Q`` (Requirement 14.1, task 37.3).

It tells two people with similar names apart without exposing the database
id. Assigned once when the account is created and never changed.
"""

import secrets

# No 0/O, 1/I/L: easy to read aloud and to type.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
PREFIX = "SP-"
LENGTH = 6


def new_user_code() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
