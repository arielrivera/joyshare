// Sign-in with passkeys, the Devices screen, and the shared api() helper.
const $ = (id) => document.getElementById(id);
const fmtWhen = (epoch) => new Date(epoch * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

let me = null; // { id, name, role } once signed in

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
    showSignedOut(false);
  }
  if (!res.ok) throw new Error((data && data.detail) || "Something went wrong. Try again.");
  return data;
}

function showError(el, message) {
  el.textContent = message || "";
  el.hidden = !message;
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
  if (err && err.name === "NotAllowedError") return "The passkey prompt was closed. Try again when you're ready.";
  if (err && err.name === "InvalidStateError") return "This device is already registered. Use Sign in instead.";
  if (!window.PublicKeyCredential) return "This browser doesn't support passkeys.";
  return (err && err.message) || "The passkey didn't work. Try again.";
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
  return me;
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
  return me;
}

// ---------- which screen is showing ----------

function guessDeviceName() {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android phone";
  if (/Macintosh/.test(ua)) return "Mac";
  if (/Windows/.test(ua)) return "Windows PC";
  return "My device";
}

function showSignedOut(firstRun) {
  $("app").hidden = true;
  $("devices").hidden = true;
  $("nav").hidden = true;
  $("auth").hidden = false;
  $("signin-box").hidden = firstRun;
  $("join-title").textContent = firstRun ? "Set up joyshare" : "New device?";
  $("join-help").textContent = firstRun
    ? "Enter the setup code printed in the server log to register your first device."
    : "On a device that's already signed in, open Devices and choose \"Add a device\". Enter the code it shows.";
  if (!$("join-name").value) $("join-name").value = guessDeviceName();
  const match = location.hash.match(/^#join=([A-Za-z0-9-]+)$/);
  if (match) {
    $("join-code").value = match[1];
    history.replaceState(null, "", location.pathname);
  }
}

function showSignedIn() {
  $("auth").hidden = true;
  $("devices").hidden = true;
  $("app").hidden = false;
  $("nav").hidden = false;
  $("who").textContent = me.role === "admin" ? `${me.name} (admin)` : me.name;
  document.dispatchEvent(new CustomEvent("joyshare:signed-in"));
}

$("sign-in").addEventListener("click", async () => {
  showError($("auth-error"), "");
  try {
    await passkeySignIn();
    showSignedIn();
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
    showSignedIn();
  } catch (err) {
    showError($("auth-error"), passkeyProblem(err));
  }
});

$("sign-out").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
  me = null;
  showSignedOut(false);
});

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
    p.current ? `${p.name} (this device)` : p.name,
    `Added ${fmtWhen(p.created_at)}` + (p.last_used_at ? ` · last used ${fmtWhen(p.last_used_at)}` : ""),
    p.current || data.passkeys.length < 2 ? null : "Remove",
    () => act(async () => { await api(`/api/auth/devices/${p.id}`, { method: "DELETE" }); await loadDevices(); }),
  )));
  $("token-list").replaceChildren(...data.tokens.map((t) => row(
    t.name,
    `Created ${fmtWhen(t.created_at)}` + (t.last_used_at ? ` · last used ${fmtWhen(t.last_used_at)}` : " · never used"),
    "Revoke",
    () => act(async () => { await api(`/api/auth/tokens/${t.id}`, { method: "DELETE" }); await loadDevices(); }),
  )));
  $("people").hidden = me.role !== "admin";
  if (me.role === "admin") {
    const people = await api("/api/admin/users");
    $("people-list").replaceChildren(...people.map((u) => row(
      u.me ? `${u.name} (you)` : u.name,
      `${u.role} · ${u.devices} device${u.devices === 1 ? "" : "s"} · ${u.jobs} video${u.jobs === 1 ? "" : "s"}` + (u.disabled ? " · turned off" : ""),
      u.me ? null : (u.disabled ? "Turn on" : "Turn off"),
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
  $("invite-expiry").textContent = `Works once, until ${fmtWhen(invite.expires_at)}.`;
  $("invite-box").hidden = false;
  $("invite-box").scrollIntoView({ block: "nearest" });
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
  showInvite(invite, "On the new device, scan this with the camera. It opens joyshare ready to register.");
}));

$("person-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(async () => {
    const name = $("person-name").value;
    const invite = await api("/api/auth/invites", { method: "POST", body: JSON.stringify({ kind: "user", name }) });
    $("person-name").value = "";
    showInvite(invite, `Have ${name} scan this on their own device. It creates their account.`);
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

$("token-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("token-value").value);
    $("token-copy").textContent = "Copied";
  } catch {
    $("token-value").select();
    $("token-copy").textContent = "Select and copy";
  }
  setTimeout(() => { $("token-copy").textContent = "Copy"; }, 2000);
});

$("sign-out-all").addEventListener("click", () => act(async () => {
  await api("/api/auth/logout-all", { method: "POST" });
  me = null;
  showSignedOut(false);
}));

// ---------- start ----------

(async function boot() {
  try {
    const status = await api("/api/auth/status");
    if (status.signed_in) {
      me = status.user;
      showSignedIn();
    } else {
      showSignedOut(status.first_run);
    }
  } catch (err) {
    $("auth").hidden = false;
    showError($("auth-error"), "joyshare isn't answering. Check that the server is running.");
  }
})();
