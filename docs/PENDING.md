# What's still pending

A short summary of everything left. The full checklist with technical detail is in [ROADMAP.md](ROADMAP.md).

Last updated: 13 Nov 2026.

## 1. Things only you can do

| What | Why | Where the steps are |
|---|---|---|
| **Buy a domain and put its DNS on Cloudflare** | Phones can only use passkeys on an `https://` address. Without it joyshare stays on your laptop. Passkeys are tied to the domain, so pick the final one. | Go-live phase |
| **Set up Cloudflare R2** (create a bucket and an access key) | So videos are served from Cloudflare's storage and never pass through the tunnel. Cloudflare's rules don't allow video through the tunnel itself. Also gives backups a safe place off the machine. | [SETUP.md](SETUP.md), "Serve videos from Cloudflare R2" |
| **Install the ntfy app and choose a topic** | So alerts reach your phone. | [SETUP.md](SETUP.md), "Turn on alerts" |
| **Set `JOYSHARE_SECRET` in `.env`** | Stronger protection for connected accounts and the R2 secret. Do it before anyone uploads a cookie file. Keep a copy of it somewhere safe. | [SETUP.md](SETUP.md), "Settings" |
| **Connect your accounts** (cookie files, ideally from spare accounts) | Instagram, and some videos elsewhere, are only shown to signed-in accounts. | App: ☰ → Connected accounts |
| **Create the DigitalOcean droplet for Uptime Kuma** | To be told when the Mac mini is down. | Go-live phase |
| **Decide the Mac mini's restart behavior** | Docker on a Mac starts only after login, and FileVault blocks automatic login after a power cut. | Go-live phase |

## 2. Still to build

| What | Size | Notes |
|---|---|---|
| **Go live on the Mac mini** | Large | Cloudflare Tunnel container, move the data with `./joyshare backup` and `restore`, register every device again on the real domain, Uptime Kuma, write the moving and troubleshooting guides. R2 must be on first. |
| **3D progress scenes** | Large | Demolition, Compressor and Voyage first. A calm set for devices with "Reduce motion" on, with a small note. |
| **App icon and home-screen install** | Small | So it opens full-screen like an app on the phone. |
| **Share page in the sender's look** | Small | Friends currently always see the dark default look. |
| **Alerts per person** | Medium | Today every alert goes to the admin's ntfy topic. Members should get their own "video ready" and "account stopped working". |
| **Platforms tab** | Small | An optional proxy per platform, for when a platform blocks your address. |
| **Pictures in the cookie how-to** | Small | The steps are text only. |
| **Readable activity log** | Small | Details show as raw text. |
| **More looks** | Small each | Sketched but not built: chrome, arcade, deco, lava glass, notebook, receipt, graffiti. |

## 3. Decisions waiting for you

**A second engine besides yt-dlp**

- *Why it could matter:* joyshare depends entirely on yt-dlp. If a yt-dlp release is broken for a platform, that platform stops until the fix arrives.
- *Why it's probably not urgent:* yt-dlp is very actively maintained and usually fixes breakage within days. joyshare already checks for updates daily, tests a new version before using it, can go back a version, and tells you when a platform breaks. And when a platform blocks everyone, a second engine is blocked too: it only helps against yt-dlp's own bugs.
- *Options, smallest first:* let the updater fall back to yt-dlp's nightly builds; add `gallery-dl` as a backup for X and Instagram; run a self-hosted `cobalt` container as a full second engine.
- *Suggestion:* add the nightly fallback when convenient, and anything bigger only if yt-dlp actually lets you down.

**SvelteKit or plain HTML/CSS/JavaScript**

- The interface is plain files today and works well. Moving to SvelteKit would add a build step. Suggestion: stay as is unless the 3D scenes make the code hard to manage.

**Cloudflare Access in front of the admin panel**

- Skipped for launch. It would add an emailed code before anyone can even reach the admin screens. Worth revisiting after go-live if the logs show strangers probing.

## 4. If you ever stop using Cloudflare

joyshare currently has **no web server of its own** in front of it, because the Cloudflare Tunnel does that job. If you move away from Cloudflare you need three things:

1. **A web server for HTTPS**, such as Caddy, in front of the app. It gets and renews the certificate.
2. **A way for the internet to find the machine:** a fixed IP address, or dynamic DNS that updates when the address changes.
3. **Open ports** (80 and 443) on the router or firewall, forwarded to the machine.

The first thing lost is the protection of having no open ports. R2 (or any S3-compatible storage) keeps working without the tunnel. This will be a chapter of the moving guide.

## 5. Built but not yet proven in real conditions

| What | What's missing |
|---|---|
| **Passkeys on a phone, the Share button, the iPhone Shortcut** | All need the `https://` address. |
| **R2 storage** | Proven against a stand-in, not real Cloudflare R2. Check the download file name, the two bucket rules and the Share button with files in R2. |
| **Alerts** | Never sent to the real ntfy service. No topic is set yet. |
| **Connected accounts** | Never tried against a real sign-in wall with a real cookie file. |
| **A real yt-dlp update arriving** | The installed version has been the newest all along. The install, test, switch and go-back steps were each run for real. |
| **Cloud copy of backups** | Needs R2. The local daily backup and both restore commands were run for real. |
| **Facebook** | No link tried. Instagram worked once. TikTok worked for one public video and was refused for another. |
| **The looks** | Most screens were only viewed in one or two looks. Windows 95 and Clay are the likeliest to need touch-ups. |
| **Expiry after 1 hour and 48 hours** | Covered by automated tests only. |
