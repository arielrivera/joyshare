import gzip
import itertools
import json
import sqlite3

import pytest

from app import backup, db, engine, media, notify, settings, storage
from test_storage import DETAILS, FakeBucket


@pytest.fixture()
def sent(monkeypatch, conn):
    box = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, token: box.append(payload))
    settings.put(conn, "ntfy_topic", "t")
    return box


@pytest.fixture()
def folder(monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "FOLDER", tmp_path / "backups")
    counter = itertools.count(1)
    monkeypatch.setattr(backup.time, "strftime", lambda fmt, when=None: f"joyshare-20261113-{next(counter):06d}.db.gz")
    return tmp_path / "backups"


@pytest.fixture()
def bucket(monkeypatch, conn):
    fake = FakeBucket()
    fake.lifecycle = None

    def list_objects_v2(Bucket, Prefix=""):
        return {"Contents": [{"Key": k} for k in fake.objects if k.startswith(Prefix)]}

    def lifecycle(**kwargs):
        fake.lifecycle = kwargs["LifecycleConfiguration"]

    fake.list_objects_v2 = list_objects_v2
    fake.put_bucket_lifecycle_configuration = lifecycle
    monkeypatch.setattr(storage, "_client", lambda cfg: fake)
    monkeypatch.setattr(storage.urllib.request, "urlopen",
                        lambda url, timeout=None: __import__("io").BytesIO(fake.objects[url.split("?")[0].split("/joyshare/", 1)[1]]))
    storage.forget_cache()
    yield fake
    storage.forget_cache()


def open_backup(path, tmp_path):
    plain = tmp_path / "restored.db"
    plain.write_bytes(gzip.decompress(path.read_bytes()))
    return sqlite3.connect(plain)


def test_backup_is_a_complete_readable_database(conn, folder, tmp_path):
    conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),))
    settings.put(conn, "max_file_mb", 77)
    state = backup.run(conn)
    assert state["ok"] and state["cloud"] is False and state["local_count"] == 1 and state["size"] > 0
    copy = open_backup(folder / state["name"], tmp_path)
    assert [r[0] for r in copy.execute("SELECT name FROM users ORDER BY id")] == ["owner", "Sofia"]
    assert copy.execute("SELECT value FROM settings WHERE key='max_file_mb'").fetchone()[0] == "77"
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not list(folder.glob("*.db"))                      # no uncompressed leftovers


def test_only_the_newest_copies_are_kept(conn, folder, monkeypatch):
    monkeypatch.setattr(backup, "KEEP_LOCAL", 3)
    made = [backup.run(conn)["name"] for _ in range(5)]
    assert [p.name for p in backup.local_backups()] == made[-3:]


def test_cloud_copy_when_storage_is_set_up(client, conn, folder, bucket, monkeypatch):
    assert backup.run(conn)["cloud"] is False                 # storage not set up: server copy only
    client.put("/api/admin/settings", json={"changes": DETAILS})
    assert client.post("/api/admin/storage/test").json()["passed"]
    assert bucket.lifecycle["Rules"][0]["Filter"] == {"Prefix": "outputs/"}   # the clean-up rule never touches backups

    monkeypatch.setattr(backup, "KEEP_CLOUD", 2)
    for _ in range(3):
        state = backup.run(conn)
    assert state["ok"] and state["cloud"] is True
    in_bucket = sorted(k for k in bucket.objects if k.startswith("backups/"))
    assert len(in_bucket) == 2 and in_bucket[-1] == "backups/" + state["name"]
    assert gzip.decompress(bucket.objects[in_bucket[-1]]).startswith(b"SQLite format 3")
    assert storage.mode(conn) == "local"                      # backing up to the bucket doesn't change where videos are served


def test_failures_alert_and_never_raise(client, conn, folder, bucket, sent, monkeypatch):
    client.put("/api/admin/settings", json={"changes": DETAILS})
    client.post("/api/admin/storage/test")
    bucket.fail.add("upload")
    state = backup.run(conn)
    assert state["ok"] is False and state["local_ok"] is True and "upload refused" in state["error"]
    assert sent[-1]["title"] == "Backup failed" and "copy on the server was made" in sent[-1]["message"]

    def broken(target):
        raise OSError("disk full")
    monkeypatch.setattr(backup, "snapshot", broken)
    state = backup.run(conn)
    assert state["ok"] is False and state["local_ok"] is False
    assert "No backup was made: disk full" in sent[-1]["message"]


def test_daily_schedule_and_switch(conn, folder):
    assert backup.due(conn)
    backup.run(conn)
    assert not backup.due(conn)
    db.set_state(conn, "backup", json.dumps({"at": db.now() - backup.EVERY - 1, "ok": True}))
    assert backup.due(conn)
    settings.put(conn, "backup_auto", False)
    assert not backup.due(conn)


def test_back_up_now_from_the_system_tab(client, conn, folder):
    assert client.get("/api/admin/system").json()["backup"]["at"] is None
    assert client.post("/api/admin/system", json={"action": "backup"}).status_code == 200
    assert client.get("/api/admin/system").json()["backup"]["running"] is True
    settings.put(conn, "ytdlp_auto_update", False)
    db.set_state(conn, "canary_at", str(db.now()))            # nothing else is due
    from app.worker import Worker
    Worker.engine_tasks(conn)
    shown = client.get("/api/admin/system").json()["backup"]
    assert shown["ok"] is True and shown["running"] is False and shown["local_count"] == 1 and shown["cloud_ready"] is False
    assert client.put("/api/admin/settings", json={"changes": {"backup_auto": False}}).status_code == 200


# ---------- platform tests: rationed, and the admin picks what is included ----------

def test_manual_platform_tests_are_limited_to_two_in_three_hours(client, conn):
    assert client.get("/api/admin/system").json()["manual_tests_left"] == 2
    for left in (1, 0):
        assert client.post("/api/admin/system", json={"action": "platforms"}).status_code == 200
        assert client.get("/api/admin/system").json()["manual_tests_left"] == left
    blocked = client.post("/api/admin/system", json={"action": "platforms"})
    assert blocked.status_code == 429 and "limited to 2 every 3 hours" in blocked.json()["detail"]
    assert client.get("/api/admin/system").json()["next_manual_test_at"] > db.now()
    client.cookies.set("joyshare_lang", "es")
    assert "limitadas a 2 cada 3 horas" in client.post("/api/admin/system", json={"action": "platforms"}).json()["detail"]

    assert client.post("/api/admin/system", json={"action": "backup"}).status_code == 200   # other actions aren't rationed

    old = db.now() - 3 * 3600 - 5
    db.set_state(conn, "canary_manual", json.dumps([old, db.now() - 60]))    # one of the two has aged out
    assert client.post("/api/admin/system", json={"action": "platforms"}).status_code == 200


def test_admin_chooses_which_platforms_are_checked(client, conn, monkeypatch):
    looked_up = []
    monkeypatch.setattr(media, "inspect", lambda url: looked_up.append(url) or {})
    engine.check_platforms(conn)
    assert len(looked_up) == 2 and any("youtube" in u for u in looked_up) and any("x.com" in u for u in looked_up)

    res = client.put("/api/admin/settings", json={"changes": {"canary_platforms": ["tiktok", "instagram"],
                                                              "canary_urls": {"instagram": []}}})
    assert res.status_code == 200 and res.json()["settings"]["canary_platforms"] == ["tiktok", "instagram"]
    looked_up.clear()
    engine.check_platforms(conn)
    assert len(looked_up) == 1 and "tiktok.com" in looked_up[0]             # Instagram has no test videos now, so it is skipped

    ok = client.put("/api/admin/settings", json={"changes": {"canary_urls": {"instagram": "https://www.instagram.com/reel/abc123/"}}})
    assert ok.status_code == 200 and ok.json()["settings"]["canary_urls"]["youtube"][0].startswith("https://www.youtube.com")
    looked_up.clear()
    engine.check_platforms(conn)
    assert len(looked_up) == 2

    rows = {c["platform"]: c for c in client.get("/api/admin/system").json()["platform_checks"]}
    assert rows["tiktok"]["included"] and rows["tiktok"]["ok"] is True and not rows["youtube"]["included"]

    many = client.put("/api/admin/settings", json={"changes": {"canary_urls": {"x": [
        "https://x.com/a/status/1", "https://x.com/b/status/2", "https://x.com/a/status/1"]}}})
    assert many.status_code == 200 and len(many.json()["settings"]["canary_urls"]["x"]) == 2   # duplicates dropped
    rows = {c["platform"]: c for c in client.get("/api/admin/system").json()["platform_checks"]}
    assert rows["x"]["url"].count("\n") == 1

    for bad in ({"canary_platforms": ["myspace"]}, {"canary_urls": {"x": ["https://x.com/a/status/1", 5]}}, {"canary_urls": {"x": "https://www.youtube.com/watch?v=1"}},
                {"canary_urls": {"x": "https://example.com/v"}}, {"canary_urls": {"myspace": ""}}):
        assert client.put("/api/admin/settings", json={"changes": bad}).status_code == 422, bad


def test_system_tab_is_admin_only(conn):
    from app import auth
    from conftest import browser
    user_id = conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid
    member = browser(auth.create_session(conn, user_id))
    assert member.get("/api/admin/system").status_code == 403
    for action in ("platforms", "backup", "update", "rollback"):
        assert member.post("/api/admin/system", json={"action": action}).status_code == 403
    assert browser().get("/api/admin/system").status_code == 401            # not signed in at all
