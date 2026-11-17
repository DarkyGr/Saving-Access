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
        "two_factor_subject": "Save-Pass: two-step verification was set up",
        "two_factor_body": (
            "Hello {name},\n\n"
            "Two-step verification was set up on a device for your Save-Pass account on {when} (UTC), "
            "and new recovery codes were issued (the old ones no longer work).\n\n"
            "If you did not do it, contact the administrator right away.\n"
        ),
        "recovery_subject": "Save-Pass: new recovery codes",
        "recovery_body": (
            "Hello {name},\n\n"
            "New recovery codes were issued for your Save-Pass account on {when} (UTC). The old ones no longer work.\n\n"
            "If you did not do it, contact the administrator right away.\n"
        ),
        "two_factor_reset_subject": "Save-Pass: two-step verification was reset",
        "two_factor_reset_body": (
            "Hello {name},\n\n"
            "The administrator reset the two-step verification of your Save-Pass account on {when} (UTC). "
            "Your sessions were closed; the next time you sign in you will set it up again.\n\n"
            "If you did not ask for it, contact the administrator.\n"
        ),
        "reset_subject": "Save-Pass: reset your password",
        "reset_body": (
            "Hello {name},\n\n"
            "Someone asked to reset the password of your Save-Pass account on {when} (UTC). "
            "If it was you, choose a new password with this link (valid for 1 hour, works once):\n\n{link}\n\n"
            "Your saved passwords are kept, every session is closed, and you will still need your two-step code to sign in.\n\n"
            "If it was not you, ignore this email: your password does not change.\n"
        ),
        "export_subject": "Save-Pass: your passwords were exported",
        "export_body": (
            "Hello {name},\n\n"
            "All the passwords saved in your Save-Pass account were downloaded on {when} (UTC).\n\n"
            "The file is not encrypted: keep it safe and delete it when you no longer need it. "
            "If you did not do it, change your password and contact the administrator right away.\n"
        ),
        "deleted_subject": "Save-Pass: your account was deleted",
        "deleted_body": (
            "Hello {name},\n\n"
            "Your Save-Pass account and every password saved in it were deleted on {when} (UTC). "
            "This cannot be undone.\n\n"
            "If you did not do it, contact the administrator right away.\n"
        ),
        "locked_subject": "Save-Pass: your account was locked",
        "locked_body": (
            "Hello {name},\n\n"
            "Your Save-Pass account was locked on {when} (UTC) after too many wrong passwords or codes in a row.\n\n"
            "If it was you, unlock it with this link (valid for 24 hours, works once):\n\n{link}\n\n"
            "Signing in with your password and a valid two-factor or recovery code, resetting your password, "
            "or the administrator can also unlock it.\n\n"
            "If it was not you, someone is trying your password: change it after unlocking.\n"
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
        "two_factor_subject": "Save-Pass: se configuró la verificación en dos pasos",
        "two_factor_body": (
            "Hola {name}:\n\n"
            "Se configuró la verificación en dos pasos en un dispositivo para tu cuenta de Save-Pass el {when} (UTC) "
            "y se generaron códigos de recuperación nuevos (los anteriores ya no sirven).\n\n"
            "Si no fuiste tú, avisa al administrador de inmediato.\n"
        ),
        "recovery_subject": "Save-Pass: códigos de recuperación nuevos",
        "recovery_body": (
            "Hola {name}:\n\n"
            "Se generaron códigos de recuperación nuevos para tu cuenta de Save-Pass el {when} (UTC). Los anteriores ya no sirven.\n\n"
            "Si no fuiste tú, avisa al administrador de inmediato.\n"
        ),
        "two_factor_reset_subject": "Save-Pass: se reinició la verificación en dos pasos",
        "two_factor_reset_body": (
            "Hola {name}:\n\n"
            "El administrador reinició la verificación en dos pasos de tu cuenta de Save-Pass el {when} (UTC). "
            "Se cerraron tus sesiones; la próxima vez que entres la configurarás de nuevo.\n\n"
            "Si no lo pediste, habla con el administrador.\n"
        ),
        "reset_subject": "Save-Pass: restablece tu contraseña",
        "reset_body": (
            "Hola {name}:\n\n"
            "Alguien pidió restablecer la contraseña de tu cuenta de Save-Pass el {when} (UTC). "
            "Si fuiste tú, elige una contraseña nueva con este enlace (vale 1 hora y una sola vez):\n\n{link}\n\n"
            "Tus contraseñas guardadas se conservan, se cierran todas las sesiones y seguirás necesitando tu código de dos pasos para entrar.\n\n"
            "Si no fuiste tú, ignora este correo: tu contraseña no cambia.\n"
        ),
        "export_subject": "Save-Pass: se exportaron tus contraseñas",
        "export_body": (
            "Hola {name}:\n\n"
            "Todas las contraseñas guardadas en tu cuenta de Save-Pass se descargaron el {when} (UTC).\n\n"
            "El archivo no está cifrado: guárdalo en un lugar seguro y bórralo cuando ya no lo necesites. "
            "Si no fuiste tú, cambia tu contraseña y avisa al administrador de inmediato.\n"
        ),
        "deleted_subject": "Save-Pass: se borró tu cuenta",
        "deleted_body": (
            "Hola {name}:\n\n"
            "Tu cuenta de Save-Pass y todas las contraseñas guardadas en ella se borraron el {when} (UTC). "
            "No se puede deshacer.\n\n"
            "Si no fuiste tú, avisa al administrador de inmediato.\n"
        ),
        "locked_subject": "Save-Pass: se bloqueó tu cuenta",
        "locked_body": (
            "Hola {name}:\n\n"
            "Tu cuenta de Save-Pass se bloqueó el {when} (UTC) tras demasiadas contraseñas o códigos incorrectos seguidos.\n\n"
            "Si fuiste tú, desbloquéala con este enlace (vale 24 horas y una sola vez):\n\n{link}\n\n"
            "También se desbloquea al entrar con tu contraseña y un código de dos pasos o de recuperación válido, "
            "al restablecer tu contraseña o si lo hace el administrador.\n\n"
            "Si no fuiste tú, alguien está probando tu contraseña: cámbiala después de desbloquear.\n"
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


def two_factor_enabled_email(user: User) -> OutgoingEmail:
    """Requirement 16.7: 2FA set up (first time or a new device)."""
    return _notice(user, "two_factor")


def recovery_codes_email(user: User) -> OutgoingEmail:
    """Requirement 16.7: recovery codes replaced."""
    return _notice(user, "recovery")


def two_factor_reset_email(user: User) -> OutgoingEmail:
    return _notice(user, "two_factor_reset")


def password_reset_email(user: User, link: str) -> OutgoingEmail:
    """Task 37.5 (Requirement 16.3): the one-time reset link."""
    return _notice(user, "reset", link=link)


def export_email(user: User) -> OutgoingEmail:
    """Task 35.8 (Requirement 19.1)."""
    return _notice(user, "export")


def account_deleted_email(user: User) -> OutgoingEmail:
    """Task 35.8 (Requirement 19.2): built before the row is anonymised."""
    return _notice(user, "deleted")


def account_locked_email(user: User, link: str) -> OutgoingEmail:
    """Task 37.5 (Requirement 16.2): the lock and how to undo it."""
    return _notice(user, "locked", link=link)


def account_reactivated_email(user: User) -> OutgoingEmail:
    return _notice(user, "reactivated")
