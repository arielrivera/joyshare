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

# Every address the app may be opened at. The first is the main one (share links and invites use it).
# By default the app can also be opened on the server itself at http://localhost:PORT, which is handy
# for the first setup and as a way back in. Passkeys are tied to the address they were made at.
_extra = os.environ.get("JOYSHARE_EXTRA_ORIGINS", f"http://localhost:{os.environ.get('JOYSHARE_PORT', '8080')}")
ORIGINS = list(dict.fromkeys([PUBLIC_URL] + [o.strip().rstrip("/") for o in _extra.split(",") if o.strip()]))

# The name shown at the top until a person picks their own.
APP_NAME = os.environ.get("JOYSHARE_NAME", "vidshare").strip()[:24] or "vidshare"

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Phase 1 has a single built-in user. Sign-in and more users arrive in phase 2.
DEFAULT_USER_ID = 1


def ensure_dirs() -> None:
    for d in (DATA_DIR, SOURCES_DIR, OUTPUTS_DIR, TMP_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
