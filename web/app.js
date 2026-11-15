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

// ---------- a timeline with two handles, for picking a clip ----------
// rangeSlider(box, from, to, onChange) draws a track from `from` to `to` seconds with a start and an end handle.
// Drag a handle, tap the track (the nearer handle jumps there), or use the arrow keys (Shift for bigger steps).
// onChange(start, end, which) is called while dragging; which is "start" or "end".
function rangeSlider(box, from, to, onChange) {
  const span = Math.max(to - from, 0.1);
  const state = { start: from, end: to };
  box.replaceChildren();
  box.hidden = false;
  const track = document.createElement("div");
  track.className = "range-track";
  const fill = document.createElement("div");
  fill.className = "range-fill";
  const handles = {};
  for (const which of ["start", "end"]) {
    const h = document.createElement("button");
    h.type = "button";
    h.className = `range-handle ${which}`;
    h.setAttribute("role", "slider");
    h.setAttribute("aria-label", t(which === "start" ? "clip.start" : "clip.end"));
    h.setAttribute("aria-valuemin", String(from));
    h.setAttribute("aria-valuemax", String(to));
    handles[which] = h;
  }
  track.append(fill, handles.start, handles.end);
  box.append(track);

  const at = (v) => `${((v - from) / span) * 100}%`;
  const paint = () => {
    handles.start.style.left = at(state.start);
    handles.end.style.left = at(state.end);
    fill.style.left = at(state.start);
    fill.style.width = `${((state.end - state.start) / span) * 100}%`;
    for (const which of ["start", "end"]) {
      handles[which].setAttribute("aria-valuenow", String(state[which]));
      handles[which].setAttribute("aria-valuetext", fmtClock(state[which]));
    }
  };
  const move = (which, value) => {
    value = Math.round(Math.min(Math.max(value, from), to) * 10) / 10;
    if (which === "start") state.start = Math.min(value, state.end - 1);
    else state.end = Math.max(value, state.start + 1);
    state.start = Math.max(state.start, from);
    state.end = Math.min(state.end, to);
    paint();
    onChange(state.start, state.end, which);
  };
  const valueAt = (clientX) => {
    const r = track.getBoundingClientRect();
    return from + ((clientX - r.left) / Math.max(r.width, 1)) * span;
  };
  let dragging = null;
  for (const which of ["start", "end"]) {
    const h = handles[which];
    h.addEventListener("pointerdown", (e) => { dragging = which; h.setPointerCapture(e.pointerId); e.preventDefault(); });
    h.addEventListener("pointermove", (e) => { if (dragging === which) move(which, valueAt(e.clientX)); });
    h.addEventListener("pointerup", () => { dragging = null; });
    h.addEventListener("pointercancel", () => { dragging = null; });
    h.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 5 : 0.5;
      const keys = { ArrowLeft: -step, ArrowDown: -step, ArrowRight: step, ArrowUp: step };
      if (e.key in keys) { move(which, state[which] + keys[e.key]); e.preventDefault(); }
      else if (e.key === "Home") { move(which, from); e.preventDefault(); }
      else if (e.key === "End") { move(which, to); e.preventDefault(); }
    });
  }
  track.addEventListener("pointerdown", (e) => {
    if (e.target !== track && e.target !== fill) return;
    const value = valueAt(e.clientX);
    const which = Math.abs(value - state.start) <= Math.abs(value - state.end) ? "start" : "end";
    move(which, value);
    handles[which].focus();
  });
  paint();
  return {
    set(start, end) { state.start = start; state.end = end; paint(); },
    get: () => ({ ...state }),
  };
}

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

// ---------- one-tap mode: choosing a size for the person ----------

const EASY_SIZE = 25 * MB;   // small enough to send in a chat without a long wait

// Returns { preset, target_mb? } or null when nothing can be made without asking.
// The person's chosen size comes first; "easy" (or a chosen size this video doesn't offer) picks one that's quick to send.
function autoPick({ presets }) {
  const usable = presets.filter((p) => p.allowed);
  const chosen = prefs.size_pick !== "easy" && usable.find((p) => p.id === prefs.size_pick);
  if (chosen) return { preset: chosen.id };
  const usual = usable.find((p) => p.recommended) || usable.find((p) => p.kind === "video");
  if (usual && usual.id !== "fit" && (!usual.est_bytes || usual.est_bytes <= EASY_SIZE)) return { preset: usual.id };
  // Too big to send comfortably: shrink it to fit.
  const fit = usable.find((p) => p.id === "fit" && p.targets && p.targets.length);
  if (fit) {
    const under = fit.targets.filter((x) => x.mb <= 25).pop() || fit.targets[0];
    return { preset: "fit", target_mb: under.mb };
  }
  const smallest = usable.filter((p) => p.kind === "video" && p.id !== "fit" && p.est_bytes)
    .sort((a, b) => a.est_bytes - b.est_bytes)[0];
  const choice = smallest || usual || usable.find((p) => p.id !== "fit");
  return choice ? { preset: choice.id } : null;
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
    $("size-remember").checked = false;
    renderMedia();
    // One-tap mode: no size step. A sensible size is picked and the file is made straight away.
    // "Another size" on the finished screen still leads to the size step.
    const pick = prefs.sizes === "ask" ? null : autoPick(current);
    if (pick) {
      try {
        const job = await api("/api/jobs", { method: "POST", body: JSON.stringify({ media_id: current.media.id, ...pick }) });
        watch(job.id);
        return;
      } catch (err) {
        showError($("make-error"), err.message);   // couldn't start it: let the person choose
      }
    }
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

let pickSlider = null;   // the timeline on the size step, and which video it belongs to

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
  // The timeline under the boxes: dragging it fills the boxes in, typing in the boxes moves it.
  if (clip.on && media.duration) {
    if (!pickSlider || pickSlider.media !== media.id) {
      const slider = rangeSlider($("clip-range-pick"), 0, media.duration, (start, end) => {
        $("clip-start").value = fmtClock(start);
        $("clip-end").value = fmtClock(end);
        renderMedia();
      });
      pickSlider = { media: media.id, slider };
    }
    if (clip.ok) pickSlider.slider.set(clip.start, clip.end);
  } else {
    $("clip-range-pick").hidden = true;
    if (!clip.on) pickSlider = null;
  }
  // A clip is smaller than the whole: sizes shrink by the same share.
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
  if ($("size-remember").checked) {
    // From now on links are made straight away at this size. Changed back in the pencil panel, under Sizes.
    setPrefs({ sizes: "auto", size_pick: ["best", "720", "480", "audio"].includes(picked.value) ? picked.value : "easy" });
    $("size-remember").checked = false;
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
// Under the finished video: drag the two handles (or tap Start here / End here while it plays), check it with
// "Play the clip", then make it. The clip is cut from this very file, so nothing is fetched from the platform again.
function setUpClipTools(job, player) {
  const tools = $("clip-tools");
  const file = job.file;
  tools.hidden = !job.media || !file || !file.duration;
  if (tools.hidden) return;
  // Times count from the start of the whole video, even when this file is itself a clip.
  const from = job.clip ? job.clip[0] : 0;
  const to = Math.round((from + file.duration) * 10) / 10;
  let playing = false;
  const stopPlaying = () => {
    playing = false;
    player.removeEventListener("timeupdate", watchEnd);
    $("clip-play").textContent = t("clip.play");
  };
  const watchEnd = () => {
    if (player.currentTime >= slider.get().end - from - 0.05) { player.pause(); stopPlaying(); }
  };
  const paint = (start, end) => {
    const whole = start <= from + 0.3 && end >= to - 0.3;
    $("clip-picked").textContent = t("clip.picked", { range: fmtRange([start, end]), len: fmtClock(end - start) });
    $("clip-make").disabled = whole || end - start < 1;
    showError($("clip-error"), "");
  };
  const slider = rangeSlider($("clip-range"), from, to, (start, end, which) => {
    if (playing) { player.pause(); stopPlaying(); }
    // Show the frame where the handle is.
    try { player.currentTime = (which === "start" ? start : end) - from; } catch { /* not loaded yet */ }
    paint(start, end);
  });
  const now = () => Math.round((from + (player.currentTime || 0)) * 10) / 10;
  $("clip-here-start").onclick = () => {
    const { end } = slider.get();
    const start = Math.min(now(), end - 1);
    slider.set(Math.max(start, from), end);
    paint(slider.get().start, end);
  };
  $("clip-here-end").onclick = () => {
    const { start } = slider.get();
    const end = Math.max(now(), start + 1);
    slider.set(start, Math.min(end, to));
    paint(start, slider.get().end);
  };
  $("clip-play").onclick = () => {
    if (playing) { player.pause(); stopPlaying(); return; }
    const { start } = slider.get();
    try { player.currentTime = start - from; } catch { /* not loaded yet */ }
    playing = true;
    $("clip-play").textContent = t("clip.stop");
    player.addEventListener("timeupdate", watchEnd);
    player.play().catch(stopPlaying);
  };
  player.addEventListener("pause", () => { if (playing) stopPlaying(); });
  $("clip-make").onclick = async () => {
    const { start, end } = slider.get();
    const body = { media_id: job.media.id, preset: job.preset, clip_start: start, clip_end: end, from_file: file.id };
    if (job.preset === "fit") body.target_mb = job.target_mb;
    try {
      const made = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
      player.pause();
      watch(made.id, job.media);
    } catch (err) {
      showError($("clip-error"), err.message);
    }
  };
  paint(from, to);
}

// The phone's share sheet needs the whole file in memory and a fresh tap,
// so we fetch it ahead of time and only then show the button.
// Fetches the finished file into memory as something the share sheet accepts. null when it can't be shared that way.
async function fetchShareFile(job, file) {
  if (!navigator.canShare || file.size > SHARE_SHEET_MAX) return null;
  try {
    const blob = await (await fetch(file.stream_url)).blob();
    const ext = file.kind === "audio" ? "m4a" : "mp4";
    const base = (job.media && job.media.title ? job.media.title : brandName()).replace(/[\\/:*?"<>|]+/g, " ").slice(0, 60).trim() || "video";
    const candidate = new File([blob], `${base}.${ext}`, { type: file.mime });
    return navigator.canShare({ files: [candidate] }) ? candidate : null;
  } catch {
    return null;
  }
}

// A phone or tablet: there the share sheet is the natural way to send a video or keep it in Photos.
const touchDevice = () => window.matchMedia("(pointer: coarse)").matches;

async function prepareShare(job, file) {
  const button = $("share"), note = $("share-note"), help = $("share-help"), more = $("more-options");
  shareFile = null;
  note.hidden = true;
  help.hidden = true;
  // Without the share sheet, Download and the link are simply the buttons.
  const plain = () => { button.hidden = true; more.open = true; more.classList.add("plain"); };
  if (!navigator.canShare) { plain(); return; }
  if (file.size > SHARE_SHEET_MAX) {
    note.textContent = t("res.tooBig");
    note.hidden = false;
    plain();
    return;
  }
  // On a phone: one big button, with Download and the link folded under "More options".
  const first = touchDevice();
  more.classList.toggle("plain", !first);
  more.open = !first;
  button.hidden = false;
  button.disabled = true;
  button.textContent = t("res.preparing");
  const ready = await fetchShareFile(job, file);
  if (lastJob !== job) return;      // something newer is on screen
  if (!ready) { plain(); return; }
  shareFile = ready;
  button.disabled = false;
  button.textContent = t("res.send");
  help.hidden = false;
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

// Two ways to see Recent, switched with the icons beside its heading and saved to the account:
//   "list": short rows (picture, title, details). Tap one and its buttons open right under it.
//   "grid": pictures, like the Photos app. ↗ sends; tapping a picture opens it on the finished screen.
let openRecentId = null;   // the row that is open in the list, kept when the list is redrawn

// Shows an earlier video on the finished screen: player, Send or save, link, and the clip timeline.
function openFinished(job, toClip) {
  if (events) { events.close(); events = null; }
  stopScene();
  current = null;   // no size step behind it
  lastJob = job;
  renderResult(job, true);
  showStep("result");
  if (toClip) setTimeout(() => $("clip-tools").scrollIntoView({ block: "center", behavior: "smooth" }), 350);
}

const recentDetails = (job) => {
  const preset = job.preset === "fit" ? t("recent.fit", { mb: job.target_mb }) : t(`short.${job.preset}`);
  const state = job.status === "done" && job.file ? fmtSize(job.file.size)
    : job.status === "done" ? t("recent.expired")
    : job.status === "failed" ? t("recent.failed")
    : job.status === "canceled" ? t("recent.canceled") : t("recent.progress");
  return [preset, state, job.clip ? `✂️ ${fmtRange(job.clip)}` : ""].filter(Boolean).join(" · ");
};
const recentTitle = (job) => (job.media && job.media.title) || t("media.untitled");
const canSendFile = (job) => Boolean(job.status === "done" && job.file && navigator.canShare && job.file.size <= SHARE_SHEET_MAX);

function picture(job, className) {
  if (!job.media || !job.media.thumb_url) return null;
  const img = document.createElement("img");
  img.className = className;
  img.alt = "";
  img.onerror = () => img.remove();
  img.src = job.media.thumb_url;
  return img;
}

// The share sheet for one finished file. The file is fetched first; if the phone then says the tap is too old,
// the button asks for one more tap. When it can't be shared this way, onFail() decides what happens instead.
function sendButton(job, label, className, onFail) {
  let ready = null;
  const send = document.createElement("button");
  send.type = "button";
  send.className = className;
  send.innerHTML = label;
  send.addEventListener("click", async (e) => {
    e.stopPropagation();
    const offer = async () => {
      try { await navigator.share({ files: [ready] }); send.innerHTML = label; }
      catch (err) { if (err && err.name === "NotAllowedError") send.textContent = t("recent.tapToSend"); else send.innerHTML = label; }
    };
    if (ready) { await offer(); return; }
    send.disabled = true;
    send.textContent = t("res.preparing");
    ready = await fetchShareFile(job, job.file);
    send.disabled = false;
    send.innerHTML = label;
    if (!ready) { onFail(); return; }
    await offer();
  });
  return send;
}

// Copy link, saying clearly that it worked (the button flips, and a line stays under the row).
function copyLinkButton(job, note) {
  const copy = chip(t("recent.link"), async () => {
    copy.disabled = true;
    note.className = "row-note";
    try {
      const { link, copied } = await linkToClipboard(job.file);
      const when = t(link.ends_soon ? "recent.linkSoon" : "recent.linkUntil", { when: fmtWhen(link.expires_at) });
      if (copied) {
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
  return copy;
}

// What a row's panel holds, by the state of that video.
function recentPanel(job) {
  const panel = document.createElement("div");
  panel.className = "rc-panel";
  const note = document.createElement("p");
  note.className = "row-note";
  note.setAttribute("role", "status");
  note.hidden = true;
  if (job.status === "done" && job.file) {
    if (canSendFile(job)) {
      panel.append(sendButton(job, t("res.send"), "rc-send", () => {
        note.className = "row-note bad";
        note.textContent = t("recent.cantSend");
        note.hidden = false;
      }));
    }
    const buttons = document.createElement("div");
    buttons.className = "rc-buttons";
    const download = document.createElement("a");
    download.className = "button secondary";
    download.href = job.file.download_url;
    download.textContent = t("recent.saveFile");
    buttons.append(copyLinkButton(job, note));
    if (job.media && job.file.duration) buttons.append(chip(t("recent.clip"), () => openFinished(job, true)));
    buttons.append(download);
    panel.append(buttons);
  } else if (job.status === "queued" || job.status === "running") {
    panel.append(chip(t("recent.showProgress"), () => watch(job.id, job.media)));
  } else {
    if (job.status === "failed" && job.error) {
      const why = document.createElement("p");
      why.className = "muted";
      why.textContent = job.error;
      panel.append(why);
    }
    if (job.media) panel.append(chip(t("recent.again"), () => makeAgain(job, note)));
  }
  panel.append(note);
  return panel;
}

function recentRow(job) {
  const li = document.createElement("li");
  li.className = "rc-item";
  const row = document.createElement("button");
  row.type = "button";
  row.className = "rc-row";
  row.setAttribute("aria-expanded", "false");
  const words = document.createElement("span");
  words.className = "rc-words";
  const title = document.createElement("span");
  title.className = "rc-title";
  title.textContent = recentTitle(job);
  const details = document.createElement("span");
  details.className = "rc-details";
  details.textContent = recentDetails(job);
  words.append(title, details);
  const chevron = document.createElement("span");
  chevron.className = "rc-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "›";
  const img = picture(job, "rc-thumb");
  if (img) row.append(img); else { const blank = document.createElement("span"); blank.className = "rc-thumb blank"; row.append(blank); }
  row.append(words, chevron);
  const panel = recentPanel(job);
  const setOpen = (open) => {
    li.classList.toggle("open", open);
    row.setAttribute("aria-expanded", String(open));
    panel.hidden = !open;
  };
  setOpen(openRecentId === job.id);
  row.addEventListener("click", () => {
    const opening = !li.classList.contains("open");
    for (const other of $("recent-list").querySelectorAll(".rc-item.open")) {
      other.classList.remove("open");
      other.querySelector(".rc-row").setAttribute("aria-expanded", "false");
      other.querySelector(".rc-panel").hidden = true;
    }
    openRecentId = opening ? job.id : null;
    setOpen(opening);
  });
  li.append(row, panel);
  return li;
}

function recentTile(job) {
  const li = document.createElement("li");
  li.className = "rc-tile-item";
  const tile = document.createElement("button");
  tile.type = "button";
  tile.className = "rc-tile";
  tile.setAttribute("aria-label", t("recent.openVideo", { title: recentTitle(job) }));
  const img = picture(job, "rc-tile-img");
  if (img) tile.append(img);
  const shade = document.createElement("span");
  shade.className = "rc-shade";
  const words = document.createElement("span");
  words.className = "rc-tile-words";
  const title = document.createElement("span");
  title.className = "rc-title";
  title.textContent = recentTitle(job);
  const details = document.createElement("span");
  details.className = "rc-details";
  details.textContent = recentDetails(job);
  words.append(title, details);
  tile.append(shade, words);
  const finished = job.status === "done" && job.file;
  if (!finished) {
    li.classList.add("dim");
    const badge = document.createElement("span");
    badge.className = "rc-badge";
    badge.textContent = job.status === "queued" || job.status === "running" ? t("recent.progress") : `↻ ${t("recent.again")}`;
    tile.append(badge);
  }
  const note = document.createElement("p");
  note.className = "row-note";
  note.hidden = true;
  tile.addEventListener("click", () => {
    if (finished) openFinished(job, false);
    else if (job.status === "queued" || job.status === "running") watch(job.id, job.media);
    else if (job.media) makeAgain(job, note);
  });
  li.append(tile);
  if (canSendFile(job)) li.append(sendButton(job, "↗", "rc-tile-send", () => openFinished(job, false)));
  li.append(note);
  return li;
}

function paintRecentToggle() {
  for (const b of document.querySelectorAll("#recent .view-toggle [data-view]")) {
    b.setAttribute("aria-pressed", String(b.dataset.view === prefs.recent));
  }
}

let recentJobs = [];

function drawRecent() {
  const list = $("recent-list");
  const grid = prefs.recent === "grid";
  list.classList.toggle("grid", grid);
  list.replaceChildren(...recentJobs.map((job) => (grid ? recentTile(job) : recentRow(job))));
  $("recent").hidden = recentJobs.length === 0;
  paintRecentToggle();
}

async function loadRecent() {
  try { recentJobs = await api("/api/jobs?limit=12"); } catch { return; }
  drawRecent();
}

for (const b of document.querySelectorAll("#recent .view-toggle [data-view]")) {
  b.addEventListener("click", () => {
    if (prefs.recent === b.dataset.view) return;
    setPrefs({ recent: b.dataset.view });   // saved here and to the account
    drawRecent();
  });
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

// ---------- opened with a link already attached ----------
// An address like /#url=https%3A%2F%2Fx.com%2F… looks that link up as soon as the app opens.
// The iPhone Shortcut uses it: Share -> vidshare in another app lands here with the video's link.
function openAttachedLink() {
  const attached = location.hash.match(/^#url=(.+)$/);
  if (!attached || !me) return false;
  history.replaceState(null, "", location.pathname);
  let link = attached[1];
  try { link = decodeURIComponent(link); } catch { /* use it as it came */ }
  showScreen("app");
  $("url").value = link;
  syncUrlTools();
  lookUp();
  return true;
}
window.addEventListener("hashchange", openAttachedLink);

// ---------- how it works, and the first-time intro ----------

const INTRO_KEY = "joyshare_intro";
const introSeen = () => { try { return localStorage.getItem(INTRO_KEY) === "1"; } catch { return true; } };
function closeIntro() {
  $("intro").hidden = true;
  try { localStorage.setItem(INTRO_KEY, "1"); } catch { /* private window */ }
}
$("intro-ok").addEventListener("click", closeIntro);

function openHelp() {
  closeIntro();
  $("shortcut-address").value = `${location.origin}/#url=`;
  showScreen("help");
  window.scrollTo({ top: 0 });
}
$("intro-more").addEventListener("click", openHelp);
$("open-help").addEventListener("click", () => { hideHint(); openHelp(); });
$("close-help").addEventListener("click", () => showScreen("app"));
$("shortcut-copy").addEventListener("click", () => copyFrom($("shortcut-address"), $("shortcut-copy")));

// Sizes in the style panel: see the sizes every time (the default), or always make one size straight away.
const sizeMode = () => (prefs.sizes === "auto" ? prefs.size_pick : "ask");
$("size-mode").addEventListener("change", () => {
  const value = $("size-mode").value;
  setPrefs(value === "ask" ? { sizes: "ask" } : { sizes: "auto", size_pick: value });
});
$("open-style").addEventListener("click", () => { $("size-mode").value = sizeMode(); });

// ---------- reloading ----------
// A page added to the iPhone home screen has no address bar and no pull-to-reload, so this adds one:
// pull down from the very top and let go. The video on screen (in progress or finished) comes back after the reload.

const homeScreenApp = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

function reloadPage() {
  const onScreen = lastJob && (!$("job").hidden || !$("result").hidden) ? lastJob.id : null;
  if (onScreen) history.replaceState(null, "", `${location.pathname}#job=${onScreen}`);
  location.reload();
}

(() => {
  const pull = $("pull");
  const READY = 80;           // how far to pull, in pixels, before letting go reloads
  let startY = null, distance = 0;
  const reset = () => {
    startY = null;
    distance = 0;
    pull.classList.remove("ready", "show");
    pull.style.removeProperty("--pull");
  };
  document.addEventListener("touchstart", (e) => {
    if (!homeScreenApp() || window.scrollY > 0 || e.touches.length !== 1) return;
    // Not while dragging something that moves on its own: the clip timeline, a slider, the video.
    const el = e.target instanceof Element ? e.target : null;
    if (el && el.closest(".range, input, textarea, select, video, audio, .menu-panel")) return;
    startY = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener("touchmove", (e) => {
    if (startY === null) return;
    distance = e.touches[0].clientY - startY;
    if (distance <= 0 || window.scrollY > 0) { pull.classList.remove("show"); return; }
    const shown = Math.min(distance * 0.55, READY + 30);   // follows the finger, a little slower
    pull.style.setProperty("--pull", `${shown}px`);
    pull.classList.add("show");
    pull.classList.toggle("ready", distance * 0.55 >= READY);
  }, { passive: true });
  document.addEventListener("touchend", () => {
    if (startY === null) return;
    if (pull.classList.contains("ready")) {
      pull.classList.add("spinning");
      setTimeout(reloadPage, 250);   // long enough to see the spinner start
      return;
    }
    reset();
  }, { passive: true });
  document.addEventListener("touchcancel", reset, { passive: true });
})();

// Coming back to the app after a while: refresh the list, and offer a reload if the app was updated meanwhile.
let hiddenAt = 0;
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) { hiddenAt = Date.now(); return; }
  if (!me || Date.now() - hiddenAt < 30_000) return;
  loadRecent();
  try {
    const health = await (await fetch("/api/health", { cache: "no-store" })).json();
    const mine = ASSET_BASE.split("/").filter(Boolean).pop();
    if (health.version && mine && health.version !== mine) $("update-banner").hidden = false;
  } catch { /* offline for now: nothing to say */ }
});
$("update-reload").addEventListener("click", reloadPage);

// Runs each time someone signs in. A link like /#job=12 shows that video (also after a reload);
// /#url=… looks a link up.
document.addEventListener("joyshare:signed-in", async () => {
  loadRecent();
  $("size-mode").value = sizeMode();
  const match = location.hash.match(/^#job=(\d+)$/);
  if (match) {
    history.replaceState(null, "", location.pathname);
    try {
      const job = await api(`/api/jobs/${match[1]}`);
      if (job.status === "done" && job.file) openFinished(job, false);   // finished: straight to it, no animation
      else watch(job.id, job.media);
    } catch { /* gone: just the main screen */ }
    return;
  }
  if (openAttachedLink()) return;
  $("intro").hidden = introSeen();
  if (introSeen()) maybeShowHint();   // one tip at a time
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
