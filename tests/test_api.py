import re
import pytest

from app import config, media, store


FAKE_INFO = {
    "id": "abc123", "title": "Test <clip>", "uploader": "someone", "duration": 60.0,
    "thumbnail": "https://example.com/t.jpg", "webpage_url": "https://x.com/someone/status/1",
}


@pytest.fixture()
def fake_media(monkeypatch):
    monkeypatch.setattr(media, "inspect", lambda url: dict(FAKE_INFO))
    monkeypatch.setattr(media, "estimate", lambda info, key: {
        "bytes": {"v1080": 300, "v720": 12, "v480": 5, "audio": 1}[key] * 1024 * 1024,
        "exact": True, "height": {"v1080": 1080, "v720": 720, "v480": 480}.get(key),
        "vcodec": "avc1", "acodec": "mp4a", "needs_convert": False,
    })


def test_health_and_static(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["worker_alive"] is False and len(health["instance"]) == 12
    page = client.get("/")
    assert page.status_code == 200 and "vidshare" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    # Scripts and styles are referenced at an address that changes with every update, so no cache can serve old ones.
    import re
    assert page.headers["cache-control"] == "no-cache"
    script = re.search(r'src="(/a/[0-9a-f]{12}/auth\.js)"', page.text).group(1)
    assert re.search(r'href="/a/[0-9a-f]{12}/style\.css"', page.text) and 'src="/auth.js"' not in page.text
    asset = client.get(script)
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert client.get(script.rsplit("/", 1)[0] + "/scenes/demolition.js").status_code == 200
    assert client.get("/a/000000000000/auth.js").status_code == 404        # an old version's address is simply gone
    assert client.get("/manifest.webmanifest").status_code == 200


def test_inspect_rejects_unknown_site(client):
    res = client.post("/api/inspect", json={"url": "https://example.com/video"})
    assert res.status_code == 422
    assert "X, YouTube, TikTok" in res.json()["detail"]


def test_inspect_marks_oversized_presets(client, fake_media):
    data = client.post("/api/inspect", json={"url": "https://x.com/someone/status/1"}).json()
    by_id = {p["id"]: p for p in data["presets"]}
    assert by_id["best"]["allowed"] is False and "limit" in by_id["best"]["reason"]
    assert by_id["720"]["allowed"] is True and by_id["720"]["est_bytes"] == 12 * 1024 * 1024
    assert by_id["audio"]["allowed"] is True
    assert [p["id"] for p in data["presets"] if p["recommended"]] == ["720"]
    assert [t["mb"] for t in by_id["fit"]["targets"]] == [8]  # only sizes smaller than the 12 MB 720p file


def test_inspect_same_video_reuses_media_row(client, fake_media):
    first = client.post("/api/inspect", json={"url": "https://x.com/someone/status/1"}).json()
    second = client.post("/api/inspect", json={"url": "https://twitter.com/someone/status/1"}).json()
    assert first["media"]["id"] == second["media"]["id"]


def test_job_validation(client, fake_media):
    media_id = client.post("/api/inspect", json={"url": "https://x.com/someone/status/1"}).json()["media"]["id"]
    assert client.post("/api/jobs", json={"media_id": media_id, "preset": "nope"}).status_code == 422
    assert client.post("/api/jobs", json={"media_id": media_id, "preset": "fit"}).status_code == 422
    assert client.post("/api/jobs", json={"media_id": media_id, "preset": "fit", "target_mb": 999}).status_code == 422
    assert client.post("/api/jobs", json={"media_id": 9999, "preset": "720"}).status_code == 404
    job = client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).json()
    assert job["status"] == "queued"
    canceled = client.delete(f"/api/jobs/{job['id']}").json()
    assert canceled["status"] == "canceled"


def test_share_link_lifecycle(client, fake_media, conn):
    media_id = client.post("/api/inspect", json={"url": "https://x.com/someone/status/1"}).json()["media"]["id"]
    path = config.OUTPUTS_DIR / "shared.mp4"
    path.write_bytes(b"0123456789")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720",
                             path=path, ttl_seconds=3600, meta={"width": 1280, "height": 720})

    link = client.post(f"/api/files/{file_id}/share").json()
    token = link["url"].rsplit("/", 1)[1]
    assert len(token) >= 22
    assert client.post(f"/api/files/{file_id}/share").json()["url"] == link["url"]  # reused, not duplicated

    page = client.get(f"/v/{token}")
    assert page.status_code == 200
    assert "Test &lt;clip&gt;" in page.text and "<clip>" not in page.text  # title is escaped
    assert 'data-theme="zine"' in page.text and re.search(r'href="/a/[0-9a-f]{12}/share\.css"', page.text)
    assert 'property="og:video"' in page.text

    assert client.get(f"/v/{token}/file").content == b"0123456789"
    part = client.get(f"/v/{token}/file", headers={"Range": "bytes=2-5"})
    assert part.status_code == 206 and part.content == b"2345"
    assert "attachment" in client.get(f"/v/{token}/file?download=1").headers["content-disposition"]

    assert client.delete(f"/api/share/{token}").status_code == 200
    assert client.get(f"/v/{token}").status_code == 410
    assert client.get(f"/v/{token}/file").status_code == 410
    assert client.get("/v/not-a-real-token").status_code == 410


def test_expired_file_is_gone(client, fake_media, conn):
    media_id = client.post("/api/inspect", json={"url": "https://x.com/someone/status/1"}).json()["media"]["id"]
    path = config.OUTPUTS_DIR / "old.mp4"
    path.write_bytes(b"x")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="480",
                             path=path, ttl_seconds=-1)
    assert client.get(f"/api/files/{file_id}/download").status_code == 410
    assert client.post(f"/api/files/{file_id}/share").status_code == 410
