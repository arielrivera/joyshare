# Watching joyshare from outside: Uptime Kuma

joyshare can tell you about problems it notices itself (a platform breaking, a failed update, a full disk). It can't tell you when it's down: when the Mac mini is off, your home internet is out, or the Cloudflare Tunnel stopped. For that you need a watcher somewhere else. This guide sets up [Uptime Kuma](https://github.com/louislam/uptime-kuma) on a small DigitalOcean droplet, checking joyshare every minute and sending an ntfy alert to your phone when it stops answering.

Plan for about 20 minutes. Everything for the droplet lives in the [`monitor/`](../monitor) folder: `compose.yml` (the container) and `kuma` (the one script to set up, run, update and back it up).

## What you need

- A **DigitalOcean droplet** running **Ubuntu** (24.04 or newer). The smallest size is plenty: Kuma uses about 150 MB of memory.
- To sign in to it with **SSH** from your Mac (DigitalOcean sets that up when you create the droplet with your SSH key).
- Your **ntfy topic** (the one in joyshare's Admin → Alerts), or a new one just for "site down" alerts.

## 1. Put the files on the droplet

From the joyshare folder on your Mac:

```bash
scp -r monitor root@YOUR_DROPLET_IP:~/
```

(If the GitHub repository is public, `git clone https://github.com/arielrivera/joyshare.git` on the droplet works too; then use `~/joyshare/monitor` below.)

## 2. Set it up

Sign in to the droplet and run the setup:

```bash
ssh root@YOUR_DROPLET_IP
```

```bash
cd ~/monitor && sudo ./kuma setup
```

That one command:

1. Installs **Docker** (from get.docker.com) if it isn't there, and makes it **start with the system**.
2. Turns on the **firewall** with only SSH open. The dashboard isn't reachable from the internet at all (see step 3).
3. Makes sure Ubuntu installs **security updates by itself** (`unattended-upgrades`).
4. Starts **Uptime Kuma** with a restart rule, so it comes back after a crash or a reboot.
5. Schedules a **daily backup** (04:00) and a **weekly update** (Sunday 05:00), in server time.

Running it again is safe: it only fixes what's missing.

## 3. Open the dashboard

The dashboard only listens on the droplet itself, so strangers can't even find its login page. You reach it through your SSH connection. On your **Mac**:

```bash
ssh -L 3001:localhost:3001 root@YOUR_DROPLET_IP
```

Leave that window open and go to http://localhost:3001. (`./kuma tunnel` on the droplet prints this command with the right address.)

The first time, Kuma asks which database to use: pick the built-in **SQLite**. Then create your Kuma user. This is Kuma's own sign-in, separate from joyshare's passkeys.

## 4. Watch joyshare

**Add New Monitor**:

| Field | Value |
|---|---|
| Monitor Type | **HTTP(s) - Keyword** |
| Friendly Name | joyshare |
| URL | `https://vids.arielrivera.app/api/health` |
| Keyword | `"worker_alive":true` |
| Heartbeat Interval | 60 seconds |
| Retries | 2 (so one slow answer doesn't wake you) |

Why the keyword: the health page answers as long as the web part runs, and it also says whether the **worker** (the part that makes the videos) is alive. Checking for `"worker_alive":true` catches both "the site is down" and "the site is up but nothing gets made". Open the URL in your browser once to see it says `true` right now.

## 5. Get the alert on your phone

**Settings → Notifications → Setup Notification**:

| Field | Value |
|---|---|
| Notification Type | **ntfy** |
| Server URL | `https://ntfy.sh` |
| Topic | your topic |
| Priority | 4 or 5, so it stands out from "video ready" alerts |

Tick **Default enabled** and **Apply on all existing monitors**, press **Test**, and check your phone. Kuma also tells you when the site is back up.

## 6. Keeping it running

Run these on the droplet, from `~/monitor`:

| Command | What it does |
|---|---|
| `./kuma status` | Running or not, the version, whether it starts with the system, the last backup |
| `./kuma logs` | What Kuma is doing (Ctrl+C to leave) |
| `./kuma start` / `stop` / `restart` | As it says. Monitors and history are kept. |
| `./kuma update` | Backs up, gets the newest Kuma 2.x, restarts with it, removes the old image |
| `./kuma backup` | Saves everything to `~/monitor/backups` (the newest 14 are kept) |
| `./kuma restore FILE` | Puts a backup back (asks first) |
| `sudo ./kuma schedule on` / `off` | Turns the daily backup and weekly update on or off |

### Starting with the system

Nothing extra to do after setup: Docker is a system service that starts at boot, and Kuma's container has the rule `restart: unless-stopped`, so Docker starts it again. The one exception is on purpose: after `./kuma stop` it stays stopped, even across a reboot, until `./kuma start`. Check with `./kuma status`, or try it once with `sudo reboot` and look again a minute later.

### Updates

- **Kuma**: updated every Sunday by the schedule, always within version 2 (a future version 3 could change things, so moving to it is a choice you make by editing `KUMA_TAG` in `compose.yml`). A backup is made right before each update.
- **Ubuntu**: security updates install by themselves. Some need a restart; when `ssh` greets you with "System restart required", run `sudo reboot` at a quiet time. Kuma comes back on its own.
- **Bigger Ubuntu upgrades** (a new release every two years): `sudo do-release-upgrade`, after a `./kuma backup`.

### Backups

The daily backup pauses Kuma for a few seconds while it copies the database, so one check may be skipped. Backups stay on the droplet; to keep a copy off it, from your **Mac**:

```bash
scp "root@YOUR_DROPLET_IP:~/monitor/backups/kuma-*.tar.gz" ~/Downloads/
```

DigitalOcean's own droplet backups (a paid option) also cover it.

### Moving to a new droplet, or starting over

1. On the old droplet: `./kuma backup`, then copy the newest file to your Mac (above).
2. Create the new droplet and do steps 1 and 2 of this guide there.
3. Copy the backup up: `scp ~/Downloads/kuma-….tar.gz root@NEW_IP:~/monitor/backups/`
4. On the new droplet: `./kuma restore backups/kuma-….tar.gz`

Every monitor, notification, user and the history come back. Delete the old droplet afterwards, or you get every alert twice.

## If something is off

| You see | Try |
|---|---|
| `Docker isn't installed yet` | `sudo ./kuma setup` |
| `permission denied ... docker.sock` | Run as root, or add your user to the `docker` group: `sudo usermod -aG docker $USER`, then sign in again |
| http://localhost:3001 doesn't open | The `ssh -L` window must stay open. Check Kuma runs: `./kuma status` |
| Alerts every few minutes, but the site works | Raise Retries to 3, or check that joyshare's health page shows `"worker_alive":true` |
| The monitor says the keyword is missing | Open the health URL in a browser: if it says `false`, joyshare's worker is down (`./joyshare status` on the Mac mini) |
| No alert arrived on the test | Check the topic matches the one the ntfy app subscribes to |
