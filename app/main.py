"""The website and API.

Run with:  uvicorn app.main:app
"""
import asyncio
import hashlib
import html
import json
import logging
import mimetypes
import os
import re
import secrets
import signal
from contextlib import asynccontextmanager, closing

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import account, admin, auth, config, cookies, db, engine, i18n, media, platforms, presets, settings, storage, store, thumbs, twin
from .i18n import T

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("joyshare.web")

mimetypes.add_type("font/woff2", ".woff2")

MB = 1024 * 1024
FINAL = {"done", "failed", "canceled"}
MAX_QUEUED_PER_USER = 20


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    with closing(db.connect()) as conn:
        auth.ensure_setup_code(conn)  # printed in the log until the first device registers

    async def reload_when_ytdlp_changes():
        # The worker installs yt-dlp updates. When one is ready, stop cleanly; Docker starts us again with it.
        while True:
            await asyncio.sleep(20)
            if engine.needs_restart():
                log.info("Restarting to load the updated yt-dlp")
                os.kill(os.getpid(), signal.SIGTERM)
                return

    watcher = asyncio.create_task(reload_when_ytdlp_changes())
    yield
    watcher.cancel()


app = FastAPI(title="vidshare", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(auth.admin_router)
app.include_router(admin.router)
app.include_router(account.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Pages, scripts and styles: always check for a newer copy, so an update shows up right away.
    # Fonts and the 3D library never change under the same name, so they can be kept for a week.
    # Scripts and styles live under an address that changes with every update (/a/<version>/...), so a browser
    # or Cloudflare can keep them for as long as it likes and still never show an old copy.
    # Pages themselves are never stored.
    path = request.url.path
    if path.startswith(ASSETS + "/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith(("/fonts/", "/vendor/", "/icons/")):
        response.headers.setdefault("Cache-Control", "public, max-age=604800")
    elif not path.startswith("/api/"):
        # "no-cache" means: ask the server before reusing. Unlike "no-store" it doesn't push browsers to
        # throw the page away (and reload it) the moment you look at another app.
        response.headers.setdefault("Cache-Control", "no-cache")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    # When files live in cloud storage, the page may play and fetch video from that one address.
    bucket = storage.media_origin_if_fresh()
    if bucket is None:
        with closing(db.connect()) as conn:
            bucket = storage.media_origin(conn)
    extra = f" {bucket}" if bucket else ""
    response.headers.setdefault(
        "Content-Security-Policy",
        f"default-src 'self'; img-src 'self' https: data:; media-src 'self' blob:{extra}; "
        f"connect-src 'self'{extra}; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    )
    return response


def _version_of_interface() -> str:
    """A short fingerprint of every interface file. It changes whenever any of them changes."""
    digest = hashlib.sha256()
    for file in sorted(p for p in config.WEB_DIR.rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".html")):
        digest.update(str(file.relative_to(config.WEB_DIR)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


ASSETS = f"/a/{_version_of_interface()}"


def versioned(page: str) -> str:
    """Point a page's own scripts and styles at the versioned address."""
    return re.sub(r'((?:src|href)=")/([\w\-./]+\.(?:js|css)")', rf"\1{ASSETS}/\2", page)


@app.exception_handler(StarletteHTTPException)
async def translated_errors(request: Request, exc: StarletteHTTPException):
    """Every error message goes out in the reader's language."""
    detail = i18n.render(exc.detail, i18n.pick_lang(request)) if isinstance(exc.detail, str) else exc.detail
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


def get_lang(request: Request) -> str:
    return i18n.pick_lang(request)


# ---------- request bodies ----------

LINK_NEARLY_OVER = 2 * 3600   # a share link with less than this left counts as "about to run out"


class InspectBody(BaseModel):
    url: str


class JobBody(BaseModel):
    media_id: int
    preset: str
    target_mb: int | None = None
    clip_start: float | None = None   # only part of the video: seconds from the beginning
    clip_end: float | None = None
    from_file: int | None = None      # cut the clip from this finished file of yours, not from the platform


class QuickBody(BaseModel):
    url: str
    preset: str | None = None
    target_mb: int | None = None


# ---------- helpers ----------

def preset_options(info: dict, cfg: dict, lang: str = "en") -> list[dict]:
    """Each preset with its estimated size and whether it's within the limits."""
    limit = cfg["max_file_mb"] * MB
    source_limit = cfg["max_source_mb"] * MB
    duration = info.get("duration")
    estimates: dict = {}

    def estimate(key: str):
        if key not in estimates:
            estimates[key] = media.estimate(info, key)
        return estimates[key]

    options, seen_video = [], set()
    for preset in presets.PRESETS:
        option = {"id": preset["id"], "label": i18n.render(preset["label"], lang),
                  "detail": i18n.render(preset["detail"], lang),
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
                option["reason"] = i18n.render("This video is too long to shrink to these sizes."
                                               if duration else "This video's length is unknown.", lang)
            options.append(option)
            continue

        est = estimate(presets.source_key(preset["id"]))
        if est is None:
            option["allowed"] = False
            option["reason"] = i18n.render("Not available for this video.", lang)
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
        # A part of the video can still be made when the whole thing is too big to share,
        # as long as the original itself can be downloaded.
        option["clip_ok"] = not est["bytes"] or est["bytes"] <= source_limit
        if est["bytes"] and est["bytes"] > limit * 1.03:
            option["allowed"] = False
            option["reason"] = i18n.render(T("About {size} MB, over the {limit} MB limit.",
                                             size=round(est["bytes"] / MB), limit=cfg["max_file_mb"]), lang)
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
    if row["deleted_at"] is not None or row["expires_at"] <= db.now() or not file_exists(row):
        raise HTTPException(410, "This file has expired.")
    return row


def file_exists(row) -> bool:
    return row["storage"] != "local" or store.abs_path(row).is_file()


def file_response(conn, row, download: bool):
    item = conn.execute("SELECT title, uploader FROM media WHERE id=?", (row["media_id"],)).fetchone()
    if row["storage"] != "local":
        # The file is in cloud storage: send the viewer there with a link that works for about an hour.
        suffix = "." + row["path"].rsplit(".", 1)[-1]
        name = store.download_name(item["title"], item["uploader"], suffix) if download else None
        try:
            url = storage.signed_url(conn, row["path"], mime=row["mime"], download_name=name)
        except Exception as exc:
            log.error("Couldn't make a cloud storage link: %s", exc)
            raise HTTPException(503, "Cloud storage isn't reachable right now. Try again in a moment.") from exc
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    path = store.abs_path(row)
    return FileResponse(
        path,
        media_type=row["mime"] or "application/octet-stream",
        filename=store.download_name(item["title"], item["uploader"], path.suffix),
        content_disposition_type="attachment" if download else "inline",
    )


# ---------- API ----------

@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    """What a phone needs to add joyshare to the home screen as an app."""
    return JSONResponse({
        "name": config.APP_NAME, "short_name": config.APP_NAME, "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#efe8d8", "theme_color": "#efe8d8",
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, media_type="application/manifest+json")


@app.get("/api/health")
def health(conn=Depends(db.get_conn)):
    """Public on purpose (uptime monitors call it), so it says very little."""
    beat, _ = db.get_state(conn, "worker_heartbeat")
    # "instance" is a random id of this copy, so a copy can tell when another one answers at its address.
    # "version" changes with every update of the interface, so an open page can tell it is out of date.
    return {"ok": True, "worker_alive": bool(beat and db.now() - int(beat) < 90), "instance": twin.instance_id(),
            "version": ASSETS.rsplit("/", 1)[-1]}


@app.get("/api/config")
def get_config(conn=Depends(db.get_conn), _user: int = Depends(auth.current_user)):
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


def do_inspect(conn, user_id: int, raw_url: str, lang: str = "en") -> dict:
    cfg = settings.get_all(conn)
    try:
        platform, url = platforms.detect(raw_url, cfg["platforms"])
        # Try without the person's connected account first; bring it in only if the platform asks for a sign-in.
        info, used_account = cookies.with_login(
            conn, user_id, platform,
            lambda cookie_file: media.inspect(url) if cookie_file is None else media.inspect(url, cookiefile=cookie_file))
    except (platforms.LinkError, media.MediaError) as exc:
        raise HTTPException(422, exc.args[0]) from exc

    duration = info.get("duration")
    if duration and duration > cfg["max_duration_min"] * 60:
        raise HTTPException(422, T("This video is {minutes} minutes long. The limit is {limit} minutes.",
                                   minutes=round(duration / 60), limit=cfg["max_duration_min"]))

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

    conn.execute("UPDATE media SET needs_login=? WHERE id=?", (int(used_account), media_id))
    thumbs.save_soon(media_id, info.get("thumbnail"))   # keep our own copy: the platform's address won't last

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
            "thumb_url": f"/api/media/{media_id}/thumb" if info.get("thumbnail") else None,
        },
        "presets": preset_options(info, cfg, lang),
        "max_file_mb": cfg["max_file_mb"],
    }


def do_create_job(conn, user_id: int, media_id: int, preset: str, target_mb: int | None,
                  lang: str = "en", clip_start: float | None = None, clip_end: float | None = None,
                  from_file: int | None = None) -> dict:
    cfg = settings.get_all(conn)
    if preset not in presets.BY_ID:
        raise HTTPException(422, "Unknown preset.")
    item = conn.execute("SELECT * FROM media WHERE id=? AND user_id=?", (media_id, user_id)).fetchone()
    if not item:
        raise HTTPException(404, "Look up the link again first.")
    try:
        clip = presets.check_clip(clip_start, clip_end, item["duration"])
    except (presets.PresetError, ValueError) as exc:
        raise HTTPException(422, exc.args[0]) from exc
    if not clip:
        from_file = None   # only clips are cut from a file we hold
    if from_file is not None:
        base = owned_file(conn, from_file, user_id)   # 404 or 410 if it isn't yours or is gone
        if base["media_id"] != media_id:
            raise HTTPException(422, "That file belongs to another video.")
    if preset != "fit":
        target_mb = None
    else:
        if not target_mb or target_mb < 1 or target_mb > cfg["max_file_mb"]:
            raise HTTPException(422, T("Pick a size between 1 and {max} MB.", max=cfg["max_file_mb"]))
        try:
            presets.fit_plan(target_mb * MB, (clip[1] - clip[0]) if clip else (item["duration"] or 0))
        except presets.PresetError as exc:
            raise HTTPException(422, exc.args[0]) from exc
    if cfg["paused"]:
        raise HTTPException(503, "New videos are paused for now. Try again later.")
    disk, _ = db.get_state(conn, "disk")
    if disk and json.loads(disk).get("level") == "paused":
        raise HTTPException(503, "The server's disk is almost full, so new videos are paused for now.")
    queued = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user_id,)
    ).fetchone()[0]
    if queued >= MAX_QUEUED_PER_USER:
        raise HTTPException(429, "Too many videos are already in progress. Wait for some to finish.")
    job_id = conn.execute(
        "INSERT INTO jobs (user_id, media_id, preset, target_mb, clip_start, clip_end, from_file_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, media_id, preset, target_mb, clip[0] if clip else None, clip[1] if clip else None, from_file, db.now()),
    ).lastrowid
    return store.job_view(conn, job_id, user_id, lang)


@app.post("/api/inspect")
def inspect(body: InspectBody, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user),
            lang: str = Depends(get_lang)):
    return do_inspect(conn, user_id, body.url, lang)


@app.get("/api/media/{media_id}/thumb")
def media_thumb(media_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
    """The saved preview picture of one of your videos."""
    item = conn.execute("SELECT thumbnail FROM media WHERE id=? AND user_id=?", (media_id, user_id)).fetchone()
    if not item:
        raise HTTPException(404, "Not found.")
    # Usually saved when the link was looked up. If not (an older video), try once now.
    path = thumbs.find(media_id) or thumbs.save(media_id, item["thumbnail"])
    if not path:
        raise HTTPException(404, "Not found.")
    return FileResponse(path, media_type=thumbs.MIME[path.suffix],
                        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@app.post("/api/jobs")
def create_job(body: JobBody, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user),
               lang: str = Depends(get_lang)):
    return do_create_job(conn, user_id, body.media_id, body.preset, body.target_mb, lang, body.clip_start, body.clip_end,
                         body.from_file)


@app.post("/api/quick")
def quick(body: QuickBody, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user),
          lang: str = Depends(get_lang)):
    """One call for the iOS Shortcut: look up a link and start the suggested preset.

    Returns the job and a page to open, where progress and the Share button appear.
    """
    found = do_inspect(conn, user_id, body.url, lang)
    preset = body.preset
    if not preset:
        pick = next((p for p in found["presets"] if p.get("recommended")), None)
        if not pick:
            raise HTTPException(422, "No size of this video fits within the limits.")
        preset = pick["id"]
    job = do_create_job(conn, user_id, found["media"]["id"], preset, body.target_mb, lang)
    return {"job": job, "media": found["media"], "page_url": f"{config.PUBLIC_URL}/#job={job['id']}"}




@app.get("/api/jobs")
def list_jobs(limit: int = 20, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user),
              lang: str = Depends(get_lang)):
    rows = conn.execute(
        "SELECT id FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, max(1, min(limit, 100)))
    ).fetchall()
    return [store.job_view(conn, row["id"], user_id, lang) for row in rows]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user),
            lang: str = Depends(get_lang)):
    view = store.job_view(conn, job_id, user_id, lang)
    if not view:
        raise HTTPException(404, "Job not found.")
    return view


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
    view = store.job_view(conn, job_id, user_id)
    if not view:
        raise HTTPException(404, "Job not found.")
    conn.execute(
        "UPDATE jobs SET status='canceled', finished_at=? WHERE id=? AND status='queued'", (db.now(), job_id)
    )
    conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=? AND status='running'", (job_id,))
    return store.job_view(conn, job_id, user_id)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: int, user_id: int = Depends(auth.current_user), lang: str = Depends(get_lang)):
    """Live progress as Server-Sent Events."""
    def read():
        with closing(db.connect()) as conn:
            return store.job_view(conn, job_id, user_id, lang)

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
def stream_file(file_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
    return file_response(conn, owned_file(conn, file_id, user_id), download=False)


@app.get("/api/files/{file_id}/download")
def download_file(file_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
    return file_response(conn, owned_file(conn, file_id, user_id), download=True)


@app.post("/api/files/{file_id}/share")
def share_file(file_id: int, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
    row = owned_file(conn, file_id, user_id)
    link = conn.execute(
        "SELECT * FROM share_links WHERE file_id=? AND user_id=? AND revoked_at IS NULL AND expires_at>? "
        "ORDER BY expires_at DESC",
        (file_id, user_id, db.now()),
    ).fetchone()
    ttl = settings.get(conn, "link_ttl_hours") * 3600
    longest = min(db.now() + ttl, row["expires_at"])   # a link never outlives its file
    # Hand back the link that already exists, unless it is about to run out and a new one would last longer.
    if link and (link["expires_at"] - db.now() > LINK_NEARLY_OVER or longest - link["expires_at"] < 600):
        token, expires_at = link["token"], link["expires_at"]
    else:
        token = secrets.token_urlsafe(16)  # 128 random bits
        expires_at = longest
        conn.execute(
            "INSERT INTO share_links (token, file_id, user_id, created_at, expires_at) VALUES (?,?,?,?,?)",
            (token, file_id, user_id, db.now(), expires_at),
        )
        db.audit(conn, user_id, "share_link.create", json.dumps({"file_id": file_id}))
    return {"url": f"{config.PUBLIC_URL}/v/{token}", "expires_at": expires_at,
            "ends_soon": expires_at - db.now() <= LINK_NEARLY_OVER}


@app.delete("/api/share/{token}")
def revoke_share(token: str, conn=Depends(db.get_conn), user_id: int = Depends(auth.current_user)):
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
<html lang="{lang}" data-theme="{theme}" data-font="{font}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:site_name" content="{brand}">
<meta property="og:type" content="{og_type}">
<meta property="og:description" content="{about}">
<meta name="twitter:card" content="{card}">
{og_media}
<link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png">
<link rel="stylesheet" href="{assets}/style.css">
<link rel="stylesheet" href="{assets}/share.css">
</head><body><div class="glow" aria-hidden="true"></div><main class="share">
<section class="card">
{body}
</section>
<p class="brand">{shared_with}</p>
</main></body></html>"""


def share_shell(title: str, body: str, lang: str, look: dict, og_type: str = "website", og_media: str = "",
                status: int = 200, about: str = ""):
    """The page a friend sees. It wears the sender's look: their name, colors and lettering."""
    brand = html.escape(look["name"])
    page = SHARE_PAGE.format(
        title=html.escape(title), body=body, og_type=og_type, og_media=og_media, lang=lang, brand=brand,
        theme=look["theme"], font=look["font"], assets=ASSETS, about=html.escape(about or look["name"]),
        card="summary_large_image" if "og:image" in og_media else "summary",
        shared_with=i18n.render(T("shared with {name}", name=f"<strong>{brand}</strong>"), lang),
    )
    return HTMLResponse(page, status_code=status)


def live_share(conn, token: str):
    """Returns (link, file) for a working share link, or (None, None)."""
    link = conn.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    if not link or link["revoked_at"] is not None or link["expires_at"] <= db.now():
        return None, None
    row = conn.execute("SELECT * FROM files WHERE id=?", (link["file_id"],)).fetchone()
    if not row or row["deleted_at"] is not None or not file_exists(row):
        return None, None
    return link, row


@app.get("/v/{token}", response_class=HTMLResponse)
def share_page(token: str, conn=Depends(db.get_conn), lang: str = Depends(get_lang)):
    tr = lambda text: i18n.render(text, lang)  # noqa: E731
    link, row = live_share(conn, token)
    if not link:
        gone = tr("This video has expired")
        why = tr("Shared videos are only kept for a short time. Ask the person who sent it to share it again.")
        plain = {"name": config.APP_NAME, "theme": auth.DEFAULT_THEME, "font": auth.DEFAULT_FONT}
        return share_shell(gone, f"<h2>{html.escape(gone)}</h2><p>{html.escape(why)}</p>", lang, plain, status=410)
    look = auth.get_prefs(conn, link["user_id"])  # friends see the name and look the sender chose
    conn.execute("UPDATE share_links SET views=views+1 WHERE token=?", (token,))
    item = conn.execute("SELECT * FROM media WHERE id=?", (row["media_id"],)).fetchone()
    title = item["title"] or tr("Shared video")
    src = f"/v/{token}/file"
    absolute = f"{config.PUBLIC_URL}{src}"
    is_audio = (row["mime"] or "").startswith("audio")
    credit = ""
    if item["uploader"]:
        credit = "<p class=\"credit\">" + html.escape(tr(T(
            "From {uploader} on {platform}", uploader=item["uploader"],
            platform=platforms.PLATFORMS[item["platform"]]["label"]))) + "</p>"
    if is_audio:
        player = f'<audio controls preload="metadata" src="{src}"></audio>'
        og_type = "music.song"
        og_media = f'<meta property="og:audio" content="{html.escape(absolute)}">'
    else:
        poster = f' poster="/v/{token}/thumb"' if item["thumbnail"] else ""
        player = f'<video controls playsinline preload="metadata"{poster} src="{src}"></video>'
        og_type = "video.other"
        og_media = (f'<meta property="og:video" content="{html.escape(absolute)}">\n'
                    f'<meta property="og:video:type" content="video/mp4">')
        if row["width"] and row["height"]:
            og_media += (f'\n<meta property="og:video:width" content="{row["width"]}">'
                         f'\n<meta property="og:video:height" content="{row["height"]}">')
    if item["thumbnail"]:
        # Our own copy of the picture: the platform's address stops working, and then the card in the chat goes blank.
        og_media += f'\n<meta property="og:image" content="{config.PUBLIC_URL}/v/{token}/thumb">'
    # The line under the title in the chat's preview card: who made it, where, how long.
    length = int(row["duration"] or 0)
    about = " · ".join(part for part in (
        item["uploader"], platforms.PLATFORMS[item["platform"]]["label"],
        f"{length // 60}:{length % 60:02d}" if length else "") if part)
    body = (f"{player}<h2>{html.escape(title)}</h2>{credit}"
            f'<p><a class="button" href="{src}?download=1">{html.escape(tr("Download"))}</a></p>')
    return share_shell(title, body, lang, look, og_type, og_media, about=about)


@app.get("/v/{token}/thumb")
def share_thumb(token: str, conn=Depends(db.get_conn)):
    """The preview picture for a shared video: what chat apps show in the link's card."""
    link, row = live_share(conn, token)
    if not link:
        raise HTTPException(410, "This video has expired.")
    item = conn.execute("SELECT thumbnail FROM media WHERE id=?", (row["media_id"],)).fetchone()
    path = thumbs.find(row["media_id"]) or thumbs.save(row["media_id"], item["thumbnail"] if item else None)
    if not path:
        raise HTTPException(404, "Not found.")
    return FileResponse(path, media_type=thumbs.MIME[path.suffix],
                        headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})


@app.get("/v/{token}/file")
def share_file_bytes(token: str, download: int = 0, conn=Depends(db.get_conn)):
    link, row = live_share(conn, token)
    if not link:
        raise HTTPException(410, "This video has expired.")
    return file_response(conn, row, download=bool(download))


HOME_PAGE = versioned((config.WEB_DIR / "index.html").read_text())


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return HTMLResponse(HOME_PAGE)


# The interface files, at their versioned address and (last, so it never shadows the routes above) at the plain one.
app.mount(ASSETS, StaticFiles(directory=config.WEB_DIR), name="assets")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
