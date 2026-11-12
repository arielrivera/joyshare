// joyshare phase 1 interface. Plain on purpose: the API is the part that lasts.
const $ = (id) => document.getElementById(id);
const MB = 1024 * 1024;
const SHARE_SHEET_MAX = 100 * MB; // bigger files are too heavy to hand to the phone's share sheet

let current = null;   // { media, presets }
let events = null;    // EventSource for the running job
let shareFile = null; // File prepared for the share sheet

const fmtSize = (bytes) => {
  if (!bytes) return "size unknown";
  return bytes >= 10 * MB ? `${Math.round(bytes / MB)} MB` : `${(bytes / MB).toFixed(1)} MB`;
};
const fmtDuration = (s) => {
  if (!s) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};
const fmtWhen = (epoch) => new Date(epoch * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error((data && data.detail) || "Something went wrong. Try again.");
  return data;
}

function showError(el, message) {
  el.textContent = message || "";
  el.hidden = !message;
}

// ---------- look up a link ----------

$("lookup").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError($("lookup-error"), "");
  const button = $("lookup-button");
  button.disabled = true;
  button.textContent = "Looking…";
  try {
    current = await api("/api/inspect", { method: "POST", body: JSON.stringify({ url: $("url").value }) });
    renderMedia();
  } catch (err) {
    $("media").hidden = true;
    showError($("lookup-error"), err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Look up";
  }
});

function renderMedia() {
  const { media, presets } = current;
  $("title").textContent = media.title || "Untitled video";
  $("meta").textContent = [media.uploader, media.platform_label, fmtDuration(media.duration)].filter(Boolean).join(" · ");
  $("experimental").hidden = !media.experimental;
  const thumb = $("thumb");
  thumb.hidden = !media.thumbnail;
  if (media.thumbnail) thumb.src = media.thumbnail;

  const box = $("presets");
  box.replaceChildren();
  let checked = false;
  for (const p of presets) {
    const label = document.createElement("label");
    label.className = "preset" + (p.allowed ? "" : " off");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "preset";
    radio.value = p.id;
    radio.id = `preset-${p.id}`;
    radio.disabled = !p.allowed;
    if (p.recommended) {
      radio.checked = true;
      checked = true;
    }
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = `${p.label} · ${p.detail}`;
    const size = document.createElement("span");
    size.className = "size";
    label.append(radio, name, size);

    if (p.id === "fit" && p.allowed) {
      const select = document.createElement("select");
      select.id = "fit-target";
      select.setAttribute("aria-label", "Target size");
      for (const t of p.targets) {
        const option = document.createElement("option");
        option.value = t.mb;
        option.textContent = `under ${t.mb} MB (${t.height}p)`;
        select.append(option);
      }
      const preferred = p.targets.find((t) => t.mb === 25) || p.targets[0];
      select.value = preferred.mb;
      select.addEventListener("change", () => { radio.checked = true; });
      size.append(select);
    } else if (p.allowed) {
      size.textContent = p.est_bytes ? `about ${fmtSize(p.est_bytes)}` : "size unknown";
    }
    const extra = p.reason || (p.needs_convert ? "Needs converting, so it takes longer." : "");
    if (extra) {
      const note = document.createElement("span");
      note.className = "extra";
      note.textContent = extra;
      label.append(note);
    }
    box.append(label);
  }
  if (!checked) {
    const first = box.querySelector("input:not(:disabled)");
    if (first) first.checked = true;
  }
  $("make-button").disabled = !box.querySelector("input:not(:disabled)");
  showError($("make-error"), "");
  $("media").hidden = false;
}

// ---------- make the file ----------

$("make").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError($("make-error"), "");
  const picked = document.querySelector('input[name="preset"]:checked');
  if (!picked) return;
  const body = { media_id: current.media.id, preset: picked.value };
  if (picked.value === "fit") body.target_mb = Number($("fit-target").value);
  try {
    const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    watch(job.id);
  } catch (err) {
    showError($("make-error"), err.message);
  }
});

const STAGES = { starting: "Starting", downloading: "Downloading", converting: "Converting", done: "Done" };

function watch(jobId) {
  if (events) events.close();
  $("result").hidden = true;
  $("job").hidden = false;
  $("make-button").disabled = true;
  $("cancel").onclick = () => api(`/api/jobs/${jobId}`, { method: "DELETE" }).catch(() => {});
  events = new EventSource(`/api/jobs/${jobId}/events`);
  events.onmessage = (msg) => {
    const job = JSON.parse(msg.data);
    renderJob(job);
    if (["done", "failed", "canceled"].includes(job.status)) {
      events.close();
      events = null;
      $("make-button").disabled = false;
      loadRecent();
    }
  };
}

function renderJob(job) {
  const pct = Math.round((job.progress || 0) * 100);
  if (job.status === "queued") {
    $("stage").textContent = "Waiting in line";
    $("bar").removeAttribute("value");
  } else if (job.status === "running") {
    $("stage").textContent = `${STAGES[job.stage] || "Working"} · ${pct}%`;
    $("bar").value = pct;
  } else if (job.status === "failed") {
    $("job").hidden = true;
    showError($("make-error"), job.error || "That didn't work.");
  } else if (job.status === "canceled") {
    $("job").hidden = true;
  } else if (job.status === "done") {
    $("job").hidden = true;
    renderResult(job);
  }
}

// ---------- the finished file ----------

function renderResult(job) {
  const file = job.file;
  if (!file) return;
  $("result-title").textContent = job.reused ? "Ready (you already had this one)" : "Ready";
  const bits = [fmtSize(file.size)];
  if (file.kind === "video" && file.height) bits.push(`${file.height}p`);
  if (file.duration) bits.push(fmtDuration(file.duration));
  bits.push(`kept until ${fmtWhen(file.expires_at)}`);
  $("result-meta").textContent = bits.join(" · ");

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
  $("result").hidden = false;
}

// The phone's share sheet needs the whole file in memory and a fresh tap,
// so we fetch it ahead of time and only then enable the button.
async function prepareShare(job, file) {
  const button = $("share"), note = $("share-note");
  shareFile = null;
  button.hidden = true;
  note.hidden = true;
  if (!navigator.canShare) return;
  if (file.size > SHARE_SHEET_MAX) {
    note.textContent = "This file is too big for the share sheet. Use Download or a link instead.";
    note.hidden = false;
    return;
  }
  try {
    const blob = await (await fetch(file.stream_url)).blob();
    const ext = file.kind === "audio" ? "m4a" : "mp4";
    const base = (job.media && job.media.title ? job.media.title : "joyshare").replace(/[\\/:*?"<>|]+/g, " ").slice(0, 60).trim() || "joyshare";
    const candidate = new File([blob], `${base}.${ext}`, { type: file.mime });
    if (!navigator.canShare({ files: [candidate] })) throw new Error("not shareable");
    shareFile = candidate;
    button.hidden = false; // shown only once the file is ready, so the buttons don't jump around
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
    $("link-note").textContent = `Anyone with this link can watch until ${fmtWhen(link.expires_at)}.`;
    $("link-note").hidden = false;
  } catch (err) {
    $("link-note").textContent = err.message;
    $("link-note").hidden = false;
  }
}

$("copy").addEventListener("click", async () => {
  const input = $("link-url");
  try {
    await navigator.clipboard.writeText(input.value);
    $("copy").textContent = "Copied";
  } catch {
    input.select();
    $("copy").textContent = "Select and copy";
  }
  setTimeout(() => { $("copy").textContent = "Copy"; }, 2000);
});

// ---------- recent ----------

const PRESET_NAMES = { best: "Best", 720: "720p", 480: "480p", fit: "Fit", audio: "Audio" };

async function loadRecent() {
  let jobs = [];
  try { jobs = await api("/api/jobs?limit=10"); } catch { return; }
  const list = $("recent-list");
  list.replaceChildren();
  for (const job of jobs) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    const preset = job.preset === "fit" ? `Fit ${job.target_mb} MB` : PRESET_NAMES[job.preset] || job.preset;
    name.textContent = `${(job.media && job.media.title) || "Untitled"} · ${preset}`;
    const state = document.createElement("span");
    if (job.status === "done" && job.file) {
      const a = document.createElement("a");
      a.href = job.file.download_url;
      a.textContent = `Download (${fmtSize(job.file.size)})`;
      state.append(a);
    } else if (job.status === "done") {
      state.textContent = "Expired";
    } else if (job.status === "failed") {
      state.textContent = "Failed";
      state.title = job.error || "";
    } else {
      state.textContent = job.status === "canceled" ? "Canceled" : "In progress";
    }
    li.append(name, state);
    list.append(li);
  }
  $("recent").hidden = jobs.length === 0;
}

loadRecent();
