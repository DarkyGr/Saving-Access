"""
Security notices by email (Requirement 14.4 / 16.7, task 37.3).

Sent after the change is saved, from a background task: a mail failure never
undoes it. Every notice tells the owner what to do if it was not them.
"""

from __future__ import annotations

from app.models import User
from app.services.email_sender import OutgoingEmail
from app.utils.audit_columns import utc_date_time

_TEXTS = {
    "en": {
        "password_changed_subject": "Save-Pass: your password was changed",
        "password_changed_body": (
            "Hello {name},\n\n"
            "The password of your Save-Pass account was changed on {when} (UTC). "
            "Your other sessions were closed.\n\n"
            "If you did not do it, contact the administrator right away: someone may know your password.\n"
        ),
    },
    "es": {
        "password_changed_subject": "Save-Pass: se cambió tu contraseña",
        "password_changed_body": (
            "Hola {name}:\n\n"
            "La contraseña de tu cuenta de Save-Pass se cambió el {when} (UTC). "
            "Se cerraron tus otras sesiones.\n\n"
            "Si no fuiste tú, avisa al administrador de inmediato: alguien podría conocer tu contraseña.\n"
        ),
    },
}


def _texts(user: User) -> dict[str, str]:
    return _TEXTS.get((user.preferred_language or "en")[:2].lower(), _TEXTS["en"])


def password_changed_email(user: User) -> OutgoingEmail:
    texts = _texts(user)
    day, time = utc_date_time()
    return OutgoingEmail(
        to=user.email,
        subject=texts["password_changed_subject"],
        body=texts["password_changed_body"].format(
            name=user.display_name or user.username,
            when=f"{day.isoformat()} {time.strftime('%H:%M')}",
        ),
    )
