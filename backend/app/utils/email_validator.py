"""
Email validation utility.

Provides :func:`validate_email` which checks:
  1. RFC 5321 structural format (local-part@domain, length limits).
  2. The domain is not on the bundled disposable-domain blocklist.

Requirements: 4.13
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RFC 5321 regex
# ---------------------------------------------------------------------------
# Constraints enforced:
#   - Total length ≤ 254 characters (RFC 5321 §4.5.3.1.3)
#   - Local part ≤ 64 characters (RFC 5321 §4.5.3.1.1)
#   - Domain labels: 1–63 chars each, start/end with alphanumeric,
#     may contain hyphens internally
#   - At least one dot in the domain portion
#
# We deliberately keep this as a *pragmatic* regex rather than a full
# RFC 5321 parser; it covers the vast majority of real-world addresses
# while remaining readable and testable.

_LOCAL_PART = r"[a-zA-Z0-9._%+\-]{1,64}"
_DOMAIN_LABEL = r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
_DOMAIN = rf"(?:{_DOMAIN_LABEL}\.)+[a-zA-Z]{{2,}}"

_EMAIL_RE = re.compile(
    rf"^(?P<local>{_LOCAL_PART})@(?P<domain>{_DOMAIN})$",
    re.ASCII,
)

# ---------------------------------------------------------------------------
# Disposable-domain blocklist
# ---------------------------------------------------------------------------

_BLOCKLIST_PATH = Path(__file__).parent / "disposable_domains.txt"


@lru_cache(maxsize=1)
def _load_blocklist() -> frozenset[str]:
    """Load and cache the disposable-domain blocklist.

    Returns an empty frozenset (and logs a warning) if the file is missing
    or unreadable, so that the rest of the validation pipeline still works.
    """
    try:
        with open(_BLOCKLIST_PATH, encoding="utf-8") as fh:
            domains: set[str] = set()
            for raw_line in fh:
                line = raw_line.strip().lower()
                if line and not line.startswith("#"):
                    domains.add(line)
            return frozenset(domains)
    except OSError as exc:
        logger.warning(
            "Could not load disposable-domain blocklist from %s: %s",
            _BLOCKLIST_PATH,
            exc,
        )
        return frozenset()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_email(email: str) -> bool:
    """Return True iff *email* is structurally valid AND its domain is not
    on the disposable-domain blocklist.

    Validation steps:
      1. Total length check: reject if > 254 characters.
      2. Regex match against the RFC 5321 structural pattern.
      3. Domain lookup in the disposable-domain blocklist (case-insensitive).

    :param email: The raw email string submitted by the user.
    :returns: ``True`` if the address passes all checks, ``False`` otherwise.
    """
    if not isinstance(email, str):
        return False

    # Step 1 — total length (RFC 5321 §4.5.3.1.3)
    if len(email) > 254:
        return False

    # Step 2 — structural regex
    match = _EMAIL_RE.fullmatch(email)
    if match is None:
        return False

    # Step 3 — disposable-domain check (normalise to lowercase)
    domain: str = match.group("domain").lower()
    blocklist = _load_blocklist()
    if domain in blocklist:
        return False

    return True
