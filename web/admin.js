// The admin panel: numbers, everyone's videos and links, people, limits, alerts and the activity log.
// $, api(), showError(), fmtWhen(), row(), showInvite(), showScreen(), passkeyProblem() come from auth.js;
// fmtSize() from app.js; t() from i18n.js. Changing anything asks for the passkey again when needed (api() does that).

let adminTab = "overview";
let adminSettings = null; // { settings, limits, platforms, alert_events } from the server

// The order limits appear in, and the unit shown in each label.
const LIMIT_ORDER = ["max_file_mb", "max_duration_min", "max_concurrent_jobs", "source_ttl_min",
  "output_ttl_hours", "link_ttl_hours", "disk_warn_pct", "disk_pause_pct", "max_source_mb"];

// ---------- not losing what was typed ----------
// A phone often reloads a page when you leave it to copy something from another app. So every admin form
// remembers what was typed, for this browser tab only, until it has been saved. The tab you were on is
// remembered too, so a reload brings you back to the same place.

const DRAFT_FORMS = ["sto-form", "adm-alerts", "adm-limits", "sys-checks-form"];
const draftKey = (formId) => `joyshare_draft_${formId}`;
const store = {
  get(key) { try { return JSON.parse(sessionStorage.getItem(key) || "null"); } catch { return null; } },
  set(key, value) { try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* private window */ } },
  drop(key) { try { sessionStorage.removeItem(key); } catch { /* private window */ } },
};

function rememberDraft(formId) {
  const draft = {};
  for (const field of $(formId).querySelectorAll("input[id], select[id]")) {
    draft[field.id] = field.type === "checkbox" ? field.checked : field.value;
  }
  store.set(draftKey(formId), draft);
}

// Puts unsaved typing back over the values that came from the server. Returns true if there was any.
function restoreDraft(formId) {
  const draft = store.get(draftKey(formId));
  if (!draft) return false;
  for (const [id, value] of Object.entries(draft)) {
    const field = document.getElementById(id);
    if (!field) continue;
    if (field.type === "checkbox") field.checked = value; else field.value = value;
  }
  return true;
}

const forgetDraft = (formId) => store.drop(draftKey(formId));

for (const formId of DRAFT_FORMS) {
  $(formId).addEventListener("input", () => rememberDraft(formId));
  $(formId).addEventListener("change", () => rememberDraft(formId));
}

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
  store.set("joyshare_admin_tab", name);   // so a reload comes back here
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
  $("adm-second-copy").hidden = !d.second_copy;
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
  $("people-list").replaceChildren(...people.map((u) => {
    const li = row(
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
    );
    // Make a member an admin, or an admin a member. Not offered for yourself, so you can't lock yourself out by accident.
    if (u.me) return li;
    const role = document.createElement("button");
    role.type = "button";
    role.className = "quiet";
    role.textContent = u.role === "admin" ? t("ppl.makeMember") : t("ppl.makeAdmin");
    role.addEventListener("click", () => adminAct(async () => {
      await api(`/api/admin/users/${u.id}/role`, { method: "POST", body: JSON.stringify({ role: u.role === "admin" ? "member" : "admin" }) });
      await loadPeople();
    }, t("adm.saved")));
    li.append(role);
    return li;
  }));
}

$("person-form").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(async () => {
    const name = $("person-name").value, role = $("person-role").value;
    const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "user", name, role }) });
    $("person-name").value = "";
    $("person-role").value = "member";
    showInvite(invite, t(role === "admin" ? "dev.scanAdmin" : "dev.scanPerson", { name }), "pinvite");
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
  restoreDraft("adm-limits");
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
    forgetDraft("adm-limits");
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
  restoreDraft("adm-alerts");
}

async function saveAlerts() {
  const changes = { ntfy_topic: $("adm-ntfy-topic").value.trim(), ntfy_url: $("adm-ntfy-url").value.trim(), alerts: {} };
  if ($("adm-ntfy-token").value) changes.ntfy_token = $("adm-ntfy-token").value; // empty box = keep the saved one
  for (const box of document.querySelectorAll("#adm-events input")) changes.alerts[box.value] = box.checked;
  await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes }) });
  forgetDraft("adm-alerts");
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

// Turns one entry's details into a sentence. Each kind of entry has a pattern in the dictionary
// ("actd.<action>") with {blanks}; a blank the entry can't fill means the pattern doesn't apply.
function fill(key, detail) {
  const pattern = t(key);
  if (pattern === key) return null;
  let missing = false;
  const text = pattern.replace(/\{(\w+)\}/g, (_, name) => {
    const value = detail[name];
    if (value === undefined || value === null || value === "") { missing = true; return ""; }
    const known = t(`actv.${name}.${value}`);                 // some values have a friendlier name
    return known === `actv.${name}.${value}` ? String(value) : known;
  });
  return missing ? null : text;
}

function settingName(key) {
  for (const prefix of ["set.", "lim."]) {
    const known = t(prefix + key);
    if (known !== prefix + key) return known;
  }
  return key.replaceAll("_", " ");
}

function settingValue(value) {
  if (value === true) return t("log.on");
  if (value === false) return t("log.off");
  if (Array.isArray(value)) return value.join(", ") || "—";
  if (value && typeof value === "object") {
    return Object.entries(value).map(([k, v]) => `${k.replaceAll("_", " ")} ${settingValue(v)}`).join(", ");
  }
  return String(value);
}

function describeEntry(entry) {
  const detail = entry.detail || {};
  if (entry.action === "settings.change") {
    return Object.entries(detail).map(([key, value]) => `${settingName(key)}: ${settingValue(value)}`).join(" · ");
  }
  if (entry.action === "storage.test") return t(detail.passed ? "log.passed" : "log.notPassed");
  const sentence = fill(`actd.${entry.action}.${detail.kind}`, detail) || fill(`actd.${entry.action}`, detail);
  if (sentence !== null) return sentence;
  // No pattern for this one: still better than raw text.
  return Object.entries(detail).filter(([, v]) => v !== null && v !== "")
    .map(([k, v]) => `${k.replaceAll("_", " ")}: ${settingValue(v)}`).join(" · ");
}

async function loadLog() {
  const entries = await api("/api/admin/audit?limit=150");
  $("adm-log").replaceChildren(...entries.map((entry) => {
    const known = t(`act.${entry.action}`);
    const what = known === `act.${entry.action}` ? entry.action.replaceAll(/[._]/g, " ") : known;
    const li = document.createElement("li");
    li.className = "log-entry";
    const head = document.createElement("span");
    head.className = "log-what";
    head.textContent = what;
    const detail = document.createElement("span");
    detail.className = "log-detail";
    detail.textContent = describeEntry(entry);
    const meta = document.createElement("span");
    meta.className = "log-meta muted";
    const who = entry.person || t(entry.action === "auth.failure" ? "log.nobody" : "log.system");
    meta.textContent = [fmtWhen(entry.created_at), who].join(" · ");
    li.append(head, meta);
    if (detail.textContent) li.append(detail);
    return li;
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
  $("sto-draft-note").hidden = !restoreDraft("sto-form");   // unsaved typing wins over what the server has
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
    forgetDraft("sto-form");   // it is saved on the server now
    const result = await api("/api/admin/storage/test", { method: "POST" });
    await loadStorage(result.steps);
    if (!result.passed) throw new Error(t("sto.testFailed"));
  }, t("sto.testPassed"));
});

// "Clear what I typed": throw away unsaved typing and show what is saved on the server.
$("sto-clear").addEventListener("click", () => {
  forgetDraft("sto-form");
  adminAct(() => loadStorage());
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

  // One row per platform: include it or not, the test video's link, and the last result.
  $("sys-checks").replaceChildren(...data.platform_checks.filter((c) => c.enabled).map((check) => {
    const li = document.createElement("li");
    const box = checkbox(`sys-check-${check.platform}`, check.platform, check.label, check.included);
    box.firstChild.dataset.role = "include";
    const state = document.createElement("span");
    state.className = check.ok === false ? "bad" : "muted";
    state.textContent = check.at
      ? `${check.ok ? t("sys.works") : t("sys.broken")} · ${fmtWhen(check.at)}${check.error ? ` · ${check.error}` : ""}`
      : t("sys.notChecked");
    const link = document.createElement("input");
    link.type = "text";
    link.id = `sys-url-${check.platform}`;
    link.dataset.platform = check.platform;
    link.value = check.url;
    link.placeholder = t("sys.urlPlaceholder", { platform: check.label });
    link.setAttribute("aria-label", t("sys.urlLabel", { platform: check.label }));
    link.spellcheck = false;
    const stack = document.createElement("span");
    stack.className = "stack";
    stack.append(box, state, link);
    li.append(stack);
    return li;
  }));
  restoreDraft("sys-checks-form");
  $("sys-test-platforms").disabled = data.checking_platforms || data.manual_tests_left <= 0;
  $("sys-tests-left").textContent = data.manual_tests_left > 0
    ? t("sys.testsLeft", { n: data.manual_tests_left })
    : t("sys.testsNone", { when: fmtWhen(data.next_manual_test_at) });

  // Backups
  const bak = data.backup;
  const where = bak.cloud ? t("bak.whereBoth") : t("bak.whereServer");
  $("bak-tiles").replaceChildren(
    tile(t("bak.last"), bak.at ? fmtWhen(bak.at) : t("sys.never"), bak.at ? (bak.ok ? where : t("bak.failed")) : "", bak.at && !bak.ok),
    tile(t("bak.size"), bak.size ? (bak.size < 100 * 1024 ? `${Math.round(bak.size / 1024)} KB` : fmtSize(bak.size)) : "—"),
    tile(t("bak.copies"), String(bak.local_count || 0), bak.cloud_ready ? t("bak.cloudOn") : t("bak.cloudOff")),
  );
  const failed = bak.at && !bak.ok;
  $("bak-message").textContent = failed ? `${bak.local_ok ? t("bak.cloudFailed") : t("bak.noneMade")} ${bak.error || ""}` : "";
  $("bak-message").hidden = !failed;
  $("bak-auto").checked = bak.auto;
  $("bak-now").disabled = bak.running;

  // While the worker is busy, keep looking until it's done.
  if (busy || data.checking_platforms || bak.running) {
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
$("bak-now").addEventListener("click", () => adminAct(() => systemAction("backup")));
$("bak-auto").addEventListener("change", () => adminAct(async () => {
  await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { backup_auto: $("bak-auto").checked } }) });
}, t("adm.saved")));
$("sys-checks-form").addEventListener("submit", (e) => {
  e.preventDefault();
  adminAct(async () => {
    const included = [...document.querySelectorAll('#sys-checks input[data-role="include"]:checked')].map((b) => b.value);
    const urls = {};
    for (const input of document.querySelectorAll("#sys-checks input[data-platform]")) urls[input.dataset.platform] = input.value.trim();
    await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ changes: { canary_platforms: included, canary_urls: urls } }) });
    forgetDraft("sys-checks-form");
    await loadSystem();
  }, t("adm.saved"));
});
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

$("close-admin").addEventListener("click", () => {
  store.drop("joyshare_admin_tab");
  showScreen("app");
});

// After a reload (a phone does this on its own when you switch apps), go back to the tab that was open.
document.addEventListener("joyshare:signed-in", () => {
  const tab = store.get("joyshare_admin_tab");
  if (!tab || !ADMIN_LOADERS[tab] || !me || me.role !== "admin") return;
  showScreen("admin");
  showAdminTab(tab);
});

// Language changed while the panel is open: reload the tab so its words follow.
document.addEventListener("joyshare:prefs", () => {
  if (me && !$("admin").hidden) adminAct(ADMIN_LOADERS[adminTab]);
});
