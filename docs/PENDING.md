# What's still pending

A short summary of everything left. The full checklist with technical detail is in [ROADMAP.md](ROADMAP.md).

Last updated: 13 Nov 2026 (after the moving guides and the one-script controls).

## 1. Things only you can do

| What | Why | Where the steps are |
|---|---|---|
| **Move the tunnel into the app's network** | Your `cloudflared` runs as a separate container reaching the app through the host. Put `CLOUDFLARE_TUNNEL_TOKEN` in `.env`, set the tunnel's service to `http://web:8080`, run `./joyshare start`, and remove the separate container. Then the tunnel starts, stops and moves together with the app. | [SETUP.md](SETUP.md), "Going live", step 2 |
| **Set up Cloudflare R2** (create a bucket and an access key) | So videos are served from Cloudflare's storage and never pass through the tunnel. Cloudflare's rules don't allow video through the tunnel itself. Also gives backups a safe place off the machine. | [R2.md](R2.md), a step-by-step guide |
| **Install the ntfy app and choose a topic** | So alerts reach your phone. | [SETUP.md](SETUP.md), "Turn on alerts" |
| **Set `JOYSHARE_SECRET` in `.env`** | Stronger protection for connected accounts and the R2 secret. Do it before anyone uploads a cookie file. Keep a copy of it somewhere safe. | [SETUP.md](SETUP.md), "Settings" |
| **Connect your accounts** (cookie files, ideally from spare accounts) | Instagram, and some videos elsewhere, are only shown to signed-in accounts. | App: ☰ → Connected accounts |
| **Create the DigitalOcean droplet for Uptime Kuma** | To be told when the Mac mini is down. | Go-live phase |
| **Decide the Mac mini's restart behavior** | Docker on a Mac starts only after login, and FileVault blocks automatic login after a power cut. | Go-live phase |

## 2. Still to build

| What | Size | Notes |
|---|---|---|
| **Go live on the Mac mini** | Medium | The steps are written: [MOVING-MAC.md](MOVING-MAC.md). Nobody has to register again. Still to build: Uptime Kuma and a troubleshooting guide. |
| **Clips from very long videos** | Small | Clips are built. What's left: fetching only the part, so a video over the download limit can be clipped too. |
| **More progress scenes** | Small each | Seven are built: Demolition, Compressor, Voyage, Rocket, Black hole, Dominoes, Abduction, plus two calm ones. Scenes with ready-made 3D models (free CC0 packs such as Kenney or Quaternius) would need a model loader added. |
| **Alerts per person** | Medium | Today every alert goes to the admin's ntfy topic. Members should get their own "video ready" and "account stopped working". |
| **Platforms tab** | Small | An optional proxy per platform, for when a platform blocks your address. |
| **Pictures in the cookie how-to** | Small | The steps are text only. |
| **More looks** | Small each | Eleven are built. Earlier sketches not built: chrome, arcade, deco, lava glass, notebook, receipt, graffiti. |

## 3. Decisions waiting for you

**A second engine besides yt-dlp**

- *Why it could matter:* joyshare depends entirely on yt-dlp. If a yt-dlp release is broken for a platform, that platform stops until the fix arrives.
- *Why it's probably not urgent:* yt-dlp is very actively maintained and usually fixes breakage within days. joyshare already checks for updates daily, tests a new version before using it, can go back a version, and tells you when a platform breaks. And when a platform blocks everyone, a second engine is blocked too: it only helps against yt-dlp's own bugs.
- *Options, smallest first:* let the updater fall back to yt-dlp's nightly builds; add `gallery-dl` as a backup for X and Instagram; run a self-hosted `cobalt` container as a full second engine.
- *Suggestion:* add the nightly fallback when convenient, and anything bigger only if yt-dlp actually lets you down.

**Podman instead of Docker**

- *It would work.* Podman runs the same images and reads the same compose file, and the `joyshare` script already accepts `JOYSHARE_COMPOSE="podman compose"`.
- *For:* no background service running as root, no Docker Desktop to license or keep logged in, and on Linux it ties in neatly with the system's own service manager.
- *Against:* on a Mac it still needs a small virtual machine, the same as Docker. Its compose support is less polished. And joyshare relies on containers being restarted automatically (after a yt-dlp update the app stops itself and expects to be started again), which Docker does out of the box and Podman needs extra setup for.
- *Suggestion:* stay on Docker for the Mac mini, where it already works. Revisit if you move to a Linux server or a Raspberry Pi. Nothing has been tested on Podman yet.

**SvelteKit or plain HTML/CSS/JavaScript**

- The interface is plain files today and works well. Moving to SvelteKit would add a build step. Suggestion: stay as is unless the 3D scenes make the code hard to manage.

**Cloudflare Access in front of the admin panel**

- Skipped for launch. It would add an emailed code before anyone can even reach the admin screens. Worth revisiting after go-live if the logs show strangers probing.

## 4. If you ever stop using Cloudflare

The Cloudflare Tunnel does the job of a web server today. A web server is now built in for the day you leave: set `JOYSHARE_DOMAIN` in `.env` and `./joyshare start` runs Caddy in front of the app. The steps are in [MOVING-LINUX.md](MOVING-LINUX.md). Without Cloudflare you need three things:

1. **A web server for HTTPS.** Built in (Caddy). It gets and renews the certificate.
2. **A way for the internet to find the machine:** a fixed IP address, or dynamic DNS that updates when the address changes.
3. **Open ports** (80 and 443) on the router or firewall, forwarded to the machine.

The first thing lost is the protection of having no open ports. R2 (or any S3-compatible storage) keeps working without the tunnel.

## 5. Built but not yet proven in real conditions

| What | What's missing |
|---|---|
| **The Share button and the iPhone Shortcut** | Passkeys on the domain are confirmed (iPhone and Mac). The phone's Share button and the Shortcut can now be tried, and haven't been yet. |
| **R2 storage** | Proven against a stand-in, not real Cloudflare R2. Check the download file name, the two bucket rules and the Share button with files in R2. |
| **Moving to another computer** | Backup and restore were run on one computer. A full move between two machines hasn't been done. The Caddy web server passed requests through in a test, but has never fetched a real certificate. |
| **Clips** | One real clip was made from an X video. "Start here / End here" was tried with a desktop browser, not on a phone. |
| **New scenes and the look-up animation** | Confirmed to draw in every state by reading pixels. Nobody has watched them yet. |
| **Recent list layouts** | List and Pictures were viewed in Zine, Midnight and Nordic at phone size, with a stand-in share sheet. Not yet on a real phone. |
| **The clip timeline on a phone** | Dragging was checked with the keyboard in a desktop browser, not with a finger on a real phone. |
| **The phone flow** | "Send or save", sharing from the Recent list and the link card were checked in a desktop browser at phone size with a stand-in share sheet. On a real iPhone: try Send or save, Save Video, a link pasted into WhatsApp, and building the Shortcut from the How it works page. |
| **Second-copy warning** | Covered by automated tests, and the check reaches the real domain. Two real copies have never been run at once to watch it fire. |
| **Alerts** | Never sent to the real ntfy service. No topic is set yet. |
| **Connected accounts** | Never tried against a real sign-in wall with a real cookie file. |
| **A real yt-dlp update arriving** | The installed version has been the newest all along. The install, test, switch and go-back steps were each run for real. |
| **Cloud copy of backups** | Needs R2. The local daily backup and both restore commands were run for real. |
| **Facebook** | No link tried. Instagram worked once. TikTok worked for one public video and was refused for another. |
| **3D scenes on a phone** | Viewed on the laptop only. Also unseen: a phone's real "Reduce motion" setting switching to the calm scenes. |
| **Home-screen install** | Needs the `https://` address to try on a phone. |
| **The looks** | Most screens were only viewed in one or two looks. Windows 95 and Clay are the likeliest to need touch-ups. The six classic looks were each viewed on the main screen only, plus one or two other screens. |
| **Expiry after 1 hour and 48 hours** | Covered by automated tests only. |
