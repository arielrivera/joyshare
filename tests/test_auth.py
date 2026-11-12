import pytest
from softauth import SoftPasskey

from app import auth, config, db, store
from conftest import browser


def register(client, code, name="Test device", passkey=None):
    passkey = passkey or SoftPasskey(config.PUBLIC_URL, auth.rp_id())
    start = client.post("/api/auth/register/options", json={"code": code, "device_name": name})
    assert start.status_code == 200, start.text
    done = client.post("/api/auth/register/verify", json={
        "challenge_id": start.json()["challenge_id"], "credential": passkey.register(start.json()["publicKey"]),
    })
    return done, passkey


def sign_in(client, passkey):
    start = client.post("/api/auth/login/options").json()
    return client.post("/api/auth/login/verify", json={
        "challenge_id": start["challenge_id"], "credential": passkey.sign_in(start["publicKey"]),
    })


@pytest.fixture()
def owner(conn):
    """A browser where the owner registered the first device with the setup code."""
    client = browser()
    client.__enter__()
    code = auth.ensure_setup_code(conn)
    done, passkey = register(client, code, "Laptop")
    assert done.status_code == 200, done.text
    yield client, passkey
    client.__exit__(None, None, None)


# ---------- first run ----------

def test_everything_is_locked_when_signed_out(anon):
    assert anon.get("/api/auth/status").json() == {"signed_in": False, "user": None, "first_run": True}
    for method, path in [("get", "/api/jobs"), ("get", "/api/config"), ("get", "/api/files/1/download"),
                         ("get", "/api/auth/devices"), ("get", "/api/admin/users")]:
        assert getattr(anon, method)(path).status_code == 401, path
    assert anon.post("/api/inspect", json={"url": "https://x.com/a/status/1"}).status_code == 401
    assert anon.post("/api/auth/invites", json={"kind": "device"}).status_code == 401
    assert anon.get("/api/health").json()["ok"] is True  # monitors may call this
    assert anon.get("/").status_code == 200              # the sign-in page itself


def test_setup_code_registers_first_device_once(conn, anon):
    code = auth.ensure_setup_code(conn)
    done, passkey = register(anon, code, "Laptop")
    assert done.status_code == 200
    assert done.json()["user"] == {"id": 1, "name": "owner", "role": "admin"}
    assert anon.get("/api/auth/status").json()["signed_in"] is True
    assert anon.get("/api/jobs").status_code == 200
    assert auth.ensure_setup_code(conn) is None          # no more setup codes once a device exists

    other = browser()
    again = other.post("/api/auth/register/options", json={"code": code, "device_name": "Thief"})
    assert again.status_code == 400                      # the code is used up
    assert sign_in(other, passkey).status_code == 200    # the passkey itself signs in anywhere


def test_wrong_codes_are_rejected_and_rate_limited(conn, anon):
    auth.ensure_setup_code(conn)
    for _ in range(auth.MAX_FAILURES):
        assert anon.post("/api/auth/register/options",
                         json={"code": "AAAA-BBBB-CCCC", "device_name": "x"}).status_code == 400
    assert anon.post("/api/auth/register/options",
                     json={"code": "AAAA-BBBB-CCCC", "device_name": "x"}).status_code == 429


def test_passkey_from_another_site_is_rejected(conn, anon):
    code = auth.ensure_setup_code(conn)
    fake = SoftPasskey("https://evil.example", auth.rp_id())
    done, _ = register(anon, code, "Laptop", passkey=fake)
    assert done.status_code == 400
    assert auth.has_any_passkey(conn) is False


def test_unknown_passkey_cannot_sign_in(owner):
    stranger = SoftPasskey(config.PUBLIC_URL, auth.rp_id())
    stranger.user_handle = "AAAA"
    assert sign_in(browser(), stranger).status_code == 401


def test_challenge_cannot_be_replayed(owner):
    _, passkey = owner
    other = browser()
    start = other.post("/api/auth/login/options").json()
    credential = passkey.sign_in(start["publicKey"])
    body = {"challenge_id": start["challenge_id"], "credential": credential}
    assert other.post("/api/auth/login/verify", json=body).status_code == 200
    assert browser().post("/api/auth/login/verify", json=body).status_code == 400


# ---------- sessions ----------

def test_sign_out_and_cross_site_requests(owner):
    client, passkey = owner
    cookie = client.cookies.get(auth.SESSION_COOKIE)

    forged = browser(cookie)
    forged.headers["origin"] = "https://evil.example"
    assert forged.post("/api/auth/logout").status_code == 403       # another site can't act as you
    assert forged.get("/api/jobs").status_code == 200                # reading from our pages still works

    assert client.post("/api/auth/logout").status_code == 200
    assert browser(cookie).get("/api/jobs").status_code == 401       # the old cookie is dead
    assert sign_in(client, passkey).status_code == 200


def test_sign_out_everywhere(owner):
    client, passkey = owner
    second = browser()
    assert sign_in(second, passkey).status_code == 200
    assert client.post("/api/auth/logout-all").status_code == 200
    assert second.get("/api/jobs").status_code == 401


# ---------- devices, invites, tokens ----------

def test_add_second_device_and_remove_it(owner):
    client, _ = owner
    invite = client.post("/api/auth/invites", json={"kind": "device"}).json()
    assert invite["url"].endswith("#join=" + invite["code"]) and invite["qr"].startswith("data:image/svg+xml")

    phone = browser()
    done, _ = register(phone, invite["code"], "iPhone")
    assert done.json()["user"]["id"] == 1                            # same person, new device

    devices = client.get("/api/auth/devices").json()["passkeys"]
    assert [d["name"] for d in devices] == ["Laptop", "iPhone"]
    assert [d["current"] for d in devices] == [True, False]

    iphone_id = devices[1]["id"]
    assert client.delete(f"/api/auth/devices/{iphone_id}").status_code == 200
    assert phone.get("/api/jobs").status_code == 401                 # removed device is signed out
    assert client.delete(f"/api/auth/devices/{devices[0]['id']}").status_code == 409  # never the last one


def test_invite_code_works_only_once(owner):
    client, _ = owner
    code = client.post("/api/auth/invites", json={"kind": "device"}).json()["code"]
    assert register(browser(), code, "First")[0].status_code == 200
    second = browser().post("/api/auth/register/options", json={"code": code, "device_name": "Second"})
    assert second.status_code == 400


def test_sensitive_actions_need_a_recent_passkey_check(owner, conn):
    client, passkey = owner
    conn.execute("UPDATE sessions SET authenticated_at=authenticated_at-3600")
    stale = client.post("/api/auth/invites", json={"kind": "device"})
    assert stale.status_code == 401 and stale.headers["x-joyshare-reauth"] == "1"
    assert client.get("/api/jobs").status_code == 200                # everyday use is unaffected
    assert sign_in(client, passkey).status_code == 200               # Face ID again
    assert client.post("/api/auth/invites", json={"kind": "device"}).status_code == 200


def test_access_token_can_add_videos_but_not_manage_account(owner, monkeypatch):
    client, _ = owner
    token = client.post("/api/auth/tokens", json={"name": "iPhone Shortcut"}).json()["token"]
    assert token.startswith("js_")

    from app import media
    monkeypatch.setattr(media, "inspect", lambda url: {"id": "v1", "title": "Clip", "duration": 30.0})
    monkeypatch.setattr(media, "estimate", lambda info, key: {
        "bytes": 5_000_000, "exact": True, "height": None if key == "audio" else int(key[1:]),
        "vcodec": "avc1", "acodec": "mp4a", "needs_convert": False})

    script = browser()
    del script.headers["origin"]                                     # a script, not a browser
    script.headers["authorization"] = f"Bearer {token}"
    quick = script.post("/api/quick", json={"url": "https://x.com/a/status/1"})
    assert quick.status_code == 200, quick.text
    assert quick.json()["job"]["status"] == "queued"
    assert quick.json()["page_url"].endswith(f"#job={quick.json()['job']['id']}")

    assert script.get("/api/auth/devices").status_code == 403
    assert script.post("/api/auth/invites", json={"kind": "device"}).status_code == 403
    assert script.post("/api/auth/tokens", json={"name": "more"}).status_code == 403
    assert script.get("/api/admin/users").status_code == 403

    token_id = client.get("/api/auth/devices").json()["tokens"][0]["id"]
    assert client.delete(f"/api/auth/tokens/{token_id}").status_code == 200
    assert script.get("/api/jobs").status_code == 401                # revoked


# ---------- people and roles ----------

def test_member_account_is_separate_and_not_admin(owner, conn):
    client, _ = owner
    assert client.post("/api/auth/invites", json={"kind": "user", "name": ""}).status_code == 422
    invite = client.post("/api/auth/invites", json={"kind": "user", "name": "Sofia"}).json()

    member = browser()
    done, _ = register(member, invite["code"], "Sofia's iPhone")
    user = done.json()["user"]
    assert user["name"] == "Sofia" and user["role"] == "member" and user["id"] != 1

    # The owner's video and file are invisible to the member.
    media_id = conn.execute(
        "INSERT INTO media (user_id, url, platform, source_id, created_at) VALUES (1, 'https://x.com/a/status/1', 'x', 's', ?)",
        (db.now(),)).lastrowid
    path = config.OUTPUTS_DIR / "owner.mp4"
    path.write_bytes(b"secret")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=600)
    job_id = conn.execute("INSERT INTO jobs (user_id, media_id, preset, created_at) VALUES (1, ?, '720', ?)",
                          (media_id, db.now())).lastrowid
    assert client.get(f"/api/files/{file_id}/download").status_code == 200
    assert member.get(f"/api/files/{file_id}/download").status_code == 404
    assert member.get(f"/api/jobs/{job_id}").status_code == 404
    assert member.get(f"/api/jobs/{job_id}/events").status_code == 404
    assert member.post(f"/api/files/{file_id}/share").status_code == 404
    assert member.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).status_code == 404
    assert member.get("/api/jobs").json() == []

    # Members can add their own devices but can't invite people or see the people list.
    assert member.post("/api/auth/invites", json={"kind": "device"}).status_code == 200
    assert member.post("/api/auth/invites", json={"kind": "user", "name": "Friend"}).status_code == 403
    assert member.get("/api/admin/users").status_code == 403
    assert member.post("/api/admin/users/1/disable").status_code == 403

    people = client.get("/api/admin/users").json()
    assert [(p["name"], p["role"], p["devices"]) for p in people] == [("owner", "admin", 1), ("Sofia", "member", 1)]

    # Turning a person off signs them out and blocks their passkey.
    assert client.post(f"/api/admin/users/{user['id']}/disable").status_code == 200
    assert member.get("/api/jobs").status_code == 401
    assert client.post("/api/admin/users/1/disable").status_code == 409  # not yourself, not the last admin
    assert client.post(f"/api/admin/users/{user['id']}/enable").status_code == 200


def test_recovery_code_for_a_locked_out_owner(owner, conn):
    code = auth.recovery_code(conn)
    done, _ = register(browser(), code, "Replacement laptop")
    assert done.status_code == 200 and done.json()["user"]["role"] == "admin"
