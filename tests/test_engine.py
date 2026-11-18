import json

import pytest

from app import db, engine, media, notify, platforms, settings


@pytest.fixture()
def sent(monkeypatch):
    box = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, token: box.append(payload))
    return box


@pytest.fixture()
def fake_engine(monkeypatch, tmp_path, conn):
    """An updater that never touches the network or pip."""
    monkeypatch.setattr(engine, "BASE", tmp_path / "ytdlp")
    monkeypatch.setattr(engine, "POINTER", tmp_path / "ytdlp" / "current")
    monkeypatch.setattr(engine, "loaded_version", lambda: "2026.01.05")
    calls = {"installed": [], "probe": {}}

    def install(version):
        folder = engine.BASE / version
        folder.mkdir(parents=True)
        calls["installed"].append(version)
        return folder

    monkeypatch.setattr(engine, "install", install)
    monkeypatch.setattr(engine, "probe", lambda path, url: calls["probe"].get("new" if path else "old", (True, "ok")))
    settings.put(conn, "ntfy_topic", "t")
    return calls


def test_version_comparison():
    assert engine.is_newer("2026.10.26", "2026.9.30")
    assert engine.is_newer("2026.1.15", "2026.01.05")
    assert not engine.is_newer("2026.01.05", "2026.1.5")      # same version, written differently
    assert not engine.is_newer("2025.12.31", "2026.01.05")


def test_nothing_to_do_when_current(conn, fake_engine, monkeypatch, sent):
    monkeypatch.setattr(engine, "latest_version", lambda: "2026.1.5")
    state = engine.check_and_update(conn)
    assert state["status"] == "current" and fake_engine["installed"] == [] and sent == []
    assert not engine.needs_restart() and not engine.due(conn)   # checked just now, so not due for a day


def test_update_installs_tests_and_switches(conn, fake_engine, monkeypatch, sent):
    monkeypatch.setattr(engine, "latest_version", lambda: "2026.2.1")
    state = engine.check_and_update(conn)
    assert state["status"] == "updated" and fake_engine["installed"] == ["2026.2.1"]
    assert engine.active_name() == "2026.2.1" and engine.needs_restart()   # both containers will restart
    assert sent[-1]["title"] == "yt-dlp updated" and "2026.2.1" in sent[-1]["message"]
    assert engine.check_and_update(conn)["status"] == "updated"            # waits for the restart, no second install
    assert fake_engine["installed"] == ["2026.2.1"]

    back = engine.roll_back(conn)                                          # the admin's "go back" button
    assert back["status"] == "rolled_back" and engine.active_name() == ""


def test_bad_update_is_refused(conn, fake_engine, monkeypatch, sent):
    monkeypatch.setattr(engine, "latest_version", lambda: "2026.2.1")
    fake_engine["probe"]["new"] = (False, "ExtractorError: broken")
    state = engine.check_and_update(conn)
    assert state["status"] == "failed" and engine.active_name() == "" and not engine.needs_restart()
    assert not (engine.BASE / "2026.2.1").exists()                         # the bad install is removed
    assert sent[-1]["title"] == "yt-dlp update failed" and sent[-1]["priority"] == 4


def test_update_goes_ahead_when_the_test_video_fails_everywhere(conn, fake_engine, monkeypatch):
    monkeypatch.setattr(engine, "latest_version", lambda: "2026.2.1")
    fake_engine["probe"].update(new=(False, "blocked"), old=(False, "blocked"))   # not the new version's fault
    assert engine.check_and_update(conn)["status"] == "updated"


def test_network_trouble_never_raises(conn, fake_engine, monkeypatch, sent):
    def boom():
        raise OSError("no network")
    monkeypatch.setattr(engine, "latest_version", boom)
    state = engine.check_and_update(conn)
    assert state["status"] == "failed" and "no network" in db.get_state(conn, "ytdlp")[0]
    assert sent[-1]["title"] == "yt-dlp update failed"


def test_auto_update_switch(conn, fake_engine):
    assert engine.due(conn)
    settings.put(conn, "ytdlp_auto_update", False)
    assert not engine.due(conn)


def test_platform_check_alerts_only_when_something_newly_breaks(conn, monkeypatch, sent):
    settings.put(conn, "ntfy_topic", "t")
    working = {"youtube": True, "x": True}

    def inspect(url):
        name = "youtube" if "youtube" in url else "x"
        if not working[name]:
            raise media.MediaError("This video is private.")
        return {}

    monkeypatch.setattr(media, "inspect", inspect)
    assert all(r["ok"] for r in engine.check_platforms(conn).values()) and sent == []
    assert not engine.platforms_due(conn)

    working["x"] = False
    results = engine.check_platforms(conn)
    assert results["x"]["ok"] is False and results["youtube"]["ok"] is True
    assert len(sent) == 1 and sent[0]["title"] == "X (Twitter) stopped working" and "private" in sent[0]["message"]
    engine.check_platforms(conn)
    assert len(sent) == 1                                                   # still broken: no second alert


def test_system_tab_data_and_actions(client, conn, fake_engine, monkeypatch):
    monkeypatch.setattr(engine, "latest_version", lambda: "2026.2.1")
    data = client.get("/api/admin/system").json()
    assert data["ytdlp"]["version"] == "2026.01.05" and data["ytdlp"]["auto_update"] is True

    assert client.post("/api/admin/system", json={"action": "format-disk"}).status_code == 422
    assert client.post("/api/admin/system", json={"action": "update"}).status_code == 200
    assert db.get_state(conn, "engine_request")[0] == "update"
    assert client.get("/api/admin/system").json()["ytdlp"]["status"] == "checking"

    from app.worker import Worker
    Worker.engine_tasks(conn)                                              # what the worker does within half a minute
    data = client.get("/api/admin/system").json()["ytdlp"]
    assert data["status"] == "updated" and data["restart_pending"] and data["can_roll_back"]
    client.cookies.set("joyshare_lang", "es")
    assert "Actualizado de 2026.01.05 a 2026.2.1" in client.get("/api/admin/system").json()["ytdlp"]["message"]

    assert client.put("/api/admin/settings", json={"changes": {"ytdlp_auto_update": False}}).status_code == 200
    assert client.put("/api/admin/settings", json={"changes": {"ytdlp_auto_update": "no"}}).status_code == 422


def test_members_cannot_touch_the_system_tab(conn):
    from app import auth
    from conftest import browser
    user_id = conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid
    member = browser(auth.create_session(conn, user_id))
    assert member.get("/api/admin/system").status_code == 403
    assert member.post("/api/admin/system", json={"action": "update"}).status_code == 403


def test_platform_check_runs_at_a_different_time_each_day(conn, monkeypatch):
    """After each check the next one is planned 12 to 36 hours later, so it doesn't land at the same time every day."""
    from app import db, media
    monkeypatch.setattr(media, "inspect", lambda url: {})
    assert engine.platforms_due(conn)                      # never checked: right away
    gaps = set()
    for _ in range(20):
        engine.check_platforms(conn)
        assert not engine.platforms_due(conn)
        gap = engine.next_platform_check(conn) - db.now()
        assert engine.PLATFORM_GAP[0] <= gap <= engine.PLATFORM_GAP[1]
        gaps.add(gap)
    assert len(gaps) > 10                                   # really random, not one fixed time
    planned = engine.next_platform_check(conn)
    monkeypatch.setattr(db, "now", lambda: planned)
    assert engine.platforms_due(conn)


def test_platform_check_picks_a_random_test_video(conn, monkeypatch):
    looked_up = []
    monkeypatch.setattr(media, "inspect", lambda url: looked_up.append(url) or {})
    for _ in range(30):
        engine.check_platforms(conn)
    youtube = {u for u in looked_up if "youtube" in u}
    assert len(youtube) > 1 and youtube <= set(settings.DEFAULTS["canary_urls"]["youtube"])


def test_platform_check_tries_a_second_video_before_calling_it_broken(conn, monkeypatch, sent):
    settings.put(conn, "ntfy_topic", "t")
    settings.put(conn, "canary_platforms", ["youtube"])
    tried = []

    def first_fails(url):
        tried.append(url)
        if len(tried) == 1:
            raise media.MediaError("This video is private.")
        return {}

    monkeypatch.setattr(media, "inspect", first_fails)
    result = engine.check_platforms(conn)["youtube"]
    assert result["ok"] is True and len(set(tried)) == 2 and result["url"] == tried[1] and sent == []

    def all_fail(url):
        raise media.MediaError("Sign in to confirm you're not a bot.")

    monkeypatch.setattr(media, "inspect", all_fail)
    assert engine.check_platforms(conn)["youtube"]["ok"] is False and len(sent) == 1


def test_old_single_link_settings_still_work(conn):
    settings.put(conn, "canary_urls", {"youtube": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                                       "tiktok": "https://www.tiktok.com/@pokemonlife22/video/7059698374567611694",
                                       "x": "https://x.com/a/status/1", "instagram": "", "facebook": ""})
    cfg = settings.get_all(conn)
    for name in ("youtube", "tiktok", "instagram"):                                               # old defaults: new pools
        assert settings.canary_links(cfg, name) == settings.DEFAULTS["canary_urls"][name]
    assert settings.canary_links(cfg, "x") == ["https://x.com/a/status/1"]                         # their own pick stays
    assert settings.canary_links(cfg, "facebook") == []

    settings.put(conn, "canary_urls", {"instagram": []})                                         # cleared on purpose: stays empty
    assert settings.canary_links(settings.get_all(conn), "instagram") == []


def test_default_test_videos_are_valid_links():
    for name, links in settings.DEFAULTS["canary_urls"].items():
        assert len(set(links)) == len(links)
        for url in links:
            assert platforms.detect(url)[0] == name, url
