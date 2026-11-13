"""Small helpers for file and job records, shared by the web app and the worker."""
import re
import sqlite3
import unicodedata
from pathlib import Path

from . import config, db, i18n

MIME = {".mp4": "video/mp4", ".m4a": "audio/mp4"}


def abs_path(row) -> Path:
    return config.DATA_DIR / row["path"]


def find_file(conn: sqlite3.Connection, user_id: int, media_id: int, kind: str, key: str):
    """A still-valid file for this user, video and key, or None."""
    rows = conn.execute(
        "SELECT * FROM files WHERE user_id=? AND media_id=? AND kind=? AND key=? "
        "AND deleted_at IS NULL AND expires_at>? ORDER BY id DESC",
        (user_id, media_id, kind, key, db.now()),
    ).fetchall()
    for row in rows:
        if row["storage"] != "local" or abs_path(row).is_file():  # files in cloud storage are trusted to be there
            return row
    return None


def add_file(conn: sqlite3.Connection, *, user_id: int, media_id: int, kind: str, key: str,
             path: Path, ttl_seconds: int, meta: dict | None = None) -> int:
    meta = meta or {}
    created = db.now()
    cur = conn.execute(
        "INSERT INTO files (user_id, media_id, kind, key, path, size, mime, width, height, duration, "
        "vcodec, acodec, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, media_id, kind, key, str(path.relative_to(config.DATA_DIR)), path.stat().st_size,
         MIME.get(path.suffix), meta.get("width"), meta.get("height"), meta.get("duration"),
         meta.get("vcodec"), meta.get("acodec"), created, created + ttl_seconds),
    )
    return cur.lastrowid


def file_view(row) -> dict:
    return {
        "id": row["id"],
        "kind": "audio" if (row["mime"] or "").startswith("audio") else "video",
        "size": row["size"],
        "mime": row["mime"],
        "width": row["width"],
        "height": row["height"],
        "duration": row["duration"],
        "expires_at": row["expires_at"],
        "stream_url": f"/api/files/{row['id']}/stream",
        "download_url": f"/api/files/{row['id']}/download",
    }


def job_view(conn: sqlite3.Connection, job_id: int, user_id: int | None = None,
             lang: str = "en") -> dict | None:
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or (user_id is not None and job["user_id"] != user_id):
        return None
    media = conn.execute(
        "SELECT id, title, uploader, platform, thumbnail, duration FROM media WHERE id=?",
        (job["media_id"],),
    ).fetchone()
    view = {
        "id": job["id"],
        "media": dict(media) if media else None,
        "preset": job["preset"],
        "target_mb": job["target_mb"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": round(job["progress"] or 0, 3),
        "error": i18n.unpack(job["error"], lang),
        "reused": bool(job["reused"]),
        "created_at": job["created_at"],
        "finished_at": job["finished_at"],
        "file": None,
    }
    if job["file_id"]:
        row = conn.execute("SELECT * FROM files WHERE id=?", (job["file_id"],)).fetchone()
        if row and row["deleted_at"] is None and row["expires_at"] > db.now():
            view["file"] = file_view(row)
        elif row:
            view["file_expired"] = True
    return view


def download_name(title: str | None, uploader: str | None, suffix: str) -> str:
    """A tidy file name such as 'Me at the zoo - jawed.mp4'."""
    parts = [p for p in (title, uploader) if p]
    name = " - ".join(parts) if parts else "video"
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:80].rstrip(" .") or "video") + suffix
