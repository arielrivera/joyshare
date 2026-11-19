# joyshare at a glance

How a video link becomes something you can send, where each part runs, how the parts connect, and how long everything is kept.

![joyshare at a glance: the process in five steps (paste, inspect, process, adjust, send); where things run (your devices, Cloudflare, the joyshare server, Uptime Kuma on DigitalOcean); how the parts connect (the step-by-step diagram and what keeps it running); how a share link delivers the video (from the server, or from R2, which is in use); how long things are kept (originals 1 hour, finished videos and share links 48 hours); and the stack, layer by layer.](infographic.png)

## About this page

- **The source** is [infographic.html](infographic.html): a normal web page. Download the repo and open it in any browser to see it in full, including dark mode. The picture above is made from it.
- **After editing it**, make the picture again (needs Google Chrome):

```bash
tools/render_infographic.sh
```

- **The diagrams** inside it come from [architecture-flow.d2](architecture-flow.d2) and [architecture-upkeep.d2](architecture-upkeep.d2) (see the command at the top of each file). Render those first, then the picture.

More: the [README](../README.md) · the [project plan](proposal.html) (source) · [what's pending](PENDING.md)
