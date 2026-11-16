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
        "deactivated_subject": "Save-Pass: your account was deactivated",
        "deactivated_body": (
            "Hello {name},\n\n"
            "The administrator deactivated your Save-Pass account on {when} (UTC). "
            "You cannot sign in and your sessions were closed. Your saved passwords are kept.\n\n"
            "Reason: {reason}\n\n"
            "If you think this is a mistake, contact the administrator.\n"
        ),
        "reactivated_subject": "Save-Pass: your account was reactivated",
        "reactivated_body": (
            "Hello {name},\n\n"
            "The administrator reactivated your Save-Pass account on {when} (UTC). You can sign in again.\n"
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
        "deactivated_subject": "Save-Pass: se desactivó tu cuenta",
        "deactivated_body": (
            "Hola {name}:\n\n"
            "El administrador desactivó tu cuenta de Save-Pass el {when} (UTC). "
            "No puedes iniciar sesión y se cerraron tus sesiones. Tus contraseñas guardadas se conservan.\n\n"
            "Motivo: {reason}\n\n"
            "Si crees que es un error, habla con el administrador.\n"
        ),
        "reactivated_subject": "Save-Pass: se reactivó tu cuenta",
        "reactivated_body": (
            "Hola {name}:\n\n"
            "El administrador reactivó tu cuenta de Save-Pass el {when} (UTC). Ya puedes iniciar sesión.\n"
        ),
    },
}


def _texts(user: User) -> dict[str, str]:
    return _TEXTS.get((user.preferred_language or "en")[:2].lower(), _TEXTS["en"])


def _notice(user: User, kind: str, **values: str) -> OutgoingEmail:
    texts = _texts(user)
    day, time = utc_date_time()
    return OutgoingEmail(
        to=user.email,
        subject=texts[f"{kind}_subject"],
        body=texts[f"{kind}_body"].format(
            name=user.display_name or user.username,
            when=f"{day.isoformat()} {time.strftime('%H:%M')}",
            **values,
        ),
    )


def password_changed_email(user: User) -> OutgoingEmail:
    return _notice(user, "password_changed")


def account_deactivated_email(user: User, reason: str) -> OutgoingEmail:
    """Task 37.4 (Requirement 15.2): tells the owner why."""
    return _notice(user, "deactivated", reason=reason)


def account_reactivated_email(user: User) -> OutgoingEmail:
    return _notice(user, "reactivated")
