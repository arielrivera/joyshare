"""Paths and values that come from the environment (not editable at runtime)."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("JOYSHARE_DATA", "/data"))
DB_PATH = DATA_DIR / "joyshare.db"
MEDIA_DIR = DATA_DIR / "media"
SOURCES_DIR = MEDIA_DIR / "sources"
OUTPUTS_DIR = MEDIA_DIR / "outputs"
TMP_DIR = MEDIA_DIR / "tmp"
CACHE_DIR = DATA_DIR / "cache"

PUBLIC_URL = os.environ.get("JOYSHARE_PUBLIC_URL", "http://localhost:8080").rstrip("/")

# The name shown at the top until a person picks their own.
APP_NAME = os.environ.get("JOYSHARE_NAME", "joyshare").strip()[:24] or "joyshare"

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Phase 1 has a single built-in user. Sign-in and more users arrive in phase 2.
DEFAULT_USER_ID = 1


def ensure_dirs() -> None:
    for d in (DATA_DIR, SOURCES_DIR, OUTPUTS_DIR, TMP_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
