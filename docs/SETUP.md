# Setting up joyshare

> **Where this guide stands:** phase 1. It covers running joyshare on your own computer.
> Sign-in, alerts, the admin panel and going live on a domain are added to this guide as each phase is built.

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

Paste a link from X or YouTube, pick a size, press **Make it**.

> **Phase 1 has no sign-in yet.** That's why joyshare only answers on this computer (`localhost`).
> Don't expose it to your network or the internet until phase 2 adds passkeys.

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

Copy `.env.example` to `.env` to change these. Both are optional.

| Setting | What it does | Default |
|---|---|---|
| `JOYSHARE_PORT` | The port on your computer | `8080` |
| `JOYSHARE_PUBLIC_URL` | The address used to build share links | `http://localhost:8080` |

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

## Troubleshooting

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
