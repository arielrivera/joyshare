import json

import pytest

from app import auth, cleanup, db, notify, settings
from conftest import browser


@pytest.fixture()
def sent(monkeypatch):
    """Catch alerts instead of sending them to the internet."""
    box = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, token: box.append({"url": url, "token": token, **payload}))
    return box


@pytest.fixture()
def member(conn):
    user_id = conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid
    with browser(auth.create_session(conn, user_id)) as c:
        yield c


def test_admin_api_is_for_admins_only(anon, member):
    for path in ("/api/admin/overview", "/api/admin/settings", "/api/admin/jobs", "/api/admin/share-links", "/api/admin/audit"):
        assert anon.get(path).status_code == 401, path
        assert member.get(path).status_code == 403, path
    assert member.put("/api/admin/settings", json={"changes": {"max_file_mb": 5}}).status_code == 403
    assert member.post("/api/admin/alerts/test").status_code == 403


def test_overview_has_the_numbers(client):
    data = client.get("/api/admin/overview").json()
    assert data["queue"] == 0 and data["people"] == 1 and data["paused"] is False
    assert data["yt_dlp"] and "jobs_today" in data and "disk" in data


def test_change_settings_with_validation_and_audit(client, conn):
    res = client.put("/api/admin/settings", json={"changes": {"max_file_mb": 50, "output_ttl_hours": 24, "link_ttl_hours": 24}})
    assert res.status_code == 200 and res.json()["settings"]["max_file_mb"] == 50
    assert settings.get(conn, "max_file_mb") == 50
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='settings.change'").fetchone()[0] == 1

    bad = [
        {"max_file_mb": 0}, {"max_file_mb": "big"}, {"max_file_mb": True}, {"nope": 1},
        {"disk_warn_pct": 95, "disk_pause_pct": 90},       # pause must be above warn
        {"link_ttl_hours": 100},                           # links can't outlive files (24 h)
        {"platforms": []}, {"platforms": ["myspace"]},
        {"ntfy_url": "ftp://x"}, {"ntfy_topic": "has spaces"}, {"alerts": {"made_up": True}},
    ]
    for changes in bad:
        assert client.put("/api/admin/settings", json={"changes": changes}).status_code == 422, changes
    assert settings.get(conn, "disk_warn_pct") == 90           # nothing from a rejected request is saved

    client.cookies.set("joyshare_lang", "es")
    assert "número entero" in client.put("/api/admin/settings", json={"changes": {"max_file_mb": 0}}).json()["detail"]


def test_secret_is_never_sent_back(client, conn):
    client.put("/api/admin/settings", json={"changes": {"ntfy_topic": "my-topic", "ntfy_token": "tk_secret"}})
    shown = client.get("/api/admin/settings").json()["settings"]
    assert "ntfy_token" not in shown and shown["has_ntfy_token"] is True and shown["ntfy_topic"] == "my-topic"
    assert "tk_secret" not in json.dumps(client.get("/api/admin/audit").json())


def test_changes_need_a_recent_passkey_check(client, conn):
    conn.execute("UPDATE sessions SET authenticated_at=authenticated_at-3600")
    stale = client.put("/api/admin/settings", json={"changes": {"max_file_mb": 50}})
    assert stale.status_code == 401 and stale.headers["x-joyshare-reauth"] == "1"
    assert client.get("/api/admin/settings").status_code == 200   # reading is still fine


def test_test_alert_and_switching_alerts_off(client, conn, sent):
    assert client.post("/api/admin/alerts/test").status_code == 422           # no topic yet
    client.put("/api/admin/settings", json={"changes": {"ntfy_topic": "my-topic", "ntfy_token": "tk"}})
    assert client.post("/api/admin/alerts/test").status_code == 200
    assert sent[-1]["topic"] == "my-topic" and sent[-1]["token"] == "tk" and sent[-1]["url"] == "https://ntfy.sh"
    assert sent[-1]["title"] == "Test alert"

    client.put("/api/auth/prefs", json={"lang": "es"})                        # alerts follow the admin's language
    notify.send(conn, "new_device", "New device added", notify.T("{device} was registered for {person}.", device="iPhone", person="owner"))
    assert sent[-1]["title"] == "Dispositivo nuevo añadido" and sent[-1]["message"] == "iPhone se registró para owner."

    count = len(sent)
    client.put("/api/admin/settings", json={"changes": {"alerts": {"new_device": False}}})
    assert notify.send(conn, "new_device", "New device added", "x") is False and len(sent) == count
    assert settings.get(conn, "alerts")["job_failed"] is True                  # the other switches are untouched


def test_a_failing_alert_never_raises(client, conn, monkeypatch):
    client.put("/api/admin/settings", json={"changes": {"ntfy_topic": "my-topic"}})
    def boom(*args):
        raise OSError("network down")
    monkeypatch.setattr(notify, "_post", boom)
    assert notify.send(conn, "job_failed", "Video failed", "x") is False
    assert client.post("/api/admin/alerts/test").status_code == 502


def test_pause_switch_blocks_new_videos(client, conn):
    media_id = conn.execute(
        "INSERT INTO media (user_id, url, platform, duration, created_at) VALUES (1, 'https://x.com/a/status/1', 'x', 30, ?)",
        (db.now(),)).lastrowid
    client.put("/api/admin/settings", json={"changes": {"paused": True}})
    assert client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).status_code == 503
    client.put("/api/admin/settings", json={"changes": {"paused": False}})
    assert client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).status_code == 200
    jobs = client.get("/api/admin/jobs").json()
    assert jobs[0]["person"] == "owner" and jobs[0]["status"] == "queued"


def test_disk_alert_fires_once_then_waits(client, conn, sent, monkeypatch):
    import collections
    import shutil
    client.put("/api/admin/settings", json={"changes": {"ntfy_topic": "my-topic"}})
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(100 * 1024 ** 3, 92 * 1024 ** 3, 8 * 1024 ** 3))
    assert cleanup.check_disk(conn)["level"] == "warn"
    assert cleanup.check_disk(conn)["level"] == "warn"
    disk = [s for s in sent if s["title"] == "Disk is filling up"]
    assert len(disk) == 1 and "92.0% used (92.0 of 100.0 GB)" in disk[0]["message"]

    db.set_state(conn, "disk_alert_at", str(db.now() - cleanup.ALERT_EVERY - 1))   # six hours later
    cleanup.check_disk(conn)
    assert len([s for s in sent if s["title"] == "Disk is filling up"]) == 2

    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(100 * 1024 ** 3, 97 * 1024 ** 3, 3 * 1024 ** 3))
    assert cleanup.check_disk(conn)["level"] == "paused"
    assert sent[-1]["priority"] == 5 and "paused" in sent[-1]["title"]


def test_admin_sees_and_revokes_any_share_link(client, conn):
    from app import config, store
    media_id = conn.execute(
        "INSERT INTO media (user_id, url, platform, title, created_at) VALUES (1, 'https://x.com/a/status/1', 'x', 'Clip', ?)",
        (db.now(),)).lastrowid
    path = config.OUTPUTS_DIR / "adm.mp4"
    path.write_bytes(b"x")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=600)
    token = client.post(f"/api/files/{file_id}/share").json()["url"].rsplit("/", 1)[1]
    links = client.get("/api/admin/share-links").json()
    assert links[0]["token"] == token and links[0]["title"] == "Clip" and links[0]["person"] == "owner"
    assert client.delete(f"/api/admin/share-links/{token}").status_code == 200
    assert client.get("/api/admin/share-links").json() == []
    assert client.get(f"/v/{token}").status_code == 410
