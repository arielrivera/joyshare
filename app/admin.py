"""The admin's side of the API: numbers, settings, alerts, everyone's jobs and links, the audit log.

Reading needs an admin signed in with a passkey. Changing anything also needs a passkey check
from the last few minutes, and every change is written to the audit log.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, backup, codeupdate, config, db, engine, i18n, notify, platforms, settings, storage, store, thumbs, twin
from .i18n import T

router = APIRouter(prefix="/api/admin")

# key -> (lowest, highest) for whole-number settings
NUMBER_LIMITS = {
    "max_file_mb": (1, 2000),
    "max_source_mb": (1, 10000),
    "max_duration_min": (1, 1440),
    "max_concurrent_jobs": (1, 4),
    "source_ttl_min": (5, 1440),
    "output_ttl_hours": (1, 168),
    "link_ttl_hours": (1, 168),
    "disk_warn_pct": (50, 99),
    "disk_pause_pct": (60, 100),
}
SECRET_KEYS = {"ntfy_token", "r2_secret_access_key"}
MANUAL_TESTS, MANUAL_WINDOW = 2, 3 * 3600   # "Test platforms now": at most 2 in any 3 hours
R2_TEXT = {"r2_account_id": r"[A-Za-z0-9]{0,64}", "r2_bucket": r"[a-z0-9][a-z0-9.\-]{1,62}|", "r2_access_key_id": r"[A-Za-z0-9]{0,128}",
           "r2_region": r"[a-z0-9\-]{1,32}", "r2_endpoint": r"(https?://[A-Za-z0-9.\-]+(:\d+)?)?"}


def changing_admin(auth_info: auth.Auth = Depends(auth.fresh_auth)) -> auth.Auth:
    if auth_info.role != "admin":
        raise HTTPException(403, "Only an admin can do that.")
    return auth_info


def public_settings(conn) -> dict:
    """Settings as the admin screen may see them: secrets are never sent back."""
    cfg = settings.get_all(conn)
    for key in SECRET_KEYS:
        cfg[f"has_{key}"] = bool(cfg.pop(key))
    return cfg


def check_setting(key: str, value, merged: dict):
    """Returns the cleaned value or raises a 422 the admin can read."""
    if key not in settings.DEFAULTS:
        raise HTTPException(422, T("Unknown setting: {key}", key=key))
    if key in NUMBER_LIMITS:
        low, high = NUMBER_LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise HTTPException(422, T("{key} must be a whole number from {low} to {high}.", key=key, low=low, high=high))
        return value
    if key == "canary_platforms":
        if not isinstance(value, list) or any(p not in platforms.PLATFORMS for p in value):
            raise HTTPException(422, "Pick platforms from the list.")
        return [p for p in platforms.PLATFORMS if p in value]
    if key == "canary_urls":
        if not isinstance(value, dict) or any(p not in platforms.PLATFORMS or not isinstance(u, str) for p, u in value.items()):
            raise HTTPException(422, "Pick platforms from the list.")
        cleaned = dict(merged["canary_urls"])
        for name, url in value.items():
            url = url.strip()
            if url:
                try:
                    found, url = platforms.detect(url)
                except platforms.LinkError as exc:
                    raise HTTPException(422, exc.args[0]) from exc
                if found != name:
                    raise HTTPException(422, T("That link isn't a {platform} link.", platform=platforms.PLATFORMS[name]["label"]))
            cleaned[name] = url
        return cleaned
    if key in ("paused", "ytdlp_auto_update", "backup_auto"):
        if not isinstance(value, bool):
            raise HTTPException(422, T("Unknown setting: {key}", key=key))
        return value
    if key == "platforms":
        if not isinstance(value, list) or not value or any(p not in platforms.PLATFORMS for p in value):
            raise HTTPException(422, "Pick at least one platform from the list.")
        return [p for p in platforms.PLATFORMS if p in value]
    if key == "fit_targets_mb":
        ok = isinstance(value, list) and 1 <= len(value) <= 8 and all(
            isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 2000 for v in value)
        if not ok:
            raise HTTPException(422, "Target sizes must be one to eight whole numbers of MB.")
        return sorted(set(value))
    if key == "alerts":
        if not isinstance(value, dict) or any(k not in notify.EVENTS or not isinstance(v, bool) for k, v in value.items()):
            raise HTTPException(422, "Unknown alert.")
        return {**merged["alerts"], **value}
    if key == "ntfy_url":
        if not isinstance(value, str) or not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?(/[\w\-./]*)?", value.strip()):
            raise HTTPException(422, "The ntfy address must start with https:// or http://.")
        return value.strip().rstrip("/")
    if key == "ntfy_topic":
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{0,64}", value.strip()):
            raise HTTPException(422, "A topic can use letters, numbers, - and _ (up to 64).")
        return value.strip()
    if key in R2_TEXT:
        if not isinstance(value, str) or not re.fullmatch(R2_TEXT[key], value.strip()):
            raise HTTPException(422, T("That doesn't look right for {key}.", key=key))
        return value.strip()
    if key == "r2_secret_access_key":
        if not isinstance(value, str) or len(value) > 300:
            raise HTTPException(422, T("Unknown setting: {key}", key=key))
        return storage.seal(value.strip())
    if key == "storage":
        if value not in ("local", "r2"):
            raise HTTPException(422, T("Unknown setting: {key}", key=key))
        return value
    if key == "ntfy_token":
        if not isinstance(value, str) or len(value) > 200:
            raise HTTPException(422, T("Unknown setting: {key}", key=key))
        return value.strip()
    raise HTTPException(422, T("Unknown setting: {key}", key=key))


class SettingsBody(BaseModel):
    changes: dict


# ---------- reading ----------

@router.get("/overview")
def overview(_admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    import yt_dlp.version

    now = db.now()

    def count(sql: str, *args) -> int:
        return conn.execute(sql, args).fetchone()[0] or 0

    def by_status(since: int) -> dict:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs WHERE created_at>=? GROUP BY status", (since,))
        return {row["status"]: row["n"] for row in rows}

    disk, _ = db.get_state(conn, "disk")
    beat, _ = db.get_state(conn, "worker_heartbeat")
    platform_rows = conn.execute(
        "SELECT m.platform, COUNT(*) AS n FROM jobs j JOIN media m ON m.id=j.media_id "
        "WHERE j.created_at>=? GROUP BY m.platform", (now - 7 * 86400,))
    return {
        "jobs_today": by_status(now - 86400),
        "jobs_week": by_status(now - 7 * 86400),
        "jobs_by_platform_week": {row["platform"]: row["n"] for row in platform_rows},
        "queue": count("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"),
        "files": count("SELECT COUNT(*) FROM files WHERE deleted_at IS NULL"),
        "files_bytes": count("SELECT SUM(size) FROM files WHERE deleted_at IS NULL"),
        "share_links": count("SELECT COUNT(*) FROM share_links WHERE revoked_at IS NULL AND expires_at>?", now),
        "people": count("SELECT COUNT(*) FROM users WHERE disabled=0"),
        "disk": json.loads(disk) if disk else None,
        "worker_alive": bool(beat and now - int(beat) < 90),
        "paused": settings.get(conn, "paused"),
        "second_copy": bool(twin.read_state(conn).get("found")),
        "yt_dlp": yt_dlp.version.__version__,
    }


@router.get("/settings")
def read_settings(_admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    return {"settings": public_settings(conn), "limits": NUMBER_LIMITS,
            "platforms": {pid: spec["label"] for pid, spec in platforms.PLATFORMS.items()},
            "alert_events": list(notify.EVENTS)}


@router.get("/jobs")
def all_jobs(request: Request, limit: int = 50, status: str | None = None, q: str | None = None,
             _admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    """Everyone's videos, newest first. `q` searches the title, channel, description, link, platform and person."""
    lang = i18n.pick_lang(request)
    sql = ("SELECT j.id, u.name AS person, m.url, m.webpage_url, m.channel, m.uploader_id, m.description, m.upload_date "
           "FROM jobs j JOIN users u ON u.id=j.user_id JOIN media m ON m.id=j.media_id")
    where, args = [], []
    if status:
        where.append("j.status=?")
        args.append(status)
    words = (q or "").strip()[:100].split()
    for word in words[:6]:   # every word must appear somewhere
        like = f"%{word.replace('%', '').replace('_', '')}%"
        where.append("(m.title LIKE ? OR m.uploader LIKE ? OR m.channel LIKE ? OR m.description LIKE ? "
                     "OR m.url LIKE ? OR m.webpage_url LIKE ? OR m.platform LIKE ? OR u.name LIKE ?)")
        args.extend([like] * 8)
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = conn.execute(sql + " ORDER BY j.id DESC LIMIT ?", (*args, max(1, min(limit, 200)))).fetchall()
    found = []
    for row in rows:
        view = store.job_view(conn, row["id"], None, lang)
        if view["media"] and view["media"]["thumbnail"]:
            view["media"]["thumb_url"] = f"/api/admin/media/{view['media']['id']}/thumb"   # any person's, for the admin
        found.append({**view, "person": row["person"], "details": {
            "link": row["webpage_url"] or row["url"], "channel": row["channel"], "uploader_id": row["uploader_id"],
            "description": (row["description"] or "")[:400], "upload_date": row["upload_date"],
            "platform_label": platforms.PLATFORMS.get(view["media"]["platform"], {}).get("label") if view["media"] else None,
        }})
    return found


@router.get("/media/{media_id}/thumb")
def any_thumb(media_id: int, _admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    """The saved preview picture of anyone's video. Pictures are kept after the video files expire."""
    item = conn.execute("SELECT thumbnail FROM media WHERE id=?", (media_id,)).fetchone()
    if not item:
        raise HTTPException(404, "Not found.")
    path = thumbs.find(media_id) or thumbs.save(media_id, item["thumbnail"])
    if not path:
        raise HTTPException(404, "Not found.")
    return FileResponse(path, media_type=thumbs.MIME[path.suffix],
                        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.get("/share-links")
def all_share_links(_admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    rows = conn.execute(
        "SELECT s.token, s.created_at, s.expires_at, s.views, u.name AS person, m.title, f.size "
        "FROM share_links s JOIN users u ON u.id=s.user_id JOIN files f ON f.id=s.file_id "
        "JOIN media m ON m.id=f.media_id WHERE s.revoked_at IS NULL AND s.expires_at>? ORDER BY s.created_at DESC",
        (db.now(),),
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/audit")
def audit_log(limit: int = 100, _admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    rows = conn.execute(
        "SELECT a.id, a.action, a.detail, a.created_at, u.name AS person FROM audit_log a "
        "LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?", (max(1, min(limit, 500)),)
    ).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        try:
            detail = json.loads(row["detail"]) if row["detail"] else {}
        except ValueError:
            detail = {"text": row["detail"]}
        if not isinstance(detail, dict):
            detail = {"text": str(detail)}
        # Numbers mean nothing to a reader: add the person's name and the video's title.
        if "user_id" in detail and "name" not in detail:
            who = conn.execute("SELECT name FROM users WHERE id=?", (detail["user_id"],)).fetchone()
            detail["name"] = who["name"] if who else None
        if "file_id" in detail:
            video = conn.execute("SELECT m.title FROM files f JOIN media m ON m.id=f.media_id WHERE f.id=?",
                                 (detail["file_id"],)).fetchone()
            detail["title"] = video["title"] if video else None
        entry["detail"] = detail
        entries.append(entry)
    return entries


@router.get("/system")
def system(request: Request, _admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    lang = i18n.pick_lang(request)
    state = engine.read_state(conn)
    asked, _ = db.get_state(conn, "engine_request")
    raw, _ = db.get_state(conn, "canary")
    checks = json.loads(raw) if raw else {}
    cfg = settings.get_all(conn)
    recent = recent_manual_tests(conn)
    state_b = backup.read_state(conn)
    return {
        "ytdlp": {
            "version": engine.loaded_version(),
            "latest": state.get("latest"),
            "status": "checking" if asked in ("update", "rollback") else state.get("status"),
            "message": i18n.unpack(state.get("message"), lang),
            "checked_at": state.get("checked_at"),
            "updated_at": state.get("updated_at"),
            "can_roll_back": state.get("status") == "updated" and "previous" in state,
            "previous_version": state.get("previous_version"),
            "restart_pending": engine.needs_restart(),
            "auto_update": settings.get(conn, "ytdlp_auto_update"),
        },
        "platform_checks": [
            {"platform": name, "label": spec["label"],
             "included": name in cfg["canary_platforms"], "url": cfg["canary_urls"].get(name, ""),
             "enabled": name in cfg["platforms"],
             "ok": checks.get(name, {}).get("ok"), "at": checks.get(name, {}).get("at"),
             "error": i18n.unpack(checks.get(name, {}).get("error"), lang)}
            for name, spec in platforms.PLATFORMS.items()
        ],
        "code": codeupdate.view(conn),
        "checking_platforms": asked == "platforms",
        "next_platform_check": engine.next_platform_check(conn) if cfg["canary_platforms"] else None,
        "manual_tests_left": MANUAL_TESTS - len(recent),
        "next_manual_test_at": (min(recent) + MANUAL_WINDOW) if len(recent) >= MANUAL_TESTS else None,
        "backup": {
            **{k: state_b.get(k) for k in ("at", "ok", "size", "cloud", "error", "local_ok", "local_count")},
            "auto": cfg["backup_auto"], "cloud_ready": storage.is_tested(conn), "running": asked == "backup",
        },
    }


def recent_manual_tests(conn) -> list[int]:
    raw, _ = db.get_state(conn, "canary_manual")
    return [t for t in (json.loads(raw) if raw else []) if db.now() - t < MANUAL_WINDOW]


class SystemAction(BaseModel):
    action: str   # "update", "rollback", "platforms" or "backup"


@router.post("/system")
def system_action(body: SystemAction, admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    """Leaves a note for the worker, which does the work within half a minute."""
    if body.action not in ("update", "rollback", "platforms", "backup"):
        raise HTTPException(422, "Unknown action.")
    if body.action == "platforms":
        # Each test really contacts the platforms, so it is rationed: 2 in any 3 hours.
        recent = recent_manual_tests(conn)
        if len(recent) >= MANUAL_TESTS:
            minutes = max(1, (min(recent) + MANUAL_WINDOW - db.now() + 59) // 60)
            raise HTTPException(429, T("Platform tests are limited to {count} every 3 hours. Try again in {minutes} minutes.",
                                       count=MANUAL_TESTS, minutes=minutes))
        db.set_state(conn, "canary_manual", json.dumps(recent + [db.now()]))
    db.set_state(conn, "engine_request", body.action)
    db.audit(conn, admin.user_id, f"system.{body.action}", None)
    return {"ok": True}


@router.post("/code-update")
def code_update(admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    """Ask the update helper on the server to put GitHub's main live now. Only a note: see app/codeupdate.py."""
    if not codeupdate.view(conn)["helper_alive"]:
        raise HTTPException(409, "The update helper isn't running on the server. Turn it on there with: ./joyshare autoupdate on-request")
    return codeupdate.request(conn, admin.user_id)


@router.get("/storage")
def storage_status(_admin: auth.Auth = Depends(auth.admin_auth), conn=Depends(db.get_conn)):
    cfg = storage.read_config(conn)
    steps, _ = db.get_state(conn, "r2_test_steps")
    in_cloud = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS bytes FROM files WHERE storage!='local' AND deleted_at IS NULL").fetchone()
    return {
        "mode": storage.mode(conn),
        "complete": cfg["complete"],
        "tested": storage.is_tested(conn, cfg),
        "settings": {k: v for k, v in public_settings(conn).items() if k.startswith(("r2_", "has_r2_", "storage"))},
        "last_test": json.loads(steps) if steps else [],
        "files_in_cloud": in_cloud["n"], "bytes_in_cloud": in_cloud["bytes"],
        "site_address": config.PUBLIC_URL,
    }


@router.post("/storage/test")
def storage_test(admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    try:
        steps = storage.test(conn)
    except storage.StorageError as exc:
        raise HTTPException(422, exc.args[0]) from exc
    passed = storage.is_tested(conn)
    db.audit(conn, admin.user_id, "storage.test", json.dumps({"passed": passed}))
    return {"passed": passed, "steps": steps}


# ---------- changing ----------

@router.put("/settings")
def change_settings(body: SettingsBody, admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    merged = settings.get_all(conn)
    cleaned = {key: check_setting(key, value, merged) for key, value in body.changes.items()}
    merged.update(cleaned)
    if merged["disk_pause_pct"] <= merged["disk_warn_pct"]:
        raise HTTPException(422, "The pause level must be higher than the warning level.")
    if merged["link_ttl_hours"] > merged["output_ttl_hours"]:
        raise HTTPException(422, "Share links can't outlive the files they point to.")
    for key, value in cleaned.items():
        settings.put(conn, key, value)
    storage.forget_cache()
    if merged["storage"] == "r2" and not storage.is_tested(conn):
        # Never switch to a bucket that hasn't just proved it works with these exact details.
        settings.put(conn, "storage", "local")
        if cleaned.get("storage") == "r2":
            raise HTTPException(422, "Test the connection first. Cloud storage turns on only after the test passes.")
    shown = {k: ("(changed)" if k in SECRET_KEYS else v) for k, v in cleaned.items()}
    db.audit(conn, admin.user_id, "settings.change", json.dumps(shown))
    return {"settings": public_settings(conn)}


@router.post("/alerts/test")
def test_alert(admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    if not settings.get(conn, "ntfy_topic"):
        raise HTTPException(422, "Set an ntfy topic first.")
    sent = notify.send(conn, "test", "Test alert", "Alerts are working.")
    if not sent:
        raise HTTPException(502, "The alert couldn't be sent. Check the ntfy address, topic and token.")
    return {"ok": True}


@router.delete("/share-links/{token}")
def revoke_any_link(token: str, admin: auth.Auth = Depends(changing_admin), conn=Depends(db.get_conn)):
    done = conn.execute("UPDATE share_links SET revoked_at=? WHERE token=? AND revoked_at IS NULL",
                        (db.now(), token)).rowcount
    if not done:
        raise HTTPException(404, "Link not found.")
    db.audit(conn, admin.user_id, "share_link.revoke_by_admin", None)
    return {"ok": True}
