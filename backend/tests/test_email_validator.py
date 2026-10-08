"""
Property-based tests for the email validation utility.

Feature: password-manager-website

Properties tested:
  Property 16: Email Validation Rejects Invalid Formats and Disposable Domains
               — Validates: Requirements 4.13

Design reference (design.md — Property 16):
  For any string submitted as an email address, the validator SHALL accept the
  string if and only if it conforms to RFC 5321 format AND its domain is not on
  the disposable-domain blocklist.
"""

import string

import pytest
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from app.utils.email_validator import validate_email, _load_blocklist

# ---------------------------------------------------------------------------
# Reference oracle helpers
# ---------------------------------------------------------------------------
# These mirror the acceptance criteria without delegating to the implementation
# itself, so that property tests have an independent ground truth.


_RFC5321_MAX_TOTAL = 254
_RFC5321_MAX_LOCAL = 64

# Known-valid domains that must NEVER appear in the blocklist.
_KNOWN_VALID_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "example.com",
    "test.org",
    "company.net",
    "university.edu",
]

# Known disposable domains that MUST be rejected by the validator.
_KNOWN_DISPOSABLE_DOMAINS = [
    "mailinator.com",
    "guerrillamail.com",
    "temp-mail.org",
    "throwaway.email",
    "yopmail.com",
    "sharklasers.com",
    "trashmail.com",
    "trashmail.net",
    "maildrop.cc",
    "discard.email",
    "fakeinbox.com",
    "tempinbox.com",
    "spam4.me",
]


def _domain_is_blocked(domain: str) -> bool:
    """Return True if *domain* is in the loaded blocklist."""
    return domain.lower() in _load_blocklist()


# ---------------------------------------------------------------------------
# Unit tests — concrete examples
# ---------------------------------------------------------------------------


class TestValidateEmailUnit:
    """Concrete example-based tests for validate_email."""

    # --- Valid addresses ---
    @pytest.mark.parametrize("email", [
        "alice@gmail.com",
        "bob.smith@example.com",
        "user+tag@company.net",
        "test_user@university.edu",
        "user123@yahoo.com",
        "a@b.co",
        "user@test.org",
    ])
    def test_valid_emails_accepted(self, email):
        assert validate_email(email) is True, (
            f"Expected valid email to be accepted: {email!r}"
        )

    # --- Invalid format ---
    @pytest.mark.parametrize("email", [
        "notanemail",             # no @
        "double@@example.com",   # double @
        "@nodomain.com",         # empty local part
        "noDomain@",             # no domain
        "spaces in@example.com", # space in local
        "user@",                 # missing domain
        "",                      # empty string
        "a" * 65 + "@example.com",  # local part > 64 chars
        "a@" + "b" * 64 + ".com",   # long but valid domain label
    ])
    def test_invalid_format_rejected(self, email):
        assert validate_email(email) is False, (
            f"Expected invalid email to be rejected: {email!r}"
        )

    def test_total_length_over_254_rejected(self):
        # Build an address that totals > 254 chars
        local = "a" * 64
        domain_label = "b" * 63
        # local(64) + @(1) + domain_label(63) + .(1) + "com"(3) = 132 — still valid
        # Push total over 254
        long_email = "a" * 64 + "@" + "b" * 60 + "." + "c" * 60 + ".com"
        assert len(long_email) > 254
        assert validate_email(long_email) is False

    # --- Disposable domains ---
    @pytest.mark.parametrize("domain", _KNOWN_DISPOSABLE_DOMAINS)
    def test_known_disposable_domains_rejected(self, domain):
        email = f"user@{domain}"
        assert validate_email(email) is False, (
            f"Expected disposable-domain email to be rejected: {email!r}"
        )

    # --- Known-safe domains ---
    @pytest.mark.parametrize("domain", _KNOWN_VALID_DOMAINS)
    def test_known_valid_domains_accepted(self, domain):
        email = f"user@{domain}"
        assert validate_email(email) is True, (
            f"Expected valid-domain email to be accepted: {email!r}"
        )

    def test_non_string_input_rejected(self):
        assert validate_email(None) is False   # type: ignore[arg-type]
        assert validate_email(123) is False    # type: ignore[arg-type]
        assert validate_email([]) is False     # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Property 16: Email Validation Rejects Invalid Formats and Disposable Domains
# Validates: Requirements 4.13
# ---------------------------------------------------------------------------


class TestEmailValidationProperty16:
    """
    Property 16: Email Validation Rejects Invalid Formats and Disposable Domains

    For any string submitted as an email address, the validator SHALL accept the
    string if and only if it conforms to RFC 5321 format AND its domain is not
    on the disposable-domain blocklist.

    Feature: password-manager-website, Property 16: Email Validation
    Validates: Requirements 4.13
    """

    # ------------------------------------------------------------------
    # Sub-test A: hypothesis-generated valid-looking emails (st.emails())
    # All addresses produced by st.emails() should pass the format check;
    # some may be rejected if their domain happens to appear in the blocklist.
    # ------------------------------------------------------------------

    @given(email=st.emails())
    @settings(max_examples=200)
    def test_hypothesis_emails_either_valid_or_blocked(self, email):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        Every address from st.emails() is structurally valid per Hypothesis.
        validate_email() must therefore return True UNLESS the domain is on the
        blocklist — in which case returning False is correct.

        The invariant is: we never wrongly reject a structurally valid email
        UNLESS it is on the blocklist.
        """
        result = validate_email(email)

        if result is False:
            # Rejection is only acceptable if the domain is on the blocklist.
            at_idx = email.rfind("@")
            domain = email[at_idx + 1:].lower() if at_idx != -1 else ""
            assert _domain_is_blocked(domain), (
                f"validate_email rejected a structurally valid email that is NOT "
                f"on the blocklist: {email!r} (domain={domain!r})"
            )
        else:
            # Acceptance is always fine for a structurally valid address.
            assert result is True

    # ------------------------------------------------------------------
    # Sub-test B: arbitrary strings — validate_email must accept iff
    # format is valid AND domain is not blocked.
    # ------------------------------------------------------------------

    @given(s=st.text(min_size=0, max_size=300))
    @settings(max_examples=200)
    def test_arbitrary_strings_accepted_iff_valid_and_not_blocked(self, s):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        For any arbitrary string:
          - If accepted → it must pass the RFC 5321 structural check AND its
            domain must not be on the blocklist.
          - If rejected → it fails the structural check OR its domain is blocked.
        """
        result = validate_email(s)

        if result is True:
            # Must have a single @, local ≤ 64, total ≤ 254, valid domain shape.
            at_count = s.count("@")
            assert at_count == 1, (
                f"Accepted email has {at_count} @ symbol(s): {s!r}"
            )
            local_part, domain = s.split("@", 1)
            assert len(local_part) <= _RFC5321_MAX_LOCAL, (
                f"Accepted email has local part > 64 chars: {s!r}"
            )
            assert len(s) <= _RFC5321_MAX_TOTAL, (
                f"Accepted email exceeds 254 total chars: {s!r}"
            )
            assert len(domain) > 0 and "." in domain, (
                f"Accepted email has an invalid domain: {s!r}"
            )
            # Domain must NOT be on the blocklist
            assert not _domain_is_blocked(domain), (
                f"Accepted email has a blocked domain: {s!r} (domain={domain!r})"
            )

    # ------------------------------------------------------------------
    # Sub-test C: manually constructed known-invalid strings
    # ------------------------------------------------------------------

    @given(
        local=st.text(
            alphabet=string.ascii_letters + string.digits + "._+-",
            min_size=1,
            max_size=64,
        ),
        domain=st.sampled_from(_KNOWN_VALID_DOMAINS),
    )
    @settings(max_examples=200)
    def test_valid_local_and_known_domain_accepted(self, local, domain):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        Any combination of a simple alphanumeric local part and a known valid
        domain should be accepted (assuming the full address stays ≤ 254 chars).
        """
        email = f"{local}@{domain}"
        assume(len(email) <= _RFC5321_MAX_TOTAL)
        assume(len(local) <= _RFC5321_MAX_LOCAL)

        result = validate_email(email)
        assert result is True, (
            f"Expected acceptance for valid-format email with safe domain: {email!r}"
        )

    @given(
        local=st.text(
            alphabet=string.ascii_letters + string.digits,
            min_size=1,
            max_size=30,
        ),
        domain=st.sampled_from(_KNOWN_DISPOSABLE_DOMAINS),
    )
    @settings(max_examples=200)
    def test_disposable_domain_always_rejected(self, local, domain):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        Any email whose domain is on the known disposable-domain list must be
        rejected regardless of the local part.
        """
        email = f"{local}@{domain}"
        result = validate_email(email)
        assert result is False, (
            f"Expected rejection for disposable-domain email: {email!r}"
        )

    @given(
        text_without_at=st.text(
            alphabet=string.ascii_letters + string.digits + ".",
            min_size=1,
            max_size=100,
        )
    )
    @settings(max_examples=200)
    def test_strings_without_at_always_rejected(self, text_without_at):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        Any string that contains no @ character can never be a valid email.
        """
        assume("@" not in text_without_at)
        result = validate_email(text_without_at)
        assert result is False, (
            f"Expected rejection for string without @: {text_without_at!r}"
        )

    @given(
        local=st.text(
            alphabet=string.ascii_letters,
            min_size=65,   # force local part > 64 chars
            max_size=100,
        ),
        domain=st.sampled_from(_KNOWN_VALID_DOMAINS),
    )
    @settings(max_examples=200)
    def test_oversized_local_part_always_rejected(self, local, domain):
        """
        Feature: password-manager-website, Property 16: Email Validation
        Validates: Requirements 4.13

        Any email with a local part exceeding 64 characters must be rejected
        (RFC 5321 §4.5.3.1.1).
        """
        email = f"{local}@{domain}"
        assert len(local) > _RFC5321_MAX_LOCAL
        result = validate_email(email)
        assert result is False, (
            f"Expected rejection for oversized local part: {email!r}"
        )
