"""Encryption for things that must not sit readable in the database (cookie files today).

The key comes from JOYSHARE_SECRET in .env. If that isn't set, a key is created once and kept in the
data volume (/data/secret.key). Setting JOYSHARE_SECRET is better: then a copy of the data alone
can't be read. Changing the secret makes everything encrypted with the old one unreadable, and
people simply upload their cookie files again.
"""
import base64
import hashlib
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from . import config


class Unreadable(Exception):
    """The data was encrypted with a different secret."""


def _secret() -> str:
    from_env = os.environ.get("JOYSHARE_SECRET", "").strip()
    if from_env:
        return from_env
    path = config.DATA_DIR / "secret.key"
    try:
        return path.read_text().strip()
    except OSError:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(48)
        path.write_text(value)
        path.chmod(0o600)
        return value


def _box() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret().encode()).digest()))


def encrypt(text: str) -> bytes:
    return _box().encrypt(text.encode())


def decrypt(data: bytes) -> str:
    try:
        return _box().decrypt(bytes(data)).decode()
    except InvalidToken as exc:
        raise Unreadable() from exc
