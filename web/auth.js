// Sign-in with passkeys, the Devices screen, and the shared api() helper.
// t() comes from i18n.js; prefs, setPrefs() and adoptAccountPrefs() come from prefs.js.
const $ = (id) => document.getElementById(id);
const fmtWhen = (epoch) => new Date(epoch * 1000).toLocaleString(LANG, { dateStyle: "medium", timeStyle: "short" });

let me = null;          // { id, name, role } once signed in
let firstRun = false;   // true until the very first device is registered

// ---------- talking to the server ----------

async function api(path, options = {}, retried = false) {
  const res = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (res.status === 401 && res.headers.get("x-joyshare-reauth") && !retried) {
    await passkeySignIn(); // sensitive action: confirm with the passkey, then try once more
    return api(path, options, true);
  }
  if (res.status === 401 && me) {
    me = null;
    showSignedOut();
  }
  if (!res.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || t("err.generic"));
  return data;
}

function showError(el, message) {
  el.textContent = message || "";
  el.hidden = !message;
}

async function copyFrom(input, button) {
  try {
    await navigator.clipboard.writeText(input.value);
    button.textContent = t("copied");
  } catch {
    input.select();
    button.textContent = t("selectCopy");
  }
  setTimeout(() => { button.textContent = t("copy"); }, 2000);
}

// ---------- passkey plumbing (WebAuthn wants bytes, JSON wants text) ----------

const b64 = {
  toBytes(text) {
    const padded = text.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(text.length / 4) * 4, "=");
    return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  },
  fromBytes(buffer) {
    let binary = "";
    for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  },
};

function credentialToJSON(cred) {
  const r = cred.response;
  const out = {
    id: cred.id,
    rawId: b64.fromBytes(cred.rawId),
    type: cred.type,
    authenticatorAttachment: cred.authenticatorAttachment || undefined,
    response: { clientDataJSON: b64.fromBytes(r.clientDataJSON) },
  };
  if (r.attestationObject) {
    out.response.attestationObject = b64.fromBytes(r.attestationObject);
    if (r.getTransports) out.response.transports = r.getTransports();
  } else {
    out.response.authenticatorData = b64.fromBytes(r.authenticatorData);
    out.response.signature = b64.fromBytes(r.signature);
    out.response.userHandle = r.userHandle ? b64.fromBytes(r.userHandle) : null;
  }
  return out;
}

function passkeyProblem(err) {
  if (err && err.name === "NotAllowedError") return t("pk.closed");
  if (err && err.name === "InvalidStateError") return t("pk.exists");
  if (!window.PublicKeyCredential) return t("pk.unsupported");
  return (err && err.message) || t("pk.failed");
}

async function passkeySignIn() {
  const start = await api("/api/auth/login/options", { method: "POST" });
  const pk = start.publicKey;
  const cred = await navigator.credentials.get({
    publicKey: {
      ...pk,
      challenge: b64.toBytes(pk.challenge),
      allowCredentials: (pk.allowCredentials || []).map((c) => ({ ...c, id: b64.toBytes(c.id) })),
    },
  });
  const done = await api("/api/auth/login/verify", {
    method: "POST",
    body: JSON.stringify({ challenge_id: start.challenge_id, credential: credentialToJSON(cred) }),
  });
  me = done.user;
}

async function passkeyRegister(code, deviceName) {
  const start = await api("/api/auth/register/options", {
    method: "POST",
    body: JSON.stringify({ code, device_name: deviceName }),
  });
  const pk = start.publicKey;
  const cred = await navigator.credentials.create({
    publicKey: {
      ...pk,
      challenge: b64.toBytes(pk.challenge),
      user: { ...pk.user, id: b64.toBytes(pk.user.id) },
      excludeCredentials: (pk.excludeCredentials || []).map((c) => ({ ...c, id: b64.toBytes(c.id) })),
    },
  });
  const done = await api("/api/auth/register/verify", {
    method: "POST",
    body: JSON.stringify({ challenge_id: start.challenge_id, credential: credentialToJSON(cred) }),
  });
  me = done.user;
}

// ---------- which screen is showing ----------

function guessDeviceName() {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android";
  if (/Macintosh/.test(ua)) return "Mac";
  if (/Windows/.test(ua)) return "Windows PC";
  return "My device";
}

function paintAuthText() {
  $("signin-box").hidden = firstRun;
  $("join-title").textContent = firstRun ? t("join.titleSetup", { name: brandName() }) : t("join.titleNew");
  $("join-help").textContent = firstRun ? t("join.helpSetup") : t("join.helpNew");
  if (me) $("who").textContent = me.role === "admin" ? `${me.name} · ${t("nav.admin")}` : me.name;
}

function showSignedOut() {
  prefsSignedIn = false;
  $("app").hidden = true;
  $("devices").hidden = true;
  $("nav").hidden = true;
  $("auth").hidden = false;
  paintAuthText();
  if (!$("join-name").value) $("join-name").value = guessDeviceName();
  const match = location.hash.match(/^#join=([A-Za-z0-9-]+)$/);
  if (match) {
    $("join-code").value = match[1];
    history.replaceState(null, "", location.pathname);
  }
}

// After a passkey check succeeds: load the account's saved look, then open the app.
async function enter() {
  const status = await api("/api/auth/status");
  me = status.user;
  firstRun = false;
  adoptAccountPrefs(status);
  $("auth").hidden = true;
  $("devices").hidden = true;
  $("app").hidden = false;
  $("nav").hidden = false;
  paintAuthText();
  document.dispatchEvent(new CustomEvent("joyshare:signed-in"));
}

$("sign-in").addEventListener("click", async () => {
  showError($("auth-error"), "");
  try {
    await passkeySignIn();
    await enter();
  } catch (err) {
    showError($("auth-error"), passkeyProblem(err));
  }
});

$("join").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError($("auth-error"), "");
  try {
    await passkeyRegister($("join-code").value, $("join-name").value);
    $("join-code").value = "";
    await enter();
  } catch (err) {
    showError($("auth-error"), passkeyProblem(err));
  }
});

$("sign-out").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
  me = null;
  showSignedOut();
});

// ---------- the small menu at the top ----------

function setMenu(open) {
  $("menu-panel").hidden = !open;
  $("menu-button").setAttribute("aria-expanded", String(open));
}
$("menu-button").addEventListener("click", (e) => { e.stopPropagation(); setMenu($("menu-panel").hidden); });
$("menu-panel").addEventListener("click", (e) => { if (e.target.closest("button")) setMenu(false); });
document.addEventListener("click", (e) => { if (!e.target.closest("#nav")) setMenu(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });

// ---------- Devices screen ----------

function row(text, detail, buttonLabel, onClick) {
  const li = document.createElement("li");
  const left = document.createElement("span");
  const name = document.createElement("strong");
  name.textContent = text;
  const small = document.createElement("span");
  small.className = "muted";
  small.textContent = detail;
  left.append(name, document.createElement("br"), small);
  li.append(left);
  if (buttonLabel) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    button.textContent = buttonLabel;
    button.addEventListener("click", onClick);
    li.append(button);
  }
  return li;
}

async function act(fn) {
  showError($("devices-error"), "");
  try {
    await fn();
  } catch (err) {
    showError($("devices-error"), err.name && err.name !== "Error" ? passkeyProblem(err) : err.message);
  }
}

async function loadDevices() {
  const data = await api("/api/auth/devices");
  $("passkey-list").replaceChildren(...data.passkeys.map((p) => row(
    p.current ? `${p.name} ${t("dev.this")}` : p.name,
    t("dev.added", { when: fmtWhen(p.created_at) }) + (p.last_used_at ? ` · ${t("dev.lastUsed", { when: fmtWhen(p.last_used_at) })}` : ""),
    p.current || data.passkeys.length < 2 ? null : t("dev.remove"),
    () => act(async () => { await api(`/api/auth/devices/${p.id}`, { method: "DELETE" }); await loadDevices(); }),
  )));
  $("token-list").replaceChildren(...data.tokens.map((k) => row(
    k.name,
    t("tok.created", { when: fmtWhen(k.created_at) }) + " · " + (k.last_used_at ? t("dev.lastUsed", { when: fmtWhen(k.last_used_at) }) : t("tok.never")),
    t("tok.revoke"),
    () => act(async () => { await api(`/api/auth/tokens/${k.id}`, { method: "DELETE" }); await loadDevices(); }),
  )));
  $("people").hidden = me.role !== "admin";
  if (me.role === "admin") {
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
      () => act(async () => {
        await api(`/api/admin/users/${u.id}/${u.disabled ? "enable" : "disable"}`, { method: "POST" });
        await loadDevices();
      }),
    )));
  }
}

function showInvite(invite, help) {
  $("invite-help").textContent = help;
  $("invite-qr").src = invite.qr;
  $("invite-code").textContent = invite.code;
  $("invite-expiry").textContent = t("dev.expires", { when: fmtWhen(invite.expires_at) });
  $("invite-box").hidden = false;
  $("invite-box").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

$("open-devices").addEventListener("click", () => act(async () => {
  $("app").hidden = true;
  $("devices").hidden = false;
  $("invite-box").hidden = true;
  $("token-box").hidden = true;
  await loadDevices();
}));

$("close-devices").addEventListener("click", () => {
  $("devices").hidden = true;
  $("app").hidden = false;
});

$("add-device").addEventListener("click", () => act(async () => {
  const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "device" }) });
  showInvite(invite, t("dev.scanDevice"));
}));

$("person-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(async () => {
    const name = $("person-name").value;
    const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "user", name }) });
    $("person-name").value = "";
    showInvite(invite, t("dev.scanPerson", { name }));
  });
});

$("token-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(async () => {
    const made = await api("/api/auth/tokens", { method: "POST", body: JSON.stringify({ name: $("token-name").value }) });
    $("token-name").value = "";
    $("token-value").value = made.token;
    $("token-box").hidden = false;
    await loadDevices();
  });
});

$("token-copy").addEventListener("click", () => copyFrom($("token-value"), $("token-copy")));

$("sign-out-all").addEventListener("click", () => act(async () => {
  await api("/api/auth/logout-all", { method: "POST" });
  me = null;
  showSignedOut();
}));

// Language or name changed: repaint the parts that aren't plain data-i18n labels.
document.addEventListener("joyshare:prefs", () => {
  paintAuthText();
  if (me && !$("devices").hidden) loadDevices().catch(() => {});
});

// ---------- start ----------

(async function boot() {
  try {
    const status = await api("/api/auth/status");
    firstRun = status.first_run;
    if (status.signed_in) {
      await enter();
    } else {
      adoptAccountPrefs(status);
      showSignedOut();
    }
  } catch (err) {
    $("auth").hidden = false;
    showError($("auth-error"), t("boot.down"));
  }
})();
