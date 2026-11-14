"""Preview pictures are copied to this server and shown from here."""
import time

import pytest

from app import thumbs
from test_api import fake_media  # noqa: F401  (a fixture)
from conftest import browser

URL = "https://x.com/someone/status/1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


@pytest.fixture()
def folder(monkeypatch, tmp_path):
    monkeypatch.setattr(thumbs, "FOLDER", tmp_path / "thumbs")
    return tmp_path / "thumbs"


def wait_for(check):
    for _ in range(100):
        if check():
            return True
        time.sleep(0.02)
    return False


def test_the_picture_is_saved_at_lookup_and_served_from_here(client, fake_media, folder, monkeypatch):
    asked = []
    monkeypatch.setattr(thumbs, "_download", lambda url: (asked.append(url), (JPEG, "image/jpeg"))[1])
    media = client.post("/api/inspect", json={"url": URL}).json()["media"]
    assert media["thumb_url"] == f"/api/media/{media['id']}/thumb"
    assert wait_for(lambda: thumbs.find(media["id"])) and asked == ["https://example.com/t.jpg"]
    picture = client.get(media["thumb_url"])
    assert picture.status_code == 200 and picture.content == JPEG and picture.headers["content-type"] == "image/jpeg"
    assert "private" in picture.headers["cache-control"] and len(asked) == 1          # served from the saved copy
    job = client.post("/api/jobs", json={"media_id": media["id"], "preset": "720"}).json()
    assert job["media"]["thumb_url"] == media["thumb_url"]                             # so the Recent list can show it
    assert client.get("/api/jobs").json()[0]["media"]["thumb_url"] == media["thumb_url"]


def test_an_older_video_gets_its_picture_on_first_view(client, fake_media, folder, monkeypatch):
    monkeypatch.setattr(thumbs, "_download", lambda url: (_ for _ in ()).throw(OSError("offline")))
    media = client.post("/api/inspect", json={"url": URL}).json()["media"]
    time.sleep(0.1)
    assert thumbs.find(media["id"]) is None and client.get(media["thumb_url"]).status_code == 404
    monkeypatch.setattr(thumbs, "_download", lambda url: (JPEG, "image/jpeg"))
    assert client.get(media["thumb_url"]).status_code == 200 and thumbs.find(media["id"])


def test_only_your_own_videos_and_only_real_pictures(client, fake_media, folder, monkeypatch):
    monkeypatch.setattr(thumbs, "_download", lambda url: (b"<html>", "text/html"))
    media = client.post("/api/inspect", json={"url": URL}).json()["media"]
    time.sleep(0.1)
    assert client.get(media["thumb_url"]).status_code == 404                 # not a picture: nothing is kept
    assert thumbs.find(media["id"]) is None
    assert browser().get(media["thumb_url"]).status_code == 401              # signed out
    assert client.get("/api/media/99999/thumb").status_code == 404


def test_addresses_inside_the_network_are_refused():
    assert thumbs._safe("http://example.com/a.jpg") is False                 # not https
    assert thumbs._safe("https://127.0.0.1/a.jpg") is False
    assert thumbs._safe("https://10.0.0.5/a.jpg") is False
    assert thumbs._safe("https://localhost/a.jpg") is False
    assert thumbs._safe("not an address") is False
    assert thumbs._safe("https://192.168.1.1/a.jpg") is False


def test_a_shared_link_shows_our_copy_of_the_picture(client, fake_media, folder, monkeypatch, conn):
    from app import config, store
    monkeypatch.setattr(thumbs, "_download", lambda url: (JPEG, "image/jpeg"))
    media = client.post("/api/inspect", json={"url": URL}).json()["media"]
    path = config.OUTPUTS_DIR / "card.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0123456789")
    file_id = store.add_file(conn, user_id=1, media_id=media["id"], kind="output", key="720", path=path,
                             ttl_seconds=3600, meta={"width": 1280, "height": 720, "duration": 75})
    token = client.post(f"/api/files/{file_id}/share").json()["url"].rsplit("/", 1)[1]
    stranger = browser()
    page = stranger.get(f"/v/{token}").text
    assert f'property="og:image" content="{config.PUBLIC_URL}/v/{token}/thumb"' in page       # not the platform's address
    assert 'name="twitter:card" content="summary_large_image"' in page
    assert 'property="og:description" content="someone · X (Twitter) · 1:15"' in page
    assert f'poster="/v/{token}/thumb"' in page
    picture = stranger.get(f"/v/{token}/thumb")                                               # no sign-in needed
    assert picture.status_code == 200 and picture.content == JPEG
    client.delete(f"/api/share/{token}")
    assert stranger.get(f"/v/{token}/thumb").status_code == 410                               # gone with the link
    path.unlink()
