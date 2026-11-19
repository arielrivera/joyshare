# What's still pending

A short summary of everything left. The full checklist with technical detail is in [ROADMAP.md](ROADMAP.md).

Last updated: 18 Nov 2026 (after random platform test videos, "View as member" and the iPhone popup fix).

## Done since the last update

- **Live on the Mac mini** at its own domain, with the Cloudflare Tunnel. The laptop is retired.
- **Cloudflare R2** is set up, tested and serving videos. `JOYSHARE_SECRET` is set.
- **The iPhone Share button** works with the real app.
- **Uptime Kuma** runs on the DigitalOcean droplet and watches joyshare's health page every minute ([UPTIME-KUMA.md](UPTIME-KUMA.md)).
- **Alerts** reach your phone through ntfy (the daily platform check sent one on 18 Nov).
- **Updating by itself**: the update helper runs on the Mac mini, and the admin panel's Update button puts new code live after the tests pass.
- **Platform checks** run at a random time each day, on a randomly picked test video from a list per platform (YouTube, X, TikTok, Instagram), with a second try before an alert.
- **View as member**: an admin can use one device as a regular member, and back. Members can never switch.
- **Smaller things**: the "…" menu on every video (original link, delete with Undo), swipe left to delete in Recent, EXPIRED stamps in the grid, popups that keep their size on iPhone.

## 1. Things only you can do

| What | Why | Where the steps are |
|---|---|---|
| **Find out why YouTube failed the daily check (18 Nov)** | The alert's text says why. If it's "sign in to confirm you're not a bot", YouTube is refusing the Mac mini's address without a signed-in account: connect a spare YouTube account. | Admin → System, platform checks; app: ☰ → Connected accounts |
| **Connect your accounts** (cookie files, ideally from spare accounts) | Instagram, and some videos elsewhere (YouTube from a home address, often), are only shown to signed-in accounts. | App: ☰ → Connected accounts |
| **Decide the Mac mini's restart behavior** | Docker on a Mac starts only after login, and FileVault blocks automatic login after a power cut. | Go-live phase |

## 2. Still to build

| What | Size | Notes |
|---|---|---|
| **A troubleshooting guide** | Small | The last piece of going live, covering the Mac mini's restart notes. |
| **Clips from very long videos** | Small | Clips are built. What's left: fetching only the part, so a video over the download limit can be clipped too. |
| **Test videos for Facebook** | Small | YouTube, X, TikTok and Instagram ship with lists of test videos. Facebook has none, so its daily check can't run until links are added in System. |
| **More progress scenes** | Small each | Seven are built: Demolition, Compressor, Voyage, Rocket, Black hole, Dominoes, Abduction, plus two calm ones. Scenes with ready-made 3D models (free CC0 packs such as Kenney or Quaternius) would need a model loader added. |
| **Alerts per person** | Medium | Today every alert goes to the admin's ntfy topic. Members should get their own "video ready" and "account stopped working". |
| **Platforms tab** | Small | An optional proxy per platform, for when a platform blocks your address. |
| **"Download this backup" button** | Small | Getting a backup off the machine without R2 means copying it out by hand. |
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

- The interface is plain files, and the 3D scenes, admin panel and phone flow were all built that way without trouble. Moving to SvelteKit would add a build step. Suggestion: consider it settled (plain files) unless the code becomes hard to manage.

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
| **Uptime Kuma's alert** | The monitor is green. Still to see: the ntfy alert arriving when joyshare stops answering (Kuma's Test button, or stop joyshare for two minutes). |
| **Popups on iPhone** (fixed 18 Nov) | Check that a popup (for example Update in System) keeps its size and reacts to the first tap. |
| **View as member** (18 Nov) | Checked in a desktop browser at phone size and by automated tests. Try it on your iPhone after the update. |
| **The iPhone Shortcut** | The Share button works on the iPhone. The Shortcut hasn't been built and tried yet. |
| **R2 storage** | In use, and the iPhone Share button works with it. Still to confirm: the file name when a video is downloaded. |
| **Cloud copy of backups** | Should be running now that R2 is on. Check System → Backups says the last one went to both places. |
| **Updating by itself** | The helper is connected on the Mac mini. Not yet run on a real Linux machine (the service files were generated and read, not run). |
| **Moving to another computer** | The move to the Mac mini worked. The Caddy web server (for leaving Cloudflare) has never fetched a real certificate. |
| **Clips** | One real clip was made from an X video. "Start here / End here" and the timeline were tried in a desktop browser, not with a finger on a phone. |
| **New scenes and the look-up animation** | Confirmed to draw in every state by reading pixels. Not yet watched on a phone, nor the calm scenes from a phone's real "Reduce motion" setting. |
| **Recent list layouts and the phone flow** | Checked in a desktop browser at phone size with a stand-in share sheet. On a real iPhone: Send or save, Save Video, a link pasted into WhatsApp, and building the Shortcut from the How it works page. |
| **Pull down to reload** | Checked with simulated touches in a desktop browser. Try it in the home-screen app on your iPhone. |
| **Second-copy warning** | Covered by automated tests. Two real copies have never been run at once to watch it fire. |
| **Connected accounts** | Never tried against a real sign-in wall with a real cookie file. |
| **A real yt-dlp update arriving** | The install, test, switch and go-back steps were each run for real, but a newer release arriving on its own hasn't been seen yet. |
| **Facebook** | No link tried. Instagram worked once. TikTok worked for one public video and was refused for another. |
| **The looks** | Most screens were only viewed in one or two looks. Windows 95 and Clay are the likeliest to need touch-ups. |
| **Expiry after 1 hour and 48 hours** | Covered by automated tests only. |
