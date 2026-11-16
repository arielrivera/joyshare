"""SQLite access. One file, WAL mode, a short list of numbered migrations."""
import sqlite3
import time

from . import config

MIGRATIONS = [
    # 1: initial schema
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
        disabled INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE TABLE state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE TABLE media (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        url TEXT NOT NULL,
        platform TEXT NOT NULL,
        source_id TEXT,
        title TEXT,
        uploader TEXT,
        uploader_id TEXT,
        channel TEXT,
        description TEXT,
        duration REAL,
        thumbnail TEXT,
        webpage_url TEXT,
        upload_date TEXT,
        info_json TEXT,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE files (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        media_id INTEGER NOT NULL REFERENCES media(id),
        kind TEXT NOT NULL CHECK (kind IN ('source', 'output')),
        key TEXT NOT NULL,
        path TEXT NOT NULL,
        size INTEGER NOT NULL,
        mime TEXT,
        width INTEGER,
        height INTEGER,
        duration REAL,
        vcodec TEXT,
        acodec TEXT,
        storage TEXT NOT NULL DEFAULT 'local',
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        deleted_at INTEGER
    );
    CREATE INDEX files_lookup ON files (user_id, media_id, kind, key);
    CREATE INDEX files_expiry ON files (expires_at) WHERE deleted_at IS NULL;
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        media_id INTEGER NOT NULL REFERENCES media(id),
        preset TEXT NOT NULL,
        target_mb INTEGER,
        status TEXT NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'running', 'done', 'failed', 'canceled')),
        stage TEXT,
        progress REAL NOT NULL DEFAULT 0,
        error TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        reused INTEGER NOT NULL DEFAULT 0,
        file_id INTEGER REFERENCES files(id),
        created_at INTEGER NOT NULL,
        started_at INTEGER,
        finished_at INTEGER
    );
    CREATE INDEX jobs_status ON jobs (status, id);
    CREATE TABLE share_links (
        token TEXT PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES files(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        revoked_at INTEGER,
        views INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        action TEXT NOT NULL,
        detail TEXT,
        created_at INTEGER NOT NULL
    );
    """,
    # 2: sign-in (passkeys, sessions, invites, access tokens)
    """
    ALTER TABLE users ADD COLUMN handle BLOB;
    CREATE TABLE credentials (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        credential_id BLOB NOT NULL UNIQUE,
        public_key BLOB NOT NULL,
        sign_count INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL,
        transports TEXT,
        created_at INTEGER NOT NULL,
        last_used_at INTEGER
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        credential_pk INTEGER,
        created_at INTEGER NOT NULL,
        authenticated_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        user_agent TEXT
    );
    CREATE TABLE invites (
        code_hash TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('setup', 'device', 'user')),
        user_id INTEGER REFERENCES users(id),
        role TEXT,
        name TEXT,
        created_by INTEGER,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        used_at INTEGER
    );
    CREATE TABLE challenges (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        challenge BLOB NOT NULL,
        invite_hash TEXT,
        user_handle BLOB,
        device_name TEXT,
        expires_at INTEGER NOT NULL
    );
    CREATE TABLE api_tokens (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL,
        last_used_at INTEGER,
        revoked_at INTEGER
    );
    """,
    # 3: each person's own look (name shown at the top, font, theme, language)
    """
    ALTER TABLE users ADD COLUMN prefs TEXT;
    """,
    # 4: connected accounts (each person's own cookie file per platform, encrypted)
    """
    CREATE TABLE cookies (
        user_id INTEGER NOT NULL REFERENCES users(id),
        platform TEXT NOT NULL,
        data BLOB NOT NULL,
        cookie_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ok',
        updated_at INTEGER NOT NULL,
        last_used_at INTEGER,
        PRIMARY KEY (user_id, platform)
    );
    ALTER TABLE media ADD COLUMN needs_login INTEGER NOT NULL DEFAULT 0;
    """,
    # 5: clips (only part of a video): where the part starts and ends, in seconds
    """
    ALTER TABLE jobs ADD COLUMN clip_start REAL;
    ALTER TABLE jobs ADD COLUMN clip_end REAL
    """,
    # 6: a clip can be cut from a finished file we already hold, instead of fetching the video again
    """
    ALTER TABLE jobs ADD COLUMN from_file_id INTEGER REFERENCES files(id)
    """,
    # 7: a person can delete a video from their history (undo is possible for a few minutes)
    """
    ALTER TABLE jobs ADD COLUMN deleted_at INTEGER
    """,
]


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    # check_same_thread=False: the web server may open a request's connection on one worker
    # thread and close it on another. Each connection still serves one request at a time.
    conn = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def get_conn():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    """Create folders, apply pending migrations, make sure the owner exists."""
    config.ensure_dirs()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, sql in enumerate(MIGRATIONS, start=1):
            if number > version:
                for statement in sql.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute(f"PRAGMA user_version={number}")
        conn.execute(
            "INSERT OR IGNORE INTO users (id, name, role, created_at) VALUES (?, 'owner', 'admin', ?)",
            (config.DEFAULT_USER_ID, now()),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def audit(conn: sqlite3.Connection, user_id, action: str, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (user_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
        (user_id, action, detail, now()),
    )


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, now()),
    )


def get_state(conn: sqlite3.Connection, key: str):
    """Returns (value, updated_at) or (None, None)."""
    row = conn.execute("SELECT value, updated_at FROM state WHERE key=?", (key,)).fetchone()
    return (row["value"], row["updated_at"]) if row else (None, None)
