"""
hCaptcha verification for the login form (Requirement 2.6; task 33.4).

Fails closed: a missing token, a rejected token or an unreachable hCaptcha
API all count as "not passed".
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

VERIFY_URL = "https://api.hcaptcha.com/siteverify"


def verify_captcha(token: str | None, remote_ip: str | None = None) -> bool:
    if not token:
        return False
    fields = {
        "secret": os.environ.get("HCAPTCHA_SECRET", ""),
        "response": token,
        "sitekey": os.environ.get("HCAPTCHA_SITE_KEY", ""),
    }
    if remote_ip:
        fields["remoteip"] = remote_ip
    data = urllib.parse.urlencode(fields).encode()
    try:
        with urllib.request.urlopen(VERIFY_URL, data=data, timeout=5) as response:
            body = json.load(response)
    except (OSError, ValueError):
        logger.warning("hCaptcha verification request failed", exc_info=True)
        return False
    return body.get("success") is True
