import pytest

from app import config, db, notify, settings, twin


@pytest.fixture()
def sent(monkeypatch, conn):
    box = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, token: box.append(payload))
    settings.put(conn, "ntfy_topic", "t")
    return box


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://vids.example")


def answers(monkeypatch, *instances):
    replies = iter(instances)

    def ask(url):
        assert url == "https://vids.example/api/health"
        reply = next(replies)
        if reply is None:
            raise OSError("down")
        return {"ok": True, "instance": reply}
    monkeypatch.setattr(twin, "_ask", ask)


def test_no_check_when_not_live_on_a_domain(conn):
    assert config.PUBLIC_URL.startswith("http://localhost")
    assert twin.due(conn) is False


def test_alone_is_quiet(conn, sent, live, monkeypatch):
    me = twin.instance_id()
    assert twin.due(conn) is True
    answers(monkeypatch, me, me, me, me)
    assert twin.check(conn)["found"] is False
    assert sent == [] and twin.due(conn) is False


def test_a_second_copy_alerts_once_then_waits(conn, sent, live, monkeypatch):
    me = twin.instance_id()
    answers(monkeypatch, me, "another-copy", None, me)
    state = twin.check(conn)
    assert state["found"] is True and state["reached"] == 3
    assert len(sent) == 1 and "./joyshare retire" in sent[0]["message"] and sent[0]["priority"] == 5
    answers(monkeypatch, "another-copy", me, me, me)
    assert twin.check(conn)["found"] is True and len(sent) == 1      # same problem: no second alert yet
    answers(monkeypatch, me, me, me, me)
    assert twin.check(conn)["found"] is False                         # the old copy was stopped
    answers(monkeypatch, me, "another-copy", me, me)
    twin.check(conn)
    assert len(sent) == 2                                             # it came back: alert again


def test_an_unreachable_address_is_not_a_second_copy(conn, sent, live, monkeypatch):
    answers(monkeypatch, None, None, None, None)
    state = twin.check(conn)
    assert state["found"] is False and state["reached"] == 0 and sent == []
    assert twin.due(conn) is False                                    # but it looks again within a minute
    conn.execute("UPDATE state SET value=replace(value, ?, ?) WHERE key='twin'",
                 (str(state["checked_at"]), str(state["checked_at"] - 61)))
    assert twin.due(conn) is True


def test_overview_tells_the_admin(client, conn, live, monkeypatch):
    assert client.get("/api/admin/overview").json()["second_copy"] is False
    answers(monkeypatch, "another-copy", "another-copy", "another-copy", "another-copy")
    twin.check(conn)
    assert client.get("/api/admin/overview").json()["second_copy"] is True
