"""Housekeeping: delete expired files and watch disk space.

Runs on the worker's built-in scheduler every few minutes and once at startup.
"""
import json
import logging
import shutil
import sqlite3
import time

from . import config, db, notify, settings, storage, store
from .i18n import T

log = logging.getLogger("joyshare.cleanup")

STALE_TMP_SECONDS = 6 * 3600
ALERT_EVERY = 6 * 3600


def delete_expired(conn: sqlite3.Connection, in_use: set[int] = frozenset()) -> int:
    rows = conn.execute(
        "SELECT * FROM files WHERE deleted_at IS NULL AND expires_at<=?", (db.now(),)
    ).fetchall()
    removed = 0
    for row in rows:
        if row["id"] in in_use:
            continue
        if row["storage"] == "local":
            store.abs_path(row).unlink(missing_ok=True)
        else:
            try:
                storage.delete(conn, row["path"])
            except Exception as exc:
                # Try again next round. After three days give up: the bucket's own clean-up rule removes leftovers.
                if db.now() - row["expires_at"] < 3 * 86400:
                    log.warning("Couldn't delete %s from cloud storage yet: %s", row["path"], exc)
                    continue
        conn.execute("UPDATE files SET deleted_at=? WHERE id=?", (db.now(), row["id"]))
        removed += 1
    return removed


def purge_deleted(conn: sqlite3.Connection) -> int:
    """Files of videos their owners deleted (and didn't undo): expire them now, end their share links,
    so delete_expired removes them. A file another of the person's videos still uses is kept."""
    rows = conn.execute(
        "SELECT DISTINCT j.file_id FROM jobs j JOIN files f ON f.id=j.file_id "
        "WHERE j.deleted_at IS NOT NULL AND j.deleted_at<=? AND f.deleted_at IS NULL",
        (db.now() - store.UNDO_SECONDS,),
    ).fetchall()
    purged = 0
    for row in rows:
        if not store.withdrawn(conn, row["file_id"]):
            continue
        conn.execute("UPDATE files SET expires_at=MIN(expires_at, ?) WHERE id=?", (db.now(), row["file_id"]))
        conn.execute("UPDATE share_links SET revoked_at=? WHERE file_id=? AND revoked_at IS NULL", (db.now(), row["file_id"]))
        purged += 1
    return purged


def delete_stale_tmp() -> None:
    cutoff = time.time() - STALE_TMP_SECONDS
    if not config.TMP_DIR.is_dir():
        return
    for entry in config.TMP_DIR.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink()
        except FileNotFoundError:
            pass


def check_disk(conn: sqlite3.Connection) -> dict:
    """Record disk use. Pause new jobs when the disk is nearly full."""
    cfg = settings.get_all(conn)
    usage = shutil.disk_usage(config.DATA_DIR)
    pct = round(usage.used / usage.total * 100, 1)
    level = "ok"
    if pct >= cfg["disk_pause_pct"]:
        level = "paused"
    elif pct >= cfg["disk_warn_pct"]:
        level = "warn"
    report = {"pct": pct, "used": usage.used, "total": usage.total, "level": level}
    previous, _ = db.get_state(conn, "disk")
    changed = not previous or json.loads(previous).get("level") != level
    last_alert, _ = db.get_state(conn, "disk_alert_at")
    # Alert when the level changes, and again every 6 hours while it stays high.
    if level != "ok" and (changed or not last_alert or db.now() - int(last_alert) >= ALERT_EVERY):
        log.warning("Disk is %s%% full (%s)", pct, level)
        gb = lambda n: round(n / 1024 ** 3, 1)  # noqa: E731
        if level == "paused":
            notify.send(conn, "disk_paused", "Disk almost full: new videos paused",
                        T("{pct}% used ({used} of {total} GB). Free some space.", pct=pct, used=gb(usage.used), total=gb(usage.total)))
        else:
            notify.send(conn, "disk_warn", "Disk is filling up",
                        T("{pct}% used ({used} of {total} GB).", pct=pct, used=gb(usage.used), total=gb(usage.total)))
        db.set_state(conn, "disk_alert_at", str(db.now()))
    db.set_state(conn, "disk", json.dumps(report))
    return report


def delete_expired_auth(conn: sqlite3.Connection) -> None:
    """Old sessions, used-up sign-in challenges and expired invite codes."""
    moment = db.now()
    conn.execute("DELETE FROM sessions WHERE expires_at<=?", (moment,))
    conn.execute("DELETE FROM challenges WHERE expires_at<=?", (moment,))
    conn.execute("DELETE FROM invites WHERE expires_at<=? OR used_at IS NOT NULL AND used_at<=?",
                 (moment - 86400, moment - 86400))


def run(conn: sqlite3.Connection, in_use: set[int] = frozenset()) -> dict:
    purge_deleted(conn)
    removed = delete_expired(conn, in_use)
    delete_expired_auth(conn)
    delete_stale_tmp()
    disk = check_disk(conn)
    if removed:
        log.info("Deleted %s expired file(s)", removed)
    return {"removed": removed, "disk": disk}
