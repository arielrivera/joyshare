"""Everything that talks to yt-dlp and ffmpeg."""
import copy
import json
import logging
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import config, platforms, presets
from .i18n import T

log = logging.getLogger("joyshare.media")

OK_PIXEL_FORMATS = {"yuv420p", "yuvj420p"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class MediaError(Exception):
    """Something went wrong that the user should hear about. The message is shown as is."""

    needs_login = False  # True when the platform wanted a signed-in account


class Canceled(Exception):
    pass


class _YdlLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        log.debug("yt-dlp warning: %s", msg)

    def error(self, msg):
        log.info("yt-dlp error: %s", msg)


def _ydl_opts(extra: dict | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "playlist_items": "1",
        "allowed_extractors": platforms.allowed_extractors(),
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "cachedir": str(config.CACHE_DIR),
        "logger": _YdlLogger(),
    }
    opts.update(extra or {})
    return opts


def wants_login(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(w in text for w in ("sign in", "log in", "login", "cookies", "authentication", "age-restricted"))


def as_media_error(exc: Exception) -> MediaError:
    error = MediaError(friendly_error(exc))
    error.needs_login = wants_login(exc)
    return error


def friendly_error(exc: Exception) -> str:
    """Turn a yt-dlp error into one plain sentence."""
    raw = _ANSI.sub("", str(exc)).replace("ERROR: ", "").strip()
    text = raw.lower()
    if wants_login(exc):
        return "The platform only shows this video to signed-in accounts."
    if "private" in text:
        return "This video is private."
    if "unsupported url" in text or "no suitable extractor" in text:
        return "That link doesn't point to a video that can be read."
    if any(w in text for w in ("no video", "not available", "unavailable", "removed", "does not exist", "not found")):
        return "No video was found at that link. It may have been removed, or the post has no video."
    if "timed out" in text or "connection" in text:
        return "The platform didn't answer in time. Try again in a moment."
    return T("The platform refused the request: {reason}", reason=raw.split("\n")[0][:200])


# ---------- reading a link ----------

def inspect(url: str, cookiefile: Path | None = None) -> dict:
    """Ask the platform about a link without downloading anything."""
    with YoutubeDL(_ydl_opts({"cookiefile": str(cookiefile)} if cookiefile else None)) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except DownloadError as exc:
            raise as_media_error(exc) from exc
        if info and info.get("_type") in ("playlist", "multi_video"):
            entries = [e for e in (info.get("entries") or []) if e]
            info = entries[0] if entries else None
        if not info:
            raise MediaError("No video was found at that link.")
        if info.get("is_live"):
            raise MediaError("Live streams can't be downloaded while they are live.")
        info = ydl.sanitize_info(info)
    # Drop yt-dlp's own default pick, so each preset chooses its streams from scratch.
    for stale in ("requested_formats", "requested_downloads", "format", "format_id"):
        info.pop(stale, None)
    return info


def estimate(info: dict, key: str) -> dict | None:
    """What a download with this source key would pick, and roughly how big it is."""
    try:
        with YoutubeDL(_ydl_opts(presets.ydl_format(key))) as ydl:
            picked = ydl.process_video_result(copy.deepcopy(info), download=False)
    except Exception as exc:  # no matching format, etc.
        log.debug("estimate failed for %s: %s", key, exc)
        return None
    parts = picked.get("requested_formats") or [picked]
    duration = picked.get("duration") or info.get("duration")
    total, exact = 0, True
    for part in parts:
        size = part.get("filesize")
        if not size:
            exact = False
            size = part.get("filesize_approx")
        if not size and part.get("tbr") and duration:
            size = part["tbr"] * 1000 / 8 * duration
        if not size:
            total = None
            break
        total += int(size)
    video = next((p for p in parts if p.get("vcodec") not in (None, "none")), None)
    audio = next((p for p in parts if p.get("acodec") not in (None, "none")), None)
    vcodec = (video or {}).get("vcodec") or ""
    acodec = (audio or {}).get("acodec") or ""
    needs_convert = False
    if key != presets.AUDIO_SOURCE and video and not vcodec.startswith(("avc", "h264")):
        needs_convert = True
    if audio and not acodec.startswith(("mp4a", "aac")):
        needs_convert = True
    return {
        "bytes": total,
        "exact": exact,
        "height": (video or {}).get("height"),
        "vcodec": vcodec,
        "acodec": acodec,
        "needs_convert": needs_convert,
    }


# ---------- downloading ----------

def download(url: str, key: str, dest_dir: Path, max_bytes: int, on_progress, should_cancel,
             cookiefile: Path | None = None) -> Path:
    """Download the streams for a source key into dest_dir. Returns the file."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen = {"finished": 0, "finished_bytes": 0}
    problem: dict = {}

    def hook(d):
        if should_cancel():
            problem["canceled"] = True
            raise Canceled()
        info = d.get("info_dict") or {}
        parts = info.get("requested_formats") or [info]
        if d["status"] == "finished":
            seen["finished"] += 1
            seen["finished_bytes"] += d.get("total_bytes") or d.get("downloaded_bytes") or 0
            return
        if d["status"] != "downloading":
            return
        got = d.get("downloaded_bytes") or 0
        current_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        sizes = [p.get("filesize") or p.get("filesize_approx") for p in parts]
        expected = sum(sizes) if all(sizes) else None
        so_far = seen["finished_bytes"] + got
        if (expected and expected > max_bytes) or so_far > max_bytes:
            problem["too_big"] = True
            raise Canceled()
        if expected:
            fraction = so_far / expected
        else:
            within = got / current_total if current_total else 0
            fraction = (seen["finished"] + within) / max(len(parts), 1)
        on_progress(min(fraction, 1.0))

    opts = _ydl_opts({
        **presets.ydl_format(key),
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "merge_output_format": "mkv",
        "progress_hooks": [hook],
        "overwrites": True,
        **({"cookiefile": str(cookiefile)} if cookiefile else {}),
    })
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        if problem.get("too_big"):
            raise MediaError(T("This video is bigger than the {mb} MB download limit. Try a smaller preset.",
                               mb=max_bytes // (1024 * 1024))) from exc
        if problem.get("canceled") or isinstance(exc, Canceled):
            raise Canceled() from exc
        if isinstance(exc, DownloadError):
            raise as_media_error(exc) from exc
        raise
    files = [p for p in dest_dir.glob("source.*") if p.suffix not in (".part", ".ytdl")]
    if not files:
        raise MediaError("The download finished but no file was produced.")
    return max(files, key=lambda p: p.stat().st_size)


# ---------- looking at and converting files ----------

def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0) or None
    return {
        "duration": duration,
        "vcodec": video.get("codec_name") if video else None,
        "pix_fmt": video.get("pix_fmt") if video else None,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "acodec": audio.get("codec_name") if audio else None,
    }


def _run_ffmpeg(args: list[str], duration: float | None, on_progress, should_cancel,
                start: float = 0.0, span: float = 1.0) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", *args]
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        try:
            for line in proc.stdout:
                if should_cancel():
                    proc.terminate()
                    proc.wait()
                    raise Canceled()
                if duration and line.startswith(("out_time_us=", "out_time_ms=")):
                    value = line.split("=", 1)[1].strip()
                    if value.lstrip("-").isdigit():
                        fraction = max(0.0, min(int(value) / 1_000_000 / duration, 1.0))
                        on_progress(start + span * fraction)
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
        if code != 0:
            err.seek(0)
            tail = err.read()[-1500:].decode(errors="replace")
            log.error("ffmpeg failed (%s): %s", code, tail)
            raise MediaError("Converting the video failed.")
    on_progress(start + span)


def _scale(height: int) -> str:
    # Never upscale, and keep both sides even (H.264 needs that).
    return f"scale=w=-2:h='min({height},trunc(ih/2)*2)'"


def convert(src: Path, out_dir: Path, preset_id: str, target_mb: int | None,
            on_progress, should_cancel) -> Path:
    """Turn a downloaded source into the finished file for a preset."""
    out_dir.mkdir(parents=True, exist_ok=True)
    preset = presets.BY_ID[preset_id]
    info = probe(src)
    duration = info["duration"]
    name = uuid.uuid4().hex
    common_in = ["-i", str(src)]
    common_out = ["-sn", "-dn", "-map_metadata", "-1", "-movflags", "+faststart"]

    if preset["kind"] == "audio":
        if not info["acodec"]:
            raise MediaError("This video has no sound.")
        out = out_dir / f"{name}.m4a"
        codec = ["-c:a", "copy"] if info["acodec"] == "aac" else ["-c:a", "aac", "-b:a", "128k"]
        _run_ffmpeg([*common_in, "-vn", "-map", "0:a:0", *codec, *common_out, str(out)],
                    duration, on_progress, should_cancel)
        return out

    if not info["vcodec"]:
        raise MediaError("No video was found in the download. Try Audio only.")
    out = out_dir / f"{name}.mp4"
    video_ok = info["vcodec"] == "h264" and info["pix_fmt"] in OK_PIXEL_FORMATS
    audio_ok = info["acodec"] in (None, "aac")
    maps = ["-map", "0:v:0", "-map", "0:a:0?"]

    fits_already = True
    if preset_id == "fit":
        target_bytes = int(target_mb) * 1024 * 1024
        fits_already = video_ok and audio_ok and src.stat().st_size <= target_bytes * 0.98

    if preset_id != "fit" or fits_already:
        if video_ok:
            vargs = ["-c:v", "copy"]
        else:
            vargs = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                     "-vf", _scale(preset["height"])]
        aargs = ["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "128k"]
        _run_ffmpeg([*common_in, *maps, *vargs, *aargs, *common_out, str(out)],
                    duration, on_progress, should_cancel)
        return out

    # Fit a size: two-pass encode at a calculated bitrate, one retry if it overshoots.
    plan = presets.fit_plan(target_bytes, duration or 0, info["height"])
    video_kbps = plan.video_kbps
    with tempfile.TemporaryDirectory(dir=config.TMP_DIR) as tmp:
        passlog = str(Path(tmp) / "pass")
        for attempt in range(2):
            base = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{video_kbps}k",
                    "-pix_fmt", "yuv420p", "-vf", _scale(plan.height), "-passlogfile", passlog]
            _run_ffmpeg([*common_in, "-map", "0:v:0", "-an", "-sn", "-dn", *base, "-pass", "1",
                         "-f", "null", "/dev/null"],
                        duration, on_progress, should_cancel, start=0.0, span=0.45)
            _run_ffmpeg([*common_in, *maps, *base, "-pass", "2",
                         "-c:a", "aac", "-b:a", f"{plan.audio_kbps}k", "-ac", "2",
                         *common_out, str(out)],
                        duration, on_progress, should_cancel, start=0.45, span=0.55)
            size = out.stat().st_size
            if size <= target_bytes or attempt == 1:
                break
            video_kbps = max(60, int(video_kbps * target_bytes / size * 0.94))
    if out.stat().st_size > target_bytes:
        out.unlink(missing_ok=True)
        raise MediaError("Couldn't get this video under that size. Pick a bigger size or use Audio only.")
    return out
