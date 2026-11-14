"""Small preview pictures of videos, kept on this server.

Platforms hand out thumbnail addresses that stop working after a while, so the picture is copied here
when a link is looked up and shown from here afterwards (the size step, the Recent list, the player).
"""
import ipaddress
import logging
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import config

log = logging.getLogger("joyshare.thumbs")

FOLDER = config.DATA_DIR / "thumbs"
MAX_BYTES = 3 * 1024 * 1024
KINDS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MIME = {ext: mime for mime, ext in KINDS.items()}


def _safe(url: str) -> bool:
    """Only https addresses on the public internet: this server must never be made to fetch from its own network."""
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            return False
        for info in socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
        return True
    except (ValueError, OSError):
        return False


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe(newurl):
            raise urllib.error.HTTPError(newurl, code, "redirect to a refused address", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str) -> tuple[bytes, str]:
    """The one place that talks to the network. Tests replace it. Returns (bytes, content type)."""
    if not _safe(url):
        raise ValueError("refused address")
    opener = urllib.request.build_opener(_CheckedRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
    with opener.open(request, timeout=8) as response:
        kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = response.read(MAX_BYTES + 1)
    return data, kind


def find(media_id: int) -> Path | None:
    for ext in MIME:
        path = FOLDER / f"{int(media_id)}{ext}"
        if path.is_file():
            return path
    return None


def save(media_id: int, url: str | None) -> Path | None:
    """Copies the picture at `url` here. Returns the file, or None when it could not be had."""
    if not url:
        return None
    try:
        data, kind = _download(url)
        if kind not in KINDS or not data or len(data) > MAX_BYTES:
            raise ValueError(f"not a usable picture ({kind or 'no type'}, {len(data)} bytes)")
        FOLDER.mkdir(parents=True, exist_ok=True)
        for old in FOLDER.glob(f"{int(media_id)}.*"):
            old.unlink(missing_ok=True)
        target = FOLDER / f"{int(media_id)}{KINDS[kind]}"
        partial = target.with_suffix(target.suffix + f".{threading.get_ident()}.part")
        partial.write_bytes(data)
        partial.replace(target)
        return target
    except Exception as exc:   # a missing picture is never worth failing a lookup for
        log.info("No thumbnail for video %s: %s", media_id, exc)
        return None


def save_soon(media_id: int, url: str | None) -> None:
    """Fetches in the background, so looking up a link doesn't wait for a picture."""
    if url:
        threading.Thread(target=save, args=(media_id, url), name="thumb", daemon=True).start()
