# Setting up joyshare

> **Where this guide stands:** phase 3 in progress. It covers running joyshare on your own computer, signing in with passkeys, the admin panel and alerts.
> Automatic updates, cloud storage, backups and going live on a domain are added as each is built.

See the whole picture first: [infographic](https://claude.ai/artifact/4xiMLuHT4FMxgrjYRsVFKD) · [project plan](https://claude.ai/artifact/Y8hfga81tr1HFhsTYAk9ya)

## What you need

- **Docker** with Docker Compose. On a Mac, Docker Desktop is enough. Make sure it is running (the whale icon in the menu bar).
- About 1 GB of free disk for the app, plus room for videos.

Nothing else. Python, ffmpeg and yt-dlp all come inside the container.

## Start it

From the joyshare folder:

```bash
docker compose up -d --build
```

The first run takes a few minutes while it downloads and builds. After that, open:

**http://localhost:8080**

## Register your first device

joyshare has no passwords. Each device signs in with a **passkey**: Face ID, Touch ID or your screen lock.

1. The first time it starts, joyshare prints a one-time **setup code** in its log. Show it with:

   ```bash
   docker compose logs web | grep -A1 "setup code"
   ```

2. Open http://localhost:8080, type the code, give the device a name and press **Register this device**.
3. Confirm with Touch ID (or your screen lock). You are now signed in as the admin.

The setup code works once and lasts 24 hours. It is only printed while **no device has ever been registered**. If it expired before you used it, restart to get a new one (`docker compose restart web`).

Once a device exists, a restart prints nothing. To register a device from the server (for example the first one on a new address, or after losing your devices), ask for a one-time code instead:

```bash
./joyshare setup-code
```

Then paste a link from X or YouTube, pick a size and press **Make it**.

> **Passkeys are tied to the address.** A passkey made at `localhost` only works at `localhost`.
> When joyshare moves to your real domain, each device registers once more there. Pick the final domain before registering all your devices.

## Make it yours

- **Language:** the flag buttons at the top switch between English and Spanish. Error messages and the page your friends see follow the language too. A friend's share page uses their own browser's language.
- **Name and look:** press the round pencil button next to the name. The first time, and now and then until you've used it, a small animated tip points at it. New people and devices start in the Zine look. You can change the name at the top (for example to "share"), the lettering and the look. There are eight looks: Void, Acid, Sunset, Zine, Clay, Windows 95, Comic and Vaporwave. Picking a look also switches to the lettering that suits it, and you can change the lettering afterwards. Your choices are saved to your account, so they follow you to every device. Friends see your name at the bottom of pages you share.
- **Default name for everyone:** set `JOYSHARE_NAME` in `.env`.
- **Progress scene:** while a video is being made, a small 3D scene plays: a soldier demolishing a tower, a press squeezing a block, or a spaceship flying between planets. By default you get a surprise each time. In the pencil panel you can pin one or choose None, and see a preview. If your device has "Reduce motion" on, you get a calm scene instead, with a button to show the full ones.
- **On your phone's home screen:** once joyshare has its `https://` address, open it on the phone and choose "Add to Home Screen" from the browser's share menu. It then opens full-screen like an app.

## Going live on your own domain

Phones can only use passkeys on an `https://` address, so this is the step that makes joyshare usable from your phone.

**1. Tell the app its address.** In `.env`:

```
JOYSHARE_PUBLIC_URL=https://your-domain.example
```

Then `docker compose up -d`. Share links and invites now use that address, and passkeys made there are tied to it.

**2. Run the Cloudflare Tunnel next to the app.** The tunnel is part of `docker-compose.yml`, in the same private network as the app, so it reaches the app by name and nothing depends on the host computer.

1. In the Cloudflare dashboard (Zero Trust → Networks → Tunnels), open your tunnel. Under **Public hostname**, set the service to `http://web:8080`.
2. Put the tunnel's token in `.env`: `CLOUDFLARE_TUNNEL_TOKEN=…`
3. Start everything: `docker compose --profile tunnel up -d`
4. If you were running `cloudflared` as a separate container before, remove that one, so only one copy is connected.

**Shortcut if you already have a device signed in at `localhost`:** open **Devices → Add a device** there. The QR code, the typed code and the link it shows all lead to the main address, so scanning it with your phone registers the phone on the domain. To register the same computer on the domain, open the link shown under the code.

**3. Register your devices on the new address.** A passkey made at `localhost` does not work on the domain, and the other way round. On the server run `./joyshare setup-code`, open the domain on your phone or computer, type the code and confirm with Face ID or Touch ID. After the first one, add more from **Devices → Add a device**.

**The server itself can still open the app at `http://localhost:8080`** with a passkey made there. That is a way back in if the domain or tunnel is down. To allow other addresses, set `JOYSHARE_EXTRA_ORIGINS` in `.env`.

Before sharing videos through the domain, turn on R2 storage (below): Cloudflare's rules don't allow video through the tunnel itself.

## Add another device

On a device that's already signed in:

1. Open **Devices** and press **Add a device**. joyshare asks for your passkey again, then shows a QR code and a code.
2. On the new device, scan the QR code with the camera (or open joyshare and type the code).
3. Name the device and confirm with Face ID or Touch ID.

The code works once and lasts 10 minutes.

> **Phones need https.** Browsers only allow passkeys on `localhost` or an `https://` address. So your iPhone can't register against your laptop's local address. That becomes possible once joyshare has its domain (the go-live phase), or earlier through a temporary tunnel to your laptop.

## Invite a person

**More admins:** in the same place, choose "as an admin" before pressing Invite, or press **Make admin** next to a person who already has an account. **Make member** takes it away again. There is always at least one admin.

Admins open **Admin panel → People** from the ☰ menu. Type a name and press **Invite**, then have that person scan the QR code on their own device. They get their own account as a *member*: they only see their own videos and can't invite others. You can turn a person off (and back on) from the same list.

## Connected accounts

Some videos are only shown to signed-in accounts: most of Instagram, and age-restricted or sensitive posts elsewhere. When that happens joyshare says so and points you here.

Open **☰ → Connected accounts**. For each platform you can upload a cookie file from a browser where you're signed in to that platform.

1. On a computer, add a browser extension that exports cookies in the "cookies.txt" format.
2. Sign in to the platform in that browser. A spare account is safer than your main one.
3. On the platform's site, export its cookies to a file with the extension.
4. In joyshare, press **Upload cookie file** next to that platform.

**On a phone:** phones can't easily export cookies. iPhone browsers have no way to do it, and on Android it only works in Firefox with an add-on. You don't need to: a connected account belongs to you, not to a device. Do it once on any computer and it works when you use joyshare from your phone. The cookie file can also be uploaded from the phone if you send it there first.

What happens to the file:

- Only that platform's cookies are kept. Everything else in the file is thrown away.
- They are stored encrypted, used only for your own videos, and never shown to anyone, including the admin.
- They are used only when the platform asks for a sign-in. Public videos are fetched without them.
- **Remove** deletes them. If a platform stops accepting them, the screen says so and you upload a fresh file.

For stronger protection, set `JOYSHARE_SECRET` in `.env` to a long random text before anyone uploads a file. Without it, joyshare creates a key and keeps it in the data volume. Changing the secret later means everyone uploads their files again.

## Admin panel

Admins see **Admin panel** in the ☰ menu. Changing anything there asks for your passkey again if the last check was more than 10 minutes ago.

| Tab | What it's for |
|---|---|
| Overview | Videos in the last day and week, what's in progress, files kept, active links, disk use, whether the worker is running, the yt-dlp version. The **Pause new videos** button is here. |
| Videos | Everyone's videos, newest first, with a filter. Failed ones show the reason. |
| Share links | Every link that still works, with its views. **Revoke** makes one stop working right away. |
| People | Invite a person, or turn a person off and on. |
| Limits | Biggest file, longest video, how long things are kept, disk alert levels, which platforms are allowed. Changes apply right away. |
| Alerts | Where alerts go and which ones you want. |
| Storage | Serve finished videos from this server or from Cloudflare R2, with the setup steps and a connection test. |
| System | The yt-dlp version in use, checking for updates, going back a version, the daily platform checks (you choose which platforms and their test videos), and backups. |
| Activity log | Sign-in problems and every change to devices, people, links and settings. |

### Serve videos from Cloudflare R2

**The full step-by-step guide is in [R2.md](R2.md).** In short:

By default, finished videos are served from the computer joyshare runs on. With R2 on, each finished video is uploaded to your R2 bucket and viewers get it straight from Cloudflare's storage.

**Turn this on before joyshare is reachable from the internet through a Cloudflare Tunnel.** Cloudflare's rules don't allow video through the tunnel itself, and with R2 the video never goes through it. R2 is free for the first 10 GB stored.

1. In the Cloudflare dashboard, open **R2** and create a bucket (for example `joyshare`).
2. In R2, choose **Manage API tokens** and create a token with **Object Read & Write** for that bucket only.
3. Copy the **Access Key ID** and **Secret Access Key** (shown once) and your **Account ID**.
4. In joyshare, open **Admin panel → Storage**, type the four values and press **Save and test**. The test writes a small file, reads it back through a signed link and deletes it.
5. When the test passes, press **Serve new files from R2**.

Good to know:

- The switch only unlocks after the test passes. If you later change any of the four values, joyshare goes back to this server until you test again.
- Files already in R2 keep working if you switch back.
- The secret key is stored encrypted and is never shown again.
- If an upload to R2 ever fails, that video stays on the server and you get an alert.

### Backups and restoring

Once a day joyshare saves a copy of its database: who can sign in, settings, history and connected accounts. Videos are not included, because they are temporary. **Admin panel → System** shows the last backup and has **Back up now**.

- Copies are kept inside the data volume (the newest 7).
- If R2 is set up and tested, each copy also goes to your bucket (the newest 14). That is the copy that survives losing the computer.

For moving to another computer, or keeping your own copy, use the `joyshare` script in the project folder:

| I want to… | Command |
|---|---|
| Pack everything into one file in `./backups` | `./joyshare backup` |
| Include the current videos too | `./joyshare backup --with-videos` |
| Replace all data with a backup file | `./joyshare restore backups/joyshare-backup-….tar.gz` |
| Put back only the database from a daily copy | `./joyshare restore-db joyshare-….db.gz` |

`backup` stops joyshare for a few seconds so the copy is consistent. Both restore commands ask you to type `yes` first, because they replace what is there.

**Moving to another computer:** run `./joyshare backup`, copy the backup file and your `.env` to the joyshare folder on the new computer, and run `./joyshare restore` there.

Keep your `.env` with your backups. If you set `JOYSHARE_SECRET`, connected accounts in a backup can only be read with that same secret.

### Turn on alerts

1. Install the free **ntfy** app on your phone.
2. In the app, subscribe to a topic. Make the name long and hard to guess, because anyone who knows it can read your alerts.
3. In joyshare, open **Admin panel → Alerts**, type the same topic and press **Save and send a test alert**. Your phone should buzz.
4. Tick the alerts you want: a video is ready, a video fails, the disk is filling up, a device is added, repeated failed sign-ins.

Leave the topic empty to turn alerts off. If you run your own ntfy server, put its address and access token in the same tab.

## Access tokens and the iPhone Shortcut

A token lets a script add videos as you without a passkey. It can't manage devices or people.

1. In **Devices → Access tokens**, type a name such as "iPhone Shortcut" and press **Create token**. Copy it right away: it is shown once.
2. In the Shortcuts app on your iPhone, create a shortcut with these actions:
   - **Receive** *URLs* from the **Share Sheet**
   - **Get Contents of URL**
     - URL: `https://YOUR-DOMAIN/api/quick`
     - Method: `POST`
     - Headers: `Authorization` = `Bearer YOUR-TOKEN`
     - Request Body: JSON, with one text field `url` = *Shortcut Input*
   - **Get Dictionary Value**: `page_url` from *Contents of URL*
   - **Open URLs**: *Dictionary Value*
3. Now, in X or YouTube, tap Share → your shortcut. joyshare starts the suggested size and opens its page, where you watch progress and tap **Share**.

To force a size, add a second JSON field `preset` with `best`, `720`, `480` or `audio`.

Like passkeys on a phone, the Shortcut needs joyshare's https address, so it works after the go-live phase.

## Locked out?

If you lose every device, get a new one-time code on the server itself:

```bash
docker compose exec web python -m app.cli setup-code
```

It registers a new device for the admin, works once and lasts 30 minutes. Only someone with access to the server can run it.

## Everyday commands

| I want to… | Command |
|---|---|
| Start joyshare | `docker compose up -d` |
| Stop it | `docker compose down` |
| See what it's doing | `docker compose logs -f` |
| See only the downloads and converting | `docker compose logs -f worker` |
| Update after pulling new code | `docker compose up -d --build` |
| Run the tests | `docker compose run --rm --no-deps web python -m pytest -q tests` |
| Check it's healthy | open http://localhost:8080/api/health |

## Settings

These live in a file called `.env` in the joyshare folder on your computer, next to `docker-compose.yml`. It is not inside the container: Docker reads it when the containers start. All settings are optional.

To change one, for example the name:

1. If there is no `.env` yet, make it from the example: `cp .env.example .env`
2. Open `.env` in any text editor and set the line, for example `JOYSHARE_NAME=vidshare`
3. Restart so the containers pick it up: `docker compose up -d`

`JOYSHARE_NAME` is the name people see until they pick their own with the pencil button. A name someone already chose for themselves stays as they set it.

| Setting | What it does | Default |
|---|---|---|
| `JOYSHARE_PORT` | The port on your computer | `8080` |
| `JOYSHARE_PUBLIC_URL` | The address people use to reach joyshare. Share links and passkeys are tied to it. | `http://localhost:8080` |
| `JOYSHARE_NAME` | The name shown at the top until a person picks their own | `vidshare` |
| `JOYSHARE_EXTRA_ORIGINS` | Other addresses the app may be opened at, separated by commas | `http://localhost:8080` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Your tunnel's token, used by `docker compose --profile tunnel up -d` | none |
| `JOYSHARE_SECRET` | Long random text used to encrypt connected accounts | made automatically |
| `JOYSHARE_BIND` | Who can reach joyshare directly. `127.0.0.1` means only this computer. | `127.0.0.1` |

Limits such as the 200 MB maximum, how long files are kept (originals 1 hour, finished files and share links 48 hours) and the disk alert levels are changed in **Admin panel → Limits**.

## Where your data lives

Everything (the database and the videos) is in one Docker volume called `joyshare_joyshare_data`.

- It survives restarts, rebuilds and `docker compose down`.
- `docker compose down -v` **deletes it**. Only use `-v` when you want to start from nothing.
- Why a volume and not a normal folder: on a Mac, a database inside a shared folder can become unreliable when two containers use it at once. A volume avoids that. The backup and move commands (coming in the go-live phase) pack it into a single file you can copy anywhere.

To look inside:

```bash
docker compose exec worker ls -lh /data/media/outputs
```

## How it works, briefly

Two containers run from the same image:

- **web** serves the page and the API. It never downloads video itself, so it always answers quickly.
- **worker** takes jobs from a queue in the database, downloads with yt-dlp and converts with ffmpeg. It also has a built-in scheduler that deletes expired files and checks disk space every 5 minutes. No cron job is needed on your computer.

## What works today

- X (Twitter), YouTube and TikTok: tested. TikTok refuses some videos depending on where your server is.
- Instagram and Facebook: built in, marked experimental. Many of their videos need a signed-in account: see Connected accounts.
- Presets: best quality, 720p, 480p, fit under a size, audio only.
- Share links that expire after 48 hours.
- Sign-in with passkeys, extra devices by QR code, member accounts, access tokens.

## Troubleshooting

**"That code isn't valid"**
Codes work once and expire (setup code: 24 hours, device codes: 10 minutes). Create a new one. After 10 wrong tries joyshare makes you wait a few minutes.

**"This device already has a passkey for your account"**
Nothing is wrong. Passkeys travel between your own devices through your password manager: one made on your iPhone shows up on your Mac through iCloud Keychain. Skip registering and press **Sign in with a passkey**.

**"The passkey prompt was closed"**
The Touch ID or Face ID window was dismissed or timed out. Press the button again.

**"That passkey isn't registered here"**
The passkey belongs to another address (for example it was made at `localhost` and you're now on the domain), or the device was removed. Register the device again with a new code.

**It keeps asking "Confirm it's you"**
Adding devices, inviting people and creating tokens need a passkey check from the last 10 minutes. That's on purpose.

**"Cannot connect to the Docker daemon"**
Docker isn't running. Open Docker Desktop and wait for it to finish starting, then try again.

**The page looks half-updated after an update**
This should no longer happen: scripts and styles get a new address with every update. If you ever see it, reload the page once.

**The page doesn't load**
Run `docker compose ps`. Both `web` and `worker` should say "Up". If not, `docker compose logs web` shows why. If port 8080 is taken by another app, set `JOYSHARE_PORT=8081` in `.env` and start again.

**"… only shows this video to signed-in accounts"**
The platform wants a login for that video. Connect an account for that platform under **☰ → Connected accounts**.

**"… didn't accept your connected account"**
The cookies expired or the platform signed that browser out. Export a fresh cookie file and upload it again.

**"No video was found at that link"**
The post may have no video, or it was deleted. Open the link in a browser to check.

**A platform suddenly stops working**
Platforms change often and yt-dlp releases fixes quickly. joyshare checks for a new yt-dlp once a day, tests it, and switches to it by itself. To check right away, open **Admin panel → System** and press **Check for updates now**. If an update made things worse, **Go back to version …** on the same tab undoes it.

The System tab also shows the daily platform checks: one known video per platform is looked up every day, and you get an alert when one stops working.

**A job sits at "Waiting in line"**
The worker isn't running. Check `docker compose logs worker`.
