# Setting up joyshare

> **Where this guide stands:** phase 2. It covers running joyshare on your own computer and signing in with passkeys.
> Alerts, the admin panel and going live on a domain are added to this guide as each phase is built.

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

The setup code works once and lasts 24 hours. If it expired before you used it, restart joyshare to get a new one (`docker compose restart web`).

Then paste a link from X or YouTube, pick a size and press **Make it**.

> **Passkeys are tied to the address.** A passkey made at `localhost` only works at `localhost`.
> When joyshare moves to your real domain, each device registers once more there. Pick the final domain before registering all your devices.

## Make it yours

- **Language:** the flag buttons at the top switch between English and Spanish. Error messages and the page your friends see follow the language too. A friend's share page uses their own browser's language.
- **Name and look:** press the round pencil button next to the name. You can change the name at the top (for example to "share"), the lettering and the look. There are eight looks: Void, Acid, Sunset, Zine, Clay, Windows 95, Comic and Vaporwave. Picking a look also switches to the lettering that suits it, and you can change the lettering afterwards. Your choices are saved to your account, so they follow you to every device. Friends see your name at the bottom of pages you share.
- **Default name for everyone:** set `JOYSHARE_NAME` in `.env`.

## Add another device

On a device that's already signed in:

1. Open **Devices** and press **Add a device**. joyshare asks for your passkey again, then shows a QR code and a code.
2. On the new device, scan the QR code with the camera (or open joyshare and type the code).
3. Name the device and confirm with Face ID or Touch ID.

The code works once and lasts 10 minutes.

> **Phones need https.** Browsers only allow passkeys on `localhost` or an `https://` address. So your iPhone can't register against your laptop's local address. That becomes possible once joyshare has its domain (the go-live phase), or earlier through a temporary tunnel to your laptop.

## Invite a person

Admins see a **People** section on the Devices screen. Type a name and press **Invite**, then have that person scan the QR code on their own device. They get their own account as a *member*: they only see their own videos and can't invite others. You can turn a person off (and back on) from the same list.

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

Copy `.env.example` to `.env` to change these. All are optional.

| Setting | What it does | Default |
|---|---|---|
| `JOYSHARE_PORT` | The port on your computer | `8080` |
| `JOYSHARE_PUBLIC_URL` | The address people use to reach joyshare. Share links and passkeys are tied to it. | `http://localhost:8080` |
| `JOYSHARE_NAME` | The name shown at the top until a person picks their own | `joyshare` |
| `JOYSHARE_BIND` | Who can reach joyshare directly. `127.0.0.1` means only this computer. | `127.0.0.1` |

Limits such as the 200 MB maximum, how long files are kept (originals 1 hour, finished files and share links 48 hours) and the disk alert levels live in the database. The admin panel (phase 3) will let you change them.

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

- X (Twitter) and YouTube: tested.
- Instagram and Facebook: built in, marked experimental, **not tested yet**. Many of their videos need a signed-in account, which arrives with Connected accounts.
- Presets: best quality, 720p, 480p, fit under a size, audio only.
- Share links that expire after 48 hours.
- Sign-in with passkeys, extra devices by QR code, member accounts, access tokens.

## Troubleshooting

**"That code isn't valid"**
Codes work once and expire (setup code: 24 hours, device codes: 10 minutes). Create a new one. After 10 wrong tries joyshare makes you wait a few minutes.

**"The passkey prompt was closed"**
The Touch ID or Face ID window was dismissed or timed out. Press the button again.

**"That passkey isn't registered here"**
The passkey belongs to another address (for example it was made at `localhost` and you're now on the domain), or the device was removed. Register the device again with a new code.

**It keeps asking "Confirm it's you"**
Adding devices, inviting people and creating tokens need a passkey check from the last 10 minutes. That's on purpose.

**"Cannot connect to the Docker daemon"**
Docker isn't running. Open Docker Desktop and wait for it to finish starting, then try again.

**The page doesn't load**
Run `docker compose ps`. Both `web` and `worker` should say "Up". If not, `docker compose logs web` shows why. If port 8080 is taken by another app, set `JOYSHARE_PORT=8081` in `.env` and start again.

**"The platform only shows this video to signed-in accounts"**
The platform wants a login for that video. This is solved by Connected accounts in a later phase.

**"No video was found at that link"**
The post may have no video, or it was deleted. Open the link in a browser to check.

**YouTube suddenly stops working**
Platforms change often and yt-dlp releases fixes quickly. Rebuild to pick up the newest version:

```bash
docker compose build --no-cache && docker compose up -d
```

Phase 3 makes this automatic.

**A job sits at "Waiting in line"**
The worker isn't running. Check `docker compose logs worker`.
