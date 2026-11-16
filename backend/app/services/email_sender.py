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


def _admin_smtp() -> dict | None:
    """The SMTP server set in System parameters (task 37.5), if any."""
    from app.services.system_settings import cached  # local: avoids an import cycle

    smtp = cached("smtp")
    return smtp if smtp and smtp.get("host") and smtp.get("from_address") else None


def _backend() -> str:
    if _admin_smtp():
        return "smtp"
    return os.environ.get("EMAIL_BACKEND", "console").strip().lower()


def _smtp_config() -> dict:
    admin = _admin_smtp()
    if admin:
        password = ""
        if admin.get("password"):
            from app.services.encryptor_service import EncryptorService

            password = EncryptorService().decrypt(admin["password"].encode("ascii"))
        return {
            "from": admin["from_address"],
            "host": admin["host"],
            "port": int(admin.get("port") or 587),
            "security": admin.get("security") or "starttls",
            "username": admin.get("username") or "",
            "password": password,
        }
    return {
        "from": os.environ["SMTP_FROM"],
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "security": os.environ.get("SMTP_SECURITY", "starttls").strip().lower(),
        "username": os.environ.get("SMTP_USERNAME", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
    }


def _send_smtp(message: OutgoingEmail) -> None:
    config = _smtp_config()
    msg = EmailMessage()
    msg["From"] = config["from"]
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg.set_content(message.body)

    host = config["host"]
    port = config["port"]
    security = config["security"]
    username = config["username"]
    password = config["password"]
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


def deliver(message: OutgoingEmail) -> str:
    """Deliver *message* now and return the backend used; raises on failure
    (the System parameters test button reports it)."""
    backend = _backend()
    if backend == "smtp":
        _send_smtp(message)
    elif backend == "file":
        _send_file(message)
    else:
        print(
            f"--- email to {message.to} ---\nSubject: {message.subject}\n\n{message.body}\n---",
            flush=True,
        )
    return backend


def send_email(message: OutgoingEmail) -> bool:
    """Deliver *message*; returns False (and logs) instead of raising."""
    try:
        deliver(message)
        return True
    except Exception:  # noqa: BLE001 — any delivery problem must not break the request
        logger.exception("Could not send email to %s via %s", message.to, _backend())
        return False
