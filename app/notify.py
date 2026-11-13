"""Push alerts to the admin's phone through ntfy (https://ntfy.sh or a self-hosted server).

Alerts are a convenience: sending one must never break the thing that triggered it.
Each event can be switched off in the settings. Alerts are written in the admin's language.
"""
import json
import logging
import urllib.request

from . import config, db, i18n, settings
from .i18n import T  # noqa: F401  (handy for callers: notify.T)

log = logging.getLogger("joyshare.notify")

# event -> (priority, emoji tag shown by ntfy)
EVENTS = {
    "job_done": ("low", "white_check_mark"),
    "job_failed": ("high", "x"),
    "disk_warn": ("high", "floppy_disk"),
    "disk_paused": ("urgent", "rotating_light"),
    "new_device": ("high", "iphone"),
    "failed_signins": ("high", "lock"),
    "ytdlp_updated": ("low", "arrows_counterclockwise"),
    "ytdlp_failed": ("high", "warning"),
    "platform_check_failed": ("high", "no_entry"),
    "cookies_rejected": ("high", "cookie"),
    "storage_failed": ("high", "cloud"),
    "test": ("default", "wave"),
}
PRIORITY = {"low": 2, "default": 3, "high": 4, "urgent": 5}


def _post(url: str, payload: dict, token: str | None) -> None:
    """The one place that talks to the network. Tests replace it."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=6) as response:
        response.read()


def admin_lang(conn) -> str:
    row = conn.execute("SELECT prefs FROM users WHERE role='admin' AND disabled=0 ORDER BY id LIMIT 1").fetchone()
    try:
        lang = json.loads(row["prefs"]).get("lang") if row and row["prefs"] else None
    except ValueError:
        lang = None
    return lang if lang in i18n.LANGS else "en"


def send(conn, event: str, title, message, click: str | None = None) -> bool:
    """Send one alert. Returns True if it went out, False if alerts are off or it failed."""
    try:
        cfg = settings.get_all(conn)
        if not cfg["ntfy_topic"] or not cfg["alerts"].get(event, True):
            return False
        priority, tag = EVENTS[event]
        lang = admin_lang(conn)
        payload = {
            "topic": cfg["ntfy_topic"],
            "title": i18n.render(title, lang),
            "message": i18n.render(message, lang),
            "priority": PRIORITY[priority],
            "tags": [tag],
        }
        if click:
            payload["click"] = click
        _post(cfg["ntfy_url"].rstrip("/"), payload, cfg["ntfy_token"] or None)
        return True
    except Exception as exc:  # never let an alert break real work
        log.warning("Alert %s was not sent: %s", event, exc)
        try:
            db.audit(conn, None, "alert.failed", json.dumps({"event": event, "error": str(exc)[:200]}))
        except Exception:
            pass
        return False


def job_link(job_id: int) -> str:
    return f"{config.PUBLIC_URL}/#job={job_id}"
