import os
import tempfile

# Point the app at a throwaway data folder before any app module is imported.
os.environ["JOYSHARE_DATA"] = tempfile.mkdtemp(prefix="joyshare-test-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, config, db, main  # noqa: E402

TABLES = ("share_links", "jobs", "files", "media", "settings", "state", "audit_log",
          "sessions", "credentials", "invites", "challenges", "api_tokens")


@pytest.fixture()
def conn():
    db.init()
    connection = db.connect()
    for table in TABLES:
        connection.execute(f"DELETE FROM {table}")
    connection.execute("DELETE FROM users WHERE id!=1")
    connection.execute("UPDATE users SET disabled=0 WHERE id=1")
    auth._failures.clear()
    yield connection
    connection.close()


def browser(session_token: str | None = None) -> TestClient:
    """A test client that behaves like a browser on joyshare's own pages."""
    client = TestClient(main.app, headers={"origin": config.PUBLIC_URL})
    if session_token:
        client.cookies.set(auth.SESSION_COOKIE, session_token)
    return client


@pytest.fixture()
def anon(conn):
    """Nobody is signed in."""
    with browser() as client:
        yield client


@pytest.fixture()
def client(conn):
    """The owner (admin, user 1) is signed in."""
    with browser(auth.create_session(conn, 1)) as c:
        yield c
