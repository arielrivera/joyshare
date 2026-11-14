# Moving joyshare to a Linux cloud server

For example a droplet at DigitalOcean or a server at Hetzner. Plan for about 30 minutes.

See the whole picture first: [infographic](https://claude.ai/artifact/4xiMLuHT4FMxgrjYRsVFKD) · [project plan](https://claude.ai/artifact/Y8hfga81tr1HFhsTYAk9ya) · Moving to another Mac instead? See [MOVING-MAC.md](MOVING-MAC.md).

> **Not yet done for real.** The web server container was started in front of the app and passed requests through correctly. Getting a real certificate on a real server has not been tried yet. If a step doesn't match what you see, tell me what the screen shows.

## First, a warning about cloud servers

Video platforms block many cloud providers' addresses, YouTube most of all. A home connection (the Mac mini) is trusted far more. If downloads start failing with "sign in to confirm you're not a bot" after the move, that is why. Connected accounts help for some platforms.

## Choose how people reach the server

| | A. Keep the Cloudflare Tunnel | B. Web server on the machine (Caddy) |
|---|---|---|
| Open ports | None | 80 and 443 |
| https certificate | Cloudflare's | Caddy gets and renews it by itself |
| Videos | Must be served from R2 (Cloudflare's rules) | Can be served from the server's own disk |
| Setup | Same as on the Mac: one token in `.env` | One line in `.env`, plus a DNS record |
| Pick it when | You want the least exposed server | You are leaving Cloudflare, or don't want R2 |

Both are built in. You choose by what you put in `.env`.

## Step 1. Prepare the server

A small server is enough to start: 2 GB of memory, 2 processors, 40 GB of disk. Ubuntu 24.04 is a good choice. Converting video is the slow part; more processors make it faster.

Sign in to the server and install Docker and git:

```bash
curl -fsSL https://get.docker.com | sudo sh
```

```bash
sudo usermod -aG docker $USER
```

Sign out and in again so the second command takes effect. Then get the code:

```bash
git clone https://github.com/arielrivera/joyshare.git
```

## Step 2. Old computer: back up, then retire

```bash
./joyshare backup
```

```bash
./joyshare retire
```

`retire` stops the old computer and keeps it stopped, so two copies never run at once. If your Cloudflare Tunnel runs as a separate container there, remove that one too.

## Step 3. Copy two files to the server

From the old computer, with your server's address in place of `SERVER`:

```bash
scp backups/joyshare-backup-*.tar.gz .env SERVER:joyshare/
```

Then, on the server, move the backup into place:

```bash
cd joyshare && mkdir -p backups && mv joyshare-backup-*.tar.gz backups/
```

## Step 4. Set up the way in

Edit `.env` on the server (`nano .env`).

### A. With the Cloudflare Tunnel

Keep `JOYSHARE_PUBLIC_URL` as it is, and make sure the token is there:

```
CLOUDFLARE_TUNNEL_TOKEN=…your token…
```

In the Cloudflare dashboard the tunnel's public hostname must point to `http://web:8080`. Leave R2 on. No firewall changes are needed.

### B. With the web server (Caddy)

1. Remove the `CLOUDFLARE_TUNNEL_TOKEN` line.
2. Add your domain, without `https://`:

```
JOYSHARE_DOMAIN=vids.example.com
```

3. Keep `JOYSHARE_PUBLIC_URL=https://vids.example.com` (the same name with `https://`).
4. **DNS:** at your domain's DNS, make an `A` record for that name pointing to the server's IP address. Remove the tunnel's record for the same name first. If the DNS is at Cloudflare, set the record to **DNS only** (grey cloud). With the orange cloud on, traffic still passes through Cloudflare and the rule about video applies again, so keep R2 on in that case.
5. **Firewall:** allow ports 80 and 443, here and in your provider's firewall if it has one:

```bash
sudo ufw allow 22,80,443/tcp && sudo ufw allow 443/udp && sudo ufw enable
```

A cloud server has a fixed address, so nothing else is needed. At home without Cloudflare you would also need dynamic DNS and port forwarding on the router.

With this choice you may switch **Admin panel → Storage** back to "this server". R2 keeps working too, if you prefer it.

## Step 5. Restore and start

```bash
./joyshare restore backups/joyshare-backup-….tar.gz
```

Type `yes`. The first time it builds the app (a few minutes), then starts everything named in `.env`. With choice B, Caddy asks for the certificate on the first start; that takes up to a minute and needs the DNS record from step 4 to be working.

## Step 6. Check

```bash
./joyshare status
```

- **Website: answering**, **Worker: running**, and `tunnel` or `caddy` in the list.
- Open your address on your phone. Nobody has to register again: passkeys are tied to the address, not the computer.
- Download one short video from each platform you use. This is where a cloud address shows its limits.
- If the certificate didn't arrive: `./joyshare logs caddy` says why. The usual cause is the DNS record not pointing at the server yet.

The server starts joyshare by itself after a restart. Nothing to configure.

## If you forget to stop the old computer

- **With the tunnel on both:** Cloudflare sends each request to either computer. People look signed out at random and videos go missing. joyshare notices within 10 minutes, sends an urgent alert and shows a red warning on **Admin panel → Overview**. Run `./joyshare retire` on the old one.
- **With Caddy on the server and the tunnel still on the old computer:** whichever the DNS record points to wins. The other copy sees a different one answering at the address, and alerts the same way.

More detail: [MOVING-MAC.md](MOVING-MAC.md), "If you forget to stop the old one".

## If the address changes

Passkeys only work on the address they were made for. With a new domain, set `JOYSHARE_PUBLIC_URL` (and `JOYSHARE_DOMAIN`), run `./joyshare restart`, then `./joyshare setup-code` and register each device again on the new address.
