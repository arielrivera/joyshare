"""Opening the app at more than one address, visitor addresses behind the tunnel, and admin roles."""
import pytest
from softauth import SoftPasskey

from app import auth, config, db
from conftest import browser
from test_auth import register, sign_in

DOMAIN = "https://vids.example.app"


@pytest.fixture()
def two_addresses(monkeypatch):
    """The app is live on a domain, and can still be opened on the server itself at localhost."""
    monkeypatch.setattr(config, "PUBLIC_URL", DOMAIN)
    monkeypatch.setattr(config, "ORIGINS", [DOMAIN, "http://localhost:8080"])


def at(address, token=None):
    client = browser(token)
    client.headers["origin"] = address
    client.headers["host"] = address.split("://")[1]
    return client


def test_passkeys_work_at_the_domain_and_at_localhost(conn, two_addresses):
    assert auth.rp_id() == "vids.example.app"                       # the main address names the passkeys

    code = auth.ensure_setup_code(conn)
    phone = at(DOMAIN)
    start = phone.post("/api/auth/register/options", json={"code": code, "device_name": "iPhone"})
    assert start.json()["publicKey"]["rp"]["id"] == "vids.example.app"
    key = SoftPasskey(DOMAIN, "vids.example.app")
    done = phone.post("/api/auth/register/verify", json={"challenge_id": start.json()["challenge_id"],
                                                          "credential": key.register(start.json()["publicKey"])})
    assert done.status_code == 200 and "Secure" in done.headers["set-cookie"]   # https: the cookie is https-only

    # On the server itself, at localhost, a passkey is tied to "localhost" instead.
    local = at("http://localhost:8080")
    options = local.post("/api/auth/login/options").json()
    assert options["publicKey"]["rpId"] == "localhost"
    code = auth.recovery_code(conn)
    start = local.post("/api/auth/register/options", json={"code": code, "device_name": "Server"})
    local_key = SoftPasskey("http://localhost:8080", "localhost")
    done = local.post("/api/auth/register/verify", json={"challenge_id": start.json()["challenge_id"],
                                                          "credential": local_key.register(start.json()["publicKey"])})
    assert done.status_code == 200 and "Secure" not in done.headers["set-cookie"]
    assert local.get("/api/jobs").status_code == 200

    # A passkey made for one address is refused at the other.
    start = at(DOMAIN).post("/api/auth/login/options").json()
    wrong = at(DOMAIN).post("/api/auth/login/verify", json={"challenge_id": start["challenge_id"],
                                                             "credential": local_key.sign_in(start["publicKey"])})
    assert wrong.status_code == 401


def test_unknown_addresses_cannot_act_with_your_session(conn, two_addresses):
    token = auth.create_session(conn, 1)
    assert at(DOMAIN, token).post("/api/auth/logout-all").status_code == 200
    token = auth.create_session(conn, 1)
    assert at("https://evil.example", token).post("/api/auth/logout-all").status_code == 403
    assert at("http://localhost:9999", token).post("/api/auth/logout-all").status_code == 403


def test_invite_links_use_the_main_address(client, two_addresses):
    client.headers["origin"] = "http://localhost:8080"
    invite = client.post("/api/auth/invites", json={"kind": "device"}).json()
    assert invite["url"].startswith(DOMAIN + "/#join=")


def test_failed_attempts_are_counted_per_real_visitor_behind_the_tunnel(conn):
    from fastapi.testclient import TestClient
    from app import main
    # Every request arrives from the tunnel container's private address.
    anon = TestClient(main.app, headers={"origin": config.PUBLIC_URL}, client=("172.19.0.5", 40000))
    auth.ensure_setup_code(conn)
    bad = {"code": "AAAA-BBBB-CCCC", "device_name": "x"}
    attacker = {"cf-connecting-ip": "203.0.113.9"}
    for _ in range(auth.MAX_FAILURES):
        assert anon.post("/api/auth/register/options", json=bad, headers=attacker).status_code == 400
    assert anon.post("/api/auth/register/options", json=bad, headers=attacker).status_code == 429
    # Someone else, coming through the same tunnel, is not locked out.
    assert anon.post("/api/auth/register/options", json=bad, headers={"cf-connecting-ip": "198.51.100.4"}).status_code == 400


def test_the_visitor_header_is_only_believed_from_a_private_network():
    class Fake:
        def __init__(self, peer, forwarded):
            self.client = type("C", (), {"host": peer})()
            self.headers = {"cf-connecting-ip": forwarded} if forwarded else {}
    assert auth._ip(Fake("172.19.0.5", "203.0.113.9")) == "203.0.113.9"      # from the tunnel container
    assert auth._ip(Fake("8.8.8.8", "203.0.113.9")) == "8.8.8.8"             # a stranger can't pretend
    assert auth._ip(Fake("172.19.0.5", None)) == "172.19.0.5"


def test_invite_a_new_admin_and_change_roles(client, conn):
    invite = client.post("/api/auth/invites", json={"kind": "user", "name": "Dana", "role": "admin"})
    assert invite.status_code == 200
    assert client.post("/api/auth/invites", json={"kind": "user", "name": "X", "role": "king"}).status_code == 422
    dana = browser()
    done, _ = register(dana, invite.json()["code"], "Dana's Mac")
    user = done.json()["user"]
    assert user["role"] == "admin" and dana.get("/api/admin/overview").status_code == 200

    member = client.post("/api/auth/invites", json={"kind": "user", "name": "Sofia"}).json()   # member by default
    sofia = browser()
    sofia_user = register(sofia, member["code"], "Sofia's iPhone")[0].json()["user"]
    assert sofia_user["role"] == "member" and sofia.get("/api/admin/overview").status_code == 403

    # Members can't promote anyone, themselves included.
    assert sofia.post(f"/api/admin/users/{sofia_user['id']}/role", json={"role": "admin"}).status_code == 403

    assert client.post(f"/api/admin/users/{sofia_user['id']}/role", json={"role": "admin"}).status_code == 200
    assert sofia.get("/api/admin/overview").status_code == 200       # takes effect right away
    assert client.post(f"/api/admin/users/{sofia_user['id']}/role", json={"role": "member"}).status_code == 200
    assert sofia.get("/api/admin/overview").status_code == 403
    assert client.post(f"/api/admin/users/{sofia_user['id']}/role", json={"role": "king"}).status_code == 422
    assert client.post("/api/admin/users/999/role", json={"role": "admin"}).status_code == 404

    # There is always at least one admin.
    assert client.post(f"/api/admin/users/{user['id']}/role", json={"role": "member"}).status_code == 200
    last = client.post("/api/admin/users/1/role", json={"role": "member"})
    assert last.status_code == 409 and "at least one admin" in last.json()["detail"]
    roles = {p["name"]: p["role"] for p in client.get("/api/admin/users").json()}
    assert roles == {"owner": "admin", "Dana": "member", "Sofia": "member"}
