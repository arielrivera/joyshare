// Sign-in with passkeys, the Devices screen, and the shared api() helper.
// t() comes from i18n.js; prefs, setPrefs() and adoptAccountPrefs() come from prefs.js.
const $ = (id) => document.getElementById(id);
const fmtWhen = (epoch) => new Date(epoch * 1000).toLocaleString(LANG, { dateStyle: "medium", timeStyle: "short" });

let me = null;          // { id, name, role } once signed in
let firstRun = false;   // true until the very first device is registered
let joining = false;    // true when the page was opened from an invite link or QR code

// ---------- talking to the server ----------

async function api(path, options = {}, retried = false) {
  let res;
  try {
    res = await fetch(path, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new Error(t("err.unreachable"));   // no answer at all: offline, or the app is restarting
  }
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
  if (!res.ok) {
    // 502 to 504 come from whatever sits in front of the app (the tunnel) when the app itself isn't answering.
    const fallback = [502, 503, 504].includes(res.status) ? t("err.unreachable") : t("err.generic");
    throw new Error((data && typeof data.detail === "string" && data.detail) || fallback);
  }
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
  // Three situations, and in each one the thing to do next is the big button at the top:
  //   first run: only the setup form;  invite link: register first, sign-in small below;  otherwise: sign in first.
  const registerFirst = firstRun || joining;
  $("signin-box").hidden = firstRun;
  $("auth").classList.toggle("joining", joining && !firstRun);
  $("signin-title").textContent = joining ? t("auth.already") : t("auth.welcome");
  $("signin-help").textContent = joining ? t("auth.alreadyHelp") : t("auth.welcomeHelp");
  $("sign-in").className = joining ? "quiet" : "";
  $("join-submit").className = registerFirst ? "big" : "secondary";
  $("join-cancel").hidden = !joining || firstRun;
  $("join-title").textContent = firstRun ? t("join.titleSetup", { name: brandName() })
    : (joining ? t("join.titleInvite") : t("join.titleNew"));
  $("join-help").textContent = firstRun ? t("join.helpSetup") : (joining ? t("join.helpInvite") : t("join.helpNew"));
  if (me) $("who").textContent = me.role === "admin" ? `${me.name} · ${t("nav.admin")}` : me.name;
  $("open-admin").hidden = !me || me.role !== "admin";
  // "View as member": the server says member_view only for an admin, so a member never sees either control.
  const memberView = Boolean(me && me.member_view);
  $("member-view-on").hidden = !me || me.role !== "admin";
  $("member-view-off").hidden = !memberView;
  $("member-view-bar").hidden = !memberView;
}

// Switches this device between admin and regular member, then starts the page over so every screen
// (and everything already loaded for the admin) is rebuilt the way a member gets it.
async function setMemberView(on) {
  try {
    await api("/api/auth/member-view", { method: "POST", body: JSON.stringify({ on }) });
  } catch (err) {
    toast(err.message || t("mv.failed"));
    return;
  }
  location.reload();
}
$("member-view-on").addEventListener("click", () => setMemberView(true));
$("member-view-off").addEventListener("click", () => setMemberView(false));
$("member-view-back").addEventListener("click", () => setMemberView(false));

// The signed-in screens: the main app, Devices, and the admin panel. Only one shows.
function showScreen(name) {
  for (const id of ["app", "devices", "admin", "accounts", "help"]) $(id).hidden = id !== name;
}

function showSignedOut() {
  prefsSignedIn = false;
  showScreen(null);
  $("nav").hidden = true;
  $("auth").hidden = false;
  if (!$("join-name").value) $("join-name").value = guessDeviceName();
  const match = location.hash.match(/^#join=([A-Za-z0-9-]+)$/);
  if (match) {
    // Opened from an invite: the code is already in, so the only thing left is to name the device and register.
    joining = true;
    $("join-code").value = match[1];
    history.replaceState(null, "", location.pathname);
  }
  paintAuthText();
  if (joining) {
    $("join-name").focus();
    $("join-name").select();
  }
}

// After a passkey check succeeds: load the account's saved look, then open the app.
async function enter() {
  const status = await api("/api/auth/status");
  me = status.user;
  firstRun = false;
  adoptAccountPrefs(status);
  $("auth").hidden = true;
  showScreen("app");
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
    joining = false;
    await enter();
  } catch (err) {
    // Some browsers (Chrome on iPhone, for one) say "the prompt was closed" when the real reason is that this
    // device already holds a passkey for the account. When registering, mention both and point at Sign in.
    const closed = err && err.name === "NotAllowedError";
    showError($("auth-error"), closed ? t("pk.closedOrExists") : passkeyProblem(err));
    // Already has a passkey here: the next step is signing in, so make that the main button again.
    if (err && err.name === "InvalidStateError") {
      joining = false;
      $("join-code").value = "";
      paintAuthText();
      $("sign-in").focus();
    }
    if (closed) $("signin-box").hidden = false;   // keep "Sign in with a passkey" in reach
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
}

// Shows a QR code and typed code. "prefix" picks which box on the page to fill (Devices or the admin's People tab).
function showInvite(invite, help, prefix = "invite") {
  $(`${prefix}-help`).textContent = help;
  $(`${prefix}-qr`).src = invite.qr;
  $(`${prefix}-code`).textContent = invite.code;
  // The same invite as a link: handy when the new "device" is this same computer at another address,
  // or to send to the other device in a message.
  const link = $(`${prefix}-link`);
  link.href = invite.url;
  link.textContent = invite.url.replace(/^https?:\/\//, "").replace(/#join=.*/, "") + " …";
  $(`${prefix}-copy`).onclick = async () => {
    const button = $(`${prefix}-copy`);
    try { await navigator.clipboard.writeText(invite.url); button.textContent = t("copied"); }
    catch { button.textContent = invite.url; }
    setTimeout(() => { button.textContent = t("dev.copyLink"); }, 2500);
  };
  $(`${prefix}-expiry`).textContent = t("dev.expires", { when: fmtWhen(invite.expires_at) });
  $(`${prefix}-box`).hidden = false;
  $(`${prefix}-box`).scrollIntoView({ block: "nearest", behavior: "smooth" });
}

$("open-devices").addEventListener("click", () => act(async () => {
  showScreen("devices");
  $("invite-box").hidden = true;
  $("token-box").hidden = true;
  await loadDevices();
}));

$("close-devices").addEventListener("click", () => showScreen("app"));

$("add-device").addEventListener("click", () => act(async () => {
  const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "device" }) });
  showInvite(invite, t("dev.scanDevice"));
}));

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

// "Cancel" on the register screen: forget the invite and go back to the normal sign-in screen.
$("join-cancel").addEventListener("click", () => {
  joining = false;
  $("join-code").value = "";
  showError($("auth-error"), "");
  paintAuthText();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

// An invite link opened in a tab where the page is already showing only changes the end of the address,
// so the page isn't loaded again. Notice that and switch to the register screen.
window.addEventListener("hashchange", () => {
  if (!me && /^#join=/.test(location.hash)) showSignedOut();
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
