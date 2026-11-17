"""Updating joyshare's own code from the admin panel, safely.

The web app never runs git or docker, and has no way to reach the computer it runs on. It only keeps a note:
"the admin asked for an update". The update helper on that computer ("./joyshare self-update", run every
minute by launchd or systemd, outside Docker) asks for that note, and does the work itself: fetch GitHub's
main, test it, wait for running videos, move forward, rebuild. It reports back each step, which shows in the
admin panel and goes to the admin's phone through ntfy.

So the most anyone with the admin account can do here is ask for what is already on GitHub's main to go
live sooner. The note carries no commands, branches or addresses.

    python -m app.cli update-check VERSION SUBJECT MODE EVERY   # the helper checking in; exit 0 = asked
    python -m app.cli update-status STATUS [VERSION] [DETAIL]   # the helper reporting a step
"""
import json

from . import db, notify
from .i18n import T

ALIVE_SECONDS = 180            # the helper checks in every minute; this long without it means it isn't running
BUSY_SECONDS = 45 * 60         # while it tests and waits for videos it doesn't check in
STATUSES = ("found", "waiting", "started", "finished", "failed", "blocked", "current")
DONE = ("finished", "failed", "blocked", "current")   # these answer a request


def _read(conn, key: str) -> dict:
    raw, _ = db.get_state(conn, key)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _write(conn, key: str, value: dict | None) -> None:
    db.set_state(conn, key, json.dumps(value) if value else "")


def request(conn, user_id: int) -> dict:
    """The admin pressed the button. Asking again while one is waiting changes nothing."""
    pending = _read(conn, "code_request")
    if not pending:
        _write(conn, "code_request", {"at": db.now(), "by": user_id})
        db.audit(conn, user_id, "code.update_request", None)
    return view(conn)


def check_in(conn, version: str, subject: str, mode: str, every: int) -> bool:
    """The helper says it is alive and which version runs. Returns True when the admin asked for an update."""
    _write(conn, "code_helper", {"seen": db.now(), "version": version[:40], "subject": subject[:200],
                                 "mode": mode if mode in ("auto", "request") else "auto", "every": max(0, int(every))})
    return bool(_read(conn, "code_request"))


def report(conn, status: str, version: str = "", detail: str = "") -> None:
    """One step of an update, from the helper. Sends the matching alert."""
    if status not in STATUSES:
        raise ValueError(status)
    _write(conn, "code_status", {"status": status, "version": version[:40], "detail": detail[:300], "at": db.now()})
    if status in DONE:
        _write(conn, "code_request", None)
    if status == "found":
        notify.send(conn, "code_update", "New code found",
                    T("{version} ({detail}). Testing it, then updating.", version=version, detail=detail or "-"))
    elif status == "started":
        notify.send(conn, "code_update", "Updating now",
                    T("Putting {version} live. joyshare restarts for a moment.", version=version))
    elif status == "finished":
        notify.send(conn, "code_update", "Update finished", T("{version} is live now.", version=version))
    elif status == "failed":
        notify.send(conn, "update_failed", "Update not put live",
                    T("joyshare stayed on the running version: {reason}", reason=detail or "-"))


def view(conn) -> dict:
    """What the admin panel shows."""
    helper = _read(conn, "code_helper")
    status = _read(conn, "code_status")
    working = status.get("status") in ("found", "waiting", "started") and db.now() - status.get("at", 0) < BUSY_SECONDS
    return {
        "helper_alive": bool(helper) and (db.now() - helper.get("seen", 0) < ALIVE_SECONDS or working),
        "helper_seen": helper.get("seen"),
        "version": helper.get("version"), "subject": helper.get("subject"),
        "mode": helper.get("mode"), "every": helper.get("every"),
        "requested": _read(conn, "code_request").get("at"),
        "status": status.get("status"), "status_version": status.get("version"),
        "status_detail": status.get("detail"), "status_at": status.get("at"),
        "working": working,
    }
