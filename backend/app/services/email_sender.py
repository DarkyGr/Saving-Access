"""
Outgoing email (task 33.3).

Backends (``EMAIL_BACKEND``):
  console  print the message to stdout (default; development)
  file     write one JSON file per message to ``EMAIL_OUTBOX_DIR`` (E2E tests)
  smtp     send through ``SMTP_HOST``:``SMTP_PORT`` (default 587) with
           ``SMTP_SECURITY`` starttls (default) | ssl | none, optional
           ``SMTP_USERNAME`` / ``SMTP_PASSWORD``, sender ``SMTP_FROM``.

Callers run :func:`send_email` from a FastAPI background task, so a slow or
failing mail server never fails the request; failures are logged and the
user can ask for the email again.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import smtplib
import ssl
import time
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str


def _backend() -> str:
    return os.environ.get("EMAIL_BACKEND", "console").strip().lower()


def _send_smtp(message: OutgoingEmail) -> None:
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg.set_content(message.body)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    context = ssl.create_default_context()

    if security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
    with server:
        if security == "starttls":
            server.starttls(context=context)
        if username:
            server.login(username, password)
        server.send_message(msg)


def _send_file(message: OutgoingEmail) -> None:
    outbox = Path(os.environ["EMAIL_OUTBOX_DIR"])
    outbox.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
    (outbox / name).write_text(json.dumps(asdict(message)), encoding="utf-8")


def send_email(message: OutgoingEmail) -> bool:
    """Deliver *message*; returns False (and logs) instead of raising."""
    backend = _backend()
    try:
        if backend == "smtp":
            _send_smtp(message)
        elif backend == "file":
            _send_file(message)
        else:
            print(
                f"--- email to {message.to} ---\nSubject: {message.subject}\n\n{message.body}\n---",
                flush=True,
            )
        return True
    except Exception:  # noqa: BLE001 — any delivery problem must not break the request
        logger.exception("Could not send email to %s via %s", message.to, backend)
        return False
