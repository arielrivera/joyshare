// The main screen: paste a link, pick a size, watch progress, send the file.
// One step shows at a time, so the finished file is never hidden below the fold.
// $, api(), showError(), fmtWhen(), copyFrom() come from auth.js; t() from i18n.js.
const MB = 1024 * 1024;
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

function watch(jobId) {
  if (events) events.close();
  lastJob = null;
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
}

function renderJob(job) {
  if (job.status === "queued" || job.status === "running") {
    paintProgress(job);
  } else if (job.status === "done") {
    renderResult(job, true);
    showStep("result");
  } else {
    // Failed or canceled: back to the size picker (or the link box if we came from a shortcut link).
    if (job.status === "failed") showError($(current ? "make-error" : "lookup-error"), job.error || t("job.failed"));
    showStep(current ? "media" : null);
  }
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

async function makeLink(file) {
  try {
    const link = await api(`/api/files/${file.id}/share`, { method: "POST" });
    $("link-url").value = link.url;
    $("link-box").hidden = false;
    $("link-note").textContent = t("res.linkNote", { when: fmtWhen(link.expires_at) });
  } catch (err) {
    $("link-note").textContent = err.message;
  }
  $("link-note").hidden = false;
}

$("copy").addEventListener("click", () => copyFrom($("link-url"), $("copy")));
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

// Runs each time someone signs in. A link like /#job=12 (opened by the iPhone Shortcut) jumps to that job.
document.addEventListener("joyshare:signed-in", () => {
  loadRecent();
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
