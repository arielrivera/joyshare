"""Limits and switches that can change while the app runs. Stored in the database.

The admin panel (phase 3) will edit these. Until then the defaults apply.
"""
import json
import sqlite3

from . import db

DEFAULTS = {
    "max_file_mb": 200,          # biggest finished file we hand out
    "max_source_mb": 1024,       # biggest download we accept before shrinking it
    "max_duration_min": 180,     # longest video we accept
    "max_concurrent_jobs": 2,
    "source_ttl_min": 60,        # how long the downloaded original is kept
    "output_ttl_hours": 48,      # how long finished files are kept
    "link_ttl_hours": 48,        # how long share links work
    "disk_warn_pct": 90,
    "disk_pause_pct": 95,
    "platforms": ["x", "youtube", "tiktok", "instagram", "facebook"],
    "fit_targets_mb": [8, 16, 25, 50, 100],
    "paused": False,             # the admin's "pause new jobs" switch
    # Where finished files are served from: "local" (this server) or "r2" (Cloudflare R2). See app/storage.py.
    "storage": "local",
    "r2_account_id": "",
    "r2_bucket": "",
    "r2_access_key_id": "",
    "r2_secret_access_key": "",  # kept encrypted
    "r2_endpoint": "",           # only for other S3-compatible storage; R2's address is built from the account ID
    "r2_region": "auto",
    # Alerts through ntfy. No topic means alerts are off.
    "ntfy_url": "https://ntfy.sh",
    "ntfy_topic": "",
    "ntfy_token": "",
    "alerts": {"job_done": True, "job_failed": True, "disk_warn": True, "disk_paused": True,
               "new_device": True, "failed_signins": True, "ytdlp_updated": True, "ytdlp_failed": True,
               "platform_check_failed": True, "cookies_rejected": True,
               "storage_failed": True, "backup_failed": True, "update_failed": True, "code_update": True},
    # yt-dlp is checked for updates once a day. See app/engine.py.
    "ytdlp_auto_update": True,
    # Known, long-lived public videos per platform, looked up once a day to notice breakage early.
    # Each check picks one at random, so no single video is looked up every day. See canary_links().
    "canary_urls": {
        "youtube": [f"https://www.youtube.com/watch?v={v}" for v in (
            "jNQXAC9IVRw", "dQw4w9WgXcQ", "9bZkp7q19f0", "kJQP7kiw5Fk", "OPf0YbXqDm0",
            "JGwWNGJdvx8", "RgKAFK5djSk", "hT_nvWreIhg", "YQHsXMglC9A")],
        # Official brand and team accounts, all checked to work without signing in (2026-11-18).
        "x": [f"https://x.com/{t}" for t in (
            "BrooklynNets/status/1349794411333394432", "captainamerica/status/719944021058060289",
            "primevideouk/status/1578401165338976258", "SamsungMobileSA/status/1348609186725289984",
            "SouthamptonFC/status/1347577658079641604", "CAF_Online/status/1349365911120195585",
            "historyinmemes/status/1790637656616943991")],
        "tiktok": [f"https://www.tiktok.com/{t}" for t in (
            "@pokemonlife22/video/7059698374567611694", "@nasa/video/7708867568920038669",
            "@nasa/video/7705995616794561805", "@nasa/video/7705574810113314061",
            "@nasa/video/7701866987609197837", "@nasa/video/7698805564884733198",
            "@nasa/video/7695060950394703118", "@nasa/video/7694283957839400206",
            "@nasa/video/7700397098994273549")],
        "instagram": [f"https://www.instagram.com/{t}/" for t in (
            "reel/Chunk8-jurw", "p/BQ0eAlwhDrw", "p/-Cmh1cukG2")],
        "facebook": [],
    },
    # Which platforms the daily check (and "Test platforms now") includes. A platform also needs a test video above.
    "canary_platforms": ["youtube", "x"],
    # A database backup once a day. See app/backup.py.
    "backup_auto": True,
}


def get_all(conn: sqlite3.Connection) -> dict:
    values = dict(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] in DEFAULTS:
            saved = json.loads(row["value"])
            # Dictionaries keep any defaults added after they were saved.
            values[row["key"]] = {**DEFAULTS[row["key"]], **saved} if isinstance(saved, dict) else saved
    return values


def get(conn: sqlite3.Connection, key: str):
    return get_all(conn)[key]


def put(conn: sqlite3.Connection, key: str, value) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    if type(value) is not type(DEFAULTS[key]):
        raise TypeError(f"{key} must be {type(DEFAULTS[key]).__name__}")
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, json.dumps(value), db.now()),
    )


# Before test videos became lists, each platform had one link, and saving the form stored the defaults too.
_OLD_SINGLE_DEFAULTS = {"https://www.youtube.com/watch?v=jNQXAC9IVRw",
                        "https://x.com/BrooklynNets/status/1349794411333394432",
                        "https://www.tiktok.com/@pokemonlife22/video/7059698374567611694"}


def canary_links(cfg: dict, platform: str) -> list[str]:
    """The test videos for one platform, as a list, whatever shape they were saved in."""
    value = cfg["canary_urls"].get(platform, [])
    if isinstance(value, str):
        # An untouched old default (a known link, or Instagram's old empty one): use the new pool.
        if value in _OLD_SINGLE_DEFAULTS or (not value and platform == "instagram"):
            return list(DEFAULTS["canary_urls"][platform])
        value = value.split()
    return [u for u in value if u]
