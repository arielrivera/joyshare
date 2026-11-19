# Moving joyshare to another Mac

For example from the computer you tried it on to a Mac that stays on as your joyshare server. Plan for about 15 minutes, with the site down for a few of them.

See the whole picture first: [infographic](https://claude.ai/artifact/4xiMLuHT4FMxgrjYRsVFKD) · [project plan](https://claude.ai/artifact/Y8hfga81tr1HFhsTYAk9ya) · Moving to a Linux server instead? See [MOVING-LINUX.md](MOVING-LINUX.md).

> **Done for real once**, from one Mac to another, with everyone staying signed in. If a step doesn't match what you see, tell me what the screen shows.

## What moves and what doesn't

| Moves with the backup | Stays behind or is made again |
|---|---|
| People, their devices (passkeys) and roles | Videos, unless you ask for them. They are temporary anyway. |
| Settings, limits, alerts, R2 details | The yt-dlp copy: the new Mac downloads it again |
| History, share links, connected accounts | |

**Nobody has to register again.** Passkeys are tied to the address (`https://your-domain`), not to the computer. Same address, same data: every device keeps working.

Two files travel: the backup file and your `.env`. The `.env` holds your address, the tunnel token and the secret that unlocks connected accounts. Without the same `JOYSHARE_SECRET`, connected accounts and the R2 secret can't be read on the new Mac.

## Before you start, on the new Mac

1. Install **Docker Desktop** and open it once. In its settings turn on **Start Docker Desktop when you sign in**.
2. Get the code:

```bash
git clone https://github.com/arielrivera/joyshare.git
```

## Step 1. Old Mac: make the backup

In the joyshare folder:

```bash
./joyshare backup
```

It stops the app for a few seconds and writes one file into `backups/`. Add `--with-videos` if you want the current videos to come along.

## Step 2. Old Mac: retire it

```bash
./joyshare retire
```

This stops everything on the old Mac and keeps it stopped, even after a restart. Nothing is deleted. **Do this before starting the new Mac**, so two copies never run at once (see "If you forget to stop the old one" below).

If your Cloudflare Tunnel runs as a separate container (not started by `./joyshare`), stop that one too:

```bash
docker ps --filter ancestor=cloudflare/cloudflared
```

then `docker rm -f` followed by the name it shows.

## Step 3. Copy two files to the new Mac

Copy these into the joyshare folder on the new Mac, by AirDrop, a USB stick or a shared folder:

- `backups/joyshare-backup-….tar.gz`
- `.env` (it is a hidden file: in Finder press **Cmd + Shift + .** to see it)

## Step 4. New Mac: put the tunnel in `.env`

So the tunnel moves together with the app from now on, add your tunnel's token to `.env` if it isn't there yet:

```
CLOUDFLARE_TUNNEL_TOKEN=…your token…
```

In the Cloudflare dashboard (Zero Trust → Networks → Tunnels → your tunnel → Public hostname), the service must be `http://web:8080`.

## Step 5. New Mac: restore and start

```bash
./joyshare restore backups/joyshare-backup-….tar.gz
```

Type `yes` when asked. The first time it builds the app, which takes a few minutes. Then it starts everything, including the tunnel.

## Step 6. Check

```bash
./joyshare status
```

- **Website: answering** and **Worker: running**.
- Open your address on your phone. You should still be signed in, or sign in with your passkey as usual.
- Download one short video.
- **Admin panel → Overview** shows no red warning about a second copy.

## Keep the new Mac running

- **System Settings → Energy**: turn on **Prevent automatic sleeping when the display is off** and **Start up automatically after a power failure**.
- Docker Desktop only starts after someone signs in to the Mac. If the Mac restarts by itself (a power cut, an update), joyshare is down until you sign in. Automatic login fixes that, but macOS doesn't allow automatic login while FileVault is on. Pick one: FileVault off with automatic login, or FileVault on and you sign in after a restart.
- Uptime Kuma will tell you when the site is down ([UPTIME-KUMA.md](UPTIME-KUMA.md)).

## If you forget to stop the old one

With the same tunnel token on both Macs, Cloudflare treats them as two doors to the same site and sends each request through either one. What you would see:

- **Signed in, then signed out, then in again.** Sign-ins made after the move exist on one Mac only.
- **Videos that vanish.** A video made on one Mac is "not found" when the next request lands on the other. Share links work only some of the time.
- **Doubled alerts and doubled daily checks**, and both Macs writing backups to the same R2 bucket.
- **When the old Mac sleeps**, the requests sent its way fail or hang.

Nothing is destroyed: each Mac only deletes its own videos. Stopping the old one fixes it.

**How joyshare helps:**

- **It notices.** Every 10 minutes each copy asks your public address who is answering. If the answer comes from a different copy, you get an urgent alert on your phone ("A second copy is running") and a red warning on **Admin panel → Overview**.
- **`./joyshare retire`** on the old Mac stops it and refuses to start it again by accident. `./joyshare unretire` undoes that.
- **`./joyshare status` and `start`** warn when a second tunnel container is running on the same Mac.

To fix it at any time: on the old Mac run `./joyshare retire`. If you can't reach the old Mac, open the Cloudflare dashboard, create a new token for the tunnel (this disconnects every computer using the old token), and put the new token in the new Mac's `.env`, then `./joyshare restart`.

## Going back

The old Mac still has its data from the day you moved. To return to it: `./joyshare backup` on the new Mac, `./joyshare retire` there, then on the old Mac `./joyshare unretire` and `./joyshare restore` with the new backup file.
