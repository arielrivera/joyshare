import os
import tempfile

# Point the app at a throwaway data folder before any app module is imported.
os.environ["JOYSHARE_DATA"] = tempfile.mkdtemp(prefix="joyshare-test-")

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture()
def conn():
    db.init()
    connection = db.connect()
    for table in ("share_links", "jobs", "files", "media", "settings", "state", "audit_log"):
        connection.execute(f"DELETE FROM {table}")
    yield connection
    connection.close()
