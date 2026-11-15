import ast
import pathlib

from app import auth, i18n

APP = pathlib.Path(i18n.__file__).parent
MESSAGE_CALLS = {"HTTPException", "MediaError", "LinkError", "PresetError", "T", "tr", "render", "send", "CookieError", "StorageError"}


def messages_in_code():
    """Every English message the server can show: text passed to an error, T(...) or render(...)."""
    found = set()
    for path in APP.glob("*.py"):
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in MESSAGE_CALLS:
                continue
            for arg in node.args:
                parts = [arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else [arg]
                for part in parts:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str) and " " in part.value:
                        found.add(part.value)
    return found


def test_every_server_message_has_spanish():
    missing = sorted(m for m in messages_in_code() if m not in i18n.ES)
    assert not missing, f"Add Spanish for: {missing}"


def test_spanish_keeps_the_same_fill_in_values():
    import string
    fields = lambda text: {name for _, name, _, _ in string.Formatter().parse(text) if name}  # noqa: E731
    for english, spanish in i18n.ES.items():
        assert fields(english) == fields(spanish), english


def test_render_and_stored_messages():
    msg = i18n.T("Pick a size between 1 and {max} MB.", max=200)
    assert msg == "Pick a size between 1 and 200 MB."
    assert i18n.render(msg, "es") == "Elige un tamaño entre 1 y 200 MB."
    assert i18n.render("This video is private.", "es") == "Este video es privado."
    assert i18n.render("Something never translated", "es") == "Something never translated"
    assert i18n.unpack(i18n.pack(msg), "es") == "Elige un tamaño entre 1 y 200 MB."
    assert i18n.unpack("Plain old English row", "en") == "Plain old English row"
    assert i18n.unpack(None) is None


def test_errors_and_presets_follow_the_language(client, monkeypatch):
    from app import media
    assert client.post("/api/inspect", json={"url": "https://example.com/v"}).json()["detail"].startswith("This works with")
    client.cookies.set(i18n.LANG_COOKIE, "es")
    assert client.post("/api/inspect", json={"url": "https://example.com/v"}).json()["detail"].startswith("Funciona con")
    assert client.get("/api/jobs/999").json()["detail"] == "Tarea no encontrada."

    monkeypatch.setattr(media, "inspect", lambda url: {"id": "a", "title": "Clip", "duration": 60.0})
    monkeypatch.setattr(media, "estimate", lambda info, key: {
        "bytes": 300 * 1024 * 1024, "exact": True, "height": 1080, "vcodec": "avc1", "acodec": "mp4a",
        "needs_convert": False})
    best = client.post("/api/inspect", json={"url": "https://x.com/a/status/1"}).json()["presets"][0]
    assert best["label"] == "Mejor calidad" and best["reason"] == "Unos 300 MB, supera el límite de 200 MB."


def test_browser_language_is_used_when_nothing_is_chosen(anon):
    res = anon.get("/v/nope", headers={"accept-language": "es-MX,es;q=0.9,en;q=0.5"})
    assert res.status_code == 410 and "Este video ha caducado" in res.text and '<html lang="es"' in res.text
    assert "This video has expired" in anon.get("/v/nope", headers={"accept-language": "fr"}).text


def test_saved_look_follows_the_account(client, conn):
    status = client.get("/api/auth/status").json()
    assert status["prefs"] == {"name": "vidshare", "font": "mono", "theme": "zine", "lang": None,
                               "scene": "random", "motion": "auto", "sizes": "ask", "size_pick": "easy", "recent": "list"}

    saved = client.put("/api/auth/prefs", json={"name": "  share  ", "font": "glitch", "theme": "acid", "lang": "es"})
    assert saved.json() == {"name": "share", "font": "glitch", "theme": "acid", "lang": "es", "scene": "random", "motion": "auto", "sizes": "ask", "size_pick": "easy", "recent": "list"}
    assert client.put("/api/auth/prefs", json={"scene": "voyage", "motion": "full"}).json()["scene"] == "voyage"
    assert client.put("/api/auth/prefs", json={"scene": "fireworks"}).status_code == 422
    assert client.put("/api/auth/prefs", json={"sizes": "auto", "size_pick": "480"}).json()["size_pick"] == "480"
    assert client.put("/api/auth/prefs", json={"sizes": "maybe"}).status_code == 422
    assert client.put("/api/auth/prefs", json={"size_pick": "huge"}).status_code == 422
    assert client.put("/api/auth/prefs", json={"recent": "grid"}).json()["recent"] == "grid"
    assert client.put("/api/auth/prefs", json={"recent": "carousel"}).status_code == 422
    assert client.get("/api/auth/status").json()["prefs"]["recent"] == "grid"          # follows the account
    client.put("/api/auth/prefs", json={"recent": "list"})
    assert client.put("/api/auth/prefs", json={"sizes": "ask", "size_pick": "easy", "recent": "list"}).json()["sizes"] == "ask"
    assert client.get("/api/auth/status").json()["prefs"]["name"] == "share"
    assert auth.get_prefs(conn, 1)["name"] == "share"

    for theme, font in (("zine", "mono"), ("clay", "fredoka"), ("win95", "win"), ("comic", "bangers"), ("editorial", "playfair"), ("studio", "plex")):
        assert client.put("/api/auth/prefs", json={"theme": theme, "font": font}).json()["theme"] == theme
    assert client.put("/api/auth/prefs", json={"font": "comic-sans"}).status_code == 422
    assert client.put("/api/auth/prefs", json={"name": "x" * 25}).status_code == 422
    assert client.put("/api/auth/prefs", json={"name": ""}).json()["name"] == "vidshare"  # back to the default


def test_share_page_shows_the_senders_name(client, conn):
    from app import config, db, store
    client.put("/api/auth/prefs", json={"name": "share <b>", "theme": "comic", "font": "bangers"})
    media_id = conn.execute(
        "INSERT INTO media (user_id, url, platform, title, uploader, created_at) "
        "VALUES (1, 'https://x.com/a/status/1', 'x', 'Clip', 'someone', ?)", (db.now(),)).lastrowid
    path = config.OUTPUTS_DIR / "brand.mp4"
    path.write_bytes(b"x")
    file_id = store.add_file(conn, user_id=1, media_id=media_id, kind="output", key="720", path=path, ttl_seconds=600)
    token = client.post(f"/api/files/{file_id}/share").json()["url"].rsplit("/", 1)[1]
    page = client.get(f"/v/{token}", headers={"accept-language": "es"}).text
    assert "compartido con <strong>share &lt;b&gt;</strong>" in page and "<b>" not in page
    assert '<html lang="es" data-theme="comic" data-font="bangers">' in page      # the friend sees the sender's look
    assert "De someone en X (Twitter)" in page and ">Descargar<" in page
