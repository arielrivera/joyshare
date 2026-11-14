"""Noticing a second copy of joyshare answering at the same address.

This happens when the service is moved to another computer and the old one is left running with the
same Cloudflare Tunnel token: Cloudflare then sends each visitor to either computer at random. People
look signed out half the time and videos made on one copy are missing on the other.

Each copy has its own random id, kept in the cache folder. That folder is left out of backups on
purpose, so a copy restored on another computer gets a new id. The id is shown by /api/health; the
worker asks the public address a few times and checks that the answers carry its own id.
"""
import json
import logging
import secrets
import urllib.request

from . import config, db, notify
from .i18n import T

log = logging.getLogger("joyshare.twin")

ID_FILE = config.CACHE_DIR / "instance_id"
EVERY = 10 * 60          # how often the worker looks
ASKS = 4                 # separate requests per look: with two copies, each one answers some of them
ALERT_EVERY = 6 * 3600   # don't repeat the alert more often than this
_id: str | None = None


def instance_id() -> str:
    global _id
    if _id is None:
        try:
            _id = ID_FILE.read_text().strip() or None
        except OSError:
            _id = None
        if _id is None:
            _id = secrets.token_hex(6)
            ID_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(ID_FILE, "x") as fh:   # web and worker start together: the first one wins
                    fh.write(_id)
            except FileExistsError:
                _id = ID_FILE.read_text().strip()
    return _id


def _ask(url: str) -> dict:
    """The one place that talks to the network. Tests replace it."""
    request = urllib.request.Request(url, headers={"User-Agent": "joyshare-self-check", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read(4096))


def read_state(conn) -> dict:
    raw, _ = db.get_state(conn, "twin")
    return json.loads(raw) if raw else {}


def due(conn) -> bool:
    if not config.PUBLIC_URL.startswith("https://"):
        return False   # not live on a domain: nothing to compare with
    state = read_state(conn)
    last = state.get("checked_at")
    wait = EVERY if state.get("reached") else 60   # nothing answered (we may be just starting): look again soon
    return not last or db.now() - last >= wait


def check(conn) -> dict:
    """Asks the public address who is answering. Records and alerts when it isn't (only) this copy."""
    mine, others, reached = instance_id(), set(), 0
    for _ in range(ASKS):
        try:
            answer = _ask(config.PUBLIC_URL + "/api/health")
        except Exception as exc:   # the address being down is Uptime Kuma's job, not this check's
            log.debug("Self-check could not reach %s: %s", config.PUBLIC_URL, exc)
            continue
        reached += 1
        other = answer.get("instance")
        if other and other != mine:
            others.add(str(other)[:32])
    before = read_state(conn)
    state = {"checked_at": db.now(), "reached": reached, "found": bool(others),
             "alerted_at": before.get("alerted_at"), "since": before.get("since") if others else None}
    if others:
        state["since"] = state["since"] or db.now()
        if not state["alerted_at"] or db.now() - state["alerted_at"] >= ALERT_EVERY:
            log.warning("Another copy is answering at %s", config.PUBLIC_URL)
            db.audit(conn, None, "twin.found", json.dumps({"others": sorted(others)}))
            notify.send(conn, "second_copy", "A second copy is running",
                        T("Another copy of this app is answering at {url}. People will look signed out at random and "
                          "videos will go missing. Stop the old one with: ./joyshare retire", url=config.PUBLIC_URL))
            state["alerted_at"] = db.now()
    elif reached:
        state["alerted_at"] = None   # it is gone: the next time counts as new
    db.set_state(conn, "twin", json.dumps(state))
    return state
