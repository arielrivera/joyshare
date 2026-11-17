"""English and Spanish for everything the server says to a person.

English text is written where it is used and doubles as the lookup key. Messages with a
changing part use T("... {n} ...", n=5) so the same sentence can be rendered in either language.
A test checks that every message in the code has a Spanish version here.
"""
import json

LANGS = ("en", "es")
LANG_COOKIE = "joyshare_lang"


class T(str):
    """A message with fill-in values. Behaves like the finished English sentence."""

    def __new__(cls, template: str, **params):
        text = super().__new__(cls, template.format(**params) if params else template)
        text.template, text.params = template, params
        return text


def render(message, lang: str = "en") -> str:
    """The message in the requested language."""
    template = getattr(message, "template", message)
    params = getattr(message, "params", {})
    if not isinstance(template, str):
        return message
    if lang == "es":
        template = ES.get(template, template)
    return template.format(**params) if params else template


def pack(message) -> str:
    """Store a message so it can be shown later in whichever language the reader uses."""
    return json.dumps({"t": getattr(message, "template", str(message)), "p": getattr(message, "params", {})})


def unpack(stored: str | None, lang: str = "en") -> str | None:
    if not stored:
        return stored
    try:
        data = json.loads(stored)
        return render(T(data["t"], **data["p"]), lang)
    except (ValueError, KeyError, TypeError):
        return render(stored, lang)  # older rows hold plain English


def pick_lang(request) -> str:
    """The reader's language: their saved choice, else what their browser prefers."""
    chosen = request.cookies.get(LANG_COOKIE)
    if chosen in LANGS:
        return chosen
    for part in request.headers.get("accept-language", "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "en"


ES = {
    # ---- links ----
    "Paste a link first.": "Primero pega un enlace.",
    "That doesn't look like a web link.": "Eso no parece un enlace web.",
    "That doesn't look like a normal video link.": "Eso no parece un enlace de video normal.",
    "{platform} is turned off on this server.": "{platform} está desactivado en este servidor.",
    "This works with links from X, YouTube, TikTok, Instagram and Facebook.":
        "Funciona con enlaces de X, YouTube, TikTok, Instagram y Facebook.",

    # ---- reading and downloading ----
    "The platform only shows this video to signed-in accounts.":
        "La plataforma solo muestra este video a cuentas con sesión iniciada.",
    "{platform} only shows this video to signed-in accounts. Connect your account under Connected accounts in the menu.":
        "{platform} solo muestra este video a cuentas con sesión iniciada. Conecta tu cuenta en Cuentas conectadas, en el menú.",
    "{platform} didn't accept your connected account. Upload a fresh cookie file under Connected accounts.":
        "{platform} no aceptó tu cuenta conectada. Sube un archivo de cookies nuevo en Cuentas conectadas.",
    "That file is too big to be a cookie file.": "Ese archivo es demasiado grande para ser un archivo de cookies.",
    "No {platform} cookies were found in that file. Export it in the cookies.txt format while signed in to {platform}.":
        "No se encontraron cookies de {platform} en ese archivo. Expórtalo en formato cookies.txt con la sesión iniciada en {platform}.",
    "Unknown platform.": "Plataforma desconocida.",
    "That account isn't connected.": "Esa cuenta no está conectada.",
    "A connected account stopped working": "Una cuenta conectada dejó de funcionar",
    "{platform} no longer accepts the account {person} connected.": "{platform} ya no acepta la cuenta que conectó {person}.",
    "This video is private.": "Este video es privado.",
    "That link doesn't point to a video that can be read.": "Ese enlace no lleva a un video que se pueda leer.",
    "No video was found at that link. It may have been removed, or the post has no video.":
        "No se encontró ningún video en ese enlace. Puede que lo hayan borrado o que la publicación no tenga video.",
    "The platform didn't answer in time. Try again in a moment.":
        "La plataforma no respondió a tiempo. Inténtalo de nuevo en un momento.",
    "The platform refused the request: {reason}": "La plataforma rechazó la solicitud: {reason}",
    "No video was found at that link.": "No se encontró ningún video en ese enlace.",
    "Live streams can't be downloaded while they are live.":
        "Las transmisiones en vivo no se pueden descargar mientras están en vivo.",
    "This video is bigger than the {mb} MB download limit. Try a smaller preset.":
        "Este video supera el límite de descarga de {mb} MB. Prueba un tamaño más pequeño.",
    "The download finished but no file was produced.": "La descarga terminó pero no se generó ningún archivo.",
    "Converting the video failed.": "Falló la conversión del video.",
    "This video has no sound.": "Este video no tiene sonido.",
    "No video was found in the download. Try Audio only.":
        "La descarga no contenía video. Prueba Solo audio.",
    "Couldn't get this video under that size. Pick a bigger size or use Audio only.":
        "No se pudo reducir el video a ese tamaño. Elige un tamaño mayor o usa Solo audio.",
    "This video's length is unknown, so it can't be fitted to a size.":
        "No se conoce la duración de este video, así que no se puede ajustar a un tamaño.",
    "This video is too long to fit in that size. Pick a bigger size or use Audio only.":
        "Este video es demasiado largo para ese tamaño. Elige un tamaño mayor o usa Solo audio.",
    "The finished file is {size} MB, over the {limit} MB limit. Use Fit a size to shrink it.":
        "El archivo final pesa {size} MB y supera el límite de {limit} MB. Usa Ajustar tamaño para reducirlo.",
    "Something went wrong on the server. The details are in the server log.":
        "Algo salió mal en el servidor. Los detalles están en el registro del servidor.",

    # ---- sizes ----
    "Best quality": "Mejor calidad",
    "Share": "Compartir",
    "Small": "Pequeño",
    "Fit a size": "Ajustar tamaño",
    "Audio only": "Solo audio",
    "Up to 1080p": "Hasta 1080p",
    "Shrink to the size you pick": "Reduce al tamaño que elijas",
    "M4A": "M4A",
    "Not available for this video.": "No disponible para este video.",
    "About {size} MB, over the {limit} MB limit.": "Unos {size} MB, supera el límite de {limit} MB.",
    "This video is too long to shrink to these sizes.": "Este video es demasiado largo para reducirlo a estos tamaños.",
    "This video's length is unknown.": "No se conoce la duración de este video.",

    # ---- jobs and files ----
    "This video is {minutes} minutes long. The limit is {limit} minutes.":
        "Este video dura {minutes} minutos. El límite es de {limit} minutos.",
    "File not found.": "Archivo no encontrado.",
    "This file has expired.": "Este archivo ha caducado.",
    "Unknown preset.": "Tamaño desconocido.",
    "Look up the link again first.": "Vuelve a buscar el enlace primero.",
    "Pick a size between 1 and {max} MB.": "Elige un tamaño entre 1 y {max} MB.",
    "The server's disk is almost full, so new videos are paused for now.":
        "El disco del servidor está casi lleno, así que los videos nuevos están en pausa por ahora.",
    "Too many videos are already in progress. Wait for some to finish.":
        "Ya hay demasiados videos en proceso. Espera a que terminen algunos.",
    "No size of this video fits within the limits.": "Ningún tamaño de este video cabe dentro de los límites.",
    "Job not found.": "Tarea no encontrada.",
    "Link not found.": "Enlace no encontrado.",
    "This video has expired.": "Este video ha caducado.",

    # ---- sign-in ----
    "Too many failed attempts. Wait a few minutes and try again.":
        "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
    "This request didn't come from this app.": "Esta solicitud no vino de esta aplicación.",
    "Sign in to continue.": "Inicia sesión para continuar.",
    "Access tokens can't manage devices or people.": "Los tokens de acceso no pueden gestionar dispositivos ni personas.",
    "Confirm it's you to continue.": "Confirma que eres tú para continuar.",
    "Only an admin can do that.": "Solo un administrador puede hacer eso.",
    "That took too long. Try again.": "Eso tardó demasiado. Inténtalo de nuevo.",
    "That code isn't valid. Codes work once and expire quickly.":
        "Ese código no es válido. Los códigos funcionan una sola vez y caducan rápido.",
    "That passkey couldn't be verified. Try again.": "No se pudo verificar esa llave de acceso. Inténtalo de nuevo.",
    "That code was already used or has expired.": "Ese código ya se usó o ha caducado.",
    "That passkey isn't registered here.": "Esa llave de acceso no está registrada aquí.",
    "Device not found.": "Dispositivo no encontrado.",
    "This is your only device. Add another one before removing it.":
        "Este es tu único dispositivo. Añade otro antes de quitarlo.",
    "Only an admin can invite people.": "Solo un administrador puede invitar personas.",
    "Give the person a name.": "Ponle un nombre a la persona.",
    "Unknown invite type.": "Tipo de invitación desconocido.",
    "Give the token a name, such as iPhone Shortcut.": "Ponle un nombre al token, por ejemplo Atajo del iPhone.",
    "Token not found.": "Token no encontrado.",
    "Person not found.": "Persona no encontrada.",
    "You can't turn off your own account.": "No puedes desactivar tu propia cuenta.",
    "The last admin can't be turned off.": "No se puede desactivar al último administrador.",
    "That name is too long.": "Ese nombre es demasiado largo.",
    "There has to be at least one admin.": "Tiene que haber al menos un administrador.",
    "Unknown choice.": "Opción desconocida.",

    # ---- admin ----
    "Unknown setting: {key}": "Ajuste desconocido: {key}",
    "{key} must be a whole number from {low} to {high}.": "{key} debe ser un número entero entre {low} y {high}.",
    "Pick at least one platform from the list.": "Elige al menos una plataforma de la lista.",
    "Target sizes must be one to eight whole numbers of MB.": "Los tamaños objetivo deben ser de uno a ocho números enteros de MB.",
    "Unknown alert.": "Alerta desconocida.",
    "The ntfy address must start with https:// or http://.": "La dirección de ntfy debe empezar por https:// o http://.",
    "A topic can use letters, numbers, - and _ (up to 64).": "Un tema puede usar letras, números, - y _ (hasta 64).",
    "The pause level must be higher than the warning level.": "El nivel de pausa debe ser mayor que el nivel de aviso.",
    "Share links can't outlive the files they point to.": "Los enlaces no pueden durar más que los archivos a los que apuntan.",
    "Set an ntfy topic first.": "Primero configura un tema de ntfy.",
    "The alert couldn't be sent. Check the ntfy address, topic and token.":
        "No se pudo enviar la alerta. Revisa la dirección, el tema y el token de ntfy.",
    "New videos are paused for now. Try again later.": "Los videos nuevos están en pausa por ahora. Inténtalo más tarde.",

    # ---- alerts ----
    "Test alert": "Alerta de prueba",
    "Alerts are working.": "Las alertas funcionan.",
    "Video ready": "Video listo",
    "{title} · {size} MB": "{title} · {size} MB",
    "Video failed ({person})": "Falló un video ({person})",
    "{title}: {reason}": "{title}: {reason}",
    "Disk almost full: new videos paused": "Disco casi lleno: videos nuevos en pausa",
    "{pct}% used ({used} of {total} GB). Free some space.": "{pct}% usado ({used} de {total} GB). Libera espacio.",
    "Disk is filling up": "El disco se está llenando",
    "{pct}% used ({used} of {total} GB).": "{pct}% usado ({used} de {total} GB).",
    "Repeated failed sign-ins": "Intentos de acceso fallidos repetidos",
    "{count} failed attempts from {ip}. That address now has to wait.":
        "{count} intentos fallidos desde {ip}. Esa dirección ahora tiene que esperar.",
    "New device added": "Dispositivo nuevo añadido",
    "{device} was registered for {person}.": "{device} se registró para {person}.",

    # ---- keeping yt-dlp current ----
    "Checking for a newer version…": "Buscando una versión más nueva…",
    "You have the newest version.": "Tienes la versión más nueva.",
    "Version {new} failed its test, so {old} stays in use.": "La versión {new} falló su prueba, así que se sigue usando la {old}.",
    "Updated from {old} to {new}. Restarting to load it.": "Actualizado de {old} a {new}. Reiniciando para cargarla.",
    "The update check failed: {reason}": "Falló la búsqueda de actualizaciones: {reason}",
    "Went back to version {old}. Restarting to load it.": "Se volvió a la versión {old}. Reiniciando para cargarla.",
    "yt-dlp update failed": "Falló la actualización de yt-dlp",
    "yt-dlp updated": "yt-dlp actualizado",
    "{old} → {new}": "{old} → {new}",
    "{platform} stopped working": "{platform} dejó de funcionar",
    "The daily test video failed: {reason}": "Falló el video de prueba diario: {reason}",
    "Unknown action.": "Acción desconocida.",

    # ---- cloud storage ----
    "Cloud storage isn't fully set up.": "El almacenamiento en la nube no está configurado del todo.",
    "Cloud storage isn't reachable right now. Try again in a moment.":
        "El almacenamiento en la nube no responde ahora. Inténtalo de nuevo en un momento.",
    "Test the connection first. Cloud storage turns on only after the test passes.":
        "Primero prueba la conexión. El almacenamiento en la nube solo se activa cuando la prueba pasa.",
    "That doesn't look right for {key}.": "Eso no parece correcto para {key}.",
    "Cloud storage upload failed": "Falló la subida al almacenamiento en la nube",
    "A finished video stayed on the server instead: {reason}": "Un video terminado se quedó en el servidor: {reason}",

    # ---- platform tests and backups ----
    "Pick platforms from the list.": "Elige plataformas de la lista.",
    "That link isn't a {platform} link.": "Ese enlace no es de {platform}.",
    "Platform tests are limited to {count} every 3 hours. Try again in {minutes} minutes.":
        "Las pruebas de plataformas están limitadas a {count} cada 3 horas. Inténtalo de nuevo en {minutes} minutos.",
    "Backup failed": "Falló la copia de seguridad",
    "It's too late to bring this video back.": "Ya es tarde para recuperar este video.",
    "Update not put live": "La actualización no se puso en marcha",
    "New code found": "Hay código nuevo",
    "{version} ({detail}). Testing it, then updating.": "{version} ({detail}). Se prueba y luego se actualiza.",
    "Updating now": "Actualizando",
    "Putting {version} live. joyshare restarts for a moment.": "Poniendo {version} en marcha. joyshare se reinicia un momento.",
    "Update finished": "Actualización terminada",
    "{version} is live now.": "{version} ya está en marcha.",
    "The update helper isn't running on the server. Turn it on there with: ./joyshare autoupdate on-request": "El ayudante de actualizaciones no está funcionando en el servidor. Actívalo allí con: ./joyshare autoupdate on-request",
    "joyshare stayed on the running version: {reason}": "joyshare se quedó con la versión que ya funcionaba: {reason}",
    "That file belongs to another video.": "Ese archivo pertenece a otro video.",
    "The file to cut from is gone. Make the video again first.": "El archivo para recortar ya no está. Vuelve a crear el video primero.",
    "Not found.": "No encontrado.",
    "Give both a start and an end for the clip.": "Indica el inicio y el final del clip.",
    "The clip must be inside the video.": "El clip debe estar dentro del video.",
    "The end must be at least 1 second after the start.": "El final debe estar al menos 1 segundo después del inicio.",
    "That clip is outside the video.": "Ese clip está fuera del video.",
    "A second copy is running": "Hay una segunda copia funcionando",
    "Another copy of this app is answering at {url}. People will look signed out at random and "
    "videos will go missing. Stop the old one with: ./joyshare retire":
        "Otra copia de esta app está respondiendo en {url}. La gente aparecerá sin sesión al azar y "
        "faltarán videos. Detén la anterior con: ./joyshare retire",
    "The cloud copy failed, the copy on the server was made: {reason}":
        "Falló la copia en la nube; la copia en el servidor sí se hizo: {reason}",
    "No backup was made: {reason}": "No se hizo ninguna copia de seguridad: {reason}",

    # ---- the page friends see ----
    "This video has expired": "Este video ha caducado",
    "Shared videos are only kept for a short time. Ask the person who sent it to share it again.":
        "Los videos compartidos solo se guardan por poco tiempo. Pídele a quien te lo envió que lo comparta otra vez.",
    "Shared video": "Video compartido",
    "From {uploader} on {platform}": "De {uploader} en {platform}",
    "Download": "Descargar",
    "shared with {name}": "compartido con {name}",
}
