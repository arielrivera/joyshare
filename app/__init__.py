"""joyshare.

This runs before anything else in the app is imported. If an updated yt-dlp has been installed
into the data volume (see app/engine.py), its folder goes first on the import path, so
"import yt_dlp" picks it up instead of the version that came with the container.
"""
import os
import sys
from pathlib import Path


def _use_updated_ytdlp() -> str:
    base = Path(os.environ.get("JOYSHARE_DATA", "/data")) / "ytdlp"
    try:
        name = (base / "current").read_text().strip()
    except OSError:
        return ""
    folder = base / name
    if name and "/" not in name and ".." not in name and (folder / "yt_dlp").is_dir():
        sys.path.insert(0, str(folder))
        return name
    return ""


# What this process loaded: a version folder name, or "" for the built-in one.
LOADED_YTDLP = _use_updated_ytdlp()
