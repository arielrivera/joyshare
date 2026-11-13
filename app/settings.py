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
               "storage_failed": True},
    # yt-dlp is checked for updates once a day. See app/engine.py.
    "ytdlp_auto_update": True,
    # One known, long-lived public video per platform, looked up once a day to notice breakage early.
    "canary_urls": {
        "youtube": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "x": "https://x.com/BrooklynNets/status/1349794411333394432",
    },
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
