// The main screen: paste a link, pick a size, watch progress, send the file.
// One step shows at a time, so the finished file is never hidden below the fold.
// $, api(), showError(), fmtWhen(), copyFrom() come from auth.js; t() from i18n.js.
const MB = 1024 * 1024;
// Where this script was loaded from, for example "/a/3f9c2b1d7e44/". Files loaded later use the same
// versioned address, so they always match this script.
const ASSET_BASE = new URL(".", document.currentScript.src).pathname;
const SHARE_SHEET_MAX = 100 * MB; // bigger files are too heavy to hand to the phone's share sheet

let current = null;    // { media, presets } for the link being worked on
let lastJob = null;    // the job shown in the progress or result step
let events = null;     // EventSource for the running job
let shareFile = null;  // File prepared for the share sheet

const fmtSize = (bytes) => {
  if (!bytes) return t("size.unknown");
  return bytes >= 10 * MB ? `${Math.round(bytes / MB)} MB` : `${(bytes / MB).toFixed(1)} MB`;
};
const fmtDuration = (s) => {
  if (!s) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};

// ---------- which step is showing ----------

function showStep(step) {
  for (const id of ["looking", "media", "job", "result"]) $(id).hidden = id !== step;
  if (step !== "looking") stopLooking();
  if (!step) return;
  const focus = { looking: "looking-text", media: "title", job: "percent", result: "result-title" }[step];
  $(step).scrollIntoView({ block: "start", behavior: "smooth" });
  $(focus).focus({ preventScroll: true });
}

function startOver() {
  if (events) { events.close(); events = null; }
  stopScene();
  current = null;
  lastJob = null;
  showStep(null);
  showError($("lookup-error"), "");
  $("url").value = "";
  syncUrlTools();
  $("lookup").scrollIntoView({ block: "start", behavior: "smooth" });
  $("url").focus({ preventScroll: true });
}

// ---------- times, for clips ----------

// "1:30", "1:02:03", "90" or "12.5" -> seconds. null when it can't be read.
function parseTime(text) {
  const parts = String(text).trim().replace(",", ".").split(":");
  if (parts.length > 3 || parts.some((p) => p.trim() === "" || Number.isNaN(Number(p)) || Number(p) < 0)) return null;
  return parts.reduce((total, p) => total * 60 + Number(p), 0);
}

// Seconds -> "1:30" or "1:30.5" (tenths only when they matter).
function fmtClock(seconds) {
  const tenths = Math.round(seconds * 10);
  const whole = Math.floor(tenths / 10), rest = tenths % 10;
  return (fmtDuration(whole) || "0:00") + (rest ? `.${rest}` : "");
}
const fmtRange = (clip) => `${fmtClock(clip[0])}–${fmtClock(clip[1])}`;

// ---------- the wait while a link is looked up ----------

let lookingTimer = 0;
const LOOKING_LINES = 7;

function startLooking() {
  let line = Math.floor(Math.random() * LOOKING_LINES);
  const say = () => { $("looking-text").textContent = t(`look.line${line % LOOKING_LINES}`); line += 1; };
  say();
  clearInterval(lookingTimer);
  lookingTimer = setInterval(say, 1700);
  showStep("looking");
}

function stopLooking() {
  clearInterval(lookingTimer);
  lookingTimer = 0;
}

// ---------- look up a link ----------

async function lookUp() {
  if (!$("url").value.trim()) return;
  const url = webAddress($("url").value);
  if (!url) { showError($("lookup-error"), t("link.notAddress")); return; }
  showError($("lookup-error"), "");
  const button = $("lookup-button");
  button.disabled = true;
  button.textContent = t("link.looking");
  if (events) { events.close(); events = null; }
  stopScene();
  startLooking();
  try {
    current = await api("/api/inspect", { method: "POST", body: JSON.stringify({ url }) });
    $("url").value = ""; // ready for the next link
    syncUrlTools();
    $("clip-on").checked = false;
    $("clip-start").value = "";
    $("clip-end").value = "";
    renderMedia();
    showStep("media");
  } catch (err) {
    current = null;
    showStep(null);
    showError($("lookup-error"), err.message);
    $("lookup").scrollIntoView({ block: "start", behavior: "smooth" });
  } finally {
    stopLooking();
    button.disabled = false;
    button.textContent = t("link.lookup");
  }
}

$("lookup").addEventListener("submit", (e) => { e.preventDefault(); lookUp(); });

// Pasting a link looks it up straight away: no extra tap.
$("url").addEventListener("paste", (e) => {
  const text = e.clipboardData ? e.clipboardData.getData("text") : "";
  const address = webAddress(text);
  if (text && !address) {            // not a link: don't let it in
    e.preventDefault();
    urlSaid("link.notAddress");
    return;
  }
  if (address) {                     // keep just the address, even if it came wrapped in other text
    e.preventDefault();
    $("url").value = address;
    syncUrlTools();
    lookUp();
  }
});

// The web address inside a piece of text, or null. Accepts "https://…", and also "www.…" or "x.com/…"
// (https:// is added). Text around it, like the message apps add when sharing, is dropped.
function webAddress(text) {
  const full = String(text).match(/https?:\/\/[^\s<>"']+/i);
  if (full) return full[0];
  const bare = String(text).trim().match(/^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\/[^\s<>"']*$/i);
  return bare ? `https://${bare[0]}` : null;
}

// ---------- helpers for the link box ----------
// Tapping the box selects what is in it, so the next paste or keystroke replaces it and the phone's own
// Cut / Copy / Paste bubble applies to the whole link. Under the box: Paste, and Copy and Clear when it holds text.

function syncUrlTools() {
  const filled = $("url").value.trim() !== "";
  $("url-copy").hidden = !filled || !navigator.clipboard;
  $("url-clear").hidden = !filled;
}

let saidTimer = 0;
function urlSaid(key) {
  const said = $("url-said");
  said.textContent = t(key);
  said.hidden = false;
  clearTimeout(saidTimer);
  saidTimer = setTimeout(() => { said.hidden = true; }, 2500);
}

$("url").addEventListener("input", syncUrlTools);
$("url").addEventListener("focus", () => setTimeout(() => { if ($("url").value) $("url").select(); }, 0));

$("url-copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("url").value.trim()); urlSaid("link.copied"); }
  catch { $("url").focus(); }   // not allowed: the box is selected, copy by hand
});

$("url-clear").addEventListener("click", () => {
  $("url").value = "";
  syncUrlTools();
  showError($("lookup-error"), "");
  $("url").focus();
});

if (navigator.clipboard && navigator.clipboard.readText) {
  $("paste").hidden = false;
  $("paste").addEventListener("click", async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) { urlSaid("link.nothingToPaste"); return; }
      const address = webAddress(text);
      if (!address) { urlSaid("link.notAddress"); return; }   // whatever was copied isn't a link: leave the box alone
      $("url").value = address;
      syncUrlTools();
      lookUp();
    } catch {
      $("url").focus(); // the browser said no: paste by hand
      urlSaid("link.pasteByHand");
    }
  });
}

// What the "Just a part" boxes say. { on, ok, start, end, problem }
function readClip() {
  if (!$("clip-on").checked || !current) return { on: false };
  const duration = current.media.duration || 0;
  const startText = $("clip-start").value.trim(), endText = $("clip-end").value.trim();
  const start = startText ? parseTime(startText) : 0;
  const end = endText ? parseTime(endText) : (duration || null);
  if (start === null || end === null) return { on: true, ok: false, problem: endText || startText ? "clip.badTime" : "clip.needEnd" };
  if (end - start < 1) return { on: true, ok: false, problem: "clip.tooShort" };
  if (duration && end > duration + 1) return { on: true, ok: false, problem: "clip.outside" };
  return { on: true, ok: true, start, end: duration ? Math.min(end, duration) : end };
}

for (const id of ["clip-on", "clip-start", "clip-end"]) $(id).addEventListener("input", () => renderMedia());

function renderMedia() {
  if (!current) return;
  const { media, presets } = current;
  const clip = readClip();
  $("clip-box").hidden = !clip.on;
  if (clip.on) {
    $("clip-info").textContent = clip.ok
      ? t("clip.length", { len: fmtClock(clip.end - clip.start) })
      : t(clip.problem, { len: fmtDuration(media.duration) || "?" });
    $("clip-end").placeholder = fmtDuration(media.duration) || "0:30";
  }
  // A part is smaller than the whole: sizes shrink by the same share.
  const share = clip.on && clip.ok && media.duration ? (clip.end - clip.start) / media.duration : null;
  $("title").textContent = media.title || t("media.untitled");
  $("meta").textContent = [media.uploader, media.platform_label, fmtDuration(media.duration)].filter(Boolean).join(" · ");
  $("experimental").hidden = !media.experimental;
  const thumb = $("thumb");
  const picture = media.thumb_url || media.thumbnail;   // our saved copy, else the platform's
  thumb.hidden = !picture;
  thumb.onerror = () => { thumb.hidden = true; };
  if (picture) thumb.src = picture;

  const picked = document.querySelector('input[name="preset"]:checked');
  const keep = picked ? picked.value : null;
  const keepTarget = $("fit-target") ? $("fit-target").value : null;
  const box = $("presets");
  box.replaceChildren();
  for (const p of presets) {
    let allowed = p.allowed, estimate = p.est_bytes;
    if (share !== null && p.id !== "fit" && estimate) {
      estimate *= share;
      // Too big to share whole, but this part of it fits.
      if (!allowed && p.clip_ok && estimate <= current.max_file_mb * MB) allowed = true;
    }
    const label = document.createElement("label");
    label.className = "preset" + (allowed ? "" : " off");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "preset";
    radio.value = p.id;
    radio.id = `preset-${p.id}`;
    radio.disabled = !allowed;
    radio.checked = allowed && (keep ? keep === p.id : Boolean(p.recommended));
    const name = document.createElement("span");
    name.className = "name";
    const detail = p.id === "fit" ? t("preset.fitDetail") : p.detail;
    name.textContent = `${t(`preset.${p.id}`)} · ${detail}`;
    const size = document.createElement("span");
    size.className = "size";
    label.append(radio, name, size);

    if (p.id === "fit" && allowed) {
      const select = document.createElement("select");
      select.id = "fit-target";
      select.setAttribute("aria-label", t("fit.target"));
      for (const target of p.targets) {
        const option = document.createElement("option");
        option.value = target.mb;
        option.textContent = t("fit.under", { mb: target.mb, h: target.height });
        select.append(option);
      }
      const preferred = p.targets.find((x) => String(x.mb) === keepTarget) || p.targets.find((x) => x.mb === 25) || p.targets[0];
      select.value = preferred.mb;
      select.addEventListener("change", () => { radio.checked = true; });
      size.append(select);
    } else if (allowed) {
      size.textContent = estimate ? t("size.about", { size: fmtSize(estimate) }) : t("size.unknown");
    }
    const extra = (!allowed && p.reason) || (p.needs_convert ? t("preset.convert") : "");
    if (extra) {
      const note = document.createElement("span");
      note.className = "extra";
      note.textContent = extra;
      label.append(note);
    }
    box.append(label);
  }
  if (!box.querySelector("input:checked")) {
    const first = box.querySelector("input:not(:disabled)");
    if (first) first.checked = true;
  }
  $("make-button").disabled = !box.querySelector("input:not(:disabled)");
}

// ---------- make the file ----------

$("make").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError($("make-error"), "");
  const picked = document.querySelector('input[name="preset"]:checked');
  if (!picked || !current) return;
  const body = { media_id: current.media.id, preset: picked.value };
  if (picked.value === "fit") body.target_mb = Number($("fit-target").value);
  const clip = readClip();
  if (clip.on) {
    if (!clip.ok) { showError($("make-error"), t(clip.problem, { len: fmtDuration(current.media.duration) || "?" })); return; }
    body.clip_start = clip.start;
    body.clip_end = clip.end;
  }
  try {
    const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    watch(job.id);
  } catch (err) {
    showError($("make-error"), err.message);
  }
});

// ---------- the 3D progress scene ----------

let stage3d = null;     // the running scene, if any
let scenesLoading = null;
const FINALE = 1700;    // how long the ending plays before the next step shows (milliseconds)
// A job goes through stages that each count from 0 to 100%. The scene needs one number for the whole trip.
const STAGE_SPAN = { starting: [0, 0], downloading: [0, 0.65], converting: [0.65, 0.95], uploading: [0.95, 1], done: [1, 1] };

function overallProgress(job) {
  const [from, to] = STAGE_SPAN[job.stage] || [0, 0];
  return from + (to - from) * (job.progress || 0);
}

// "Reduce motion" on the device means calm scenes, unless the person asked for the full ones.
const deviceWantsCalm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const useCalm = () => deviceWantsCalm() && prefs.motion !== "full";

async function loadScenes() {
  if (!window.joyshareScenes) {
    scenesLoading = scenesLoading || import(`${ASSET_BASE}scenes/index.js`);   // fetched only when first needed
    await scenesLoading;
  }
  return window.joyshareScenes;
}

async function startScene() {
  stopScene();
  $("scene").hidden = prefs.scene === "none";
  if (prefs.scene === "none") return;
  try {
    const scenes = await loadScenes();
    stopScene();
    stage3d = scenes.start($("scene-canvas"), { choice: prefs.scene, calm: useCalm() });
  } catch {
    stage3d = null;
  }
  $("scene").hidden = !stage3d;
  $("scene-note").hidden = !(stage3d && useCalm());
  if (stage3d && lastJob) stage3d.set(overallProgress(lastJob), "running");
}

function stopScene() {
  if (stage3d) { stage3d.dispose(); stage3d = null; }
}

$("scene-full").addEventListener("click", () => {
  setPrefs({ motion: "full" });
  if (!$("job").hidden) startScene();
});

function watch(jobId, media) {
  if (events) events.close();
  lastJob = null;
  startScene();
  paintProgress({ status: "queued", progress: 0, media: media || (current && current.media) });
  showStep("job");
  $("cancel").onclick = () => api(`/api/jobs/${jobId}`, { method: "DELETE" }).catch(() => {});
  events = new EventSource(`/api/jobs/${jobId}/events`);
  events.onmessage = (msg) => {
    const job = JSON.parse(msg.data);
    lastJob = job;
    renderJob(job);
    if (["done", "failed", "canceled"].includes(job.status)) {
      events.close();
      events = null;
      loadRecent();
    }
  };
}

function paintProgress(job) {
  const pct = Math.round((job.progress || 0) * 100);
  const waiting = job.status === "queued";
  $("job-title").textContent = (job.media && job.media.title) || "";
  $("percent").textContent = waiting ? "…" : `${pct}%`;
  $("stage-text").textContent = waiting ? t("job.queued") : t(`stage.${job.stage || "working"}`);
  $("bar").style.setProperty("--p", waiting ? "0%" : `${pct}%`);
  $("job").classList.toggle("waiting", waiting);
  if (stage3d && !waiting) stage3d.set(overallProgress(job), "running");
}

function renderJob(job) {
  if (job.status === "queued" || job.status === "running") {
    paintProgress(job);
    return;
  }
  // Let the scene play its ending (the landing, the jammed gun) before moving on.
  const playEnding = stage3d && job.status !== "canceled" && !job.reused;
  if (playEnding) {
    stage3d.set(overallProgress(job), job.status);
    $("percent").textContent = job.status === "done" ? "100%" : $("percent").textContent;
    $("bar").style.setProperty("--p", job.status === "done" ? "100%" : $("bar").style.getPropertyValue("--p"));
  }
  const next = () => {
    if (lastJob !== job) return;   // something newer started meanwhile
    stopScene();
    if (job.status === "done") {
      renderResult(job, true);
      showStep("result");
    } else {
      // Failed or canceled: back to the size picker (or the link box if we came from a shortcut link).
      if (job.status === "failed") showError($(current ? "make-error" : "lookup-error"), job.error || t("job.failed"));
      showStep(current ? "media" : null);
    }
  };
  if (playEnding) setTimeout(next, FINALE); else next();
}

// ---------- the finished file ----------

function renderResult(job, fresh) {
  const file = job.file;
  if (!file) return;
  $("result-title").textContent = job.reused ? t("res.reused") : t("res.ready");
  $("result-name").textContent = (job.media && job.media.title) || "";
  const bits = [fmtSize(file.size)];
  if (file.kind === "video" && file.height) bits.push(`${file.height}p`);
  if (file.duration) bits.push(fmtDuration(file.duration));
  if (job.clip) bits.push(t("clip.part", { range: fmtRange(job.clip) }));
  bits.push(t("res.kept", { when: fmtWhen(file.expires_at) }));
  $("result-meta").textContent = bits.join(" · ");
  $("again").hidden = !current; // no size picker to go back to when opened from a shortcut link
  if (!fresh) return; // language change: only the words above needed repainting

  const player = document.createElement(file.kind === "audio" ? "audio" : "video");
  player.controls = true;
  player.preload = "metadata";
  player.playsInline = true;
  if (file.kind === "video" && job.media && (job.media.thumb_url || job.media.thumbnail)) player.poster = job.media.thumb_url || job.media.thumbnail;
  player.src = file.stream_url;
  $("player").replaceChildren(player);

  $("download").href = file.download_url;
  $("link-box").hidden = true;
  $("link-note").hidden = true;
  $("link-copied").hidden = true;
  $("link").onclick = () => makeLink(file);
  prepareShare(job, file);
  setUpClipTools(job, player);
}

// "Start here" and "End here" under the player: watch, tap, tap, and that part becomes its own file.
function setUpClipTools(job, player) {
  const tools = $("clip-tools");
  tools.hidden = !job.media;
  if (!job.media) return;
  const offset = job.clip ? job.clip[0] : 0;   // a clip of a clip still counts from the start of the whole video
  const picked = { start: null, end: null };
  const paint = () => {
    const has = (v) => v !== null;
    $("clip-picked").textContent = has(picked.start) && has(picked.end) ? fmtRange([picked.start, picked.end])
      : has(picked.start) ? t("clip.from", { time: fmtClock(picked.start) })
      : has(picked.end) ? t("clip.to", { time: fmtClock(picked.end) }) : "";
    $("clip-make").disabled = !(has(picked.start) && has(picked.end) && picked.end - picked.start >= 1);
    showError($("clip-error"), has(picked.start) && has(picked.end) && picked.end - picked.start < 1 ? t("clip.tooShort") : "");
  };
  const now = () => Math.round((offset + (player.currentTime || 0)) * 10) / 10;
  $("clip-here-start").onclick = () => { picked.start = now(); paint(); };
  $("clip-here-end").onclick = () => { picked.end = now(); paint(); };
  $("clip-make").onclick = async () => {
    const body = { media_id: job.media.id, preset: job.preset, clip_start: picked.start, clip_end: picked.end };
    if (job.preset === "fit") body.target_mb = job.target_mb;
    try {
      const made = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
      player.pause();
      watch(made.id, job.media);
    } catch (err) {
      showError($("clip-error"), err.message);
    }
  };
  paint();
}

// The phone's share sheet needs the whole file in memory and a fresh tap,
// so we fetch it ahead of time and only then show the button.
async function prepareShare(job, file) {
  const button = $("share"), note = $("share-note");
  shareFile = null;
  button.hidden = true;
  note.hidden = true;
  if (!navigator.canShare) return;
  if (file.size > SHARE_SHEET_MAX) {
    note.textContent = t("res.tooBig");
    note.hidden = false;
    return;
  }
  try {
    const blob = await (await fetch(file.stream_url)).blob();
    const ext = file.kind === "audio" ? "m4a" : "mp4";
    const base = (job.media && job.media.title ? job.media.title : brandName()).replace(/[\\/:*?"<>|]+/g, " ").slice(0, 60).trim() || "video";
    const candidate = new File([blob], `${base}.${ext}`, { type: file.mime });
    if (!navigator.canShare({ files: [candidate] })) throw new Error("not shareable");
    shareFile = candidate;
    button.hidden = false;
  } catch {
    button.hidden = true;
  }
}

$("share").addEventListener("click", async () => {
  if (!shareFile) return;
  try { await navigator.share({ files: [shareFile] }); } catch { /* closed the sheet */ }
});

// Says clearly whether the link is on the clipboard. Stays on screen: a button label that flips for two seconds is easy to miss.
function showCopied(ok) {
  const note = $("link-copied");
  note.textContent = ok ? t("res.copiedNote") : t("res.copyManual");
  note.classList.toggle("ok", ok);
  note.hidden = false;
  if (ok) {
    $("copy").textContent = t("copied");
    setTimeout(() => { $("copy").textContent = t("copy"); }, 2500);
  } else {
    $("link-url").focus();
    $("link-url").select();
  }
}

// Gets the share link for a file (the server reuses a live one, or makes a new one) and copies it in the same tap.
// Returns { link, copied }.
async function linkToClipboard(file) {
  const request = api(`/api/files/${file.id}/share`, { method: "POST" });
  let copying = null;
  if (navigator.clipboard && window.ClipboardItem) {
    try {
      const text = request.then((link) => new Blob([link.url], { type: "text/plain" }));
      copying = navigator.clipboard.write([new ClipboardItem({ "text/plain": text })]);
      copying.catch(() => {});
    } catch { copying = null; }
  }
  const link = await request;
  let copied = false;
  try {
    if (copying) { await copying; copied = true; }
    else if (navigator.clipboard) { await navigator.clipboard.writeText(link.url); copied = true; }
  } catch { copied = false; }
  return { link, copied };
}

// "Get a link for friends": make the link and put it on the clipboard in the same tap.
async function makeLink(file) {
  $("link-copied").hidden = true;
  try {
    const { link, copied } = await linkToClipboard(file);
    $("link-url").value = link.url;
    $("link-box").hidden = false;
    $("link-note").textContent = t("res.linkNote", { when: fmtWhen(link.expires_at) });
    showCopied(copied);
  } catch (err) {
    $("link-note").textContent = err.message;
  }
  $("link-note").hidden = false;
}

$("copy").addEventListener("click", async () => {
  let copied = false;
  try { await navigator.clipboard.writeText($("link-url").value); copied = true; } catch { copied = false; }
  showCopied(copied);
});
$("again").addEventListener("click", () => showStep("media"));
$("new-link").addEventListener("click", startOver);

// ---------- recent ----------

function chip(label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "chip";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

// Makes the same file again (same video, size and part) when it has expired or failed.
async function makeAgain(job, note) {
  const body = { media_id: job.media.id, preset: job.preset };
  if (job.preset === "fit") body.target_mb = job.target_mb;
  if (job.clip) { body.clip_start = job.clip[0]; body.clip_end = job.clip[1]; }
  try {
    const made = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    current = null;   // the size picker on screen (if any) belongs to another video
    watch(made.id, job.media);
  } catch (err) {
    note.textContent = err.message;
    note.hidden = false;
  }
}

async function loadRecent() {
  let jobs = [];
  try { jobs = await api("/api/jobs?limit=10"); } catch { return; }
  const list = $("recent-list");
  list.replaceChildren();
  for (const job of jobs) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "row-main";
    const preset = job.preset === "fit" ? t("recent.fit", { mb: job.target_mb }) : t(`short.${job.preset}`);
    const words = document.createElement("span");
    words.textContent = [(job.media && job.media.title) || t("media.untitled"), preset, job.clip ? fmtRange(job.clip) : ""]
      .filter(Boolean).join(" · ");
    if (job.media && job.media.thumb_url) {
      const picture = document.createElement("img");
      picture.className = "row-thumb";
      picture.alt = "";
      picture.onerror = () => picture.remove();
      picture.src = job.media.thumb_url;
      name.append(picture);
    }
    name.append(words);
    const state = document.createElement("span");
    state.className = "row-actions";
    const note = document.createElement("span");
    note.className = "row-note";
    note.setAttribute("role", "status");
    note.hidden = true;
    const again = () => (job.media ? chip(t("recent.again"), () => makeAgain(job, note)) : "");
    if (job.status === "done" && job.file) {
      const a = document.createElement("a");
      a.href = job.file.download_url;
      a.textContent = t("recent.download", { size: fmtSize(job.file.size) });
      // The link again: the same one while it lasts, a new one if it ran out or is about to.
      const copy = chip(t("recent.link"), async () => {
        copy.disabled = true;
        note.className = "row-note";
        try {
          const { link, copied } = await linkToClipboard(job.file);
          const when = t(link.ends_soon ? "recent.linkSoon" : "recent.linkUntil", { when: fmtWhen(link.expires_at) });
          if (copied) {
            // Say it twice, where the eye is: the button itself flips to "Copied", and a highlighted line stays below.
            note.textContent = `${t("recent.linkCopied")} ${when}`;
            note.classList.add("copied", "ok");
            copy.textContent = `✓ ${t("copied")}`;
            copy.classList.add("done");
            setTimeout(() => { copy.textContent = t("recent.link"); copy.classList.remove("done"); }, 3000);
          } else {
            note.textContent = `${t("recent.copyByHand")} ${link.url} · ${when}`;
            note.classList.add("copied");
          }
        } catch (err) {
          note.textContent = err.message;
          note.classList.add("bad");
        }
        note.hidden = false;
        copy.disabled = false;
      });
      state.append(a, copy);
    } else if (job.status === "done") {
      state.append(t("recent.expired"), again());
    } else if (job.status === "failed") {
      const failed = document.createElement("span");
      failed.textContent = t("recent.failed");
      failed.title = job.error || "";
      state.append(failed, again());
    } else if (job.status === "canceled") {
      state.append(t("recent.canceled"), again());
    } else {
      state.textContent = t("recent.progress");
    }
    li.append(name, state, note);
    list.append(li);
  }
  $("recent").hidden = jobs.length === 0;
}

// ---------- choosing a scene in the style panel, with a looping preview ----------

let previewStage = null, previewTimer = null;

function stopPreview() {
  clearInterval(previewTimer);
  if (previewStage) { previewStage.dispose(); previewStage = null; }
  $("scene-preview").hidden = true;
}

async function showPreview() {
  stopPreview();
  if ($("style-panel").hidden || prefs.scene === "none") return;
  let scenes;
  try { scenes = await loadScenes(); } catch { return; }
  const play = () => {
    if (previewStage) previewStage.dispose();
    $("scene-preview").hidden = false;
    previewStage = scenes.start($("scene-preview"), { choice: prefs.scene, calm: useCalm() });
    if (!previewStage) { stopPreview(); return; }
    const began = performance.now();
    clearInterval(previewTimer);
    previewTimer = setInterval(() => {
      const seconds = (performance.now() - began) / 1000;
      if (seconds > 8.5) play();                                       // start over
      else previewStage.set(Math.min(1, seconds / 6), seconds >= 6 ? "done" : "running");
    }, 100);
  };
  play();
}

for (const button of document.querySelectorAll("[data-scene]")) {
  button.addEventListener("click", () => { setPrefs({ scene: button.dataset.scene }); showPreview(); });
}
$("scene-motion").addEventListener("change", () => { setPrefs({ motion: $("scene-motion").checked ? "full" : "auto" }); showPreview(); });
$("open-style").addEventListener("click", () => {
  // prefs.js has just opened or closed the panel.
  $("scene-motion-row").hidden = !deviceWantsCalm();
  $("scene-motion").checked = prefs.motion === "full";
  if ($("style-panel").hidden) stopPreview(); else showPreview();
});
$("close-style").addEventListener("click", stopPreview);

// ---------- the hint that points at the pencil button ----------
// Shown the first time on a device, and now and then afterwards, until the pencil has been used.

const HINT_KEY = "joyshare_hint";
let hintStage = null, hintTimer = null;

const readHint = () => { try { return JSON.parse(localStorage.getItem(HINT_KEY) || "{}"); } catch { return {}; } };
const writeHint = (data) => { try { localStorage.setItem(HINT_KEY, JSON.stringify(data)); } catch { /* private window */ } };

function hideHint() {
  clearTimeout(hintTimer);
  $("pencil-hint").hidden = true;
  if (hintStage) { hintStage.dispose(); hintStage = null; }
}

async function showHint() {
  if (!$("style-panel").hidden) return;
  const hint = $("pencil-hint"), pencil = $("open-style"), brand = pencil.parentElement;
  hint.hidden = false;
  // Sit just under the pencil, with the little arrow pointing at it, without running off the screen.
  const pencilBox = pencil.getBoundingClientRect(), brandBox = brand.getBoundingClientRect();
  const center = pencilBox.left + pencilBox.width / 2;
  const left = Math.max(8, Math.min(center - 34, window.innerWidth - hint.offsetWidth - 8));
  hint.style.left = `${left - brandBox.left}px`;
  hint.style.setProperty("--arrow", `${center - left}px`);
  hintTimer = setTimeout(hideHint, 12000);
  if (deviceWantsCalm() && prefs.motion !== "full") return;   // calm: the words alone, nothing moving
  try {
    const scenes = await loadScenes();
    if (!hint.hidden) hintStage = scenes.mascot($("hint-mascot"));
  } catch { /* no 3D: the words alone are fine */ }
}

function maybeShowHint() {
  const seen = readHint();
  if (seen.used) return;
  const days = (Date.now() - (seen.at || 0)) / 86400000;
  const due = !seen.count || (days > 2 && Math.random() < 0.5);
  if (!due) return;
  writeHint({ ...seen, count: (seen.count || 0) + 1, at: Date.now() });
  setTimeout(showHint, 1500);
}

$("hint-close").addEventListener("click", hideHint);
// Moving to another screen puts the tip away, so it never covers that screen's buttons.
for (const id of ["open-admin", "open-devices", "open-accounts", "menu-button"]) $(id).addEventListener("click", hideHint);
$("open-style").addEventListener("click", () => { writeHint({ ...readHint(), used: true }); hideHint(); });

// Runs each time someone signs in. A link like /#job=12 (opened by the iPhone Shortcut) jumps to that job.
document.addEventListener("joyshare:signed-in", () => {
  loadRecent();
  maybeShowHint();
  const match = location.hash.match(/^#job=(\d+)$/);
  if (match) {
    history.replaceState(null, "", location.pathname);
    watch(Number(match[1]));
  }
});

// Language changed: repaint whatever step is showing.
document.addEventListener("joyshare:prefs", () => {
  if (!me) return;
  $("lookup-button").textContent = t("link.lookup");
  renderMedia();
  if (lastJob && !$("job").hidden) paintProgress(lastJob);
  if (lastJob && !$("result").hidden) renderResult(lastJob, false);
  loadRecent();
});
