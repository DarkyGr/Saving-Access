import type { Guide } from "./types";

/**
 * User guide (Requirement 17.1, task 37.6). A block is a paragraph (string)
 * or a list (array of strings). Section ids are stable: links point at them.
 */
export const USER_GUIDE: Guide = {
  en: [
    {
      id: "start",
      title: "Getting started",
      blocks: [
        "Save-Pass keeps your passwords encrypted. Only you can see the passwords you save: not even the administrator can read them.",
        "Create an account from the login page (Sign Up). Your account password must have at least 12 characters with an uppercase letter, a lowercase letter, a digit and one of @ $ !.",
        "Your account password is the key to everything: Save-Pass asks for it again every time you reveal, edit or delete a saved password.",
      ],
    },
    {
      id: "two-step",
      title: "Two-step verification",
      blocks: [
        "Every account uses a second step after the password: a 6-digit code from an authenticator app on your phone.",
        [
          "Install an authenticator app: Google Authenticator, Microsoft Authenticator, Aegis, 2FAS or similar.",
          "The first time you sign in, scan the QR code with the app (or type the key shown under it) and enter the code it shows.",
          "Each code changes every 30 seconds and works once. If one is refused, wait for the next one and check that your phone's time is automatic.",
        ],
        "To move it to a new phone, open Settings → Two-step verification → Use a new phone. Your current phone keeps working until the new one is confirmed.",
      ],
    },
    {
      id: "recovery-codes",
      title: "Recovery codes",
      blocks: [
        "When you set up two-step verification you get 10 recovery codes, shown only once. Each one lets you sign in once without your phone: choose \"Use a recovery code\" on the code screen.",
        "Keep them somewhere safe and away from this device: printed, or in another password manager. A notice appears when 3 or fewer are left; create new ones in Settings (the old ones stop working).",
        "If you lose both your phone and your codes, ask the administrator to reset your two-step verification.",
      ],
    },
    {
      id: "forgot-password",
      title: "Forgot your password?",
      blocks: [
        "On the login page choose \"Forgot your password?\" and type your username or email. If the account exists you receive a link that works once, for 1 hour.",
        "The new password follows the same rules as at sign-up. Your saved passwords are kept, every session is closed, and signing in still asks for your two-step code.",
      ],
    },
    {
      id: "locked",
      title: "Locked account",
      blocks: [
        "After several wrong passwords or codes in a row (5 unless the administrator changed it), the account locks to stop someone guessing. You get an email with an unlock link valid for 24 hours.",
        "It also unlocks when you sign in with your password and a valid two-step or recovery code, when you reset your password, or when the administrator unlocks it.",
        "If you did not cause the lock, someone may know or be guessing your password: change it after unlocking.",
      ],
    },
    {
      id: "save",
      title: "Saving a password",
      blocks: [
        "Choose Save Credential in the menu. Fill in the website or app name, the email or username you use there (tick \"This site uses a username instead of an email\" when needed) and the password.",
        "Save-Pass asks for your account password to confirm. The password is encrypted before it is stored.",
      ],
    },
    {
      id: "generator",
      title: "Generating a strong password",
      blocks: [
        "On Save Credential and Edit, choose \"Generate a strong password\" under the password field. Pick the length (8 to 64) and the kinds of characters; \"Avoid look-alikes\" leaves out l, 1, O, 0 and similar ones, handy if you ever type it by hand.",
        "The password is created in your browser with its secure random source and shows its strength. \"Use this password\" puts it in the field; nothing is saved until you save the form. Your choices are remembered on this device.",
      ],
    },
    {
      id: "find",
      title: "Finding and revealing passwords",
      blocks: [
        "My Credentials lists everything you saved, sorted by name. Search by site or username (capitals and accents do not matter), filter by login type and switch between list and cards; pages show 10 to 100 entries.",
        "Reveal shows a password after you confirm your account password. It hides itself again after a few seconds.",
        "Copy puts the revealed password in the clipboard; Save-Pass clears the clipboard 30 seconds later if it still holds that password.",
      ],
    },
    {
      id: "edit-delete",
      title: "Editing and deleting",
      blocks: [
        "Edit changes the name, the login or the password of an entry; Delete removes it after a confirmation. Both ask for your account password.",
        "Home shows your most recently changed passwords with the date of the change.",
      ],
    },
    {
      id: "settings",
      title: "Settings",
      blocks: [
        "Open Settings from your name at the top right.",
        [
          "Profile: your user ID (SP-…, never changes), display name and picture (one of the icons or your own photo, reduced before it is sent).",
          "Preferences: language, the screen that opens after signing in, light, dark or same-as-device theme, accent colour and private mode.",
          "Password: change it with your current one; your other devices are signed out and you get an email.",
          "Two-step verification: new phone or new recovery codes.",
          "Active sessions: where your account is signed in; end any other device's session.",
        ],
      ],
    },
    {
      id: "private-mode",
      title: "Private mode",
      blocks: [
        "The eye at the top of the screen hides usernames and emails in lists, useful when someone can see your screen. It stays on until you turn it off.",
      ],
    },
    {
      id: "sessions",
      title: "Sessions and automatic sign-out",
      blocks: [
        "For safety, a session ends after a while without activity (15 minutes by default) and after a maximum time (8 hours by default). Activity in any tab counts.",
        "A minute before, a notice offers \"Stay signed in\" or \"Extend\". If the session ends, the login page tells you why.",
        "Log Out (in the menu under your name) ends the session at once on this device.",
      ],
    },
    {
      id: "emails",
      title: "Emails you may receive",
      blocks: [
        "Save-Pass emails you when your password changes, when two-step verification or recovery codes change, when your account is locked, deactivated or reactivated, and for links you ask for (verify email, reset password).",
        "If you get one for something you did not do, change your password and tell the administrator.",
      ],
    },
  ],
  es: [
    {
      id: "start",
      title: "Primeros pasos",
      blocks: [
        "Save-Pass guarda tus contraseñas cifradas. Solo tú puedes ver las contraseñas que guardas: ni siquiera el administrador puede leerlas.",
        "Crea una cuenta desde la página de inicio de sesión (Registrarse). La contraseña de tu cuenta debe tener al menos 12 caracteres con una mayúscula, una minúscula, un número y uno de @ $ !.",
        "La contraseña de tu cuenta es la llave de todo: Save-Pass la vuelve a pedir cada vez que revelas, editas o borras una contraseña guardada.",
      ],
    },
    {
      id: "two-step",
      title: "Verificación en dos pasos",
      blocks: [
        "Todas las cuentas usan un segundo paso después de la contraseña: un código de 6 dígitos de una app de autenticación en tu teléfono.",
        [
          "Instala una app de autenticación: Google Authenticator, Microsoft Authenticator, Aegis, 2FAS u otra parecida.",
          "La primera vez que entres, escanea el código QR con la app (o escribe la clave que aparece debajo) y escribe el código que muestra.",
          "Cada código cambia cada 30 segundos y sirve una vez. Si uno no se acepta, espera al siguiente y revisa que la hora del teléfono sea automática.",
        ],
        "Para pasarla a otro teléfono, abre Configuración → Verificación en dos pasos → Usar otro teléfono. El teléfono actual sigue funcionando hasta que confirmes el nuevo.",
      ],
    },
    {
      id: "recovery-codes",
      title: "Códigos de recuperación",
      blocks: [
        "Al configurar la verificación en dos pasos recibes 10 códigos de recuperación, que solo se muestran una vez. Cada uno te deja entrar una vez sin el teléfono: elige \"Usar un código de recuperación\" en la pantalla del código.",
        "Guárdalos en un lugar seguro y lejos de este dispositivo: impresos o en otro gestor de contraseñas. Aparece un aviso cuando quedan 3 o menos; crea nuevos en Configuración (los anteriores dejan de servir).",
        "Si pierdes el teléfono y los códigos, pide al administrador que reinicie tu verificación en dos pasos.",
      ],
    },
    {
      id: "forgot-password",
      title: "¿Olvidaste tu contraseña?",
      blocks: [
        "En la página de inicio de sesión elige \"¿Olvidaste tu contraseña?\" y escribe tu usuario o correo. Si la cuenta existe recibes un enlace que sirve una vez, durante 1 hora.",
        "La contraseña nueva sigue las mismas reglas que al registrarte. Tus contraseñas guardadas se conservan, se cierran todas las sesiones y al entrar se sigue pidiendo tu código de dos pasos.",
      ],
    },
    {
      id: "locked",
      title: "Cuenta bloqueada",
      blocks: [
        "Tras varias contraseñas o códigos incorrectos seguidos (5 salvo que el administrador lo cambie), la cuenta se bloquea para que nadie pueda adivinar. Recibes un correo con un enlace de desbloqueo válido 24 horas.",
        "También se desbloquea al entrar con tu contraseña y un código de dos pasos o de recuperación válido, al restablecer tu contraseña o si el administrador la desbloquea.",
        "Si no provocaste tú el bloqueo, alguien podría conocer o estar probando tu contraseña: cámbiala después de desbloquear.",
      ],
    },
    {
      id: "save",
      title: "Guardar una contraseña",
      blocks: [
        "Elige Guardar Credencial en el menú. Escribe el nombre del sitio o la app, el correo o usuario que usas ahí (marca \"Este sitio usa un usuario en lugar de un correo electrónico\" cuando haga falta) y la contraseña.",
        "Save-Pass pide la contraseña de tu cuenta para confirmar. La contraseña se cifra antes de guardarse.",
      ],
    },
    {
      id: "generator",
      title: "Generar una contraseña segura",
      blocks: [
        "En Guardar Credencial y Editar, elige \"Generar una contraseña segura\" debajo del campo de contraseña. Escoge el largo (8 a 64) y los tipos de caracteres; \"Evitar parecidos\" deja fuera l, 1, O, 0 y similares, útil si alguna vez la escribes a mano.",
        "La contraseña se crea en tu navegador con su fuente aleatoria segura y muestra qué tan fuerte es. \"Usar esta contraseña\" la pone en el campo; no se guarda nada hasta que guardes el formulario. Tus opciones se recuerdan en este dispositivo.",
      ],
    },
    {
      id: "find",
      title: "Buscar y revelar contraseñas",
      blocks: [
        "Mis Credenciales muestra todo lo que guardaste, ordenado por nombre. Busca por sitio o usuario (mayúsculas y acentos no importan), filtra por tipo de acceso y cambia entre lista y tarjetas; cada página muestra de 10 a 100 entradas.",
        "Revelar muestra una contraseña después de confirmar la contraseña de tu cuenta. Se vuelve a ocultar sola tras unos segundos.",
        "Copiar pone la contraseña revelada en el portapapeles; Save-Pass lo borra 30 segundos después si todavía la contiene.",
      ],
    },
    {
      id: "edit-delete",
      title: "Editar y borrar",
      blocks: [
        "Editar cambia el nombre, el acceso o la contraseña de una entrada; Borrar la elimina tras una confirmación. Ambas piden la contraseña de tu cuenta.",
        "Inicio muestra las contraseñas cambiadas más recientemente con la fecha del cambio.",
      ],
    },
    {
      id: "settings",
      title: "Configuración",
      blocks: [
        "Abre Configuración desde tu nombre arriba a la derecha.",
        [
          "Perfil: tu ID de usuario (SP-…, nunca cambia), nombre visible e imagen (uno de los iconos o tu propia foto, reducida antes de enviarse).",
          "Preferencias: idioma, la pantalla que se abre al entrar, tema claro, oscuro o igual que el dispositivo, color de acento y modo privado.",
          "Contraseña: cámbiala con la actual; tus otros dispositivos cierran sesión y recibes un correo.",
          "Verificación en dos pasos: otro teléfono o códigos de recuperación nuevos.",
          "Sesiones activas: dónde está abierta tu cuenta; termina la sesión de cualquier otro dispositivo.",
        ],
      ],
    },
    {
      id: "private-mode",
      title: "Modo privado",
      blocks: [
        "El ojo arriba en la pantalla oculta usuarios y correos en las listas, útil cuando alguien puede ver tu pantalla. Sigue activo hasta que lo apagues.",
      ],
    },
    {
      id: "sessions",
      title: "Sesiones y cierre automático",
      blocks: [
        "Por seguridad, la sesión termina tras un rato sin actividad (15 minutos por defecto) y tras un tiempo máximo (8 horas por defecto). La actividad en cualquier pestaña cuenta.",
        "Un minuto antes aparece un aviso con \"Seguir conectado\" o \"Extender\". Si la sesión termina, la página de inicio de sesión te dice por qué.",
        "Cerrar Sesión (en el menú bajo tu nombre) termina la sesión en este dispositivo al momento.",
      ],
    },
    {
      id: "emails",
      title: "Correos que puedes recibir",
      blocks: [
        "Save-Pass te escribe cuando cambia tu contraseña, cuando cambian la verificación en dos pasos o los códigos de recuperación, cuando tu cuenta se bloquea, se desactiva o se reactiva, y con los enlaces que pidas (verificar correo, restablecer contraseña).",
        "Si recibes uno por algo que no hiciste, cambia tu contraseña y avisa al administrador.",
      ],
    },
  ],
};
