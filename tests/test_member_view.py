"""'View as member': an admin uses one device as a regular member. Nobody else can ever switch."""
import pytest

from app import auth, db
from conftest import browser

ADMIN_ONLY_GETS = ("/api/admin/overview", "/api/admin/settings", "/api/admin/users", "/api/admin/system")


@pytest.fixture()
def member_id(conn):
    return conn.execute("INSERT INTO users (name, role, created_at) VALUES ('Sofia', 'member', ?)", (db.now(),)).lastrowid


def who(client):
    return client.get("/api/auth/status").json()["user"]


def test_admin_gets_the_member_experience_and_comes_back(client, conn):
    assert who(client) == {"id": 1, "name": "owner", "role": "admin"}
    for path in ADMIN_ONLY_GETS:
        assert client.get(path).status_code == 200, path

    assert client.post("/api/auth/member-view", json={"on": True}).json() == {"ok": True, "member_view": True}
    assert who(client) == {"id": 1, "name": "owner", "role": "member", "member_view": True}
    for path in ADMIN_ONLY_GETS:
        assert client.get(path).status_code == 403, path                          # the server treats it as a member
    assert client.put("/api/admin/settings", json={"changes": {"max_file_mb": 5}}).status_code == 403
    assert client.post("/api/auth/invites", json={"kind": "user", "name": "Leo", "role": "member"}).status_code == 403
    assert client.get("/api/jobs").status_code == 200                              # the regular app still works

    # Only this device changed: the admin's other devices stay admins.
    with browser(auth.create_session(conn, 1)) as other:
        assert who(other)["role"] == "admin" and other.get("/api/admin/users").status_code == 200

    assert client.post("/api/auth/member-view", json={"on": False}).json() == {"ok": True, "member_view": False}
    assert who(client) == {"id": 1, "name": "owner", "role": "admin"}
    assert client.get("/api/admin/users").status_code == 200

    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["auth.member_view_on", "auth.member_view_off"]


def test_a_member_can_never_switch(conn, member_id):
    session = auth.create_session(conn, member_id)
    with browser(session) as member:
        for on in (True, False):
            assert member.post("/api/auth/member-view", json={"on": on}).status_code == 403
        # Even if the flag were somehow set on a member's device, it changes nothing.
        conn.execute("UPDATE sessions SET member_view=1 WHERE token_hash=?", (auth.sha(session),))
        assert who(member) == {"id": member_id, "name": "Sofia", "role": "member"}
        assert member.post("/api/auth/member-view", json={"on": False}).status_code == 403
        assert who(member)["role"] == "member" and member.get("/api/admin/users").status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'auth.member_view%'").fetchone()[0] == 0


def test_an_admin_made_member_loses_the_switch(client, conn):
    client.post("/api/auth/member-view", json={"on": True})
    conn.execute("UPDATE users SET role='member' WHERE id=1")
    assert who(client) == {"id": 1, "name": "owner", "role": "member"}           # no way back to admin
    assert client.post("/api/auth/member-view", json={"on": False}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_access_tokens_and_new_sign_ins_are_not_affected(client, conn):
    token = client.post("/api/auth/tokens", json={"name": "Shortcut"}).json()["token"]
    with browser() as script:
        script.headers["authorization"] = f"Bearer {token}"
        assert script.post("/api/auth/member-view", json={"on": True}).status_code == 403
    client.post("/api/auth/member-view", json={"on": True})
    with browser(auth.create_session(conn, 1)) as fresh:                         # signing in again starts as admin
        assert who(fresh)["role"] == "admin"
