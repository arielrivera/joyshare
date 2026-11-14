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
  for (const id of ["media", "job", "result"]) $(id).hidden = id !== step;
  if (!step) return;
  const focus = { media: "title", job: "percent", result: "result-title" }[step];
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
  $("lookup").scrollIntoView({ block: "start", behavior: "smooth" });
  $("url").focus({ preventScroll: true });
}

// ---------- look up a link ----------

async function lookUp() {
  const url = $("url").value.trim();
  if (!url) return;
  showError($("lookup-error"), "");
  const button = $("lookup-button");
  button.disabled = true;
  button.textContent = t("link.looking");
  try {
    current = await api("/api/inspect", { method: "POST", body: JSON.stringify({ url }) });
    $("url").value = ""; // ready for the next link
    renderMedia();
    showStep("media");
  } catch (err) {
    showError($("lookup-error"), err.message);
  } finally {
    button.disabled = false;
    button.textContent = t("link.lookup");
  }
}

$("lookup").addEventListener("submit", (e) => { e.preventDefault(); lookUp(); });

// Pasting a link looks it up straight away: no extra tap.
$("url").addEventListener("paste", () => setTimeout(() => { if (/^https?:\/\/\S+$/i.test($("url").value.trim())) lookUp(); }, 0));

if (navigator.clipboard && navigator.clipboard.readText) {
  $("paste").hidden = false;
  $("paste").addEventListener("click", async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (text) { $("url").value = text; lookUp(); }
    } catch {
      $("url").focus(); // the browser said no: paste by hand
    }
  });
}

function renderMedia() {
  if (!current) return;
  const { media, presets } = current;
  $("title").textContent = media.title || t("media.untitled");
  $("meta").textContent = [media.uploader, media.platform_label, fmtDuration(media.duration)].filter(Boolean).join(" · ");
  $("experimental").hidden = !media.experimental;
  const thumb = $("thumb");
  thumb.hidden = !media.thumbnail;
  if (media.thumbnail) thumb.src = media.thumbnail;

  const picked = document.querySelector('input[name="preset"]:checked');
  const keep = picked ? picked.value : null;
  const keepTarget = $("fit-target") ? $("fit-target").value : null;
  const box = $("presets");
  box.replaceChildren();
  for (const p of presets) {
    const label = document.createElement("label");
    label.className = "preset" + (p.allowed ? "" : " off");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "preset";
    radio.value = p.id;
    radio.id = `preset-${p.id}`;
    radio.disabled = !p.allowed;
    radio.checked = p.allowed && (keep ? keep === p.id : Boolean(p.recommended));
    const name = document.createElement("span");
    name.className = "name";
    const detail = p.id === "fit" ? t("preset.fitDetail") : p.detail;
    name.textContent = `${t(`preset.${p.id}`)} · ${detail}`;
    const size = document.createElement("span");
    size.className = "size";
    label.append(radio, name, size);

    if (p.id === "fit" && p.allowed) {
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
    } else if (p.allowed) {
      size.textContent = p.est_bytes ? t("size.about", { size: fmtSize(p.est_bytes) }) : t("size.unknown");
    }
    const extra = p.reason || (p.needs_convert ? t("preset.convert") : "");
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

function watch(jobId) {
  if (events) events.close();
  lastJob = null;
  startScene();
  paintProgress({ status: "queued", progress: 0, media: current && current.media });
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
  bits.push(t("res.kept", { when: fmtWhen(file.expires_at) }));
  $("result-meta").textContent = bits.join(" · ");
  $("again").hidden = !current; // no size picker to go back to when opened from a shortcut link
  if (!fresh) return; // language change: only the words above needed repainting

  const player = document.createElement(file.kind === "audio" ? "audio" : "video");
  player.controls = true;
  player.preload = "metadata";
  player.playsInline = true;
  if (file.kind === "video" && job.media && job.media.thumbnail) player.poster = job.media.thumbnail;
  player.src = file.stream_url;
  $("player").replaceChildren(player);

  $("download").href = file.download_url;
  $("link-box").hidden = true;
  $("link-note").hidden = true;
  $("link-copied").hidden = true;
  $("link").onclick = () => makeLink(file);
  prepareShare(job, file);
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

// "Get a link for friends": make the link and put it on the clipboard in the same tap.
async function makeLink(file) {
  $("link-copied").hidden = true;
  const request = api(`/api/files/${file.id}/share`, { method: "POST" });
  // Browsers only allow copying as a direct result of a tap. Handing the clipboard a promise (instead of
  // waiting for the link first) keeps that permission alive while the link is being made. Safari needs this.
  let copying = null;
  if (navigator.clipboard && window.ClipboardItem) {
    try {
      const text = request.then((link) => new Blob([link.url], { type: "text/plain" }));
      copying = navigator.clipboard.write([new ClipboardItem({ "text/plain": text })]);
    } catch { copying = null; }
  }
  try {
    const link = await request;
    $("link-url").value = link.url;
    $("link-box").hidden = false;
    $("link-note").textContent = t("res.linkNote", { when: fmtWhen(link.expires_at) });
    let copied = false;
    try {
      if (copying) { await copying; copied = true; }
      else if (navigator.clipboard) { await navigator.clipboard.writeText(link.url); copied = true; }
    } catch { copied = false; }
    showCopied(copied);
  } catch (err) {
    if (copying) copying.catch(() => {});
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

async function loadRecent() {
  let jobs = [];
  try { jobs = await api("/api/jobs?limit=10"); } catch { return; }
  const list = $("recent-list");
  list.replaceChildren();
  for (const job of jobs) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    const preset = job.preset === "fit" ? t("recent.fit", { mb: job.target_mb }) : t(`short.${job.preset}`);
    name.textContent = `${(job.media && job.media.title) || t("media.untitled")} · ${preset}`;
    const state = document.createElement("span");
    if (job.status === "done" && job.file) {
      const a = document.createElement("a");
      a.href = job.file.download_url;
      a.textContent = t("recent.download", { size: fmtSize(job.file.size) });
      state.append(a);
    } else if (job.status === "done") {
      state.textContent = t("recent.expired");
    } else if (job.status === "failed") {
      state.textContent = t("recent.failed");
      state.title = job.error || "";
    } else {
      state.textContent = job.status === "canceled" ? t("recent.canceled") : t("recent.progress");
    }
    li.append(name, state);
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
