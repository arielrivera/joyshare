# joyshare roadmap

What is built, what is left, and how to continue. Written so that anyone (a person or an AI assistant) can pick the project up cold.

Short summary of what's pending: [PENDING.md](PENDING.md). Full plan with reasons: [project plan](https://claude.ai/artifact/Y8hfga81tr1HFhsTYAk9ya) (source: `docs/proposal.html`) · [infographic](https://claude.ai/artifact/4xiMLuHT4FMxgrjYRsVFKD) (source: `docs/infographic.html`) · [setup guide](SETUP.md)

## Where things stand

| Phase | What | Status |
|---|---|---|
| 1 | Core: download, convert, presets, share links, cleanup | **Done**, committed on `phase-1-core` |
| 2 | Access: passkeys, devices, people, tokens, Shortcut endpoint | **Done**, committed on `phase-2-access` |
| — | Redesign: one-step flow, looks, fonts, English/Spanish, custom name, compact top bar | **Done**, on `main` |
| 3 | Admin panel, alerts, updates, R2 storage, backups, connected accounts | **Done**, on `main` (a small Platforms tab is left) |
| 4 | 3D progress scenes, app icon and home-screen install, share page look | **First part done**: three scenes, two calm ones, install, share look |
| 5 | Go live on the Mac mini with the domain, Cloudflare Tunnel, Uptime Kuma | **Started**: domain and tunnel are up on the laptop |

Branches build on each other: `phase-1-core` → `phase-2-access` → `ui-redesign`. `main` on GitHub holds everything up to connected accounts (pushed 12 Nov 2026). Later work is on its own branch until the owner asks for a push.

## How to work on it

```bash
./joyshare update
```

```bash
./joyshare test
```

The `joyshare` script is the one place to start, stop, update, back up and retire. It turns on the optional `tunnel` and `caddy` containers from what is in `.env` (`CLOUDFLARE_TUNNEL_TOKEN`, `JOYSHARE_DOMAIN`).

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
- [x] Added with 3f: backup failed.
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
- [x] Storage tab (3e).
- [ ] Platforms tab (proxy per platform, test-video addresses): not started.
- [ ] Activity log shows details as raw text; make them readable sentences.
- [ ] "Fit a size" target list (`fit_targets_mb`) has no field yet.
- [ ] Checked in the browser at phone width in the Comic look only. Look at it in the other looks, especially Windows 95 and Clay.

### 3c. Keeping yt-dlp current — done
- [x] `app/engine.py`: daily check in the worker's scheduler. A newer version is installed into the data volume (`/data/ytdlp/<version>`, no image rebuild), test-run on a known video, then `/data/ytdlp/current` is pointed at it. A version that fails its test (while the current one passes) is removed and an alert goes out.
- [x] Both containers notice the change and restart themselves (`app/__init__.py` puts the chosen folder first on the import path). Proven for real: install, switch, restart, switch back.
- [x] System tab: version in use, newest known, last checked, "Check for updates now", automatic on or off, "Go back to version X" after an update.
- [x] Daily lookup of one known video per platform (`canary_urls` setting, YouTube and X for now); alert only when a platform newly breaks; "Test platforms now" button.
- [ ] Not yet seen: a real newer release arriving (the installed version was already the newest).

### 3c-bis. A second engine, in case yt-dlp itself stops working (not started, owner to decide)
- [ ] First fallback, small: let the updater switch to yt-dlp's nightly builds when the stable one is broken.
- [ ] Second fallback, bigger: a self-hosted **cobalt** container (open source, covers X, YouTube, TikTok, Instagram, Facebook) called when yt-dlp fails for a link. `gallery-dl` is a lighter option for X and Instagram only.
- [ ] Design note: `app/media.py` is the only file that talks to yt-dlp, so a second engine means one more implementation of `inspect` and `download` there.

### 3d. Connected accounts (cookies) — done
- [x] Per person, per platform, on the "Connected accounts" screen in the ☰ menu (`web/accounts.js`, `app/account.py`, `app/cookies.py`). Passkey sign-in only, not access tokens.
- [x] Only that platform's cookies are kept from the uploaded file; the rest is discarded. Stored encrypted (`app/secretbox.py`, key from `JOYSHARE_SECRET` or a generated key in the data volume). Never sent back out, not to the admin either.
- [x] Used only when the platform asks for a sign-in: lookups and downloads try without it first (`cookies.with_login`). The video then remembers it needs the account (`media.needs_login`).
- [x] The screen explains why, who can use it, what happens if you skip it, the second-account tip and how to get the file, in both languages.
- [x] A platform refusing a connected account marks it "rejected" on the screen and alerts once.
- [ ] That alert goes to the admin's ntfy topic. When people get their own topics, send it to the person instead.
- [ ] How-to has text steps only. Add pictures per browser.
- [ ] Not yet tried with a real signed-in cookie file against a real sign-in wall (tests fake the wall; a real lookup and download with a harmless cookie file worked).
- [ ] Optional proxy setting per platform (was planned for a Platforms tab).

### 3e. Storage switch (Cloudflare R2) — done, not yet tried on real R2
- [x] `app/storage.py`: with R2 on, the worker uploads each finished file (stage "uploading"), marks the row `storage='r2'` and deletes the local copy. Originals stay local.
- [x] File and share-link addresses answer with a redirect to a signed link that lasts an hour; downloads carry the nice file name. The share page itself still expires after 48 hours.
- [x] Clean-up deletes expired files from the bucket and retries if the bucket can't be reached.
- [x] Storage tab: where files are served from, setup steps, the four values, "Save and test" (write, read through a signed link, delete; also sets the bucket's CORS rule and a delete-leftovers rule), and the switch, which unlocks only after the test passes with those exact details. Changing a detail switches back to this server until retested.
- [x] The secret key is stored encrypted and never sent back. The page's security policy allows the bucket's address only when it is set up.
- [x] If an upload fails, the file stays on the server and an alert goes out.
- [x] Proven for real against an S3 emulator (moto): test, switch, a real job, fetch through the signed link, range request, download name, share link, clean-up.
- [ ] **Not yet tried on real Cloudflare R2.** Needs the owner's bucket and keys. Check there: the signed download name, the CORS rule and the lifecycle rule are accepted, and the iPhone Share button works with files in R2.
- [ ] R2 must be on before the app is reachable through the Cloudflare Tunnel (Cloudflare's terms on video). Phase 5 should refuse to go live otherwise, or warn loudly.
- [ ] boto3 adds about 100 MB to the image. A slimmer client is possible later.

### 3f. Backups — done
- [x] `app/backup.py`: a daily snapshot of the database (SQLite's own backup, taken while the app runs), compressed into `/data/backups`, newest 7 kept. Videos are not backed up.
- [x] If cloud storage is set up and tested, the snapshot also goes to the bucket under `backups/`, newest 14 kept. The bucket's clean-up rule now only covers `outputs/`, so it never deletes backups.
- [x] System tab: last backup, size, copies, "Back up now", automatic on or off. A failed backup alerts and says whether the local copy was made.
- [x] `./joyshare backup` (packs the data volume into `./backups`, videos left out unless `--with-videos`), `./joyshare restore FILE` and `./joyshare restore-db FILE.db.gz`. All three were run for real; both restores were verified in a scratch copy.
- [ ] The cloud copy has not run for real (needs R2).
- [ ] No "download this backup" button in the panel. Getting a snapshot off the machine without R2 means copying it out of the data volume by hand.

### Platform checks — tightened
- [x] "Test platforms now" is limited to 2 in any 3 hours (the daily automatic check doesn't count).
- [x] The admin picks which platforms are checked and can set each one's test video. YouTube and X are on by default; TikTok has a test video but is off; Instagram and Facebook need a link first.

## Phase 4: look and feel — first part done
- [x] 3D progress scenes with Three.js (`web/scenes/`, library in `web/vendor/`, loaded only when a video is being made). Each scene is a plug-in with the same inputs: progress, and whether it is running, done or failed.
- [x] Built: **Demolition** (soldier shoots a tower down; the gun jams on failure), **Compressor** (a press squeezes a block; it springs back on failure), **Voyage** (a ship flies planet to planet and lands; it drifts off on failure).
- [x] Random per video. In the pencil panel a person can pin one, or choose None, with a looping preview. Saved to the account (`scene`, `motion` in the saved look).
- [x] "Reduce motion" on the device: a random calm scene (**Ring**, **Bloom**), never a plain bar, with a small note and a button to show the full scenes.
- [x] The ending plays for about 1.7 seconds before the finished file (or the error) shows. Scenes take the look's colors.
- [x] App icon and home-screen install (`/manifest.webmanifest`, `web/icons/`, made by `tools/make_icons.py`).
- [x] The share page wears the sender's look.
- [x] Scripts and styles are served from an address that changes with every update (`/a/<fingerprint>/…`, see `ASSETS` in `app/main.py`), and pages are never stored. Reason: Cloudflare tells browsers to keep scripts and styles for 4 hours whatever the app says, which gave people a new page with old scripts.
- [ ] More scenes: Rocket, Black hole, Dominoes, and whatever the owner thinks up. To add one: a file in `web/scenes/`, import it in `web/scenes/index.js`, a button in the pencil panel, its name in `web/i18n.js`, and the allowed list in `app/auth.py` (`SCENES`) and `web/prefs.js`.
- [ ] Scenes use simple shapes drawn in code. Proper 3D models could replace them.
- [ ] Not yet seen: the scenes on a real phone, and the calm set triggered by a device's real Reduce Motion setting (they were viewed by asking for them directly).
- [ ] More looks from `docs/design/` if the owner picks them. Built: Void, Acid, Sunset, Zine, Clay, Windows 95, Comic, Vaporwave. Sketched only: A chrome, C arcade, E deco, F lava, I notebook, K receipt, L graffiti.
- [ ] Adding a look: a variables block and an override block in `web/style.css`, a swatch button in `web/index.html`, the name in `web/i18n.js`, its lettering in `THEME_FONT` (`web/prefs.js`), and the allowed lists in `app/auth.py`.
- [ ] Decide: stay with plain HTML/CSS/JS or move to SvelteKit. Current advice: stay.

## Clips: sharing only part of a video — steps 1 and 2 built (13 Nov 2026), step 3 open

Built: `jobs.clip_start` / `clip_end` (migration 5), `presets.check_clip()` and the range in `output_key()`, `media.convert(clip=…)` (always re-encodes, so the cut is exact), size estimates scaled in the interface, `clip_ok` on presets so a video too big to share whole can still be clipped. Interface: "✂️ Just a clip of the video" with Start and End on the size step, and "Start here" / "End here" / "Make this clip" under the finished video. Tests in `tests/test_clips.py` include real cuts made with ffmpeg. A real 6.5-second clip of an X video was made end to end.

Not built: step 3 below (fetching only the part with `download_ranges`). Until then the whole original is downloaded first, so the video must be within the download limit (`max_source_mb`) and the length limit.

The original plan, kept for reference:

The idea: the person gives a start and an end, and only that part is made and shared. It also lets a video that is over the size limit be shared as a clip.

**Two ways to get the part**

| | A. Fetch only the part | B. Fetch the whole video, then cut |
|---|---|---|
| How | yt-dlp's `download_ranges` (the `--download-sections` option) | The cached original is cut with ffmpeg (`-ss` / `-to`) |
| Good | Little data, quick for a short part of a long video; works when the whole video is too big | Several clips from one download; reuses today's pipeline and cache |
| Bad | Slower per second of video on some platforms; another code path to keep working | The whole video must be downloaded first, within today's size and length limits |

**Two ways to cut**

- *Copy without re-encoding:* instant, no quality loss, but the clip can only start on a keyframe, so it may begin a few seconds early.
- *Re-encode the clip:* starts and ends exactly where asked. Clips are short, so this takes seconds.

**Plan**

1. **Server, step one (B + re-encode).** `jobs` gets `clip_start` and `clip_end` (seconds). `media.convert()` takes them and re-encodes just that range (libx264, AAC, fast start). The range becomes part of the output key, so the same clip is reused and different clips don't collide. Size estimate = the preset's estimate × (clip length ÷ video length); the size limit applies to the clip. Validate: start < end, both inside the video, a minimum length of 1 second.
2. **Interface, two entry points.**
   - *Before making:* a "Just a part" switch on the size step with Start and End boxes (`m:ss`), for people who already know the times.
   - *After making:* on the finished video, "Start here" and "End here" buttons that read the player's current time, then "Make this clip". This is the easy way: watch, tap, tap. It cuts from the original that is cached for an hour.
3. **Long videos, step two (A).** When the whole video is over the download limit, fetch only the requested part with `download_ranges` and `force_keyframes_at_cuts`. Until this exists, a clip from a too-big video is refused with a clear message.
4. **Fit a size + clip** work together: the clip is cut first, then fitted.
5. Tests: range validation, the output key, the estimate, a real cut of a short public video checked with ffprobe (length within 0.2 s).
6. Both languages, both guides.

Rough size: step 1 and 2 about a day of work; step 3 about half a day, plus checking each platform.

## Phase 5: go live — started by the owner
- [x] Domain and Cloudflare Tunnel are up (`https://vids.arielrivera.app`), with `JOYSHARE_PUBLIC_URL` set in `.env`.
- [x] The app accepts more than one address (`config.ORIGINS`, `auth.site()`): the main one plus `http://localhost:PORT` on the server. Passkeys, the cross-site check and the cookie's https flag follow the address in use.
- [x] The real visitor address is read from Cloudflare's header (only when the request comes from a private network), so the failed-attempt limit is per visitor, not shared by everyone behind the tunnel.
- [x] `tunnel` service in `docker-compose.yml` (profile `tunnel`), reaching the app as `http://web:8080`. The owner still runs a separate `cloudflared` container and has to switch over.
- [x] Admins can invite another admin and change a person's role (never removing the last admin).
- [x] The app is called **vidshare** in the interface (`JOYSHARE_NAME`); the repository, script and settings keep the name joyshare. New people and devices start in the Zine look.
- [x] Confirmed by the owner on 13 Nov 2026: a passkey registered on the domain from the iPhone, and sign-in on the Mac at the domain with that same passkey (it reached the Mac through iCloud Keychain).

### Moving and running in one place — done 13 Nov 2026 (branch `easier-moves`)
- [x] `./joyshare start | stop | restart | update | status | logs | test | retire | unretire`, next to backup and restore. Optional containers follow `.env`.
- [x] `caddy` service (profile `caddy`, `JOYSHARE_DOMAIN`): https without Cloudflare. The visitor's address is read from `X-Forwarded-For` when the request comes from a private network. Proxying was checked; a real certificate on a real server was not.
- [x] Second-copy detection (`app/twin.py`): each copy has a random id in `/data/cache/instance_id` (not in backups), shown by `/api/health`. The worker asks the public address 4 times every 10 minutes; a different id means another copy is answering. Urgent alert `second_copy` (at most every 6 hours), a red warning on the Overview tab, an audit entry.
- [x] `docs/MOVING-MAC.md` and `docs/MOVING-LINUX.md` (these replace the planned `docs/MOVING.md`). Neither move has been done for real yet.
- [x] Link box: tapping it selects what's there; Paste, Copy and Clear buttons under it. The iPhone's own "Paste" confirmation can't be removed by a web page.

### Polish round — done 13 Nov 2026 (branch `easier-moves`)
- [x] A lively wait while a link is looked up (`#looking`, CSS only, rotating lines in both languages).
- [x] Recent list: **Copy link** on every finished file, **Make again** on expired, failed and canceled ones. The server reuses a live link, and makes a new one only when the old one has under 2 hours left and a longer one is possible (`LINK_NEARLY_OVER`).
- [x] Style panel: looks first, then fonts.
- [x] Readable activity log: `/api/admin/audit` returns details as an object with names and titles filled in; `web/admin.js` turns them into sentences from `actd.*` and `actv.*` entries in the dictionary. A new kind of entry needs an `act.` title and, if it has details, an `actd.` pattern.
- [x] Four more scenes: Rocket, Black hole, Dominoes, Abduction (`web/scenes/`). All drawn in code, no downloaded models. Checked by reading pixels in every state; not yet watched by a person.
- [x] Looks, round 3: all six built (Editorial, Swiss, Midnight, Nordic, Library, Studio) from the sketches in `docs/design/look-options-3.html`. They share one block of "classic" rules at the end of `web/style.css` (no glow, nothing tilted, thin lines); each look only sets colors and a few shape values, plus a short block of its own. Fonts are self-hosted (`web/fonts/README.md`).
- [x] Preview pictures are copied to the server when a link is looked up (`app/thumbs.py`, `/data/thumbs`, `GET /api/media/{id}/thumb`) and shown on the size step, in the Recent list and as the player's poster. Older videos get theirs the first time it is asked for. Only https addresses on the public internet are fetched.
- [x] The link box only takes web addresses: Paste, a pasted text and Look up all go through `webAddress()` in `web/app.js`, which also pulls the address out of surrounding text.
- [x] **Copy link** in Recent says so clearly: the button flips to "✓ Copied" and a highlighted line stays under the row. When the app doesn't answer (for example while it restarts) the message now says that, instead of "Something went wrong".
- [x] Removed at the owner's request: the Void, Sunset and Vaporwave looks and the Audiowide lettering. Anyone who had one of them falls back to Zine. Looks now: Zine, Acid, Clay, Windows 95, Comic, Editorial, Swiss, Midnight, Nordic, Library, Studio.

### Easy on a phone — done 14 Nov 2026 (branch `easy-sharing`)
- [x] Finished screen is share-first on touch devices: one big **Send or save** button (the share sheet), Download and the link under **More options** (`prepareShare()` in `web/app.js`).
- [x] One-tap mode: preference `sizes` (`auto` by default, `ask` to see the size step). `autoPick()` takes the usual preset if it is under 25 MB, else Fit a size at 25 MB or the nearest offered.
- [x] Link cards: `og:image` is our own copy at `/v/{token}/thumb` (public, ends with the link), plus `og:description` and a large Twitter card. The share page's player uses it as poster.
- [x] **Send or save** on each Recent row.
- [x] `/#url=<encoded link>` looks a link up on open (after sign-in). Text around the link is dropped.
- [x] **How it works** screen (☰ menu) and a first-time three-step card: the steps, sending and saving on a phone, home screen, and how to build the iPhone Shortcut.
- [ ] Not verified on a real iPhone: the share sheet from Recent (it may ask for a second tap), and the Shortcut steps (the action names "URL Encode" and "Open URLs" are from memory).

### Clips and sizes, round 2 — done 15 Nov 2026 (branch `small-polish`)
- [x] The size step is the default again (`prefs.sizes` = `ask`). A default size can be set in the pencil panel (`size_pick`: easy, best, 720, 480, audio) or with "Always make this size" on the size step.
- [x] Clips from a finished file: `jobs.from_file_id` (migration 6). The worker cuts from that file (bringing it back from R2 to a temporary file if needed) and never calls the platform; a clip of a clip subtracts the file's own start, read from its key. Tested in `tests/test_clips.py` with real ffmpeg cuts and a stand-in bucket.
- [x] Two-handle timeline (`rangeSlider()` in `web/app.js`) on the size step and under the finished video, with keyboard support, and **▶ Play the clip**.
- [x] Pencil panel sections have headings and dividers; "part" is now "clip" with ✂️; the size button says "Do it!".
- [x] A clearer message when registering a device fails with "prompt closed" (Chrome on iPhone reports an existing passkey that way).
- [x] Recent list: the owner picked layouts C (rows that open in place) and D (picture grid), switched with two icons beside the heading. The choice is the `recent` preference (`list` or `grid`), saved to the account. Clip in the list opens the finished screen with the timeline, which cuts from the saved file (`from_file`). Sketches of all four layouts stay in `docs/design/recent-options.html`.

### Reloading the home-screen app — done 15 Nov 2026 (branch `pull-to-refresh`)
- [x] Pull down to reload, only in the app added to the home screen (`display-mode: standalone`), where iOS offers none. Touch handlers in `web/app.js`; not while touching the timeline, a field or the player.
- [x] `reloadPage()` keeps the video on screen: it reloads with `#job=ID`, and a finished video opens straight on the finished screen (`openFinished`).
- [x] `/api/health` returns `version` (the interface fingerprint). When the app comes back to the screen after 30 s or more, it refreshes Recent and shows a "new version" bar with Reload if the fingerprint changed.
- [x] The open row in the Recent list has a darker background.
- [ ] Not yet tried with a finger on a real iPhone home-screen app (checked with simulated touches).

### Admin panel polish — done 15 Nov 2026 (branch `admin-polish`)
- [x] People: inviting sits at the top in its own box; the list of people with access comes below under its own heading.
- [x] System: an animation next to **Check for updates now** while the worker checks (it shows straight away, and goes when the check is done).
- [x] Videos: pictures (admin route `/api/admin/media/{id}/thumb`, any person's video), search (`q` on `/api/admin/jobs`: every word must match the title, channel, description, link, platform or person), and a details panel per video with the original link.
- Preview pictures are kept in `/data/thumbs` after the video files expire; nothing removes them yet. At about 50 KB each that's small, but a clean-up of pictures for very old videos may be worth adding later.

## Phase 5: remaining
- [ ] Owner: buy the domain, move its DNS to Cloudflare, install the ntfy app, create the R2 bucket and the DigitalOcean droplet.
- [ ] Move to the Mac mini following `docs/MOVING-MAC.md`, and correct the guide where reality differs.
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
