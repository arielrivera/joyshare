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
