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
./joyshare update
```

`joyshare` is a small script in the project folder. Starting, stopping, updating, backups and moving all go through it; the list is under [Everyday commands](#everyday-commands).

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

Then paste a link from X or YouTube. The video is made straight away; if you have turned on **Ask me which size every time**, pick a size and press **Do it!**.

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

Then `./joyshare start`. Share links and invites now use that address, and passkeys made there are tied to it.

**2. Run the Cloudflare Tunnel next to the app.** The tunnel is part of `docker-compose.yml`, in the same private network as the app, so it reaches the app by name and nothing depends on the host computer.

1. In the Cloudflare dashboard (Zero Trust → Networks → Tunnels), open your tunnel. Under **Public hostname**, set the service to `http://web:8080`.
2. Put the tunnel's token in `.env`: `CLOUDFLARE_TUNNEL_TOKEN=…`
3. Start everything: `./joyshare start`. The script sees the token and runs the tunnel together with the app.
4. If you were running `cloudflared` as a separate container before, remove that one, so only one copy is connected.

**Shortcut if you already have a device signed in at `localhost`:** open **Devices → Add a device** there. The QR code, the typed code and the link it shows all lead to the main address, so scanning it with your phone registers the phone on the domain. To register the same computer on the domain, open the link shown under the code.

**3. Register your devices on the new address.** A passkey made at `localhost` does not work on the domain, and the other way round. On the server run `./joyshare setup-code`, open the domain on your phone or computer, type the code and confirm with Face ID or Touch ID. After the first one, add more from **Devices → Add a device**.

**The server itself can still open the app at `http://localhost:8080`** with a passkey made there. That is a way back in if the domain or tunnel is down. To allow other addresses, set `JOYSHARE_EXTRA_ORIGINS` in `.env`.

Before sharing videos through the domain, turn on R2 storage (below): Cloudflare's rules don't allow video through the tunnel itself.

## Sharing only part of a video

Two ways to make a clip:

- **Before making the file:** on the size step, tick **✂️ Just a clip of the video** and give a Start and an End, written as minutes:seconds (`1:30`). The sizes shown shrink to match the part. A video that is too big to share whole can often still be shared as a part.
- **After making the file:** drag the handles under the finished video (or press **Start here** and **End here** while it plays), check it with **▶ Play the clip**, then **Make this clip**.

Both places have a timeline with two handles: drag them to where the clip starts and ends (on the finished video the picture follows the handle). **▶ Play the clip** plays just that stretch and stops at the end handle.

A clip starts and ends exactly where you asked, and must be at least 1 second long. A clip made from a finished video is cut from that file, so the video is never fetched from the platform again; the same goes for a clip of a clip.

## Getting a link again

The **Recent** list on the main screen comes in two layouts, switched with the two icons beside its heading. The choice is saved to your account, so it follows you to other devices.

- **List:** short rows with the picture, title and details. Tap a row to open it in place: **Send or save**, **Copy link**, **✂️ Clip** (opens the video with the clip timeline) and **⬇️ Download**.
- **Pictures:** a grid like the Photos app. **↗** on a picture sends it; tapping the picture opens the video with every option.

**Copy link** says **✓ Copied** when it worked, and a line under the video confirms it. It gives the same link while it still has time left, or a fresh one if the old one ran out. If the file itself has expired, **Make again** creates it again with the same size and part.

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
| Overview | A red warning if a second copy of the app is answering at your address. Videos in the last day and week, what's in progress, files kept, active links, disk use, whether the worker is running, the yt-dlp version. The **Pause new videos** button is here. |
| Videos | Everyone's videos, newest first, with a filter. Failed ones show the reason. |
| Share links | Every link that still works, with its views. **Revoke** makes one stop working right away. |
| People | Invite a person, or turn a person off and on. |
| Limits | Biggest file, longest video, how long things are kept, disk alert levels, which platforms are allowed. Changes apply right away. |
| Alerts | Where alerts go and which ones you want. |
| Storage | Serve finished videos from this server or from Cloudflare R2, with the setup steps and a connection test. |
| System | The yt-dlp version in use, checking for updates, going back a version, the daily platform checks (you choose which platforms and their test videos), and backups. |
| Activity log | Sign-in problems and every change to devices, people, links and settings, in plain sentences: what happened, when, who did it and the details. |

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

**Moving to another computer:** follow [MOVING-MAC.md](MOVING-MAC.md) (another Mac) or [MOVING-LINUX.md](MOVING-LINUX.md) (a Linux cloud server). In short: back up, retire the old computer, copy the backup file and `.env`, restore on the new one.

Keep your `.env` with your backups. If you set `JOYSHARE_SECRET`, connected accounts in a backup can only be read with that same secret.

### Turn on alerts

1. Install the free **ntfy** app on your phone.
2. In the app, subscribe to a topic. Make the name long and hard to guess, because anyone who knows it can read your alerts.
3. In joyshare, open **Admin panel → Alerts**, type the same topic and press **Save and send a test alert**. Your phone should buzz.
4. Tick the alerts you want: a video is ready, a video fails, the disk is filling up, a device is added, repeated failed sign-ins.

Leave the topic empty to turn alerts off. If you run your own ntfy server, put its address and access token in the same tab.

## Making it easy on a phone

The app has a **How it works** page in the ☰ menu that explains all of this to the people you invite.

- **Send or save.** On a phone the finished video shows one big button. It opens the phone's own share sheet: pick WhatsApp or Messages to send the real video, or **Save Video** to keep it in Photos. Download and the link are under **More options**. (On an iPhone, Download puts the file in the Files app, which is rarely what people want.)
- **Sizes.** After a link is looked up you pick a size and press **Do it!**. To skip that step, tick **Always make this size and skip this step** under the sizes, or press the pencil and choose under **Sizes**: easy to send (under 25 MB), best quality, 720p, 480p or audio only. If a video doesn't come in your size, you get one that's easy to send. **Another size** on the finished screen always shows every size.
- **Link cards.** A share link pasted into WhatsApp or iMessage shows the video's picture, title, who made it and how long it is. WhatsApp only plays videos inside the chat for a few partners such as YouTube; a link from here opens the page, where the video plays.
- **The simple iPhone Shortcut.** Opening `https://your-domain/#url=` followed by a video's link looks that link up at once. The How it works page has the five steps to make a Shortcut that does this from any app's Share button. It needs no access token: it uses the Safari sign-in.

## Reloading the app on a phone

Safari pulls down to reload, but an app added to the home screen has no address bar and no pull-to-reload of its own. vidshare adds it: **pull down from the very top of the page and let go** when the round arrow turns solid. You come back to the video you were looking at.

When the app was updated on the server while it stayed open on your phone, a bar at the bottom says **A new version of the app is ready** with a **Reload** button. It checks each time you come back to the app after half a minute or more away, and the Recent list refreshes then too.

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
./joyshare setup-code
```

It registers a new device for the admin, works once and lasts 30 minutes. Only someone with access to the server can run it.

## Everyday commands

| I want to… | Command |
|---|---|
| Start joyshare, or apply a change in `.env` | `./joyshare start` |
| Stop it (data is kept) | `./joyshare stop` |
| Stop and start again | `./joyshare restart` |
| Update after getting new code | `git pull` then `./joyshare update` |
| See what is running and whether it's healthy | `./joyshare status` |
| See what it's doing | `./joyshare logs` |
| See only the downloads and converting | `./joyshare logs worker` |
| Run the tests | `./joyshare test` |
| Stop for good on this computer because it moved | `./joyshare retire` |

Everything joyshare runs is defined in one file, `docker-compose.yml`: the app (`web` and `worker`), plus two optional containers that the script turns on from what is in `.env`:

- **`tunnel`**, the Cloudflare Tunnel, when `CLOUDFLARE_TUNNEL_TOKEN` is set.
- **`caddy`**, a web server with automatic https for a server without Cloudflare, when `JOYSHARE_DOMAIN` is set. See [MOVING-LINUX.md](MOVING-LINUX.md).

Plain `docker compose` commands still work for the app itself, but they don't know about the optional containers unless you add `--profile tunnel` or `--profile caddy`. The script is the simpler way.

## Settings

These live in a file called `.env` in the joyshare folder on your computer, next to `docker-compose.yml`. It is not inside the container: Docker reads it when the containers start. All settings are optional.

To change one, for example the name:

1. If there is no `.env` yet, make it from the example: `cp .env.example .env`
2. Open `.env` in any text editor and set the line, for example `JOYSHARE_NAME=vidshare`
3. Restart so the containers pick it up: `./joyshare start`

`JOYSHARE_NAME` is the name people see until they pick their own with the pencil button. A name someone already chose for themselves stays as they set it.

| Setting | What it does | Default |
|---|---|---|
| `JOYSHARE_PORT` | The port on your computer | `8080` |
| `JOYSHARE_PUBLIC_URL` | The address people use to reach joyshare. Share links and passkeys are tied to it. | `http://localhost:8080` |
| `JOYSHARE_NAME` | The name shown at the top until a person picks their own | `vidshare` |
| `JOYSHARE_EXTRA_ORIGINS` | Other addresses the app may be opened at, separated by commas | `http://localhost:8080` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Your tunnel's token. With it set, `./joyshare start` runs the tunnel too. | none |
| `JOYSHARE_DOMAIN` | Your domain, without `https://`. With it set, `./joyshare start` runs the Caddy web server on ports 80 and 443. Only for servers without Cloudflare. | none |
| `JOYSHARE_SECRET` | Long random text used to encrypt connected accounts | made automatically |
| `JOYSHARE_BIND` | Who can reach joyshare directly. `127.0.0.1` means only this computer. | `127.0.0.1` |

Limits such as the 200 MB maximum, how long files are kept (originals 1 hour, finished files and share links 48 hours) and the disk alert levels are changed in **Admin panel → Limits**.

## Where your data lives

Everything (the database and the videos) is in one Docker volume called `joyshare_joyshare_data`.

- It survives restarts, rebuilds and `docker compose down`.
- `docker compose down -v` **deletes it**. Only use `-v` when you want to start from nothing.
- Why a volume and not a normal folder: on a Mac, a database inside a shared folder can become unreliable when two containers use it at once. A volume avoids that. `./joyshare backup` packs it into a single file you can copy anywhere.

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

**"A second copy is running" (alert, or a red warning on the Overview tab)**
joyshare is running on two computers that answer at the same address, usually after a move. People look signed out at random and videos go missing. On the computer that should no longer run it: `./joyshare retire`. More in [MOVING-MAC.md](MOVING-MAC.md).

**The page doesn't load**
Run `./joyshare status`. Both `web` and `worker` should say "Up". If not, `./joyshare logs web` shows why. If port 8080 is taken by another app, set `JOYSHARE_PORT=8081` in `.env` and start again.

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
