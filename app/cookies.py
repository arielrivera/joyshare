"""Connected accounts: a person's own sign-in cookies for a platform.

Some platforms only show a video to signed-in accounts. A person can upload a cookie file
(the common "cookies.txt" export) for a platform, and joyshare then fetches as them.

Rules this module keeps:
  - A cookie file belongs to one person and is used only for that person's own videos.
  - Only the cookies for that platform are kept; everything else in the uploaded file is thrown away.
  - It is stored encrypted and is never sent back out through the API, not even to the admin.
  - It is only used when the platform asks for a sign-in: we try without it first.
"""
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import config, db, media, notify, secretbox
from .i18n import T
from .platforms import PLATFORMS

# Which cookie domains count for each platform.
DOMAINS = {
    "x": ("x.com", "twitter.com"),
    "youtube": ("youtube.com", "google.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com",),
}
MAX_UPLOAD = 1024 * 1024
HEADER = "# Netscape HTTP Cookie File\n"


class CookieError(ValueError):
    """The upload can't be used. The message is safe to show."""


def clean(text: str, platform: str) -> tuple[str, int]:
    """Keep only this platform's cookies from a cookies.txt export. Returns (file text, how many)."""
    if len(text.encode()) > MAX_UPLOAD:
        raise CookieError("That file is too big to be a cookie file.")
    wanted = DOMAINS[platform]
    kept = []
    for line in text.splitlines():
        raw = line.rstrip("\r\n")
        body = raw[len("#HttpOnly_"):] if raw.startswith("#HttpOnly_") else raw
        if not body.strip() or body.startswith("#"):
            continue
        parts = body.split("\t")
        if len(parts) != 7:
            continue
        domain = parts[0].lstrip(".").lower()
        if any(domain == d or domain.endswith("." + d) for d in wanted):
            kept.append(raw)
    if not kept:
        raise CookieError(T("No {platform} cookies were found in that file. Export it in the cookies.txt format "
                            "while signed in to {platform}.", platform=PLATFORMS[platform]["label"]))
    return HEADER + "\n".join(kept) + "\n", len(kept)


def save(conn, user_id: int, platform: str, text: str) -> int:
    cleaned, count = clean(text, platform)
    conn.execute(
        "INSERT INTO cookies (user_id, platform, data, cookie_count, status, updated_at) VALUES (?,?,?,?,'ok',?) "
        "ON CONFLICT(user_id, platform) DO UPDATE SET data=excluded.data, cookie_count=excluded.cookie_count, "
        "status='ok', updated_at=excluded.updated_at, last_used_at=NULL",
        (user_id, platform, secretbox.encrypt(cleaned), count, db.now()),
    )
    db.audit(conn, user_id, "account.connect", json.dumps({"platform": platform}))
    return count


def remove(conn, user_id: int, platform: str) -> bool:
    done = conn.execute("DELETE FROM cookies WHERE user_id=? AND platform=?", (user_id, platform)).rowcount
    if done:
        db.audit(conn, user_id, "account.disconnect", json.dumps({"platform": platform}))
    return bool(done)


def has(conn, user_id: int, platform: str) -> bool:
    return conn.execute("SELECT 1 FROM cookies WHERE user_id=? AND platform=? AND status!='unreadable'",
                        (user_id, platform)).fetchone() is not None


def status_list(conn, user_id: int, enabled: list[str]) -> list[dict]:
    """What the Connected accounts screen shows. Never includes the cookies themselves."""
    rows = {row["platform"]: row for row in conn.execute(
        "SELECT platform, cookie_count, status, updated_at, last_used_at FROM cookies WHERE user_id=?", (user_id,))}
    result = []
    for platform, spec in PLATFORMS.items():
        if platform not in enabled:
            continue
        row = rows.get(platform)
        result.append({
            "platform": platform, "label": spec["label"],
            "status": row["status"] if row else "none",      # none | ok | rejected | unreadable
            "cookie_count": row["cookie_count"] if row else 0,
            "updated_at": row["updated_at"] if row else None,
            "last_used_at": row["last_used_at"] if row else None,
        })
    return result


@contextmanager
def file_for(conn, user_id: int, platform: str):
    """A temporary cookie file for yt-dlp, or None if this person hasn't connected that platform.

    yt-dlp writes back to the file it is given, so it always gets a throwaway copy.
    """
    row = conn.execute("SELECT data FROM cookies WHERE user_id=? AND platform=?", (user_id, platform)).fetchone()
    if not row:
        yield None
        return
    try:
        text = secretbox.decrypt(row["data"])
    except secretbox.Unreadable:
        conn.execute("UPDATE cookies SET status='unreadable' WHERE user_id=? AND platform=?", (user_id, platform))
        yield None
        return
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix="ck-", suffix=".txt", dir=config.TMP_DIR)
    try:
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.chmod(name, 0o600)
        yield Path(name)
    finally:
        Path(name).unlink(missing_ok=True)


def with_login(conn, user_id: int, platform: str, run, prefer: bool = False):
    """Run `run(cookie_file_or_None)`, bringing in the person's account only if the platform asks for one.

    Returns (result, used_account). `prefer=True` goes straight to the account (the lookup already needed it).
    """
    label = PLATFORMS[platform]["label"]
    if not prefer:
        try:
            return run(None), False
        except media.MediaError as exc:
            if not getattr(exc, "needs_login", False):
                raise
            if not has(conn, user_id, platform):
                raise media.MediaError(T(
                    "{platform} only shows this video to signed-in accounts. "
                    "Connect your account under Connected accounts in the menu.", platform=label)) from exc
    with file_for(conn, user_id, platform) as path:
        if path is None:
            return run(None), False
        try:
            result = run(path)
        except media.MediaError as exc:
            if not getattr(exc, "needs_login", False):
                raise
            _mark_rejected(conn, user_id, platform, label)
            raise media.MediaError(T(
                "{platform} didn't accept your connected account. "
                "Upload a fresh cookie file under Connected accounts.", platform=label)) from exc
    conn.execute("UPDATE cookies SET status='ok', last_used_at=? WHERE user_id=? AND platform=?",
                 (db.now(), user_id, platform))
    return result, True


def _mark_rejected(conn, user_id: int, platform: str, label: str) -> None:
    before = conn.execute("SELECT status FROM cookies WHERE user_id=? AND platform=?", (user_id, platform)).fetchone()
    conn.execute("UPDATE cookies SET status='rejected' WHERE user_id=? AND platform=?", (user_id, platform))
    if before and before["status"] != "rejected":  # say it once, not on every try
        person = conn.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()["name"]
        notify.send(conn, "cookies_rejected", "A connected account stopped working",
                    T("{platform} no longer accepts the account {person} connected.", platform=label, person=person))
