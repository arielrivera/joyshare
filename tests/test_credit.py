"""Credits: the hidden one in every file's details, and the optional small one drawn in a corner."""
import json
import shutil
import subprocess

from app import config, media, presets
from test_clips import URL, held_video, quiet, run, sample  # noqa: F401  (sample is a fixture)


def tags_of(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["format"].get("tags", {})


def test_the_credit_text():
    assert media.credit_line("Brooklyn Nets", "x") == "Brooklyn Nets · X"
    assert media.credit_line(None, "tiktok") == "via TikTok"
    assert media.credit_line("  Two\tspaces\n", "youtube") == "Two spaces · YouTube"
    long = media.credit_line("A" * 80, "instagram")
    assert long.startswith("A" * 39 + "…") and long.endswith("· Instagram")
    tags = media.credit_tags("Title", "Someone", "x", URL)
    assert tags == {"title": "Title", "artist": "Someone", "comment": f"Original: {URL} · via X (Twitter)"}
    assert media.credit_tags(None, None, None, None) == {}


def test_the_credit_is_part_of_the_file_name():
    assert presets.output_key("720", credit=True) == "720+credit"
    assert presets.output_key("720", clip=(1.0, 2.0), credit=True) == "720@1.0-2.0+credit"
    assert presets.output_key("audio", credit=True) == "audio"                  # nothing is drawn on sound


def test_every_file_carries_the_hidden_credit(sample, tmp_path):
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    tags = media.credit_tags("A: title", 'José "Pepe" 100%', "x", URL)
    video = media.convert(sample, tmp_path, "720", None, quiet, lambda: False, tags=tags)
    audio = media.convert(sample, tmp_path, "audio", None, quiet, lambda: False, tags=tags)
    for path in (video, audio):
        got = tags_of(path)
        assert got["title"] == "A: title" and got["artist"] == 'José "Pepe" 100%' and URL in got["comment"]


def test_the_visible_credit_redraws_the_video(sample, tmp_path, monkeypatch):
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    seen = []
    real = media._run_ffmpeg
    monkeypatch.setattr(media, "_run_ffmpeg", lambda args, *a, **k: seen.append(args) or real(args, *a, **k))

    plain = media.convert(sample, tmp_path, "720", None, quiet, lambda: False)
    assert "copy" in seen[-1][seen[-1].index("-c:v") + 1]                     # without it: copied, not redrawn
    marked = media.convert(sample, tmp_path, "720", None, quiet, lambda: False,
                           credit="Someone: 'odd' %{name} · X")
    args = seen[-1]
    assert args[args.index("-c:v") + 1] == "libx264" and "drawtext=" in args[args.index("-vf") + 1]
    assert "expansion=none" in args[args.index("-vf") + 1]                       # the text is never read as a template
    assert media.probe(marked)["vcodec"] == "h264" and abs(media.probe(marked)["duration"] - 12) < 0.2
    assert plain.stat().st_size != marked.stat().st_size

    fitted = media.convert(sample, tmp_path, "fit", 1, quiet, lambda: False, credit="Someone · X")
    assert fitted.stat().st_size <= 1024 * 1024 and "drawtext=" in seen[-1][seen[-1].index("-vf") + 1]


def test_prefs_take_the_credit_setting(client):
    assert client.get("/api/auth/status").json()["prefs"]["credit"] == "off"   # off unless the person turns it on
    assert client.put("/api/auth/prefs", json={"credit": "on"}).json()["credit"] == "on"
    assert client.put("/api/auth/prefs", json={"credit": "loud"}).status_code == 422


def fetch_from(sample):
    def download(url, key, dest, *args, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        return shutil.copy(sample, dest / "source.mkv") and dest / "source.mkv"
    return download


def spy_on_convert(monkeypatch):
    calls = []
    real = media.convert
    monkeypatch.setattr(media, "convert", lambda *a, **k: calls.append(k) or real(*a, **k))
    return calls


def test_the_worker_follows_the_setting_and_never_mixes_the_files(client, conn, sample, monkeypatch):
    monkeypatch.setattr(media, "download", lambda *a, **k: fetch_from(sample)(*a, **k))
    calls = spy_on_convert(monkeypatch)
    media_id, _ = held_video(conn, sample, key="480")

    plain = client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).json()
    run(plain["id"])
    assert calls[-1]["credit"] is None and calls[-1]["tags"]["comment"].startswith("Original: ")

    client.put("/api/auth/prefs", json={"credit": "on"})
    marked = client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).json()
    run(marked["id"])
    assert calls[-1]["credit"] == "via X"                                       # this video has no author name
    done = client.get(f"/api/jobs/{marked['id']}").json()
    assert done["status"] == "done" and not done.get("reused")                  # not the plain file from before
    keys = {r["key"] for r in conn.execute("SELECT key FROM files WHERE kind='output' AND deleted_at IS NULL")}
    assert {"720", "720+credit"} <= keys

    client.put("/api/auth/prefs", json={"credit": "off"})
    again = client.post("/api/jobs", json={"media_id": media_id, "preset": "720"}).json()
    run(again["id"])
    assert client.get(f"/api/jobs/{again['id']}").json()["file"]["id"] == \
        client.get(f"/api/jobs/{plain['id']}").json()["file"]["id"]             # the plain one is reused, as before


def test_a_clip_of_a_credited_video_keeps_one_credit(client, conn, sample, monkeypatch):
    monkeypatch.setattr(media, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetching")))
    calls = spy_on_convert(monkeypatch)
    media_id, file_id = held_video(conn, sample, key="720+credit")

    for setting in ("on", "off"):
        client.put("/api/auth/prefs", json={"credit": setting})
        job = client.post("/api/jobs", json={"media_id": media_id, "preset": "720", "clip_start": 2,
                                             "clip_end": 6 if setting == "on" else 7, "from_file": file_id}).json()
        run(job["id"])
        assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
        assert calls[-1]["credit"] is None                                      # already on the picture: not drawn twice
    keys = {r["key"] for r in conn.execute("SELECT key FROM files WHERE kind='output' AND deleted_at IS NULL")}
    assert {"720@2.0-6.0+credit", "720@2.0-7.0+credit"} <= keys                 # and its name says it has one
