"""Clips: sharing only part of a video."""
import subprocess

import pytest

from app import config, db, media, presets, settings, store
from test_api import fake_media  # noqa: F401  (a fixture)

URL = "https://x.com/someone/status/1"


def test_check_clip():
    assert presets.check_clip(None, None, 60) is None
    assert presets.check_clip(5, 12.34, 60) == (5.0, 12.3)
    assert presets.check_clip(50, 60.4, 60) == (50.0, 60.0)          # a hair past the end is trimmed
    assert presets.check_clip(5, 500, None) == (5.0, 500.0)          # unknown length: trust it, the cut checks again
    for start, end in ((5, None), (None, 5), (10, 10.5), (12, 3), (-1, 5), (5, 90)):
        with pytest.raises(presets.PresetError):
            presets.check_clip(start, end, 60)


def test_a_clip_gets_its_own_file_name():
    assert presets.output_key("720") == "720"
    assert presets.output_key("720", None, (5.0, 12.3)) == "720@5.0-12.3"
    assert presets.output_key("fit", 8, (0.0, 30.0)) == "fit-8@0.0-30.0"
    assert presets.output_key("720", None, (5.0, 12.3)) != presets.output_key("720", None, (5.0, 12.4))


def test_asking_for_a_clip(client, fake_media, conn):
    media_id = client.post("/api/inspect", json={"url": URL}).json()["media"]["id"]

    def ask(**extra):
        return client.post("/api/jobs", json={"media_id": media_id, "preset": "720", **extra})
    assert ask(clip_start=10).status_code == 422
    assert ask(clip_start=10, clip_end=10.2).status_code == 422
    assert ask(clip_start=10, clip_end=400).status_code == 422       # the video is 60 seconds long
    job = ask(clip_start=10, clip_end=25.04).json()
    assert job["clip"] == [10.0, 25.0] and job["status"] == "queued"
    row = conn.execute("SELECT clip_start, clip_end FROM jobs WHERE id=?", (job["id"],)).fetchone()
    assert (row["clip_start"], row["clip_end"]) == (10.0, 25.0)
    whole = ask().json()
    assert whole["clip"] is None


def test_a_too_big_video_can_still_be_clipped(client, fake_media, conn):
    by_id = {p["id"]: p for p in client.post("/api/inspect", json={"url": URL}).json()["presets"]}
    assert by_id["best"]["allowed"] is False and by_id["best"]["clip_ok"] is True     # 300 MB: too big to share whole
    settings.put(conn, "max_source_mb", 100)
    by_id = {p["id"]: p for p in client.post("/api/inspect", json={"url": URL}).json()["presets"]}
    assert by_id["best"]["clip_ok"] is False                                           # can't even be downloaded


def test_fitting_a_size_uses_the_length_of_the_clip(client, monkeypatch, conn):
    # Two hours can't be squeezed into 8 MB, but 30 seconds of it can.
    monkeypatch.setattr(media, "inspect", lambda url: {"id": "long", "title": "Long", "duration": 7200.0, "webpage_url": URL})
    monkeypatch.setattr(media, "estimate", lambda info, key: {"bytes": 150 * 1024 * 1024, "exact": True, "height": 720,
                                                             "vcodec": "avc1", "acodec": "mp4a", "needs_convert": False})
    media_id = client.post("/api/inspect", json={"url": URL}).json()["media"]["id"]
    body = {"media_id": media_id, "preset": "fit", "target_mb": 8}
    assert client.post("/api/jobs", json=body).status_code == 422
    assert client.post("/api/jobs", json={**body, "clip_start": 600, "clip_end": 630}).status_code == 200


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """A 12-second test video with sound, made by ffmpeg itself."""
    path = tmp_path_factory.mktemp("clips") / "sample.mkv"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=12",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-preset", "ultrafast",
                    "-g", "250", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True, timeout=120)
    return path


def quiet(*_):
    return None


def test_a_real_cut_is_the_asked_length(sample, tmp_path):
    out = media.convert(sample, tmp_path, "720", None, quiet, lambda: False, clip=(3.0, 7.5))
    info = media.probe(out)
    assert abs(info["duration"] - 4.5) < 0.2 and info["vcodec"] == "h264" and info["acodec"] == "aac"
    whole = media.convert(sample, tmp_path, "720", None, quiet, lambda: False)
    assert abs(media.probe(whole)["duration"] - 12) < 0.2


def test_a_real_audio_cut_and_a_fitted_cut(sample, tmp_path):
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    audio = media.convert(sample, tmp_path, "audio", None, quiet, lambda: False, clip=(1.0, 4.0))
    assert audio.suffix == ".m4a" and abs(media.probe(audio)["duration"] - 3.0) < 0.2
    fitted = media.convert(sample, tmp_path, "fit", 1, quiet, lambda: False, clip=(2.0, 8.0))
    assert abs(media.probe(fitted)["duration"] - 6.0) < 0.2 and fitted.stat().st_size <= 1024 * 1024


def test_a_cut_outside_the_video_is_refused(sample, tmp_path):
    with pytest.raises(media.MediaError):
        media.convert(sample, tmp_path, "720", None, quiet, lambda: False, clip=(30.0, 40.0))


def test_a_link_about_to_run_out_is_replaced_only_if_a_longer_one_is_possible(client, conn):
    conn.execute("INSERT INTO media (url, platform, title, user_id, source_id, created_at) VALUES (?,?,?,?,?,?)",
                 (URL, "x", "Clip", 1, "s1", db.now()))
    media_id = conn.execute("SELECT id FROM media").fetchone()["id"]
    path = config.OUTPUTS_DIR / "again.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 10)
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=40 * 3600)
    first = client.post(f"/api/files/{file_id}/share").json()
    assert first["ends_soon"] is False
    assert client.post(f"/api/files/{file_id}/share").json()["url"] == first["url"]          # plenty of time left: same link
    conn.execute("UPDATE share_links SET expires_at=?", (db.now() + 1800,))                  # half an hour left
    second = client.post(f"/api/files/{file_id}/share").json()
    assert second["url"] != first["url"] and second["expires_at"] > db.now() + 30 * 3600     # the file lives on: new link
    conn.execute("UPDATE share_links SET expires_at=?", (db.now() + 1800,))
    conn.execute("UPDATE files SET expires_at=? WHERE id=?", (db.now() + 1800, file_id))     # the file itself is ending
    third = client.post(f"/api/files/{file_id}/share").json()
    assert third["ends_soon"] is True and third["url"] in (first["url"], second["url"])      # nothing longer to offer
    path.unlink()


def test_the_activity_log_names_people_and_videos(client, conn):
    conn.execute("INSERT INTO media (url, platform, title, user_id, source_id, created_at) VALUES (?,?,?,?,?,?)",
                 (URL, "x", "Cat video", 1, "s2", db.now()))
    media_id = conn.execute("SELECT id FROM media").fetchone()["id"]
    path = config.OUTPUTS_DIR / "log.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=3600)
    client.post(f"/api/files/{file_id}/share")
    db.audit(conn, 1, "user.disable", '{"user_id": 1}')
    db.audit(conn, 1, "token.revoke", None)
    by_action = {e["action"]: e["detail"] for e in client.get("/api/admin/audit").json()}
    assert by_action["share_link.create"]["title"] == "Cat video"
    assert by_action["user.disable"]["name"] == "owner"
    assert by_action["token.revoke"] == {}
    path.unlink()
