import pytest

from app import cleanup, config, db, platforms, presets, settings, store

MB = 1024 * 1024


# ---------- links ----------

@pytest.mark.parametrize("url,platform", [
    ("https://x.com/user/status/123", "x"),
    ("https://twitter.com/user/status/123", "x"),
    ("https://mobile.twitter.com/user/status/123", "x"),
    ("youtu.be/jNQXAC9IVRw", "youtube"),
    ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube"),
    ("https://m.youtube.com/shorts/abc", "youtube"),
    ("https://www.instagram.com/reel/abc/", "instagram"),
    ("https://fb.watch/abc/", "facebook"),
    ("https://www.facebook.com/watch/?v=1", "facebook"),
])
def test_known_links(url, platform):
    found, clean = platforms.detect(url)
    assert found == platform
    assert clean.startswith("https://")


@pytest.mark.parametrize("url", [
    "",
    "https://example.com/video.mp4",
    "http://localhost:8080/secret",
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "ftp://youtube.com/x",
    "https://youtube.com.evil.example/watch?v=1",
    "https://evilyoutube.com/watch?v=1",
    "https://user:pass@youtube.com/watch?v=1",
    "https://youtube.com:8443/watch?v=1",
])
def test_rejected_links(url):
    with pytest.raises(platforms.LinkError):
        platforms.detect(url)


def test_disabled_platform():
    with pytest.raises(platforms.LinkError):
        platforms.detect("https://www.instagram.com/reel/abc/", enabled=["x", "youtube"])


# ---------- presets ----------

def test_fit_plan_stays_under_target():
    for target_mb, duration in [(8, 30), (25, 120), (25, 600), (100, 1800), (16, 900)]:
        plan = presets.fit_plan(target_mb * MB, duration)
        total_bytes = (plan.video_kbps + plan.audio_kbps) * 1000 / 8 * duration
        assert total_bytes < target_mb * MB
        assert plan.height in (240, 360, 480, 720)


def test_fit_plan_lowers_height_for_long_videos():
    assert presets.fit_plan(25 * MB, 60).height == 720
    assert presets.fit_plan(25 * MB, 1200).height < 480


def test_fit_plan_never_upscales():
    assert presets.fit_plan(100 * MB, 30, src_height=360).height == 360


def test_fit_plan_refuses_impossible():
    with pytest.raises(presets.PresetError):
        presets.fit_plan(8 * MB, 3 * 3600)
    with pytest.raises(presets.PresetError):
        presets.fit_plan(8 * MB, 0)


def test_source_and_output_keys():
    assert presets.source_key("best") == "v1080"
    assert presets.source_key("720") == "v720"
    assert presets.source_key("audio") == "audio"
    assert presets.source_key("fit", 25, 60) == "v720"
    assert presets.source_key("fit", 25, 1200) == "v480"
    assert presets.output_key("fit", 25) == "fit-25"
    assert presets.output_key("480") == "480"
    assert presets.ydl_format("v720")["format_sort"][0] == "res:720"


# ---------- settings ----------

def test_settings_defaults_and_overrides(conn):
    assert settings.get(conn, "max_file_mb") == 200
    assert settings.get(conn, "link_ttl_hours") == 48
    settings.put(conn, "max_file_mb", 50)
    assert settings.get(conn, "max_file_mb") == 50
    with pytest.raises(KeyError):
        settings.put(conn, "nope", 1)
    with pytest.raises(TypeError):
        settings.put(conn, "max_file_mb", "big")


# ---------- files and cleanup ----------

def _media(conn):
    return conn.execute(
        "INSERT INTO media (user_id, url, platform, created_at) VALUES (1, 'https://x.com/a/status/1', 'x', ?)",
        (db.now(),),
    ).lastrowid


def _file(conn, media_id, name, ttl, kind="output", key="720"):
    path = config.OUTPUTS_DIR / name
    path.write_bytes(b"x" * 10)
    return store.add_file(conn, user_id=1, media_id=media_id, kind=kind, key=key, path=path, ttl_seconds=ttl), path


def test_cleanup_deletes_only_expired(conn):
    media_id = _media(conn)
    old_id, old_path = _file(conn, media_id, "old.mp4", -5)
    new_id, new_path = _file(conn, media_id, "new.mp4", 3600, key="480")
    report = cleanup.run(conn)
    assert report["removed"] == 1
    assert not old_path.exists() and new_path.exists()
    assert conn.execute("SELECT deleted_at FROM files WHERE id=?", (old_id,)).fetchone()[0] is not None
    assert conn.execute("SELECT deleted_at FROM files WHERE id=?", (new_id,)).fetchone()[0] is None
    assert report["disk"]["level"] in ("ok", "warn", "paused")


def test_cleanup_skips_files_in_use(conn):
    media_id = _media(conn)
    file_id, path = _file(conn, media_id, "busy.mp4", -5)
    assert cleanup.run(conn, in_use={file_id})["removed"] == 0
    assert path.exists()


def test_find_file_ignores_expired_and_missing(conn):
    media_id = _media(conn)
    _file(conn, media_id, "gone.mp4", -5)
    assert store.find_file(conn, 1, media_id, "output", "720") is None
    _, path = _file(conn, media_id, "here.mp4", 3600)
    assert store.find_file(conn, 1, media_id, "output", "720") is not None
    assert store.find_file(conn, 2, media_id, "output", "720") is None  # another user's request
    path.unlink()
    assert store.find_file(conn, 1, media_id, "output", "720") is None


def test_download_name():
    assert store.download_name("Me at the zoo", "jawed", ".mp4") == "Me at the zoo - jawed.mp4"
    assert store.download_name('a/b:c*?"<>|', None, ".mp4") == "a b c.mp4"
    assert store.download_name(None, None, ".m4a") == "joyshare.m4a"
    assert len(store.download_name("x" * 300, None, ".mp4")) <= 84
