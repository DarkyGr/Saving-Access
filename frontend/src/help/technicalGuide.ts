import type { Guide } from "./types";

/** Technical guide for the Admin (Requirement 17.2, task 37.6). */
export const TECHNICAL_GUIDE: Guide = {
  en: [
    {
      id: "roles",
      title: "Roles and permissions",
      blocks: [
        "There are two roles: User (their own vault) and Admin (the same plus administration). Each screen and each API call asks for a named permission; nothing is allowed by role name alone.",
        "No role can see another person's saved passwords, the Admin included. Administration works on accounts, never on their contents.",
        "Change roles in Manage Users. You cannot change your own role, so there is always an Admin.",
      ],
    },
    {
      id: "users",
      title: "Managing accounts",
      blocks: [
        "Manage Users searches by name, email or user ID (SP-…) and filters by role and status: active, deactivated, locked, email not verified.",
        [
          "Deactivate: asks for a reason, signs the person out everywhere at once and emails them the reason. Their saved passwords are kept.",
          "Reactivate: lets them sign in again. An account closed for not verifying its email gets a new deadline.",
          "Unlock: lifts a lock caused by wrong passwords or codes.",
          "Reset 2FA: for someone who lost their phone and recovery codes. Their sessions end and they set it up again at the next sign-in.",
        ],
        "These changes ask for your password again when it was last confirmed in this session more than the configured minutes ago (5 by default).",
      ],
    },
    {
      id: "audit",
      title: "Audit log",
      blocks: [
        "Administration → Audit log lists who did what and when, newest first: sign-ups, sign-ins, password changes and resets, two-step changes, credential operations (by number only) and every administration action.",
        "Filter by action, by person (whoever did it or whoever it was done to) and by date. Date filters use UTC days; times are shown in your time zone. At most the latest 1000 matches are shown.",
      ],
    },
    {
      id: "parameters",
      title: "System parameters",
      blocks: [
        "Administration → System parameters holds the security values, each with its range and suggested value: failed attempts before locking, minutes before administration asks for the password again (0 = every time), idle minutes, maximum session length and how much Extend adds.",
        "Nothing is saved if a value is out of range. Changes apply from the next sign-in or request.",
      ],
    },
    {
      id: "email",
      title: "Email (SMTP) and sign-up verification",
      blocks: [
        "In System parameters → Email set the outgoing mail server: server, port, encryption (STARTTLS on 587 or SSL/TLS on 465 for most providers), user, sender address and password. Leave the server empty to use the installation's settings file instead.",
        "The SMTP password is stored encrypted and never shown again; leave the field empty to keep it. Send a test email to check the settings: the result, or the server's error, appears right away.",
        "Sign-up email verification sends new accounts a link; accounts not verified within 30 days are deactivated (reminders go out before). It needs the server's public address (APP_BASE_URL).",
      ],
    },
    {
      id: "lost-admin",
      title: "If you lose your own phone and recovery codes",
      blocks: [
        "Nobody else can reset the Admin's two-step verification from the app. On the server, from an administrator terminal in the repository folder:",
        ["powershell -ExecutionPolicy Bypass -File ops\\windows\\with-production.ps1 reset-2fa --username <name>"],
        "It also unlocks the account and ends its sessions; the next sign-in sets two-step verification up again.",
      ],
    },
    {
      id: "install-update",
      title: "Installing an update",
      blocks: [
        "From an administrator terminal in the repository folder:",
        ["git pull", "python scripts\\release.py --to Y:\\Apps\\Save-Pass", "curl.exe -k https://localhost:8443/api/health"],
        "The release stops the API, applies database migrations, swaps the application (the previous one stays in app.old and is restored if something fails) and starts it again. Reload the browser with Ctrl+F5 afterwards.",
      ],
    },
    {
      id: "backup",
      title: "Backups and restore",
      blocks: [
        "A scheduled task makes an encrypted database backup every day in the installation's Backup folder. Keep FERNET_KEY and BACKUP_KEY in your password manager: without FERNET_KEY the saved passwords cannot be recovered, even from a backup.",
        "Every Sunday a scheduled task restores the newest backup into a scratch database and compares it with the live one (log in Backup\\db\\restore-test.log). A real restore is described in docs/local-install.md (\"Restore for real\").",
      ],
    },
    {
      id: "cli",
      title: "Command-line tools",
      blocks: [
        "Run them with ops\\windows\\with-production.ps1 <command> from an administrator terminal:",
        [
          "create-admin --username <name> --email <email>: first Admin.",
          "promote --username <name>: make an account Admin.",
          "verify-email --username <name>: mark the email verified (also reactivates a deadline deactivation).",
          "reset-2fa --username <name>: remove two-step verification and unlock.",
          "rotate-fernet-key [--dry-run]: re-encrypt passwords and 2FA secrets with a new key (FERNET_KEY=\"<new>,<old>\").",
          "send-verification-reminders [--dry-run]: what the scheduled task runs.",
        ],
      ],
    },
    {
      id: "troubleshooting",
      title: "Troubleshooting",
      blocks: [
        [
          "Everyone is asked to sign in again after an update: expected when sessions change; sign in again.",
          "Codes are refused: the phone's clock must be automatic; codes are valid for 30 seconds and each works once.",
          "Emails do not arrive: send a test email from System parameters and read the error; check spam.",
          "The API does not answer: check /api/health and the Save-Pass tasks in Task Scheduler; run the release again if the update was interrupted.",
        ],
      ],
    },
  ],
  es: [
    {
      id: "roles",
      title: "Roles y permisos",
      blocks: [
        "Hay dos roles: User (su propia bóveda) y Admin (lo mismo más la administración). Cada pantalla y cada llamada a la API pide un permiso con nombre; nada se permite solo por el nombre del rol.",
        "Ningún rol puede ver las contraseñas guardadas de otra persona, tampoco el Admin. La administración trabaja sobre las cuentas, nunca sobre su contenido.",
        "Cambia roles en Administrar Usuarios. No puedes cambiar tu propio rol, así siempre hay un Admin.",
      ],
    },
    {
      id: "users",
      title: "Administrar cuentas",
      blocks: [
        "Administrar Usuarios busca por nombre, correo o ID de usuario (SP-…) y filtra por rol y estado: activa, desactivada, bloqueada, correo sin verificar.",
        [
          "Desactivar: pide un motivo, cierra la sesión de la persona en todos lados al momento y le envía el motivo por correo. Sus contraseñas guardadas se conservan.",
          "Reactivar: le permite volver a entrar. Una cuenta cerrada por no verificar su correo recibe un plazo nuevo.",
          "Desbloquear: quita un bloqueo causado por contraseñas o códigos incorrectos.",
          "Reiniciar 2FA: para quien perdió su teléfono y sus códigos de recuperación. Sus sesiones terminan y lo configura de nuevo al entrar.",
        ],
        "Estos cambios vuelven a pedir tu contraseña si la confirmaste en esta sesión hace más de los minutos configurados (5 por defecto).",
      ],
    },
    {
      id: "audit",
      title: "Auditoría",
      blocks: [
        "Administración → Auditoría muestra quién hizo qué y cuándo, lo más reciente primero: registros, inicios de sesión, cambios y restablecimientos de contraseña, cambios del segundo paso, operaciones con credenciales (solo por número) y cada acción de administración.",
        "Filtra por acción, por persona (quien lo hizo o a quien se le hizo) y por fecha. Los filtros de fecha usan días en UTC; las horas se muestran en tu zona horaria. Se muestran como mucho las últimas 1000 coincidencias.",
      ],
    },
    {
      id: "parameters",
      title: "Parámetros del sistema",
      blocks: [
        "Administración → Parámetros del sistema guarda los valores de seguridad, cada uno con su rango y valor sugerido: intentos fallidos antes de bloquear, minutos antes de que la administración vuelva a pedir la contraseña (0 = siempre), minutos de inactividad, duración máxima de la sesión y cuánto añade Extender.",
        "No se guarda nada si un valor está fuera de rango. Los cambios aplican desde el siguiente inicio de sesión o petición.",
      ],
    },
    {
      id: "email",
      title: "Correo (SMTP) y verificación al registrarse",
      blocks: [
        "En Parámetros del sistema → Correo configura el servidor de correo saliente: servidor, puerto, cifrado (STARTTLS en 587 o SSL/TLS en 465 en la mayoría de proveedores), usuario, dirección del remitente y contraseña. Deja el servidor vacío para usar el archivo de configuración de la instalación.",
        "La contraseña SMTP se guarda cifrada y nunca se vuelve a mostrar; deja el campo vacío para conservarla. Envía un correo de prueba para comprobarla: el resultado, o el error del servidor, aparece al momento.",
        "La verificación al registrarse envía un enlace a las cuentas nuevas; las que no verifican en 30 días se desactivan (antes se envían recordatorios). Necesita la dirección pública del servidor (APP_BASE_URL).",
      ],
    },
    {
      id: "lost-admin",
      title: "Si pierdes tu propio teléfono y tus códigos",
      blocks: [
        "Nadie más puede reiniciar el segundo paso del Admin desde la app. En el servidor, desde una terminal de administrador en la carpeta del repositorio:",
        ["powershell -ExecutionPolicy Bypass -File ops\\windows\\with-production.ps1 reset-2fa --username <nombre>"],
        "También desbloquea la cuenta y termina sus sesiones; el siguiente inicio de sesión vuelve a configurar la verificación en dos pasos.",
      ],
    },
    {
      id: "install-update",
      title: "Instalar una actualización",
      blocks: [
        "Desde una terminal de administrador en la carpeta del repositorio:",
        ["git pull", "python scripts\\release.py --to Y:\\Apps\\Save-Pass", "curl.exe -k https://localhost:8443/api/health"],
        "La publicación detiene la API, aplica las migraciones de la base de datos, cambia la aplicación (la anterior queda en app.old y se restaura si algo falla) y la vuelve a arrancar. Después recarga el navegador con Ctrl+F5.",
      ],
    },
    {
      id: "backup",
      title: "Respaldos y restauración",
      blocks: [
        "Una tarea programada hace cada día un respaldo cifrado de la base de datos en la carpeta Backup de la instalación. Guarda FERNET_KEY y BACKUP_KEY en tu gestor de contraseñas: sin FERNET_KEY las contraseñas guardadas no se pueden recuperar, ni siquiera desde un respaldo.",
        "Cada domingo una tarea programada restaura el respaldo más reciente en una base de datos de prueba y la compara con la real (registro en Backup\\db\\restore-test.log). La restauración real está en docs/local-install.md (\"Restore for real\").",
      ],
    },
    {
      id: "cli",
      title: "Herramientas de línea de comandos",
      blocks: [
        "Ejecútalas con ops\\windows\\with-production.ps1 <comando> desde una terminal de administrador:",
        [
          "create-admin --username <nombre> --email <correo>: primer Admin.",
          "promote --username <nombre>: hacer Admin a una cuenta.",
          "verify-email --username <nombre>: marcar el correo como verificado (también reactiva una desactivación por plazo).",
          "reset-2fa --username <nombre>: quitar la verificación en dos pasos y desbloquear.",
          "rotate-fernet-key [--dry-run]: volver a cifrar contraseñas y secretos 2FA con una clave nueva (FERNET_KEY=\"<nueva>,<vieja>\").",
          "send-verification-reminders [--dry-run]: lo que ejecuta la tarea programada.",
        ],
      ],
    },
    {
      id: "troubleshooting",
      title: "Solución de problemas",
      blocks: [
        [
          "A todos se les pide entrar de nuevo después de una actualización: es normal cuando cambian las sesiones; vuelve a entrar.",
          "Los códigos no se aceptan: la hora del teléfono debe ser automática; los códigos valen 30 segundos y cada uno sirve una vez.",
          "No llegan los correos: envía un correo de prueba desde Parámetros del sistema y lee el error; revisa el spam.",
          "La API no responde: revisa /api/health y las tareas de Save-Pass en el Programador de tareas; vuelve a ejecutar la publicación si la actualización se interrumpió.",
        ],
      ],
    },
  ],
};
