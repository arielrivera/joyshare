# joyshare roadmap

What is built, what is left, and how to continue. Written so that anyone (a person or an AI assistant) can pick the project up cold.

Full plan with reasons: [project plan](https://claude.ai/artifact/Y8hfga81tr1HFhsTYAk9ya) (source: `docs/proposal.html`) · [infographic](https://claude.ai/artifact/4xiMLuHT4FMxgrjYRsVFKD) (source: `docs/infographic.html`) · [setup guide](SETUP.md)

## Where things stand

| Phase | What | Status |
|---|---|---|
| 1 | Core: download, convert, presets, share links, cleanup | **Done**, committed on `phase-1-core` |
| 2 | Access: passkeys, devices, people, tokens, Shortcut endpoint | **Done**, committed on `phase-2-access` |
| — | Redesign: one-step flow, looks, fonts, English/Spanish, custom name, compact top bar | **Done**, on `ui-redesign` (check `git status` for uncommitted work) |
| 3 | Admin panel, alerts, updates, R2 storage, backups, connected accounts | **In progress**, see below |
| 4 | 3D progress scenes, app icon and home-screen install, share page polish | Not started |
| 5 | Go live on the Mac mini with the domain, Cloudflare Tunnel, Uptime Kuma | Not started |

Branches build on each other: `phase-1-core` → `phase-2-access` → `ui-redesign`. Nothing has been pushed or merged to `main` unless the owner did it.

## How to work on it

```bash
docker compose up -d --build
```

```bash
docker compose run --rm --no-deps web python -m pytest -q tests
```

- App: http://localhost:8080. Two containers from one image: `web` (FastAPI, `app/main.py`) and `worker` (`app/worker.py`, also runs the scheduler).
- Data lives in the Docker volume `joyshare_joyshare_data`. Never run `docker compose down -v` unless a wipe is wanted.
- To see the signed-in interface without the owner's passkey, create a short-lived session in the container with `auth.create_session(conn, 1, None, "temporary test session")`, set it as the `joyshare_session` cookie, and delete it afterwards. Do not change `users.prefs` while testing.

## Rules of the project

1. **Every commit is in the owner's name only.** No co-author lines, no "generated with" lines.
2. **Everything a person reads is in English and Spanish.**
   - Interface text: `web/i18n.js` (both languages, same keys). Use `data-i18n` attributes or `t("key")`.
   - Server messages: write the English where it is used, add the Spanish to `ES` in `app/i18n.py`. Messages with changing parts use `T("... {n} ...", n=5)`. `tests/test_i18n.py` fails if Spanish is missing.
3. **New screens use the existing look system.** Colors come from the theme variables in `web/style.css` (`--bg`, `--card`, `--ink`, `--edge`, `--hot`, `--zap`, `--pop`, `--shadow`). Check new screens in at least Void, Zine, Clay and Windows 95, at phone width.
4. **Design choices: show sketches first, build after the owner picks** (see `docs/design/`).
5. **Keep the living pages current.** After any decision or finished piece: update `docs/proposal.html` (bump the version, add a changelog line) and `docs/infographic.html` if the picture changed, then republish both artifacts. Update `docs/SETUP.md` and `README.md` when behavior changes.
6. **Each person's data is theirs.** Every query filters by `user_id`. Members never see other people's videos, files, cookies or links.
7. **Only known platforms.** Links are checked in `app/platforms.py`; never let the server fetch arbitrary addresses.
8. **Tests for everything on the server.** Passkey tests use the software passkey in `tests/softauth.py`.

## Phase 3: what to build

Settings already live in the database (`app/settings.py`); phase 3 gives them a screen and adds the operations side.

### 3a. Alerts and admin settings (server) — done, no screen yet
- [x] `app/notify.py`: alerts through ntfy (`ntfy_url`, `ntfy_topic`, `ntfy_token` settings), in the admin's language. A failed alert never breaks a job.
- [x] Events, each switchable: video ready, job failed, disk 90%, disk 95% (jobs paused), new device, repeated failed sign-ins, test.
- [x] Added with 3c: yt-dlp updated, yt-dlp update failed, platform stopped working in the daily check.
- [ ] Events still to add with their features: backup failed.
- [x] Disk alert repeats at most every 6 hours.
- [x] Admin API in `app/admin.py` under `/api/admin`: `overview`, `settings` (read and change, validated), `alerts/test`, `jobs`, `share-links` (list and revoke), `audit`. Admin only; changes need a recent passkey check and go in the audit log. The ntfy token is never sent back.
- [x] "Pause new jobs" setting (`paused`).
- [ ] Alerts currently all go to the one admin topic. Later: a topic per person, so members get their own "video ready".
- [ ] Not yet tried against the real ntfy service (tests replace the network call). Needs a topic set through the API or the coming Alerts page.

### 3b. Admin panel (interface) — first seven tabs done
- [x] Reached from the ☰ menu, admins only (`web/admin.js`, the `#admin` block in `web/index.html`). Tabs: Overview, Videos, Share links, People (moved from Devices), Limits, Alerts, Activity log.
- [x] Limits tab edits: max file size, max length, videos at once, how long originals / files / links are kept, disk alert levels, biggest download, platforms on or off.
- [x] "Pause new videos" button on Overview.
- [x] Alerts tab: ntfy topic, server address, token (never shown again once saved), a switch per event, "Save and send a test alert".
- [x] System tab (yt-dlp updates and platform checks).
- [ ] Storage and Platforms tabs: built together with 3d–3f.
- [ ] Activity log shows details as raw text; make them readable sentences.
- [ ] "Fit a size" target list (`fit_targets_mb`) has no field yet.
- [ ] Checked in the browser at phone width in the Comic look only. Look at it in the other looks, especially Windows 95 and Clay.

### 3c. Keeping yt-dlp current — done
- [x] `app/engine.py`: daily check in the worker's scheduler. A newer version is installed into the data volume (`/data/ytdlp/<version>`, no image rebuild), test-run on a known video, then `/data/ytdlp/current` is pointed at it. A version that fails its test (while the current one passes) is removed and an alert goes out.
- [x] Both containers notice the change and restart themselves (`app/__init__.py` puts the chosen folder first on the import path). Proven for real: install, switch, restart, switch back.
- [x] System tab: version in use, newest known, last checked, "Check for updates now", automatic on or off, "Go back to version X" after an update.
- [x] Daily lookup of one known video per platform (`canary_urls` setting, YouTube and X for now); alert only when a platform newly breaks; "Test platforms now" button.
- [ ] The test-video addresses can't be edited in the panel yet, and TikTok, Instagram and Facebook have none.
- [ ] Not yet seen: a real newer release arriving (the installed version was already the newest).

### 3c-bis. A second engine, in case yt-dlp itself stops working (not started, owner to decide)
- [ ] First fallback, small: let the updater switch to yt-dlp's nightly builds when the stable one is broken.
- [ ] Second fallback, bigger: a self-hosted **cobalt** container (open source, covers X, YouTube, TikTok, Instagram, Facebook) called when yt-dlp fails for a link. `gallery-dl` is a lighter option for X and Instagram only.
- [ ] Design note: `app/media.py` is the only file that talks to yt-dlp, so a second engine means one more implementation of `inspect` and `download` there.

### 3d. Connected accounts (cookies)
- [ ] Per person, per platform, under Settings → Connected accounts. Stored encrypted (key from `.env`), removable, never shared, never visible to the admin in the app.
- [ ] Worker passes the job owner's cookie file to yt-dlp for that platform only. Reuse of finished files stays per person (already true).
- [ ] The page must explain in plain words: why connect, that only you use it, what happens if you skip it, and the tip to use a second account. Wording is in the project plan, section "Connected accounts".
- [ ] Alert the person when a platform stops accepting their cookies.

### 3e. Storage switch (Cloudflare R2)
- [ ] `STORAGE` setting: `local` (today) or `r2`. Worker uploads finished files to R2; pages hand out signed R2 links that last about an hour; the share page itself still expires after 48 hours.
- [ ] Storage page: shows whether R2 is set up, a step-by-step guide, a connection test; the switch only turns on after the test passes. R2 keys stored encrypted.
- [ ] R2 must be on before the app is reachable through the Cloudflare Tunnel (Cloudflare's terms on video).

### 3f. Backups
- [ ] Nightly copy of the database to R2; "Back up now" on the System page; alert on failure.
- [ ] `./joyshare backup` and `./joyshare restore` scripts that pack and unpack the data volume (also used for moving servers).

## Phase 4: look and feel
- [ ] Three.js progress scenes as plug-ins with the same inputs (progress, stage, done or failed): Demolition, Compressor, Voyage first; then Rocket, Black hole, Dominoes. Random per job, with a favorite setting.
- [ ] "Reduce motion" on the device: never a plain bar. Show a random calm scene and a small note with a tap to switch to full scenes.
- [ ] More looks from `docs/design/` if the owner picks them. Built: Void, Acid, Sunset, Zine, Clay, Windows 95, Comic, Vaporwave. Sketched only: A chrome, C arcade, E deco, F lava, I notebook, K receipt, L graffiti.
- [ ] Adding a look: a variables block and an override block in `web/style.css`, a swatch button in `web/index.html`, the name in `web/i18n.js`, its lettering in `THEME_FONT` (`web/prefs.js`), and the allowed lists in `app/auth.py`.
- [ ] App icon, home-screen install (PWA manifest), share page in the sender's look.
- [ ] Decide: stay with plain HTML/CSS/JS or move to SvelteKit. Current advice: stay unless it starts to hurt.

## Phase 5: go live
- [ ] Owner: buy the domain, move its DNS to Cloudflare, install the ntfy app, create the R2 bucket and the DigitalOcean droplet.
- [ ] Move to the Mac mini with the backup and restore scripts; write `docs/MOVING.md` while doing it, including a "Leaving Cloudflare" chapter (then a web server such as Caddy, a fixed IP or dynamic DNS, and open ports are needed).
- [ ] Cloudflare Tunnel container in `docker-compose.yml`; set `JOYSHARE_PUBLIC_URL` to the https address; read the visitor's address from Cloudflare's header for the failed-attempt limit.
- [ ] Every device registers its passkey again on the real domain (passkeys are tied to the address).
- [ ] Uptime Kuma in a container on the DigitalOcean droplet, watching `/api/health` and a worker heartbeat, alerting through ntfy.
- [ ] `docs/TROUBLESHOOTING.md`. Mac mini notes: Docker starts only after login, and FileVault blocks automatic login after a power cut.
- [ ] iPhone checks: passkey, Share button (find the size where it stops working), the Shortcut.

## Not yet tested
- A passkey on a phone, the iPhone share sheet and the Shortcut (all need the https address).
- Facebook links. Instagram worked once for the owner. TikTok: one public video downloaded and converted fine; another was refused by TikTok for this network address.
- Real expiry after 1 hour and 48 hours (covered by automated tests only).
- The Devices screen and the finished-file step in every look.

## Open decisions for the owner
- Which further looks to build.
- SvelteKit or not.
- Whether to put Cloudflare Access in front of the admin panel later (skipped for launch).
