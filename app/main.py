"""The website and API.

Run with:  uvicorn app.main:app
"""
import asyncio
import html
import json
import logging
import secrets
from contextlib import asynccontextmanager, closing

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, media, platforms, presets, settings, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("joyshare.web")

MB = 1024 * 1024
FINAL = {"done", "failed", "canceled"}
MAX_QUEUED_PER_USER = 20


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    yield


app = FastAPI(title="joyshare", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; media-src 'self' blob:; "
        "style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    )
    return response


def get_conn():
    with closing(db.connect()) as conn:
        yield conn


def current_user() -> int:
    """Phase 1: one built-in owner. Phase 2 replaces this with passkey sign-in."""
    return config.DEFAULT_USER_ID


# ---------- request bodies ----------

class InspectBody(BaseModel):
    url: str


class JobBody(BaseModel):
    media_id: int
    preset: str
    target_mb: int | None = None


# ---------- helpers ----------

def preset_options(info: dict, cfg: dict) -> list[dict]:
    """Each preset with its estimated size and whether it's within the limits."""
    limit = cfg["max_file_mb"] * MB
    duration = info.get("duration")
    estimates: dict = {}

    def estimate(key: str):
        if key not in estimates:
            estimates[key] = media.estimate(info, key)
        return estimates[key]

    options, seen_video = [], set()
    for preset in presets.PRESETS:
        option = {"id": preset["id"], "label": preset["label"], "detail": preset["detail"],
                  "kind": preset["kind"], "allowed": True, "reason": None}
        if preset["id"] == "fit":
            # Only offer sizes that are actually smaller than the normal 720p download.
            ref = estimate("v720") or {}
            targets, too_long = [], False
            for mb in cfg["fit_targets_mb"]:
                if mb > cfg["max_file_mb"] or (ref.get("bytes") and mb * MB >= ref["bytes"]):
                    continue
                try:
                    plan = presets.fit_plan(mb * MB, duration or 0, ref.get("height"))
                    targets.append({"mb": mb, "height": plan.height})
                except presets.PresetError:
                    too_long = True
            if not targets and not too_long:
                continue  # the video is already smaller than every target
            option["targets"] = targets
            if not targets:
                option["allowed"] = False
                option["reason"] = ("This video is too long to shrink to these sizes."
                                    if duration else "This video's length is unknown.")
            options.append(option)
            continue

        est = estimate(presets.source_key(preset["id"]))
        if est is None:
            option["allowed"] = False
            option["reason"] = "Not available for this video."
            options.append(option)
            continue
        if preset["kind"] == "video":
            signature = (est["height"], est["bytes"])
            if signature in seen_video:
                continue  # same streams as a bigger preset: nothing new to offer
            seen_video.add(signature)
            if est["height"]:
                option["detail"] = f"{est['height']}p"
        option.update(est_bytes=est["bytes"], height=est["height"], needs_convert=est["needs_convert"])
        if est["bytes"] and est["bytes"] > limit * 1.03:
            option["allowed"] = False
            option["reason"] = (f"About {est['bytes'] / MB:.0f} MB, over the "
                                f"{cfg['max_file_mb']} MB limit.")
        options.append(option)

    # Suggest the biggest allowed video at 720p or below: good quality, easy to send.
    allowed_video = [o for o in options if o["allowed"] and o["kind"] == "video" and o["id"] != "fit"]
    pick = next((o for o in allowed_video if (o.get("height") or 0) <= 720), None) \
        or (allowed_video[-1] if allowed_video else next((o for o in options if o["allowed"]), None))
    for option in options:
        option["recommended"] = option is pick
    return options


def owned_file(conn, file_id: int, user_id: int):
    row = conn.execute("SELECT * FROM files WHERE id=? AND kind='output'", (file_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        raise HTTPException(404, "File not found.")
    if row["deleted_at"] is not None or row["expires_at"] <= db.now() or not store.abs_path(row).is_file():
        raise HTTPException(410, "This file has expired.")
    return row


def file_response(conn, row, download: bool) -> FileResponse:
    item = conn.execute("SELECT title, uploader FROM media WHERE id=?", (row["media_id"],)).fetchone()
    path = store.abs_path(row)
    return FileResponse(
        path,
        media_type=row["mime"] or "application/octet-stream",
        filename=store.download_name(item["title"], item["uploader"], path.suffix),
        content_disposition_type="attachment" if download else "inline",
    )


# ---------- API ----------

@app.get("/api/health")
def health(conn=Depends(get_conn)):
    beat, _ = db.get_state(conn, "worker_heartbeat")
    disk, _ = db.get_state(conn, "disk")
    return {
        "ok": True,
        "worker_alive": bool(beat and db.now() - int(beat) < 90),
        "disk": json.loads(disk) if disk else None,
    }


@app.get("/api/config")
def get_config(conn=Depends(get_conn)):
    cfg = settings.get_all(conn)
    return {
        "max_file_mb": cfg["max_file_mb"],
        "max_duration_min": cfg["max_duration_min"],
        "link_ttl_hours": cfg["link_ttl_hours"],
        "output_ttl_hours": cfg["output_ttl_hours"],
        "platforms": [
            {"id": pid, "label": spec["label"], "experimental": spec["experimental"]}
            for pid, spec in platforms.PLATFORMS.items() if pid in cfg["platforms"]
        ],
    }


@app.post("/api/inspect")
def inspect(body: InspectBody, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    cfg = settings.get_all(conn)
    try:
        platform, url = platforms.detect(body.url, cfg["platforms"])
        info = media.inspect(url)
    except (platforms.LinkError, media.MediaError) as exc:
        raise HTTPException(422, str(exc)) from exc

    duration = info.get("duration")
    if duration and duration > cfg["max_duration_min"] * 60:
        raise HTTPException(
            422, f"This video is {duration / 60:.0f} minutes long. The limit is {cfg['max_duration_min']} minutes."
        )

    fields = (
        url, platform, info.get("title"), info.get("uploader"), info.get("uploader_id"),
        info.get("channel"), info.get("description"), duration, info.get("thumbnail"),
        info.get("webpage_url"), info.get("upload_date"), json.dumps(info),
    )
    source_id = str(info.get("id") or "")
    existing = conn.execute(
        "SELECT id FROM media WHERE user_id=? AND platform=? AND source_id=? AND source_id!=''",
        (user_id, platform, source_id),
    ).fetchone()
    if existing:
        media_id = existing["id"]
        conn.execute(
            "UPDATE media SET url=?, platform=?, title=?, uploader=?, uploader_id=?, channel=?, "
            "description=?, duration=?, thumbnail=?, webpage_url=?, upload_date=?, info_json=? WHERE id=?",
            (*fields, media_id),
        )
    else:
        media_id = conn.execute(
            "INSERT INTO media (url, platform, title, uploader, uploader_id, channel, description, duration, "
            "thumbnail, webpage_url, upload_date, info_json, user_id, source_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*fields, user_id, source_id, db.now()),
        ).lastrowid

    return {
        "media": {
            "id": media_id,
            "platform": platform,
            "platform_label": platforms.PLATFORMS[platform]["label"],
            "experimental": platforms.PLATFORMS[platform]["experimental"],
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": duration,
            "thumbnail": info.get("thumbnail"),
        },
        "presets": preset_options(info, cfg),
        "max_file_mb": cfg["max_file_mb"],
    }


@app.post("/api/jobs")
def create_job(body: JobBody, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    cfg = settings.get_all(conn)
    if body.preset not in presets.BY_ID:
        raise HTTPException(422, "Unknown preset.")
    item = conn.execute("SELECT * FROM media WHERE id=? AND user_id=?", (body.media_id, user_id)).fetchone()
    if not item:
        raise HTTPException(404, "Look up the link again first.")
    target_mb = None
    if body.preset == "fit":
        target_mb = body.target_mb
        if not target_mb or target_mb < 1 or target_mb > cfg["max_file_mb"]:
            raise HTTPException(422, f"Pick a size between 1 and {cfg['max_file_mb']} MB.")
        try:
            presets.fit_plan(target_mb * MB, item["duration"] or 0)
        except presets.PresetError as exc:
            raise HTTPException(422, str(exc)) from exc
    disk, _ = db.get_state(conn, "disk")
    if disk and json.loads(disk).get("level") == "paused":
        raise HTTPException(503, "The server's disk is almost full, so new videos are paused for now.")
    queued = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user_id,)
    ).fetchone()[0]
    if queued >= MAX_QUEUED_PER_USER:
        raise HTTPException(429, "Too many videos are already in progress. Wait for some to finish.")
    job_id = conn.execute(
        "INSERT INTO jobs (user_id, media_id, preset, target_mb, created_at) VALUES (?,?,?,?,?)",
        (user_id, body.media_id, body.preset, target_mb, db.now()),
    ).lastrowid
    return store.job_view(conn, job_id, user_id)


@app.get("/api/jobs")
def list_jobs(limit: int = 20, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    rows = conn.execute(
        "SELECT id FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, max(1, min(limit, 100)))
    ).fetchall()
    return [store.job_view(conn, row["id"], user_id) for row in rows]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    view = store.job_view(conn, job_id, user_id)
    if not view:
        raise HTTPException(404, "Job not found.")
    return view


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: int, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    view = store.job_view(conn, job_id, user_id)
    if not view:
        raise HTTPException(404, "Job not found.")
    conn.execute(
        "UPDATE jobs SET status='canceled', finished_at=? WHERE id=? AND status='queued'", (db.now(), job_id)
    )
    conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=? AND status='running'", (job_id,))
    return store.job_view(conn, job_id, user_id)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: int, user_id: int = Depends(current_user)):
    """Live progress as Server-Sent Events."""
    def read():
        with closing(db.connect()) as conn:
            return store.job_view(conn, job_id, user_id)

    if await asyncio.to_thread(read) is None:
        raise HTTPException(404, "Job not found.")

    async def stream():
        last, quiet = None, 0
        while True:
            view = await asyncio.to_thread(read)
            if view is None:
                break
            payload = json.dumps(view)
            if payload != last:
                yield f"data: {payload}\n\n"
                last, quiet = payload, 0
            else:
                quiet += 1
                if quiet % 30 == 0:
                    yield ": keepalive\n\n"
            if view["status"] in FINAL:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/files/{file_id}/stream")
def stream_file(file_id: int, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    return file_response(conn, owned_file(conn, file_id, user_id), download=False)


@app.get("/api/files/{file_id}/download")
def download_file(file_id: int, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    return file_response(conn, owned_file(conn, file_id, user_id), download=True)


@app.post("/api/files/{file_id}/share")
def share_file(file_id: int, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    row = owned_file(conn, file_id, user_id)
    link = conn.execute(
        "SELECT * FROM share_links WHERE file_id=? AND user_id=? AND revoked_at IS NULL AND expires_at>?",
        (file_id, user_id, db.now()),
    ).fetchone()
    if link:
        token, expires_at = link["token"], link["expires_at"]
    else:
        token = secrets.token_urlsafe(16)  # 128 random bits
        ttl = settings.get(conn, "link_ttl_hours") * 3600
        expires_at = min(db.now() + ttl, row["expires_at"])
        conn.execute(
            "INSERT INTO share_links (token, file_id, user_id, created_at, expires_at) VALUES (?,?,?,?,?)",
            (token, file_id, user_id, db.now(), expires_at),
        )
        db.audit(conn, user_id, "share_link.create", json.dumps({"file_id": file_id}))
    return {"url": f"{config.PUBLIC_URL}/v/{token}", "expires_at": expires_at}


@app.delete("/api/share/{token}")
def revoke_share(token: str, conn=Depends(get_conn), user_id: int = Depends(current_user)):
    done = conn.execute(
        "UPDATE share_links SET revoked_at=? WHERE token=? AND user_id=? AND revoked_at IS NULL",
        (db.now(), token, user_id),
    ).rowcount
    if not done:
        raise HTTPException(404, "Link not found.")
    db.audit(conn, user_id, "share_link.revoke", None)
    return {"ok": True}


# ---------- public share pages ----------

SHARE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:site_name" content="joyshare">
<meta property="og:type" content="{og_type}">
{og_media}
<link rel="stylesheet" href="/share.css">
</head><body><main>
{body}
<p class="brand">shared with joyshare</p>
</main></body></html>"""


def share_shell(title: str, body: str, og_type: str = "website", og_media: str = "", status: int = 200):
    page = SHARE_PAGE.format(title=html.escape(title), body=body, og_type=og_type, og_media=og_media)
    return HTMLResponse(page, status_code=status)


def live_share(conn, token: str):
    """Returns (link, file) for a working share link, or (None, None)."""
    link = conn.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    if not link or link["revoked_at"] is not None or link["expires_at"] <= db.now():
        return None, None
    row = conn.execute("SELECT * FROM files WHERE id=?", (link["file_id"],)).fetchone()
    if not row or row["deleted_at"] is not None or not store.abs_path(row).is_file():
        return None, None
    return link, row


@app.get("/v/{token}", response_class=HTMLResponse)
def share_page(token: str, conn=Depends(get_conn)):
    link, row = live_share(conn, token)
    if not link:
        return share_shell(
            "This video has expired",
            "<h1>This video has expired</h1><p>Shared videos are only kept for a short time. "
            "Ask the person who sent it to share it again.</p>",
            status=410,
        )
    conn.execute("UPDATE share_links SET views=views+1 WHERE token=?", (token,))
    item = conn.execute("SELECT * FROM media WHERE id=?", (row["media_id"],)).fetchone()
    title = item["title"] or "Shared video"
    src = f"/v/{token}/file"
    absolute = f"{config.PUBLIC_URL}{src}"
    is_audio = (row["mime"] or "").startswith("audio")
    credit = ""
    if item["uploader"]:
        credit = f"<p class=\"credit\">From {html.escape(item['uploader'])} on " \
                 f"{html.escape(platforms.PLATFORMS[item['platform']]['label'])}</p>"
    if is_audio:
        player = f'<audio controls preload="metadata" src="{src}"></audio>'
        og_type = "music.song"
        og_media = f'<meta property="og:audio" content="{html.escape(absolute)}">'
    else:
        player = f'<video controls playsinline preload="metadata" src="{src}"></video>'
        og_type = "video.other"
        og_media = (f'<meta property="og:video" content="{html.escape(absolute)}">\n'
                    f'<meta property="og:video:type" content="video/mp4">')
        if row["width"] and row["height"]:
            og_media += (f'\n<meta property="og:video:width" content="{row["width"]}">'
                         f'\n<meta property="og:video:height" content="{row["height"]}">')
    if item["thumbnail"]:
        og_media += f'\n<meta property="og:image" content="{html.escape(item["thumbnail"])}">'
    body = (f"{player}<h1>{html.escape(title)}</h1>{credit}"
            f'<p><a class="button" href="{src}?download=1">Download</a></p>')
    return share_shell(title, body, og_type, og_media)


@app.get("/v/{token}/file")
def share_file_bytes(token: str, download: int = 0, conn=Depends(get_conn)):
    link, row = live_share(conn, token)
    if not link:
        raise HTTPException(410, "This video has expired.")
    return file_response(conn, row, download=bool(download))


# The interface. Mounted last so it never shadows the routes above.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
