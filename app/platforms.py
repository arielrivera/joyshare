"""Which links we accept.

Only known platforms are allowed. This is a safety rule as much as a feature:
the server must never be usable to fetch arbitrary addresses.
"""
from urllib.parse import urlsplit

from .i18n import T

PLATFORMS = {
    "x": {
        "label": "X (Twitter)",
        "hosts": {"x.com", "twitter.com"},
        "extractors": ["twitter.*"],
        "experimental": False,
    },
    "youtube": {
        "label": "YouTube",
        "hosts": {"youtube.com", "youtu.be", "music.youtube.com"},
        "extractors": ["youtube.*"],
        "experimental": False,
    },
    "tiktok": {
        "label": "TikTok",
        "hosts": {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"},
        "extractors": ["tiktok", r"vm\.tiktok"],
        "experimental": False,
    },
    "instagram": {
        "label": "Instagram",
        "hosts": {"instagram.com"},
        "extractors": ["instagram.*"],
        "experimental": True,
    },
    "facebook": {
        "label": "Facebook",
        "hosts": {"facebook.com", "fb.watch"},
        "extractors": ["facebook.*"],
        "experimental": True,
    },
}

_PREFIXES = ("www.", "m.", "mobile.", "web.")


class LinkError(ValueError):
    """The link can't be used. The message is safe to show to the user."""


def _bare_host(host: str) -> str:
    host = host.lower().rstrip(".")
    for prefix in _PREFIXES:
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def detect(url: str, enabled: list[str] | None = None) -> tuple[str, str]:
    """Returns (platform id, cleaned url) or raises LinkError."""
    url = (url or "").strip()
    if not url:
        raise LinkError("Paste a link first.")
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LinkError("That doesn't look like a web link.")
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        raise LinkError("That doesn't look like a normal video link.")
    host = _bare_host(parts.hostname)
    for platform, spec in PLATFORMS.items():
        if host in spec["hosts"]:
            if enabled is not None and platform not in enabled:
                raise LinkError(T("{platform} is turned off on this server.", platform=spec["label"]))
            clean = parts._replace(scheme="https", fragment="").geturl()
            return platform, clean
    raise LinkError("joyshare works with links from X, YouTube, TikTok, Instagram and Facebook.")


def allowed_extractors() -> list[str]:
    names: list[str] = []
    for spec in PLATFORMS.values():
        names.extend(spec["extractors"])
    return names
