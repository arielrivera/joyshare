// Every word the interface shows, in English and Spanish.
// Server messages (errors and so on) are translated on the server.
const STRINGS = {
  en: {
    "ticker": "paste a link ✦ pick a size ✦ send it anywhere ✦ no account needed ✦ ",
    "err.generic": "Something went wrong. Try again.",
    "copy": "Copy", "copied": "Copied", "selectCopy": "Select and copy",

    "lang.switch": "Switch language", "nav.menu": "Menu",
    "style.open": "Change the name and look",
    "style.title": "Make it yours",
    "style.name": "Name at the top",
    "style.nameHelp": "Shown here and on the pages your friends open. Saved to your account.",
    "style.font": "Lettering",
    "style.theme": "Colors",
    "style.done": "Done",
    "theme.void": "Void", "theme.acid": "Acid", "theme.sunset": "Sunset", "theme.zine": "Zine", "theme.clay": "Clay", "theme.win95": "Windows 95", "theme.comic": "Comic", "theme.vapor": "Vaporwave",

    "auth.welcome": "Welcome back",
    "auth.welcomeHelp": "Use the passkey saved on this device: Face ID, Touch ID or your screen lock.",
    "auth.signin": "Sign in with a passkey",
    "join.titleNew": "New device?",
    "join.titleSetup": "Set up {name}",
    "join.helpNew": "On a device that's already signed in, open Devices and choose \"Add a device\". Enter the code it shows.",
    "join.helpSetup": "Enter the setup code printed in the server log to register your first device.",
    "join.code": "Code",
    "join.deviceName": "Name for this device",
    "join.submit": "Register this device",
    "pk.closed": "The passkey prompt was closed. Try again when you're ready.",
    "pk.exists": "This device is already registered. Use Sign in instead.",
    "pk.unsupported": "This browser doesn't support passkeys.",
    "pk.failed": "The passkey didn't work. Try again.",
    "boot.down": "The server isn't answering. Check that it is running.",

    "nav.devices": "Devices", "nav.signout": "Sign out", "nav.admin": "admin",

    "link.label": "Video link",
    "link.placeholder": "Paste a link from X, YouTube, Instagram or Facebook",
    "link.lookup": "Look up", "link.looking": "Looking…", "link.paste": "Paste",
    "media.untitled": "Untitled video",
    "media.experimental": "This platform is experimental and hasn't been tested yet.",
    "media.pick": "Pick a size", "media.make": "Make it",
    "preset.best": "Best quality", "preset.720": "Share", "preset.480": "Small",
    "preset.fit": "Fit a size", "preset.audio": "Audio only",
    "preset.fitDetail": "Shrink to the size you pick",
    "preset.convert": "Needs converting, so it takes longer.",
    "size.about": "about {size}", "size.unknown": "size unknown",
    "fit.under": "under {mb} MB ({h}p)", "fit.target": "Target size",

    "job.queued": "Waiting in line", "job.cancel": "Cancel", "job.failed": "That didn't work.",
    "stage.starting": "Starting", "stage.downloading": "Downloading",
    "stage.converting": "Converting", "stage.done": "Done", "stage.working": "Working",

    "res.ready": "Ready", "res.reused": "Ready (you already had this one)",
    "res.kept": "kept until {when}",
    "res.share": "Share", "res.download": "Download", "res.link": "Get a link for friends",
    "res.tooBig": "This file is too big for the share sheet. Use Download or a link instead.",
    "res.linkNote": "Anyone with this link can watch until {when}.",
    "res.linkLabel": "Share link",
    "res.another": "Another size", "res.new": "New link",

    "recent.title": "Recent", "recent.expired": "Expired", "recent.failed": "Failed",
    "recent.canceled": "Canceled", "recent.progress": "In progress",
    "recent.download": "Download ({size})", "recent.fit": "Fit {mb} MB",
    "short.best": "Best", "short.720": "720p", "short.480": "480p", "short.audio": "Audio",

    "dev.back": "← Back",
    "dev.yours": "Your devices",
    "dev.yoursHelp": "Each device signs in with its own passkey. Only these devices can open this app as you.",
    "dev.add": "Add a device", "dev.this": "(this device)",
    "dev.added": "Added {when}", "dev.lastUsed": "last used {when}", "dev.remove": "Remove",
    "dev.scanDevice": "On the new device, scan this with the camera. It opens ready to register.",
    "dev.scanPerson": "Have {name} scan this on their own device. It creates their account.",
    "dev.orType": "Or type this code:", "dev.expires": "Works once, until {when}.",
    "dev.qrAlt": "QR code for the invite link",
    "tok.title": "Access tokens",
    "tok.help": "For the iPhone Shortcut and other scripts. A token can add videos as you, but can't manage devices or people.",
    "tok.placeholder": "Name, for example iPhone Shortcut", "tok.create": "Create token",
    "tok.copyNow": "Copy this token now. It is shown only once.",
    "tok.created": "Created {when}", "tok.never": "never used", "tok.revoke": "Revoke",
    "tok.nameLabel": "Token name", "tok.valueLabel": "New token",
    "ppl.title": "People",
    "ppl.help": "People you invite get their own account and only see their own videos.",
    "ppl.placeholder": "Name of the person to invite", "ppl.invite": "Invite", "ppl.you": "(you)",
    "ppl.devices1": "1 device", "ppl.devicesN": "{n} devices",
    "ppl.videos1": "1 video", "ppl.videosN": "{n} videos",
    "ppl.off": "turned off", "ppl.turnOn": "Turn on", "ppl.turnOff": "Turn off",
    "ppl.nameLabel": "Person's name",
    "role.admin": "admin", "role.member": "member",
    "out.title": "Sign out everywhere",
    "out.help": "Signs you out on every device. Your passkeys keep working, so you can sign back in.",
  },
  es: {
    "ticker": "pega un enlace ✦ elige un tamaño ✦ envíalo a donde quieras ✦ sin cuenta ✦ ",
    "err.generic": "Algo salió mal. Inténtalo de nuevo.",
    "copy": "Copiar", "copied": "Copiado", "selectCopy": "Selecciona y copia",

    "lang.switch": "Cambiar idioma", "nav.menu": "Menú",
    "style.open": "Cambiar el nombre y el estilo",
    "style.title": "Hazlo tuyo",
    "style.name": "Nombre de arriba",
    "style.nameHelp": "Se muestra aquí y en las páginas que abren tus amigos. Se guarda en tu cuenta.",
    "style.font": "Letra",
    "style.theme": "Colores",
    "style.done": "Listo",
    "theme.void": "Vacío", "theme.acid": "Ácido", "theme.sunset": "Atardecer", "theme.zine": "Fanzine", "theme.clay": "Arcilla", "theme.win95": "Windows 95", "theme.comic": "Cómic", "theme.vapor": "Vaporwave",

    "auth.welcome": "Hola de nuevo",
    "auth.welcomeHelp": "Usa la llave de acceso guardada en este dispositivo: Face ID, Touch ID o el bloqueo de pantalla.",
    "auth.signin": "Entrar con llave de acceso",
    "join.titleNew": "¿Dispositivo nuevo?",
    "join.titleSetup": "Configura {name}",
    "join.helpNew": "En un dispositivo con la sesión iniciada, abre Dispositivos y elige \"Añadir un dispositivo\". Escribe el código que muestra.",
    "join.helpSetup": "Escribe el código de configuración que aparece en el registro del servidor para registrar tu primer dispositivo.",
    "join.code": "Código",
    "join.deviceName": "Nombre de este dispositivo",
    "join.submit": "Registrar este dispositivo",
    "pk.closed": "Se cerró la ventana de la llave de acceso. Inténtalo cuando quieras.",
    "pk.exists": "Este dispositivo ya está registrado. Usa Entrar.",
    "pk.unsupported": "Este navegador no admite llaves de acceso.",
    "pk.failed": "La llave de acceso no funcionó. Inténtalo de nuevo.",
    "boot.down": "El servidor no responde. Comprueba que esté en marcha.",

    "nav.devices": "Dispositivos", "nav.signout": "Salir", "nav.admin": "admin",

    "link.label": "Enlace del video",
    "link.placeholder": "Pega un enlace de X, YouTube, Instagram o Facebook",
    "link.lookup": "Buscar", "link.looking": "Buscando…", "link.paste": "Pegar",
    "media.untitled": "Video sin título",
    "media.experimental": "Esta plataforma es experimental y aún no se ha probado.",
    "media.pick": "Elige un tamaño", "media.make": "Crear",
    "preset.best": "Mejor calidad", "preset.720": "Compartir", "preset.480": "Pequeño",
    "preset.fit": "Ajustar tamaño", "preset.audio": "Solo audio",
    "preset.fitDetail": "Reduce al tamaño que elijas",
    "preset.convert": "Hay que convertirlo, así que tarda más.",
    "size.about": "unos {size}", "size.unknown": "tamaño desconocido",
    "fit.under": "menos de {mb} MB ({h}p)", "fit.target": "Tamaño objetivo",

    "job.queued": "En cola", "job.cancel": "Cancelar", "job.failed": "Eso no funcionó.",
    "stage.starting": "Empezando", "stage.downloading": "Descargando",
    "stage.converting": "Convirtiendo", "stage.done": "Listo", "stage.working": "Trabajando",

    "res.ready": "Listo", "res.reused": "Listo (ya lo tenías)",
    "res.kept": "se guarda hasta {when}",
    "res.share": "Compartir", "res.download": "Descargar", "res.link": "Crear enlace para amigos",
    "res.tooBig": "Este archivo es demasiado grande para compartirlo directamente. Usa Descargar o un enlace.",
    "res.linkNote": "Cualquiera con este enlace puede verlo hasta {when}.",
    "res.linkLabel": "Enlace para compartir",
    "res.another": "Otro tamaño", "res.new": "Nuevo enlace",

    "recent.title": "Recientes", "recent.expired": "Caducado", "recent.failed": "Falló",
    "recent.canceled": "Cancelado", "recent.progress": "En proceso",
    "recent.download": "Descargar ({size})", "recent.fit": "Ajustado a {mb} MB",
    "short.best": "Mejor", "short.720": "720p", "short.480": "480p", "short.audio": "Audio",

    "dev.back": "← Volver",
    "dev.yours": "Tus dispositivos",
    "dev.yoursHelp": "Cada dispositivo entra con su propia llave de acceso. Solo estos dispositivos pueden abrir la app como tú.",
    "dev.add": "Añadir un dispositivo", "dev.this": "(este dispositivo)",
    "dev.added": "Añadido {when}", "dev.lastUsed": "último uso {when}", "dev.remove": "Quitar",
    "dev.scanDevice": "En el dispositivo nuevo, escanea esto con la cámara. Se abre listo para registrarse.",
    "dev.scanPerson": "Pídele a {name} que escanee esto en su propio dispositivo. Así se crea su cuenta.",
    "dev.orType": "O escribe este código:", "dev.expires": "Funciona una vez, hasta {when}.",
    "dev.qrAlt": "Código QR del enlace de invitación",
    "tok.title": "Tokens de acceso",
    "tok.help": "Para el Atajo del iPhone y otros scripts. Un token puede añadir videos en tu nombre, pero no gestionar dispositivos ni personas.",
    "tok.placeholder": "Nombre, por ejemplo Atajo del iPhone", "tok.create": "Crear token",
    "tok.copyNow": "Copia este token ahora. Solo se muestra una vez.",
    "tok.created": "Creado {when}", "tok.never": "nunca usado", "tok.revoke": "Revocar",
    "tok.nameLabel": "Nombre del token", "tok.valueLabel": "Token nuevo",
    "ppl.title": "Personas",
    "ppl.help": "Las personas que invitas tienen su propia cuenta y solo ven sus propios videos.",
    "ppl.placeholder": "Nombre de la persona a invitar", "ppl.invite": "Invitar", "ppl.you": "(tú)",
    "ppl.devices1": "1 dispositivo", "ppl.devicesN": "{n} dispositivos",
    "ppl.videos1": "1 video", "ppl.videosN": "{n} videos",
    "ppl.off": "desactivada", "ppl.turnOn": "Activar", "ppl.turnOff": "Desactivar",
    "ppl.nameLabel": "Nombre de la persona",
    "role.admin": "admin", "role.member": "miembro",
    "out.title": "Cerrar sesión en todas partes",
    "out.help": "Cierra tu sesión en todos los dispositivos. Tus llaves de acceso siguen funcionando, así que puedes volver a entrar.",
  },
};

let LANG = "en";

function t(key, vars) {
  let text = (STRINGS[LANG] && STRINGS[LANG][key]) || STRINGS.en[key] || key;
  if (vars) for (const [name, value] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, value);
  return text;
}

// Fill in every element marked with data-i18n (text), data-i18n-ph (placeholder) or data-i18n-aria.
function translatePage() {
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-ph]")) el.placeholder = t(el.dataset.i18nPh);
  for (const el of document.querySelectorAll("[data-i18n-aria]")) el.setAttribute("aria-label", t(el.dataset.i18nAria));
  for (const el of document.querySelectorAll("[data-i18n-alt]")) el.alt = t(el.dataset.i18nAlt);
}
