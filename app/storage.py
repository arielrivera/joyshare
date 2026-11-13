"""Where finished files are served from: this server's disk, or Cloudflare R2.

With R2 on, the worker uploads each finished file to the bucket and deletes its local copy.
Pages then hand out signed links that work for about an hour, so the video itself travels
straight from R2 to the viewer and never through this server (or the Cloudflare Tunnel in front of it).

R2 speaks the same language as Amazon S3, so this also works with other S3-compatible storage
by filling in the "endpoint" setting.
"""
import hashlib
import logging
import threading
import time
import urllib.request
from urllib.parse import quote, urlsplit

from . import config, db, secretbox, settings

log = logging.getLogger("joyshare.storage")

LINK_SECONDS = 3600
SECRET_PREFIX = "enc:"
_clients: dict = {}
_lock = threading.Lock()
_origin_cache = {"at": 0.0, "value": ""}


class StorageError(Exception):
    """Talking to the bucket failed. The message is safe to show to the admin."""


def seal(secret: str) -> str:
    """How the secret key is kept in the settings table."""
    return SECRET_PREFIX + secretbox.encrypt(secret).decode() if secret else ""


def read_config(conn) -> dict:
    cfg = settings.get_all(conn)
    secret = ""
    stored = cfg["r2_secret_access_key"]
    if stored.startswith(SECRET_PREFIX):
        try:
            secret = secretbox.decrypt(stored[len(SECRET_PREFIX):].encode())
        except secretbox.Unreadable:
            secret = ""
    endpoint = cfg["r2_endpoint"] or (f"https://{cfg['r2_account_id']}.r2.cloudflarestorage.com" if cfg["r2_account_id"] else "")
    result = {
        "endpoint": endpoint.rstrip("/"), "bucket": cfg["r2_bucket"], "key_id": cfg["r2_access_key_id"],
        "secret": secret, "region": cfg["r2_region"] or "auto", "wanted": cfg["storage"],
    }
    result["complete"] = all(result[k] for k in ("endpoint", "bucket", "key_id", "secret"))
    return result


def fingerprint(cfg: dict) -> str:
    """Changes whenever any connection detail changes, so a passed test is tied to exact details."""
    joined = "|".join(cfg[k] for k in ("endpoint", "bucket", "key_id", "secret", "region"))
    return hashlib.sha256(joined.encode()).hexdigest()


def is_tested(conn, cfg: dict | None = None) -> bool:
    cfg = cfg or read_config(conn)
    passed, _ = db.get_state(conn, "r2_tested")
    return bool(cfg["complete"] and passed == fingerprint(cfg))


def mode(conn) -> str:
    """"r2" only when it was chosen, is fully filled in and passed its test. Otherwise "local"."""
    cfg = read_config(conn)
    return "r2" if cfg["wanted"] == "r2" and is_tested(conn, cfg) else "local"


def _client(cfg: dict):
    import boto3
    from botocore.config import Config

    mark = fingerprint(cfg)
    with _lock:
        if mark not in _clients:
            _clients.clear()
            _clients[mark] = boto3.client(
                "s3", endpoint_url=cfg["endpoint"], aws_access_key_id=cfg["key_id"],
                aws_secret_access_key=cfg["secret"], region_name=cfg["region"],
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                              connect_timeout=10, read_timeout=120, retries={"max_attempts": 3}),
            )
        return _clients[mark]


def _ready(conn) -> dict:
    cfg = read_config(conn)
    if not cfg["complete"]:
        raise StorageError("Cloud storage isn't fully set up.")
    return cfg


def upload(conn, path, key: str, mime: str | None) -> None:
    cfg = _ready(conn)
    _client(cfg).upload_file(str(path), cfg["bucket"], key, ExtraArgs={"ContentType": mime or "application/octet-stream"})


def put_file(conn, path, key: str, mime: str) -> None:
    """Upload any file (used for backups)."""
    upload(conn, path, key, mime)


def list_keys(conn, prefix: str) -> list[str]:
    cfg = _ready(conn)
    found = _client(cfg).list_objects_v2(Bucket=cfg["bucket"], Prefix=prefix)
    return [item["Key"] for item in found.get("Contents", [])]


def delete(conn, key: str) -> None:
    cfg = _ready(conn)
    _client(cfg).delete_object(Bucket=cfg["bucket"], Key=key)


def signed_url(conn, key: str, *, mime: str | None = None, download_name: str | None = None,
               seconds: int = LINK_SECONDS) -> str:
    """A link to one file that works for a limited time and can't be guessed or reused later."""
    cfg = _ready(conn)
    params = {"Bucket": cfg["bucket"], "Key": key}
    if mime:
        params["ResponseContentType"] = mime
    if download_name:
        params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{quote(download_name)}"
    return _client(cfg).generate_presigned_url("get_object", Params=params, ExpiresIn=seconds)


def media_origin(conn) -> str:
    """The bucket's web address, for the page's security policy. Empty when files are local. Cached briefly."""
    if time.time() - _origin_cache["at"] > 30:
        cfg = read_config(conn)
        parts = urlsplit(cfg["endpoint"]) if cfg["complete"] else None
        _origin_cache.update(at=time.time(), value=f"{parts.scheme}://{parts.netloc}" if parts and parts.netloc else "")
    return _origin_cache["value"]


def media_origin_if_fresh() -> str | None:
    """The cached answer, or None when it is time to look again (saves opening the database on every request)."""
    return _origin_cache["value"] if time.time() - _origin_cache["at"] <= 30 else None


def forget_cache() -> None:
    _origin_cache["at"] = 0.0


def test(conn) -> list[dict]:
    """Try the bucket for real: write a file, read it through a signed link, delete it.

    Also asks the bucket to allow this site to read files (needed for the phone's Share button)
    and to delete leftovers after a few days. Those two are nice-to-have and only reported.
    Returns the steps; marks the details as tested when the three essential steps pass.
    """
    cfg = _ready(conn)
    client = _client(cfg)
    key = f"joyshare-test-{db.now()}.txt"
    body = b"joyshare connection test"
    steps = []

    def essential(name: str, action):
        try:
            action()
            steps.append({"step": name, "ok": True})
        except Exception as exc:
            steps.append({"step": name, "ok": False, "detail": str(exc)[:300]})
            raise StorageError(name) from exc

    def read_back():
        url = client.generate_presigned_url("get_object", Params={"Bucket": cfg["bucket"], "Key": key}, ExpiresIn=120)
        with urllib.request.urlopen(url, timeout=20) as response:
            if response.read() != body:
                raise ValueError("the file came back different")

    try:
        essential("write", lambda: client.put_object(Bucket=cfg["bucket"], Key=key, Body=body, ContentType="text/plain"))
        essential("read", read_back)
        essential("delete", lambda: client.delete_object(Bucket=cfg["bucket"], Key=key))
    except StorageError:
        db.set_state(conn, "r2_tested", "")
        db.set_state(conn, "r2_test_steps", __import__("json").dumps(steps))
        return steps

    def optional(name: str, action):
        try:
            action()
            steps.append({"step": name, "ok": True})
        except Exception as exc:
            steps.append({"step": name, "ok": False, "optional": True, "detail": str(exc)[:300]})

    optional("cors", lambda: client.put_bucket_cors(Bucket=cfg["bucket"], CORSConfiguration={"CORSRules": [{
        "AllowedOrigins": [config.PUBLIC_URL], "AllowedMethods": ["GET", "HEAD"], "AllowedHeaders": ["*"],
        "ExposeHeaders": ["Content-Length", "Content-Range"], "MaxAgeSeconds": 3600}]}))
    optional("lifecycle", lambda: client.put_bucket_lifecycle_configuration(Bucket=cfg["bucket"], LifecycleConfiguration={
        "Rules": [{"ID": "joyshare-leftovers", "Status": "Enabled", "Filter": {"Prefix": "outputs/"},
                   "Expiration": {"Days": max(3, settings.get(conn, "output_ttl_hours") // 24 + 2)}}]}))
    db.set_state(conn, "r2_tested", fingerprint(cfg))
    db.set_state(conn, "r2_test_steps", __import__("json").dumps(steps))
    forget_cache()
    return steps
