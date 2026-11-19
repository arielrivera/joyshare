# Troubleshooting

What to do when joyshare is down or something misbehaves. Start with the section that matches what you see. Commands run on the joyshare server, in the joyshare folder.

See also: [setup guide](SETUP.md) · [moving guides](MOVING-MAC.md) · [Uptime Kuma](UPTIME-KUMA.md) · the [architecture diagrams](../README.md#how-it-fits-together) show which part does what.

**Contents**

1. [The site is down](#1-the-site-is-down)
2. [After a restart or a power cut](#2-after-a-restart-or-a-power-cut)
3. [An alert arrived](#3-an-alert-arrived)
4. [Videos and platforms](#4-videos-and-platforms)
5. [Signing in](#5-signing-in)
6. [Updates](#6-updates)
7. [Putting data back](#7-putting-data-back)
8. [Asking for help](#8-asking-for-help)

## 1. The site is down

Work from the outside in: first what your phone shows, then what the server says.

### Step 1: what does the page show?

Open your address on your phone, ideally on mobile data (so your own Wi-Fi isn't the problem).

| You see | It means | Go to |
|---|---|---|
| A Cloudflare page with **Error 1033** | Cloudflare can't reach the server at all: it's off, offline, or the tunnel isn't running | Step 2 |
| A Cloudflare page with **502 Bad Gateway** | The tunnel is up, but the joyshare app behind it isn't answering | Step 2 |
| The page loads but says the app **can't be reached** | The app is restarting (an update or a restart takes about a minute) | Wait a minute, then Step 2 |
| The page loads, but **videos stay "Waiting in line"** | The website works but the worker (the part that makes videos) isn't running | Step 2 |
| **New videos are paused** | An admin paused them, or the disk is almost full | [Disk alerts](#3-an-alert-arrived) |
| Everything works from the phone, not from one computer | That computer's network or browser | Try another browser or a private window |

To see the same thing as Uptime Kuma, open `https://your-address/api/health`. A healthy server answers with `"ok":true` and `"worker_alive":true`.

### Step 2: ask the server

```bash
./joyshare status
```

| It says | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Docker isn't running. Mac: open Docker Desktop and wait until it says it's running. Linux: `sudo systemctl start docker`. Then `./joyshare start` |
| `This computer is retired` | On purpose: joyshare was moved to another computer. Only if this one should run it again: `./joyshare unretire`, then `./joyshare start` |
| `web` or `worker` not "Up", or **Website: not running** | `./joyshare start`. If it stops again, look at Step 3 |
| **Website: answering**, **Worker: NOT running** | `./joyshare restart`. If it stays down, look at the worker's log (Step 3) |
| Both fine, but no `tunnel` line, and the site shows Error 1033 | The tunnel isn't running. Check `CLOUDFLARE_TUNNEL_TOKEN` is in `.env`, then `./joyshare start` |
| A warning about **a second tunnel container** | Two tunnels share the token, so visitors are split. Remove the extra one with the `docker rm -f` command it shows |
| Everything is up, but Error 1033 continues | The server's internet connection. Check the computer can open any website |

### Step 3: read the logs

```bash
./joyshare logs web
```

```bash
./joyshare logs worker
```

```bash
./joyshare logs tunnel
```

Each follows the log live; press Ctrl+C to leave. The last lines before a crash usually say why. Common ones:

- **`database is locked`** or **`disk I/O error`**: the disk is full or failing. Check free space (`df -h`), then see [Putting data back](#7-putting-data-back) if the database is damaged.
- **`address already in use`**: another app took port 8080. Set `JOYSHARE_PORT=8081` in `.env` and `./joyshare start`.
- **The tunnel log repeats `Unauthorized` or `token`**: the tunnel token in `.env` is wrong or was replaced in the Cloudflare dashboard. Copy it again from Zero Trust → Networks → Tunnels.

## 2. After a restart or a power cut

joyshare's containers come back by themselves once Docker is running. Whether Docker comes back depends on the computer:

- **Mac:** Docker Desktop starts only after someone signs in to the Mac. After a power cut or an update restart, joyshare stays down until you sign in. Automatic sign-in fixes that, but macOS doesn't allow it while FileVault is on: choose FileVault off with automatic sign-in, or FileVault on and sign in yourself after a restart. Also in **System Settings → Energy**: turn on **Start up automatically after a power failure** and **Prevent automatic sleeping when the display is off**. In Docker Desktop's settings, keep **Start Docker Desktop when you sign in** on.
- **Linux (including a Raspberry Pi or a cloud server):** Docker starts with the system. Check once with `systemctl is-enabled docker`; it should say `enabled`. If not: `sudo systemctl enable --now docker`.

After any restart, `./joyshare status` should show the website answering and the worker running within a couple of minutes. Uptime Kuma sends a "back up" alert when it sees the site again.

## 3. An alert arrived

| Alert | What to do |
|---|---|
| **Uptime Kuma: site down** | [The site is down](#1-the-site-is-down). If it's back up within a few minutes on its own, it was most likely a restart or an update |
| **A second copy is running** | joyshare runs on two computers at the same address, usually after a move. People seem signed out at random and videos go missing. On the computer that shouldn't run it: `./joyshare retire`. More in [MOVING-MAC.md](MOVING-MAC.md) |
| **Disk is filling up** (90%) | Free space on the server. joyshare's own videos are deleted on schedule; look for other large files. The limits are in Admin → Limits |
| **Disk almost full: new videos paused** (95%) | Same as above. New videos start again by themselves once there's room |
| **A platform stopped working** | See [Videos and platforms](#4-videos-and-platforms) |
| **yt-dlp update failed** | Nothing to do right away: the version that worked stays in use. If it happens again with the next release, mention it when asking for help |
| **joyshare update failed** | See [Updates](#6-updates) |
| **Cloud storage upload failed** | A finished video stayed on the server instead of R2, so it still works. Open Admin → Storage and press **Save and test**. Usually the R2 key expired or was deleted: make a new one ([R2.md](R2.md)) |
| **Backup failed** | Admin → System → Backups shows why. Press **Back up now** to try again. If only the cloud copy failed, check R2 as above |
| **Connected account rejected** | That person's cookie file expired. They upload a fresh one under ☰ → Connected accounts |
| **Failed sign-ins** | Someone tried codes or passkeys that didn't work. Once is usually a mistyped code. Many from one address: check Admin → Activity log |
| **New device** | Someone added a device to an account. If it's yours or theirs, nothing to do. If nobody recognizes it, the person removes it under ☰ → Devices, or an admin turns that person off under Admin → People |

## 4. Videos and platforms

**A platform suddenly stops working**
Platforms change often, and yt-dlp releases fixes quickly. joyshare checks for a new yt-dlp once a day, tests it, and switches to it by itself. To check right away: **Admin panel → System → Check for updates now**. If an update made things worse, **Go back to version …** on the same tab undoes it.

The System tab also shows the daily platform checks: a randomly picked test video per platform is looked up at a different time each day, with a second try before an alert.

**YouTube says "Sign in to confirm you're not a bot"**
YouTube is refusing the server's internet address. It happens more on cloud servers, and sometimes on a regular internet connection too. Connect a YouTube account (a spare one is best) under **☰ → Connected accounts**.

**"… only shows this video to signed-in accounts"**
The platform wants a login for that video. Connect an account for that platform under **☰ → Connected accounts**.

**"… didn't accept your connected account"**
The cookies expired or the platform signed that browser out. Export a fresh cookie file and upload it again.

**"No video was found at that link"**
The post may have no video, or it was deleted or made private. Open the link in a browser to check.

**A video sits at "Waiting in line"**
The worker isn't running: `./joyshare status`, then `./joyshare restart`.

**The video is too big**
Pick a smaller size, or cut a clip. The limit per video is in Admin → Limits.

**A share link says it expired**
Share links last 48 hours by default (Admin → Limits). Make the video again and share the new link.

## 5. Signing in

**"That code isn't valid"**
Codes work once and expire (setup code: 24 hours, device codes: 10 minutes). Create a new one. After 10 wrong tries joyshare makes you wait a few minutes.

**"This device already has a passkey for your account"**
Nothing is wrong. Passkeys travel between your own devices through your password manager: one made on your iPhone shows up on your Mac through iCloud Keychain. Skip registering and press **Sign in with a passkey**.

**"The passkey prompt was closed"**
The Face ID or Touch ID window was dismissed or timed out. Press the button again.

**"That passkey isn't registered here"**
The passkey belongs to another address (for example it was made at `localhost` and you're now on the domain), or the device was removed. Register the device again with a new code.

**It keeps asking "Confirm it's you"**
Adding devices, inviting people and creating tokens need a passkey check from the last 10 minutes. That's on purpose.

**Every admin lost their passkeys**
On the server:

```bash
./joyshare setup-code
```

It prints a one-time code. Open your address, choose to register a device, and enter it.

**I'm stuck in "View as member"**
Use **Back to admin** in the bar under the header, or sign out and back in: a new sign-in always starts as admin.

## 6. Updates

**The update helper reported "the tests failed"**
Nothing changed: the running version stays in use, and that version of the code is skipped. The details are in `logs/autoupdate.log` on the server. The next push to GitHub that passes the tests goes live as usual.

**"Videos were still being made after 30 minutes"**
The helper waits for running videos before restarting. It tries again at its next check.

**The update helper reported "failed while starting"**
The new code passed its tests but didn't start. First look at why:

```bash
tail -n 50 logs/autoupdate.log
```

```bash
./joyshare logs web
```

To get back to the version that ran before, turn automatic updates off, go back one version, and rebuild:

```bash
./joyshare autoupdate off
```

```bash
git reset --hard HEAD~1 && ./joyshare update
```

Once the problem is fixed on GitHub, `git pull` and `./joyshare autoupdate on` again.

**The admin panel says the update helper isn't connected**
It isn't running on the server. `./joyshare autoupdate status` shows why. On a Mac it can't run while the joyshare folder is in Documents, Desktop, Downloads or iCloud Drive (the message explains how to move it).

**The page looks half-updated after an update**
Scripts and styles get a new address with every update, so this shouldn't happen. If you ever see it, reload the page once.

## 7. Putting data back

joyshare backs up its database every day: people, devices, settings, history and connected accounts. Videos aren't backed up; they're temporary anyway.

**Just the database** (for example after a `database disk image is malformed` error). The daily snapshots are inside joyshare's data. List them and copy the newest one out:

```bash
docker compose exec web ls -lt /data/backups
```

```bash
docker compose cp web:/data/backups/FILE.db.gz backups/
```

Then put it back (it asks first, and doesn't touch videos):

```bash
./joyshare restore-db backups/FILE.db.gz
```

If the server's disk itself is gone, the same snapshots are in your R2 bucket under `backups/`: download one from the Cloudflare dashboard and use the same command.

**Everything** (a full backup made with `./joyshare backup`, for example when moving):

```bash
./joyshare restore backups/joyshare-backup-FILE.tar.gz
```

Connected accounts and the R2 secret in a backup can only be read with the same `JOYSHARE_SECRET` in `.env`. Keep a copy of your `.env` somewhere safe.

## 8. Asking for help

Send these, and say what you expected and what happened instead:

```bash
./joyshare status
```

```bash
docker compose logs --tail 80 web worker
```

For update problems, also `tail -n 80 logs/autoupdate.log`. Before sending, check the output for anything private: logs don't contain passwords or tokens, but they can contain video links and people's names.
