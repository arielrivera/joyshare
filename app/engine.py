"""Keeping yt-dlp current without rebuilding the container.

Platforms change often and yt-dlp ships fixes quickly. Once a day (or when the admin asks) the worker:
  1. asks PyPI for the newest yt-dlp version,
  2. installs it into its own folder in the data volume (/data/ytdlp/<version>),
  3. test-runs it on a known video,
  4. points /data/ytdlp/current at it, or leaves things alone and alerts if the test failed.
Both containers notice the change and restart themselves to load it (Docker starts them again).
Going back is just pointing "current" at the previous folder.

app/__init__.py puts the chosen folder first on the import path before anything imports yt_dlp.
"""
import json
import logging
import random
import shutil
import subprocess
import sys
import urllib.request

from . import LOADED_YTDLP, config, db, i18n, media, notify, platforms, settings
from .i18n import T

log = logging.getLogger("joyshare.engine")

BASE = config.DATA_DIR / "ytdlp"
POINTER = BASE / "current"
CHECK_EVERY = 24 * 3600
# The platform check runs about once a day, but at a different time each day, so it looks like a person
# watching a video now and then rather than a clock: the next one is 12 to 36 hours after the last.
PLATFORM_GAP = (12 * 3600, 36 * 3600)
PROBE = ("import sys, json\n"
         "path, url = sys.argv[1], sys.argv[2]\n"
         "if path: sys.path.insert(0, path)\n"
         "import yt_dlp\n"
         "with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True, 'socket_timeout': 20}) as ydl:\n"
         "    info = ydl.extract_info(url, download=False)\n"
         "print(json.dumps({'version': yt_dlp.version.__version__, 'title': info.get('title')}))\n")


def loaded_version() -> str:
    import yt_dlp.version
    return yt_dlp.version.__version__


def active_name() -> str:
    """The folder "current" points at. Empty means: the version that came with the container."""
    try:
        return POINTER.read_text().strip()
    except OSError:
        return ""


def needs_restart() -> bool:
    """True once "current" points somewhere other than what this process loaded at startup."""
    return active_name() != LOADED_YTDLP


def as_numbers(version: str) -> tuple:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def is_newer(candidate: str, current: str) -> bool:
    return as_numbers(candidate) > as_numbers(current)


def latest_version() -> str:
    with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=15) as response:
        return json.load(response)["info"]["version"]


def install(version: str):
    """Install one exact version into its own folder. Returns the folder."""
    target = BASE / version
    shutil.rmtree(target, ignore_errors=True)
    BASE.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir", "--disable-pip-version-check",
         "--target", str(target), f"yt-dlp[default]=={version}"],
        check=True, capture_output=True, text=True, timeout=600,
    )
    return target


def probe(path, url: str) -> tuple[bool, str]:
    """Look up one video with the yt-dlp in `path` (None = the one in use), in a separate process."""
    try:
        done = subprocess.run([sys.executable, "-c", PROBE, str(path or ""), url],
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if done.returncode != 0:
        return False, (done.stderr.strip().splitlines() or ["failed"])[-1][:300]
    return True, done.stdout.strip()[:300]


def set_pointer(name: str) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(name)


def prune(keep: set[str]) -> None:
    if not BASE.is_dir():
        return
    for entry in BASE.iterdir():
        if entry.is_dir() and entry.name not in keep:
            shutil.rmtree(entry, ignore_errors=True)


def read_state(conn) -> dict:
    raw, _ = db.get_state(conn, "ytdlp")
    return json.loads(raw) if raw else {}


def _save(conn, **changes) -> dict:
    state = {**read_state(conn), **changes}
    db.set_state(conn, "ytdlp", json.dumps(state))
    return state


def check_and_update(conn) -> dict:
    """One full check. Safe to call any time; never raises."""
    if needs_restart():
        return read_state(conn)  # an update is already waiting for the restart
    current = loaded_version()
    _save(conn, status="checking", message=i18n.pack("Checking for a newer version…"))
    try:
        latest = latest_version()
        if not is_newer(latest, current):
            return _save(conn, status="current", latest=latest, checked_at=db.now(),
                         message=i18n.pack("You have the newest version."))
        log.info("yt-dlp %s is available (running %s), installing", latest, current)
        folder = install(latest)
        test_url = random.choice(settings.canary_links(settings.get_all(conn), "youtube")
                                 or ["https://www.youtube.com/watch?v=jNQXAC9IVRw"])
        ok, detail = probe(folder, test_url)
        if not ok:
            still_works, _ = probe(None, test_url)
            if still_works:  # the new one is worse than what we have: keep ours
                shutil.rmtree(folder, ignore_errors=True)
                log.warning("yt-dlp %s failed its test (%s), keeping %s", latest, detail, current)
                notify.send(conn, "ytdlp_failed", "yt-dlp update failed",
                            T("Version {new} failed its test, so {old} stays in use.", new=latest, old=current))
                return _save(conn, status="failed", latest=latest, checked_at=db.now(),
                             message=i18n.pack(T("Version {new} failed its test, so {old} stays in use.", new=latest, old=current)))
            log.warning("The test video fails on both versions; switching to %s anyway", latest)
        previous = active_name()
        set_pointer(latest)
        prune({latest, previous} - {""})
        db.audit(conn, None, "ytdlp.update", json.dumps({"from": current, "to": latest}))
        notify.send(conn, "ytdlp_updated", "yt-dlp updated", T("{old} → {new}", old=current, new=latest))
        return _save(conn, status="updated", latest=latest, previous=previous, previous_version=current,
                     checked_at=db.now(), updated_at=db.now(),
                     message=i18n.pack(T("Updated from {old} to {new}. Restarting to load it.", old=current, new=latest)))
    except Exception as exc:
        log.exception("yt-dlp update check failed")
        detail = (getattr(exc, "stderr", None) or str(exc)).strip().splitlines()[-1:] or ["unknown error"]
        notify.send(conn, "ytdlp_failed", "yt-dlp update failed", T("The update check failed: {reason}", reason=detail[0][:200]))
        return _save(conn, status="failed", checked_at=db.now(),
                     message=i18n.pack(T("The update check failed: {reason}", reason=detail[0][:200])))


def roll_back(conn) -> dict:
    """Go back to the version used before the last update."""
    state = read_state(conn)
    if "previous" not in state or state.get("status") != "updated":
        return state
    set_pointer(state["previous"])
    db.audit(conn, None, "ytdlp.rollback", json.dumps({"to": state.get("previous_version")}))
    return _save(conn, status="rolled_back", message=i18n.pack(
        T("Went back to version {old}. Restarting to load it.", old=state.get("previous_version", "?"))))


def due(conn) -> bool:
    if not settings.get(conn, "ytdlp_auto_update"):
        return False
    checked = read_state(conn).get("checked_at")
    return not checked or db.now() - checked >= CHECK_EVERY


# ---------- daily platform check (at a random time) ----------

def check_platforms(conn) -> dict:
    """Look up a randomly picked known video per platform. Alert when a platform that worked stops working.

    If the first pick fails and the platform has more test videos, a second one is tried, so one video
    going away (or one unlucky lookup) doesn't count as the platform breaking."""
    raw, _ = db.get_state(conn, "canary")
    before = json.loads(raw) if raw else {}
    results = {}
    cfg = settings.get_all(conn)
    for platform in cfg["canary_platforms"]:
        links = settings.canary_links(cfg, platform)
        if not links or platform not in cfg["platforms"]:
            continue
        message = None
        for url in random.sample(links, min(2, len(links))):
            try:
                media.inspect(url)
                results[platform] = {"ok": True, "at": db.now(), "url": url}
                break
            except Exception as exc:
                message = exc.args[0] if isinstance(exc, media.MediaError) and exc.args else str(exc)[:200]
                log.warning("Platform check for %s failed on %s: %s", platform, url, message)
        else:
            results[platform] = {"ok": False, "at": db.now(), "url": url, "error": i18n.pack(message)}
            if before.get(platform, {}).get("ok", True):  # only alert when it newly breaks
                label = platforms.PLATFORMS.get(platform, {}).get("label", platform)
                notify.send(conn, "platform_check_failed", T("{platform} stopped working", platform=label),
                            T("The daily test video failed: {reason}", reason=i18n.render(message, notify.admin_lang(conn))))
    db.set_state(conn, "canary", json.dumps(results))
    db.set_state(conn, "canary_at", str(db.now()))
    db.set_state(conn, "canary_next", str(db.now() + random.randint(*PLATFORM_GAP)))
    return results


def next_platform_check(conn) -> int | None:
    """When the automatic platform check runs next (None: as soon as possible)."""
    planned, _ = db.get_state(conn, "canary_next")
    if planned:
        return int(planned)
    last, _ = db.get_state(conn, "canary_at")   # from before the times were random
    return int(last) + CHECK_EVERY if last else None


def platforms_due(conn) -> bool:
    planned = next_platform_check(conn)
    return planned is None or db.now() >= planned
