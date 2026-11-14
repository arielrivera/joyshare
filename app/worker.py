"""The worker: takes queued jobs, downloads and converts, and runs scheduled housekeeping.

Run with:  python -m app.worker
"""
import json
import logging
import shutil
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import backup, cleanup, config, cookies, db, engine, i18n, media, notify, presets, settings, storage, store, twin
from .i18n import T

log = logging.getLogger("joyshare.worker")

CLEANUP_EVERY = 300
HEARTBEAT_EVERY = 30
MB = 1024 * 1024


class Worker:
    def __init__(self):
        self.stop = threading.Event()
        self.guard = threading.Lock()
        self.in_use: set[int] = set()          # file ids a running job is reading
        self.source_locks: dict[tuple, threading.Lock] = {}

    # ---------- main loop ----------

    def main(self) -> None:
        db.init()
        conn = db.connect()
        # Jobs that were running when the worker last stopped start over.
        conn.execute(
            "UPDATE jobs SET status='queued', stage=NULL, progress=0, started_at=NULL WHERE status='running'"
        )
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.stop.set())
        threading.Thread(target=self.scheduler, name="scheduler", daemon=True).start()
        log.info("Worker ready")
        active = set()
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="job") as pool:
            while not self.stop.is_set():
                active = {f for f in active if not f.done()}
                cfg = settings.get_all(conn)
                disk, _ = db.get_state(conn, "disk")
                paused = bool(disk and json.loads(disk).get("level") == "paused")
                if engine.needs_restart():
                    # A new yt-dlp is installed. Let running jobs finish, then stop; Docker starts us again.
                    if not active:
                        log.info("Restarting to load the updated yt-dlp")
                        break
                    self.stop.wait(0.5)
                    continue
                if not paused and len(active) < cfg["max_concurrent_jobs"]:
                    job_id = self.claim(conn)
                    if job_id:
                        active.add(pool.submit(self.run_job, job_id))
                        continue
                self.stop.wait(0.5)
            log.info("Stopping, waiting for running jobs to wind down")
        conn.close()

    @staticmethod
    def claim(conn) -> int | None:
        row = conn.execute(
            "UPDATE jobs SET status='running', started_at=?, stage='starting', progress=0 "
            "WHERE id=(SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT 1) RETURNING id",
            (db.now(),),
        ).fetchone()
        return row["id"] if row else None

    def scheduler(self) -> None:
        conn = db.connect()
        last_cleanup = 0.0
        while not self.stop.is_set():
            try:
                if time.time() - last_cleanup >= CLEANUP_EVERY:
                    with self.guard:
                        busy = set(self.in_use)
                    cleanup.run(conn, busy)
                    last_cleanup = time.time()
                db.set_state(conn, "worker_heartbeat", str(db.now()))
                self.engine_tasks(conn)
            except Exception:
                log.exception("Scheduled task failed")
            self.stop.wait(HEARTBEAT_EVERY)

    @staticmethod
    def engine_tasks(conn) -> None:
        """Daily yt-dlp update and platform check, plus anything the admin asked for from the System tab."""
        asked, _ = db.get_state(conn, "engine_request")
        if asked:
            db.set_state(conn, "engine_request", "")
        if asked == "rollback":
            engine.roll_back(conn)
        elif asked == "update" or engine.due(conn):
            engine.check_and_update(conn)
        if asked == "platforms" or (not engine.needs_restart() and engine.platforms_due(conn)):
            engine.check_platforms(conn)
        if asked == "backup" or backup.due(conn):
            backup.run(conn)
        if twin.due(conn):
            twin.check(conn)

    # ---------- one job ----------

    def source_lock(self, media_id: int, key: str) -> threading.Lock:
        with self.guard:
            return self.source_locks.setdefault((media_id, key), threading.Lock())

    def run_job(self, job_id: int) -> None:
        conn = db.connect()
        held: list[int] = []
        try:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            item = conn.execute("SELECT * FROM media WHERE id=?", (job["media_id"],)).fetchone()
            cfg = settings.get_all(conn)
            last = {"write": 0.0, "cancel_check": 0.0, "cancel": False}

            def set_stage(stage: str) -> None:
                conn.execute("UPDATE jobs SET stage=?, progress=0 WHERE id=?", (stage, job_id))
                last["write"] = 0.0

            def on_progress(fraction: float) -> None:
                if time.time() - last["write"] >= 0.4:
                    conn.execute("UPDATE jobs SET progress=? WHERE id=?", (fraction, job_id))
                    last["write"] = time.time()

            def should_cancel() -> bool:
                if self.stop.is_set():
                    return True
                if time.time() - last["cancel_check"] >= 1.0:
                    row = conn.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
                    last["cancel"] = bool(row and row["cancel_requested"])
                    last["cancel_check"] = time.time()
                return last["cancel"]

            def finish(file_id: int, reused: bool = False) -> None:
                conn.execute(
                    "UPDATE jobs SET status='done', stage='done', progress=1, file_id=?, reused=?, "
                    "finished_at=? WHERE id=?",
                    (file_id, int(reused), db.now(), job_id),
                )

            user_id, media_id = job["user_id"], job["media_id"]
            preset_id, target_mb = job["preset"], job["target_mb"]

            # Same video and preset asked for again: hand back the file we already have.
            clip = presets.check_clip(job["clip_start"], job["clip_end"], item["duration"])
            clip_length = clip[1] - clip[0] if clip else None
            out_key = presets.output_key(preset_id, target_mb, clip)
            existing = store.find_file(conn, user_id, media_id, "output", out_key)
            if existing:
                finish(existing["id"], reused=True)
                return

            # A clip is cut from the whole original, which is then kept for more clips of the same video.
            key = presets.source_key(preset_id, target_mb, clip_length or item["duration"])
            with self.source_lock(media_id, key):
                source = store.find_file(conn, user_id, media_id, "source", key)
                if source:
                    source_id = source["id"]
                    source_path = store.abs_path(source)
                else:
                    set_stage("downloading")
                    tmp = config.TMP_DIR / uuid.uuid4().hex
                    try:
                        def fetch(cookie_file):
                            extra = {"cookiefile": cookie_file} if cookie_file else {}
                            return media.download(item["url"], key, tmp, cfg["max_source_mb"] * MB,
                                                  on_progress, should_cancel, **extra)

                        # The owner's connected account is used only if this video needs a sign-in.
                        got, _ = cookies.with_login(conn, user_id, item["platform"], fetch,
                                                    prefer=bool(item["needs_login"]))
                        source_path = config.SOURCES_DIR / f"{uuid.uuid4().hex}{got.suffix}"
                        shutil.move(got, source_path)
                    finally:
                        shutil.rmtree(tmp, ignore_errors=True)
                    source_id = store.add_file(
                        conn, user_id=user_id, media_id=media_id, kind="source", key=key,
                        path=source_path, ttl_seconds=cfg["source_ttl_min"] * 60,
                    )
                with self.guard:
                    self.in_use.add(source_id)
                held.append(source_id)

            set_stage("converting")
            out = media.convert(source_path, config.OUTPUTS_DIR, preset_id, target_mb,
                                on_progress, should_cancel, clip=clip)
            size = out.stat().st_size
            if size > cfg["max_file_mb"] * MB:
                out.unlink(missing_ok=True)
                raise media.MediaError(i18n.T(
                    "The finished file is {size} MB, over the {limit} MB limit. Use Fit a size to shrink it.",
                    size=round(size / MB), limit=cfg["max_file_mb"]))
            file_id = store.add_file(
                conn, user_id=user_id, media_id=media_id, kind="output", key=out_key, path=out,
                ttl_seconds=cfg["output_ttl_hours"] * 3600, meta=media.probe(out),
            )
            if storage.mode(conn) == "r2":
                # Hand the finished file to cloud storage; viewers then fetch it from there, not from this server.
                set_stage("uploading")
                object_key = f"outputs/{out.name}"
                try:
                    storage.upload(conn, out, object_key, store.MIME.get(out.suffix))
                    conn.execute("UPDATE files SET storage='r2', path=? WHERE id=?", (object_key, file_id))
                    out.unlink(missing_ok=True)
                except Exception as exc:
                    log.exception("Upload to cloud storage failed; keeping job %s on this server", job_id)
                    notify.send(conn, "storage_failed", "Cloud storage upload failed",
                                T("A finished video stayed on the server instead: {reason}", reason=str(exc)[:200]))
            finish(file_id)
            log.info("Job %s done: %s, %.1f MB", job_id, preset_id, size / MB)
            notify.send(conn, "job_done", "Video ready",
                        T("{title} · {size} MB", title=item["title"] or "Video", size=round(size / MB, 1)),
                        click=notify.job_link(job_id))
        except media.Canceled:
            if self.stop.is_set():
                conn.execute("UPDATE jobs SET status='queued', stage=NULL, progress=0 WHERE id=?", (job_id,))
            else:
                conn.execute(
                    "UPDATE jobs SET status='canceled', stage=NULL, finished_at=? WHERE id=?",
                    (db.now(), job_id),
                )
        except (media.MediaError, presets.PresetError) as exc:
            self.fail(conn, job_id, exc.args[0] if exc.args else str(exc))
        except Exception:
            log.exception("Job %s crashed", job_id)
            self.fail(conn, job_id, "Something went wrong on the server. The details are in the server log.")
        finally:
            with self.guard:
                self.in_use.difference_update(held)
            conn.close()

    @staticmethod
    def fail(conn, job_id: int, message) -> None:
        log.warning("Job %s failed: %s", job_id, message)
        conn.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
            (i18n.pack(message), db.now(), job_id),  # stored so it can be shown in either language
        )
        row = conn.execute(
            "SELECT m.title, m.platform, u.name FROM jobs j JOIN media m ON m.id=j.media_id "
            "JOIN users u ON u.id=j.user_id WHERE j.id=?", (job_id,)).fetchone()
        if row:
            notify.send(conn, "job_failed", T("Video failed ({person})", person=row["name"]),
                        T("{title}: {reason}", title=row["title"] or row["platform"],
                          reason=i18n.render(message, notify.admin_lang(conn))),
                        click=notify.job_link(job_id))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Worker().main()
