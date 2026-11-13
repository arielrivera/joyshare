"""Backups of the database: who can sign in, settings, history, connected accounts.

Videos are not backed up. They are temporary by design and can be fetched again.

Once a day (and when the admin presses "Back up now") the worker:
  1. takes a consistent snapshot of the database while the app keeps running,
  2. compresses it into /data/backups (the newest few are kept),
  3. if cloud storage is set up and tested, also uploads it to the bucket under backups/.

A copy that lives on the same disk only protects against a damaged database, not a dead disk.
The copy in the bucket is the one that survives losing the machine.

Connected accounts and the storage secret inside a backup stay encrypted. To read them after a
restore you need the same JOYSHARE_SECRET (or the same /data/secret.key).
"""
import gzip
import json
import logging
import shutil
import sqlite3
import time

from . import config, db, notify, settings, storage
from .i18n import T

log = logging.getLogger("joyshare.backup")

FOLDER = config.DATA_DIR / "backups"
KEEP_LOCAL = 7
KEEP_CLOUD = 14
EVERY = 24 * 3600
CLOUD_PREFIX = "backups/"


def snapshot(target) -> None:
    """Copy the live database safely, using SQLite's own backup feature."""
    source = sqlite3.connect(config.DB_PATH, timeout=30)
    plain = target.with_suffix("")  # the .db next to the .db.gz
    try:
        copy = sqlite3.connect(plain)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    with open(plain, "rb") as raw, gzip.open(target, "wb", compresslevel=6) as packed:
        shutil.copyfileobj(raw, packed)
    plain.unlink()


def local_backups() -> list:
    return sorted(FOLDER.glob("joyshare-*.db.gz")) if FOLDER.is_dir() else []


def read_state(conn) -> dict:
    raw, _ = db.get_state(conn, "backup")
    return json.loads(raw) if raw else {}


def run(conn) -> dict:
    """One backup. Never raises; the result is saved for the System tab."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    name = time.strftime("joyshare-%Y%m%d-%H%M%S.db.gz", time.gmtime())
    target = FOLDER / name
    state = {"at": db.now(), "ok": False, "name": name, "cloud": False}
    try:
        snapshot(target)
        state.update(ok=True, size=target.stat().st_size)
        for old in local_backups()[:-KEEP_LOCAL]:
            old.unlink(missing_ok=True)
        if storage.is_tested(conn):
            storage.put_file(conn, target, CLOUD_PREFIX + name, "application/gzip")
            state["cloud"] = True
            for key in sorted(storage.list_keys(conn, CLOUD_PREFIX))[:-KEEP_CLOUD]:
                storage.delete(conn, key)
        log.info("Backup %s done (%s bytes, cloud copy: %s)", name, state["size"], state["cloud"])
    except Exception as exc:
        log.exception("Backup failed")
        partly = state["ok"]  # the local copy was made, the upload failed
        state.update(ok=False, error=str(exc)[:300], local_ok=partly)
        notify.send(conn, "backup_failed", "Backup failed",
                    T("The cloud copy failed, the copy on the server was made: {reason}", reason=str(exc)[:200]) if partly
                    else T("No backup was made: {reason}", reason=str(exc)[:200]))
    state["local_count"] = len(local_backups())
    db.set_state(conn, "backup", json.dumps(state))
    return state


def due(conn) -> bool:
    if not settings.get(conn, "backup_auto"):
        return False
    last = read_state(conn).get("at")
    return not last or db.now() - last >= EVERY
