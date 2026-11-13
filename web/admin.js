// The admin panel: numbers, everyone's videos and links, people, limits, alerts and the activity log.
// $, api(), showError(), fmtWhen(), row(), showInvite(), showScreen(), passkeyProblem() come from auth.js;
// fmtSize() from app.js; t() from i18n.js. Changing anything asks for the passkey again when needed (api() does that).

let adminTab = "overview";
let adminSettings = null; // { settings, limits, platforms, alert_events } from the server

// The order limits appear in, and the unit shown in each label.
const LIMIT_ORDER = ["max_file_mb", "max_duration_min", "max_concurrent_jobs", "source_ttl_min",
  "output_ttl_hours", "link_ttl_hours", "disk_warn_pct", "disk_pause_pct", "max_source_mb"];

async function adminAct(fn, okMessage) {
  showError($("admin-error"), "");
  $("admin-ok").hidden = true;
  try {
    await fn();
    if (okMessage) {
      $("admin-ok").textContent = okMessage;
      $("admin-ok").hidden = false;
    }
  } catch (err) {
    showError($("admin-error"), err.name && err.name !== "Error" ? passkeyProblem(err) : err.message);
    $("admin-error").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function showAdminTab(name) {
  adminTab = name;
  for (const pane of document.querySelectorAll("#admin [data-pane]")) pane.hidden = pane.dataset.pane !== name;
  for (const tab of document.querySelectorAll("#admin-tabs [data-tab]")) tab.setAttribute("aria-pressed", String(tab.dataset.tab === name));
  showError($("admin-error"), "");
  $("admin-ok").hidden = true;
  adminAct(ADMIN_LOADERS[name]);
}

// ---------- Overview ----------

function tile(label, value, detail, warn) {
  const box = document.createElement("div");
  box.className = "tile" + (warn ? " warn" : "");
  for (const [cls, text] of [["k", label], ["v", value], ["d", detail]]) {
    if (text === undefined || text === null || text === "") continue;
    const el = document.createElement("span");
    el.className = cls;
    el.textContent = text;
    box.append(el);
  }
  return box;
}

async function loadOverview() {
  const d = await api("/api/admin/overview");
  const today = d.jobs_today, week = d.jobs_week;
  const sum = (o) => Object.values(o).reduce((a, b) => a + b, 0);
  const failedNote = (o) => (o.failed ? t("adm.nFailed", { n: o.failed }) : t("adm.noneFailed"));
  const platforms = Object.entries(d.jobs_by_platform_week).sort((a, b) => b[1] - a[1])
    .map(([name, n]) => `${name} ${n}`).join(" · ");
  const disk = d.disk;
  $("adm-tiles").replaceChildren(
    tile(t("adm.today"), String(sum(today)), failedNote(today), Boolean(today.failed)),
    tile(t("adm.week"), String(sum(week)), platforms || failedNote(week), false),
    tile(t("adm.inProgress"), String(d.queue), d.paused ? t("adm.pausedNow") : "", d.paused),
    tile(t("adm.filesKept"), String(d.files), fmtSize(d.files_bytes)),
    tile(t("adm.activeLinks"), String(d.share_links)),
    tile(t("ppl.title"), String(d.people)),
    tile(t("adm.disk"), disk ? `${disk.pct}%` : "—",
      disk ? t("adm.diskOf", { used: fmtGB(disk.used), total: fmtGB(disk.total) }) : "", Boolean(disk && disk.level !== "ok")),
    tile(t("adm.worker"), d.worker_alive ? t("adm.running") : t("adm.stopped"), "", !d.worker_alive),
    tile("yt-dlp", d.yt_dlp),
  );
  const pause = $("adm-pause");
  pause.textContent = d.paused ? t("adm.resume") : t("adm.pause");
  pause.onclick = () => adminAct(async () => {
    await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { paused: !d.paused } }) });
    await loadOverview();
  });
}

const fmtGB = (bytes) => `${(bytes / 1024 ** 3).toFixed(1)} GB`;

$("adm-refresh").addEventListener("click", () => adminAct(loadOverview));

// ---------- Videos ----------

async function loadAdminJobs() {
  const status = $("adm-job-filter").value;
  const jobs = await api(`/api/admin/jobs?limit=60${status ? `&status=${status}` : ""}`);
  $("adm-jobs").replaceChildren(...jobs.map((job) => {
    const preset = job.preset === "fit" ? t("recent.fit", { mb: job.target_mb }) : t(`short.${job.preset}`);
    const bits = [job.person, preset, t(`adm.status.${job.status}`), fmtWhen(job.created_at)];
    if (job.file) bits.splice(3, 0, fmtSize(job.file.size));
    const li = row((job.media && job.media.title) || t("media.untitled"), bits.join(" · "));
    if (job.status === "failed" && job.error) {
      const why = document.createElement("span");
      why.className = "bad";
      why.textContent = job.error;
      li.firstChild.append(document.createElement("br"), why);
    }
    return li;
  }));
  $("adm-jobs-empty").hidden = jobs.length > 0;
}

$("adm-job-filter").addEventListener("change", () => adminAct(loadAdminJobs));

// ---------- Share links ----------

async function loadAdminLinks() {
  const links = await api("/api/admin/share-links");
  $("adm-links").replaceChildren(...links.map((link) => row(
    link.title || t("media.untitled"),
    [link.person, fmtSize(link.size), link.views === 1 ? t("adm.views1") : t("adm.viewsN", { n: link.views }),
      t("adm.until", { when: fmtWhen(link.expires_at) })].join(" · "),
    t("tok.revoke"),
    () => adminAct(async () => {
      await api(`/api/admin/share-links/${link.token}`, { method: "DELETE" });
      await loadAdminLinks();
    }, t("adm.linkRevoked")),
  )));
  $("adm-links-empty").hidden = links.length > 0;
}

// ---------- People ----------

async function loadPeople() {
  const people = await api("/api/admin/users");
  $("people-list").replaceChildren(...people.map((u) => row(
    u.me ? `${u.name} ${t("ppl.you")}` : u.name,
    [
      t(`role.${u.role}`),
      u.devices === 1 ? t("ppl.devices1") : t("ppl.devicesN", { n: u.devices }),
      u.jobs === 1 ? t("ppl.videos1") : t("ppl.videosN", { n: u.jobs }),
      u.disabled ? t("ppl.off") : "",
    ].filter(Boolean).join(" · "),
    u.me ? null : (u.disabled ? t("ppl.turnOn") : t("ppl.turnOff")),
    () => adminAct(async () => {
      await api(`/api/admin/users/${u.id}/${u.disabled ? "enable" : "disable"}`, { method: "POST" });
      await loadPeople();
    }),
  )));
}

$("person-form").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(async () => {
    const name = $("person-name").value;
    const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "user", name }) });
    $("person-name").value = "";
    showInvite(invite, t("dev.scanPerson", { name }), "pinvite");
  });
});

// ---------- Limits ----------

async function loadLimits() {
  adminSettings = await api("/api/admin/settings");
  const { settings, limits, platforms } = adminSettings;
  const fields = $("adm-limit-fields");
  fields.replaceChildren();
  for (const key of LIMIT_ORDER) {
    const [low, high] = limits[key];
    const label = document.createElement("label");
    label.htmlFor = `adm-limit-${key}`;
    label.textContent = t(`set.${key}`);
    const input = document.createElement("input");
    input.type = "number";
    input.id = `adm-limit-${key}`;
    input.name = key;
    input.min = low;
    input.max = high;
    input.step = 1;
    input.required = true;
    input.inputMode = "numeric";
    input.value = settings[key];
    fields.append(label, input);
  }
  $("adm-platforms").replaceChildren(...Object.entries(platforms).map(([id, name]) => checkbox(`adm-platform-${id}`, id, name, settings.platforms.includes(id))));
}

function checkbox(id, value, text, checked) {
  const label = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.id = id;
  box.value = value;
  box.checked = checked;
  label.append(box, document.createTextNode(text));
  return label;
}

$("adm-limits").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(async () => {
    const changes = {};
    for (const key of LIMIT_ORDER) {
      const value = Number($(`adm-limit-${key}`).value);
      if (value !== adminSettings.settings[key]) changes[key] = value;
    }
    const picked = [...document.querySelectorAll("#adm-platforms input:checked")].map((b) => b.value);
    if (picked.join() !== adminSettings.settings.platforms.join()) changes.platforms = picked;
    if (Object.keys(changes).length) {
      await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes }) });
    }
    await loadLimits();
  }, t("adm.saved"));
});

// ---------- Alerts ----------

async function loadAlerts() {
  adminSettings = await api("/api/admin/settings");
  const { settings, alert_events: events } = adminSettings;
  $("adm-ntfy-topic").value = settings.ntfy_topic;
  $("adm-ntfy-url").value = settings.ntfy_url;
  $("adm-ntfy-token").value = "";
  $("adm-ntfy-token").placeholder = settings.has_ntfy_token ? t("adm.tokenSaved") : t("adm.tokenNone");
  $("adm-clear-token").hidden = !settings.has_ntfy_token;
  $("adm-events").replaceChildren(...events.filter((ev) => ev !== "test")
    .map((ev) => checkbox(`adm-event-${ev}`, ev, t(`alert.${ev}`), settings.alerts[ev] !== false)));
}

async function saveAlerts() {
  const changes = { ntfy_topic: $("adm-ntfy-topic").value.trim(), ntfy_url: $("adm-ntfy-url").value.trim(), alerts: {} };
  if ($("adm-ntfy-token").value) changes.ntfy_token = $("adm-ntfy-token").value; // empty box = keep the saved one
  for (const box of document.querySelectorAll("#adm-events input")) changes.alerts[box.value] = box.checked;
  await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes }) });
  await loadAlerts();
}

$("adm-alerts").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(saveAlerts, t("adm.saved"));
});

$("adm-test-alert").addEventListener("click", () => adminAct(async () => {
  await saveAlerts(); // test what is on screen, not what was saved earlier
  await api("/api/admin/alerts/test", { method: "POST" });
}, t("adm.testSent")));

$("adm-clear-token").addEventListener("click", () => adminAct(async () => {
  await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { ntfy_token: "" } }) });
  await loadAlerts();
}, t("adm.saved")));

// ---------- Activity log ----------

async function loadLog() {
  const entries = await api("/api/admin/audit?limit=150");
  $("adm-log").replaceChildren(...entries.map((entry) => {
    const known = t(`act.${entry.action}`);
    const what = known === `act.${entry.action}` ? entry.action : known; // unknown actions show their raw name
    return row(what, [fmtWhen(entry.created_at), entry.person, entry.detail].filter(Boolean).join(" · "));
  }));
}

// ---------- Storage: this server or Cloudflare R2 ----------

async function loadStorage(steps) {
  const data = await api("/api/admin/storage");
  const s = data.settings;
  $("sto-tiles").replaceChildren(
    tile(t("sto.servedFrom"), data.mode === "r2" ? "Cloudflare R2" : t("sto.thisServer")),
    tile(t("sto.connection"), data.tested ? t("sto.tested") : (data.complete ? t("sto.notTested") : t("sto.notSetUp")), "", data.complete && !data.tested),
    tile(t("sto.inCloud"), String(data.files_in_cloud), data.files_in_cloud ? fmtSize(data.bytes_in_cloud) : ""),
  );
  $("sto-use-r2").hidden = data.mode === "r2";
  $("sto-use-r2").disabled = !data.tested;
  $("sto-use-local").hidden = data.mode !== "r2";
  $("sto-switch-note").textContent = data.mode === "r2" ? t("sto.onNote") : (data.tested ? t("sto.readyNote") : t("sto.testFirst"));
  $("sto-account").value = s.r2_account_id;
  $("sto-bucket").value = s.r2_bucket;
  $("sto-key").value = s.r2_access_key_id;
  $("sto-secret").value = "";
  $("sto-secret").placeholder = s.has_r2_secret_access_key ? t("sto.secretSaved") : "";
  $("sto-endpoint").value = s.r2_endpoint;
  $("sto-region").value = s.r2_region;
  const shown = steps || data.last_test;
  $("sto-steps").replaceChildren(...shown.map((step) => {
    const li = row(t(`sto.test.${step.step}`), step.ok ? t("sto.passed") : (step.optional ? t("sto.skipped") : t("sto.failed")));
    li.firstChild.lastChild.className = step.ok ? "good" : (step.optional ? "muted" : "bad");
    if (!step.ok && step.detail) {
      const why = document.createElement("span");
      why.className = "muted";
      why.textContent = step.detail;
      li.firstChild.append(document.createElement("br"), why);
    }
    return li;
  }));
}

$("sto-form").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(async () => {
    const changes = {
      r2_account_id: $("sto-account").value.trim(), r2_bucket: $("sto-bucket").value.trim(),
      r2_access_key_id: $("sto-key").value.trim(), r2_endpoint: $("sto-endpoint").value.trim(),
      r2_region: $("sto-region").value.trim() || "auto",
    };
    if ($("sto-secret").value) changes.r2_secret_access_key = $("sto-secret").value; // empty box = keep the saved one
    await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes }) });
    const result = await api("/api/admin/storage/test", { method: "POST" });
    await loadStorage(result.steps);
    if (!result.passed) throw new Error(t("sto.testFailed"));
  }, t("sto.testPassed"));
});

function switchStorage(mode, message) {
  adminAct(async () => {
    await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { storage: mode } }) });
    await loadStorage();
  }, message);
}
$("sto-use-r2").addEventListener("click", () => switchStorage("r2", t("sto.switchedR2")));
$("sto-use-local").addEventListener("click", () => switchStorage("local", t("sto.switchedLocal")));

// ---------- System: keeping yt-dlp current, nightly platform checks ----------

let systemTimer = null;

async function loadSystem() {
  clearTimeout(systemTimer);
  const data = await api("/api/admin/system");
  const y = data.ytdlp;
  const busy = y.status === "checking" || y.restart_pending;
  $("sys-tiles").replaceChildren(
    tile(t("sys.inUse"), y.version),
    tile(t("sys.newest"), y.latest || "—"),
    tile(t("sys.lastChecked"), y.checked_at ? fmtWhen(y.checked_at) : t("sys.never")),
  );
  const message = y.restart_pending ? t("sys.restarting") : (y.status === "checking" ? t("sys.working") : y.message);
  $("sys-message").textContent = message || "";
  $("sys-message").hidden = !message;
  $("sys-auto").checked = y.auto_update;
  $("sys-update").disabled = busy;
  $("sys-rollback").hidden = !y.can_roll_back || busy;
  $("sys-rollback").textContent = t("sys.rollback", { version: y.previous_version || "" });

  $("sys-checks").replaceChildren(...data.platform_checks.map((check) => {
    const li = row(check.label, `${check.ok ? t("sys.works") : t("sys.broken")} · ${fmtWhen(check.at)}`);
    if (!check.ok && check.error) {
      const why = document.createElement("span");
      why.className = "bad";
      why.textContent = check.error;
      li.firstChild.append(document.createElement("br"), why);
    }
    return li;
  }));
  $("sys-checks-empty").hidden = data.platform_checks.length > 0;
  $("sys-test-platforms").disabled = data.checking_platforms;

  // While the worker is busy, keep looking until it's done.
  if (busy || data.checking_platforms) {
    systemTimer = setTimeout(() => {
      if (adminTab === "system" && !$("admin").hidden) loadSystem().catch(() => { systemTimer = setTimeout(loadSystem, 5000); });
    }, 4000);
  }
}

async function systemAction(action) {
  await api("/api/admin/system", { method: "POST", body: JSON.stringify({ action }) });
  await loadSystem();
}

$("sys-update").addEventListener("click", () => adminAct(() => systemAction("update")));
$("sys-rollback").addEventListener("click", () => adminAct(() => systemAction("rollback")));
$("sys-test-platforms").addEventListener("click", () => adminAct(() => systemAction("platforms")));
$("sys-auto").addEventListener("change", () => adminAct(async () => {
  await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { ytdlp_auto_update: $("sys-auto").checked } }) });
}, t("adm.saved")));

const ADMIN_LOADERS = {
  overview: loadOverview, videos: loadAdminJobs, links: loadAdminLinks, people: loadPeople,
  limits: loadLimits, alerts: loadAlerts, storage: () => loadStorage(), system: loadSystem, log: loadLog,
};

// ---------- opening and closing ----------

for (const tab of document.querySelectorAll("#admin-tabs [data-tab]")) {
  tab.addEventListener("click", () => showAdminTab(tab.dataset.tab));
}

$("open-admin").addEventListener("click", () => {
  showScreen("admin");
  $("pinvite-box").hidden = true;
  showAdminTab("overview");
});

$("close-admin").addEventListener("click", () => showScreen("app"));

// Language changed while the panel is open: reload the tab so its words follow.
document.addEventListener("joyshare:prefs", () => {
  if (me && !$("admin").hidden) adminAct(ADMIN_LOADERS[adminTab]);
});
