"""The size and quality choices offered to the user, and how each maps to yt-dlp."""
from dataclasses import dataclass

PRESETS = [
    {"id": "best", "label": "Best quality", "detail": "Up to 1080p", "kind": "video", "height": 1080},
    {"id": "720", "label": "Share", "detail": "720p", "kind": "video", "height": 720},
    {"id": "480", "label": "Small", "detail": "480p", "kind": "video", "height": 480},
    {"id": "fit", "label": "Fit a size", "detail": "Shrink to the size you pick", "kind": "video", "height": 720},
    {"id": "audio", "label": "Audio only", "detail": "M4A", "kind": "audio", "height": None},
]
BY_ID = {p["id"]: p for p in PRESETS}

AUDIO_SOURCE = "audio"


class PresetError(ValueError):
    """The request can't be done. The message is safe to show to the user."""


@dataclass(frozen=True)
class FitPlan:
    video_kbps: int
    audio_kbps: int
    height: int


def fit_plan(target_bytes: int, duration: float, src_height: int | None = None) -> FitPlan:
    """Work out bitrates and picture height so a video lands under target_bytes."""
    if not duration or duration <= 0:
        raise PresetError("This video's length is unknown, so it can't be fitted to a size.")
    # Keep 4% back for the MP4 container's own overhead.
    total_kbps = target_bytes * 8 / duration / 1000 * 0.96
    audio_kbps = 96 if total_kbps >= 400 else 64 if total_kbps >= 200 else 48
    video_kbps = int(total_kbps - audio_kbps)
    if video_kbps < 80:
        raise PresetError("This video is too long to fit in that size. Pick a bigger size or use Audio only.")
    if video_kbps >= 1200:
        height = 720
    elif video_kbps >= 500:
        height = 480
    elif video_kbps >= 220:
        height = 360
    else:
        height = 240
    if src_height:
        height = min(height, src_height)
    return FitPlan(video_kbps=video_kbps, audio_kbps=audio_kbps, height=height)


def source_key(preset_id: str, target_mb: int | None = None, duration: float | None = None) -> str:
    """Which download a preset needs. Presets that share a key share one download."""
    preset = BY_ID[preset_id]
    if preset["kind"] == "audio":
        return AUDIO_SOURCE
    if preset_id == "fit":
        plan = fit_plan(int(target_mb or 0) * 1024 * 1024, duration or 0)
        return "v720" if plan.height >= 720 else "v480"
    return f"v{preset['height']}"


def source_height(key: str) -> int | None:
    return None if key == AUDIO_SOURCE else int(key[1:])


def ydl_format(key: str) -> dict:
    """yt-dlp options that pick the right streams, preferring ones that need no converting."""
    if key == AUDIO_SOURCE:
        return {"format": "ba/b", "format_sort": ["acodec:m4a"]}
    return {
        "format": "bv*+ba/b",
        "format_sort": [f"res:{source_height(key)}", "vcodec:h264", "acodec:m4a"],
    }


MIN_CLIP = 1.0   # seconds


def check_clip(start, end, duration: float | None) -> tuple[float, float] | None:
    """Tidies and checks the part of a video someone asked for. None means the whole video."""
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise PresetError("Give both a start and an end for the clip.")
    start, end = round(float(start), 1), round(float(end), 1)
    if duration and end > duration:
        if end > duration + 1:
            raise PresetError("The clip must be inside the video.")
        end = round(float(duration), 1)
    if start < 0 or end - start < MIN_CLIP:
        raise PresetError("The end must be at least 1 second after the start.")
    return start, end


CREDIT_MARK = "+credit"   # ends the key of a file with the visible credit drawn on it


def output_key(preset_id: str, target_mb: int | None = None, clip: tuple[float, float] | None = None,
               credit: bool = False) -> str:
    """Names a finished file, so the same request reuses it. A clip's range is part of the name, and so is
    the visible credit: a file with it and one without are never handed out for each other."""
    key = f"fit-{int(target_mb)}" if preset_id == "fit" else preset_id
    key = f"{key}@{clip[0]:.1f}-{clip[1]:.1f}" if clip else key
    return key + CREDIT_MARK if credit and BY_ID[preset_id]["kind"] != "audio" else key
