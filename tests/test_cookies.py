import json

import pytest

from app import auth, config, cookies, db, media, notify, settings
from conftest import browser

COOKIE_FILE = "\n".join([
    "# Netscape HTTP Cookie File",
    ".x.com\tTRUE\t/\tTRUE\t1999999999\tauth_token\tSECRET_X",
    "#HttpOnly_.twitter.com\tTRUE\t/\tTRUE\t1999999999\tct0\tSECRET_T",
    ".mybank.com\tTRUE\t/\tTRUE\t1999999999\tsession\tBANK_SECRET",
    ".notx.com\tTRUE\t/\tTRUE\t1999999999\tsneaky\tLOOKALIKE",
    "this line is not a cookie",
]) + "\n"


def login_error():
    error = media.MediaError("The platform only shows this video to signed-in accounts.")
    error.needs_login = True
    return error


@pytest.fixture()
def member(conn):
    user_id = conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid
    with browser(auth.create_session(conn, user_id)) as c:
        c.user_id = user_id
        yield c


@pytest.fixture()
def fake_estimate(monkeypatch):
    monkeypatch.setattr(media, "estimate", lambda info, key: {
        "bytes": 5_000_000, "exact": True, "height": None if key == "audio" else int(key[1:]),
        "vcodec": "avc1", "acodec": "mp4a", "needs_convert": False})


def test_only_the_platforms_own_cookies_are_kept():
    text, count = cookies.clean(COOKIE_FILE, "x")
    assert count == 2 and "SECRET_X" in text and "SECRET_T" in text
    assert "BANK_SECRET" not in text and "LOOKALIKE" not in text and "not a cookie" not in text
    with pytest.raises(cookies.CookieError):
        cookies.clean(COOKIE_FILE, "instagram")              # nothing for that platform in the file
    with pytest.raises(cookies.CookieError):
        cookies.clean("x" * (cookies.MAX_UPLOAD + 1), "x")


def test_upload_is_encrypted_and_never_comes_back(client, conn):
    res = client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    assert res.status_code == 200 and res.json() == {"ok": True, "cookie_count": 2}

    stored = bytes(conn.execute("SELECT data FROM cookies WHERE user_id=1 AND platform='x'").fetchone()["data"])
    assert b"SECRET_X" not in stored and b"auth_token" not in stored          # not readable in the database

    listing = client.get("/api/account/cookies")
    by_platform = {item["platform"]: item for item in listing.json()}
    assert by_platform["x"]["status"] == "ok" and by_platform["x"]["cookie_count"] == 2
    assert by_platform["youtube"]["status"] == "none" and "tiktok" in by_platform
    everything = listing.text + client.get("/api/admin/audit").text + client.get("/api/admin/overview").text
    assert "SECRET_X" not in everything and "BANK_SECRET" not in everything

    with cookies.file_for(conn, 1, "x") as path:                                # what yt-dlp will be handed
        content = path.read_text()
        assert "SECRET_X" in content and "BANK_SECRET" not in content
        assert oct(path.stat().st_mode)[-3:] == "600"
    assert not path.exists()                                                     # the temporary copy is deleted


def test_bad_uploads_and_removal(client, conn):
    assert client.put("/api/account/cookies/instagram", json={"text": COOKIE_FILE}).status_code == 422
    assert client.put("/api/account/cookies/x", json={"text": "{\"not\": \"netscape\"}"}).status_code == 422
    assert client.put("/api/account/cookies/myspace", json={"text": COOKIE_FILE}).status_code == 404
    client.cookies.set("joyshare_lang", "es")
    assert "No se encontraron cookies de Instagram" in client.put(
        "/api/account/cookies/instagram", json={"text": COOKIE_FILE}).json()["detail"]

    assert client.delete("/api/account/cookies/x").status_code == 404           # nothing connected yet
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    assert client.delete("/api/account/cookies/x").status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM cookies").fetchone()[0] == 0


def test_cookies_belong_to_one_person(client, member, conn):
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    assert all(item["status"] == "none" for item in member.get("/api/account/cookies").json())
    assert member.delete("/api/account/cookies/x").status_code == 404           # can't remove someone else's
    assert not cookies.has(conn, member.user_id, "x")
    with cookies.file_for(conn, member.user_id, "x") as path:
        assert path is None
    assert cookies.has(conn, 1, "x")


def test_access_tokens_cannot_touch_connected_accounts(client):
    token = client.post("/api/auth/tokens", json={"name": "script"}).json()["token"]
    script = browser()
    del script.headers["origin"]
    script.headers["authorization"] = f"Bearer {token}"
    assert script.get("/api/account/cookies").status_code == 403
    assert script.put("/api/account/cookies/x", json={"text": COOKIE_FILE}).status_code == 403


def test_account_is_used_only_when_the_platform_asks(client, conn, monkeypatch, fake_estimate):
    seen = []

    def inspect(url, cookiefile=None):
        seen.append(cookiefile.read_text() if cookiefile else None)
        return {"id": "open1", "title": "Public clip", "duration": 30.0}

    monkeypatch.setattr(media, "inspect", inspect)
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    found = client.post("/api/inspect", json={"url": "https://x.com/a/status/1"}).json()
    assert seen == [None]                                                        # public video: account untouched
    assert conn.execute("SELECT needs_login FROM media WHERE id=?", (found["media"]["id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT last_used_at FROM cookies").fetchone()[0] is None


def test_sign_in_wall_without_and_with_an_account(client, conn, monkeypatch, fake_estimate):
    def inspect(url, cookiefile=None):
        if cookiefile is None:
            raise login_error()
        assert "SECRET_X" in cookiefile.read_text()
        return {"id": "locked1", "title": "Members only", "duration": 30.0}

    monkeypatch.setattr(media, "inspect", inspect)
    blocked = client.post("/api/inspect", json={"url": "https://x.com/a/status/2"})
    assert blocked.status_code == 422 and "Connect your account under Connected accounts" in blocked.json()["detail"]
    assert blocked.json()["detail"].startswith("X (Twitter) only shows")

    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    found = client.post("/api/inspect", json={"url": "https://x.com/a/status/2"})
    assert found.status_code == 200 and found.json()["media"]["title"] == "Members only"
    media_id = found.json()["media"]["id"]
    assert conn.execute("SELECT needs_login FROM media WHERE id=?", (media_id,)).fetchone()[0] == 1   # the download goes straight to the account
    assert conn.execute("SELECT last_used_at FROM cookies").fetchone()[0] is not None


def test_rejected_account_is_flagged_and_alerted_once(client, conn, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, token: sent.append(payload))
    settings.put(conn, "ntfy_topic", "t")

    def inspect(url, cookiefile=None):
        raise login_error()                                                      # refuses with or without cookies

    monkeypatch.setattr(media, "inspect", inspect)
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    for _ in range(2):
        res = client.post("/api/inspect", json={"url": "https://x.com/a/status/3"})
        assert res.status_code == 422 and "didn't accept your connected account" in res.json()["detail"]
    status = {i["platform"]: i["status"] for i in client.get("/api/account/cookies").json()}
    assert status["x"] == "rejected"
    alerts = [s for s in sent if s["title"] == "A connected account stopped working"]
    assert len(alerts) == 1 and "X (Twitter)" in alerts[0]["message"] and "SECRET" not in json.dumps(sent)

    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})             # a fresh upload clears the flag
    assert {i["platform"]: i["status"] for i in client.get("/api/account/cookies").json()}["x"] == "ok"


def test_other_errors_never_blame_the_account(client, conn, monkeypatch):
    def inspect(url, cookiefile=None):
        raise media.MediaError("This video is private.")
    monkeypatch.setattr(media, "inspect", inspect)
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    assert client.post("/api/inspect", json={"url": "https://x.com/a/status/4"}).json()["detail"] == "This video is private."
    assert conn.execute("SELECT status FROM cookies").fetchone()[0] == "ok"


def test_changed_secret_makes_old_files_unreadable_not_broken(client, conn, monkeypatch):
    client.put("/api/account/cookies/x", json={"text": COOKIE_FILE})
    monkeypatch.setenv("JOYSHARE_SECRET", "a different secret")
    with cookies.file_for(conn, 1, "x") as path:
        assert path is None
    assert {i["platform"]: i["status"] for i in client.get("/api/account/cookies").json()}["x"] == "unreadable"
    assert not cookies.has(conn, 1, "x")
    assert not list(config.TMP_DIR.glob("ck-*"))                                 # no stray temporary files
