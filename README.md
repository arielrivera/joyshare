# joyshare

**Share the video, not the app.**

Ever wanted to send a friend a video, but they don't have an account on X, Instagram or wherever you found it?
Ever seen something in your feed you wanted to keep on your own device before it disappears?

joyshare is a small private web app you run on your own computer. Paste a link, get a video file you can send anywhere.

> **Status: in development.** The core works on your own computer today: paste a link, pick a size, get a file or a share link. Sign-in, the admin panel, alerts and the 3D progress scenes are still being built, so don't put it on the internet yet.

## How it works

1. **Paste a link** from X (Twitter), YouTube, Instagram or Facebook. On an iPhone you can send it straight from the share sheet.
2. **Pick a size.** joyshare shows how big the file will be before you commit: original, 720p, 480p, "fit under 25 MB", or audio only.
3. **Watch something fun** while it works. Progress is shown as a random 3D scene, not a boring bar.
4. **Send it.** Share it to WhatsApp or iMessage, download it, or copy a link your friend can open in any browser. No account needed on their side.

## Quick facts

| | |
|---|---|
| **Runs on** | Your own machine: a Mac, a Linux server or a Raspberry Pi. Everything ships in Docker. |
| **Works from** | iPhone, Android, Mac, Windows. Anything with a browser. |
| **Sign-in** | Face ID / Touch ID (passkeys). No passwords. Only devices you approve get in. |
| **Share links** | Expire after 48 hours. |
| **Files** | Deleted automatically. Nothing piles up. |
| **Size limit** | 200 MB per video by default. You can change it. |
| **Output** | MP4 that plays in iMessage, WhatsApp and every browser. M4A for audio. |
| **Alerts** | Push notifications to your phone when a video is ready or something breaks. |
| **Admin panel** | Stats, logs, limits, users and updates in one place. |
| **Powered by** | [yt-dlp](https://github.com/yt-dlp/yt-dlp), ffmpeg, FastAPI, SvelteKit, Three.js |

## What you need

- A computer that stays on (a Mac mini or a Raspberry Pi is plenty) with **Docker** installed
- A **domain name** (about $10–15 a year)
- A free **Cloudflare** account, so your site is reachable from anywhere without opening ports on your router
- Optional: the free **ntfy** app on your phone for alerts

## Setting it up

To try it on your own computer today:

```bash
git clone https://github.com/arielrivera/joyshare.git
```

```bash
cd joyshare && docker compose up -d --build
```

Then open http://localhost:8080 and paste a link.

The full walkthrough is in the [setup guide](docs/SETUP.md).

## Dig deeper

- **[Setup guide](docs/SETUP.md)**: running it, everyday commands, settings, troubleshooting
- **Moving guide** (coming): moving between a cloud server, a Mac mini and a Raspberry Pi, and what changes if you don't use Cloudflare
- **How it's built**: the project plan (`docs/proposal.html`) and a one-page visual of the process and stack (`docs/infographic.html`)

## Fair use

joyshare is for personal use: saving things that matter to you and sharing them with people you know. Respect the platforms' terms and the rights of the people who made the videos. Give credit where you can.
