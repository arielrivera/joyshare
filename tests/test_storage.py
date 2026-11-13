import io

import pytest

from app import auth, cleanup, config, db, settings, storage, store
from conftest import browser

DETAILS = {"r2_account_id": "abc123", "r2_bucket": "joyshare", "r2_access_key_id": "KEYID", "r2_secret_access_key": "TOPSECRET"}


class FakeBucket:
    """Stands in for Cloudflare R2: remembers objects, hands out fake signed links."""

    def __init__(self):
        self.objects, self.calls, self.fail = {}, [], set()

    def _check(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} refused")

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self._check("put")
        self.objects[Key] = Body

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self._check("upload")
        self.objects[key] = open(path, "rb").read()

    def delete_object(self, Bucket, Key):
        self._check("delete")
        self.objects.pop(Key, None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        extra = "".join(f"&{k}={v}" for k, v in Params.items() if k.startswith("Response"))
        return f"https://abc123.r2.cloudflarestorage.com/{Params['Bucket']}/{Params['Key']}?X-Amz-Expires={ExpiresIn}{extra}"

    def put_bucket_cors(self, **kwargs):
        self._check("cors")

    def put_bucket_lifecycle_configuration(self, **kwargs):
        self._check("lifecycle")


@pytest.fixture()
def bucket(monkeypatch, conn):
    fake = FakeBucket()
    monkeypatch.setattr(storage, "_client", lambda cfg: fake)

    def urlopen(url, timeout=None):
        key = url.split("?")[0].split("/joyshare/", 1)[1]
        return io.BytesIO(fake.objects[key])

    monkeypatch.setattr(storage.urllib.request, "urlopen", urlopen)
    storage.forget_cache()
    yield fake
    storage.forget_cache()


def turn_on(client):
    assert client.put("/api/admin/settings", json={"changes": DETAILS}).status_code == 200
    assert client.post("/api/admin/storage/test").json()["passed"] is True
    assert client.put("/api/admin/settings", json={"changes": {"storage": "r2"}}).status_code == 200


def make_file(conn, name="clip.mp4", user_id=1, ttl=600):
    media_id = conn.execute(
        "INSERT INTO media (user_id, url, platform, title, uploader, created_at) VALUES (?, 'https://x.com/a/status/1', 'x', 'Clip ñ', 'someone', ?)",
        (user_id, db.now())).lastrowid
    path = config.OUTPUTS_DIR / name
    path.write_bytes(b"video-bytes")
    return store.add_file(conn, user_id=user_id, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=ttl), path, media_id


def move_to_bucket(conn, bucket, file_id, path):
    key = f"outputs/{path.name}"
    storage.upload(conn, path, key, "video/mp4")
    conn.execute("UPDATE files SET storage='r2', path=? WHERE id=?", (key, file_id))
    path.unlink()
    return key


def test_cannot_switch_on_before_a_passed_test(client, conn, bucket):
    assert client.get("/api/admin/storage").json()["mode"] == "local"
    assert client.put("/api/admin/settings", json={"changes": {"storage": "r2"}}).status_code == 422   # nothing set up
    client.put("/api/admin/settings", json={"changes": DETAILS})
    assert client.put("/api/admin/settings", json={"changes": {"storage": "r2"}}).status_code == 422   # set up, not tested
    assert storage.mode(conn) == "local"

    result = client.post("/api/admin/storage/test").json()
    assert result["passed"] and [s["step"] for s in result["steps"]] == ["write", "read", "delete", "cors", "lifecycle"]
    assert bucket.objects == {}                                                                        # the test file is cleaned up
    assert client.put("/api/admin/settings", json={"changes": {"storage": "r2"}}).status_code == 200
    status = client.get("/api/admin/storage").json()
    assert status["mode"] == "r2" and status["tested"] and status["complete"]


def test_secret_is_encrypted_and_never_sent_back(client, conn, bucket):
    client.put("/api/admin/settings", json={"changes": DETAILS})
    stored = conn.execute("SELECT value FROM settings WHERE key='r2_secret_access_key'").fetchone()["value"]
    assert "TOPSECRET" not in stored and "enc:" in stored
    assert storage.read_config(conn)["secret"] == "TOPSECRET"
    pages = client.get("/api/admin/storage").text + client.get("/api/admin/settings").text + client.get("/api/admin/audit").text
    assert "TOPSECRET" not in pages and '"has_r2_secret_access_key":true' in pages.replace(" ", "")


def test_failed_test_keeps_it_off(client, conn, bucket):
    client.put("/api/admin/settings", json={"changes": DETAILS})
    bucket.fail.add("put")
    result = client.post("/api/admin/storage/test").json()
    assert result["passed"] is False and result["steps"][0] == {"step": "write", "ok": False, "detail": "put refused"}
    assert client.put("/api/admin/settings", json={"changes": {"storage": "r2"}}).status_code == 422

    bucket.fail = {"cors", "lifecycle"}                 # storage without those extras still passes
    result = client.post("/api/admin/storage/test").json()
    assert result["passed"] is True and [s["ok"] for s in result["steps"]] == [True, True, True, False, False]


def test_changing_details_switches_back_until_retested(client, conn, bucket):
    turn_on(client)
    assert storage.mode(conn) == "r2"
    client.put("/api/admin/settings", json={"changes": {"r2_bucket": "another-bucket"}})
    assert storage.mode(conn) == "local" and settings.get(conn, "storage") == "local"
    assert client.get("/api/admin/storage").json()["tested"] is False


def test_bad_details_are_refused(client, bucket):
    for changes in ({"r2_bucket": "Has Spaces"}, {"r2_endpoint": "ftp://x"}, {"r2_account_id": "no/slash"}, {"storage": "floppy"}):
        assert client.put("/api/admin/settings", json={"changes": changes}).status_code == 422, changes
    assert client.post("/api/admin/storage/test").status_code == 422        # nothing filled in yet


def test_files_in_the_bucket_are_served_by_signed_link(client, conn, bucket):
    turn_on(client)
    file_id, path, _ = make_file(conn)
    key = move_to_bucket(conn, bucket, file_id, path)

    stream = client.get(f"/api/files/{file_id}/stream", follow_redirects=False)
    assert stream.status_code == 302 and stream.headers["cache-control"] == "no-store"
    assert stream.headers["location"].startswith(f"https://abc123.r2.cloudflarestorage.com/joyshare/{key}?X-Amz-Expires=3600")
    assert "ResponseContentDisposition" not in stream.headers["location"]

    download = client.get(f"/api/files/{file_id}/download", follow_redirects=False)
    where = download.headers["location"]
    assert "ResponseContentDisposition=attachment" in where and "filename*=UTF-8''Clip%20%C3%B1%20-%20someone.mp4" in where

    token = client.post(f"/api/files/{file_id}/share").json()["url"].rsplit("/", 1)[1]
    assert client.get(f"/v/{token}").status_code == 200                       # the page itself still comes from here
    shared = browser().get(f"/v/{token}/file", follow_redirects=False)        # a friend, not signed in
    assert shared.status_code == 302 and key in shared.headers["location"]

    assert store.find_file(conn, 1, conn.execute("SELECT media_id FROM files WHERE id=?", (file_id,)).fetchone()[0],
                           "output", "720") is not None                       # reused without a local copy
    status = client.get("/api/admin/storage").json()
    assert status["files_in_cloud"] == 1 and status["bytes_in_cloud"] == len(b"video-bytes")


def test_other_people_cannot_get_a_link_to_your_file(client, conn, bucket):
    turn_on(client)
    file_id, path, _ = make_file(conn)
    move_to_bucket(conn, bucket, file_id, path)
    other = conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid
    member = browser(auth.create_session(conn, other))
    assert member.get(f"/api/files/{file_id}/stream", follow_redirects=False).status_code == 404
    assert member.get("/api/admin/storage").status_code == 403
    assert member.post("/api/admin/storage/test").status_code == 403


def test_page_policy_allows_the_bucket_only_when_set_up(client, conn, bucket):
    assert "r2.cloudflarestorage.com" not in client.get("/").headers["content-security-policy"]
    turn_on(client)
    policy = client.get("/").headers["content-security-policy"]
    assert "media-src 'self' blob: https://abc123.r2.cloudflarestorage.com;" in policy
    assert "connect-src 'self' https://abc123.r2.cloudflarestorage.com;" in policy


def test_cleanup_deletes_from_the_bucket_and_retries(client, conn, bucket):
    turn_on(client)
    file_id, path, _ = make_file(conn, ttl=-5)
    key = move_to_bucket(conn, bucket, file_id, path)

    bucket.fail.add("delete")
    assert cleanup.delete_expired(conn) == 0 and key in bucket.objects        # couldn't reach the bucket: try again later
    assert conn.execute("SELECT deleted_at FROM files WHERE id=?", (file_id,)).fetchone()[0] is None

    bucket.fail.clear()
    assert cleanup.delete_expired(conn) == 1 and key not in bucket.objects
    assert client.get(f"/api/files/{file_id}/stream", follow_redirects=False).status_code == 410


def test_going_back_to_this_server_keeps_bucket_files_working(client, conn, bucket):
    turn_on(client)
    file_id, path, _ = make_file(conn)
    move_to_bucket(conn, bucket, file_id, path)
    assert client.put("/api/admin/settings", json={"changes": {"storage": "local"}}).status_code == 200
    assert storage.mode(conn) == "local"
    assert client.get(f"/api/files/{file_id}/stream", follow_redirects=False).status_code == 302
