// Connected accounts: each person can upload their own cookie file per platform.
// $, api(), showError(), fmtWhen(), showScreen() come from auth.js; t() from i18n.js.
// The file's contents go up once and never come back down: the server only reports a status.

async function accountsAct(fn, okMessage) {
  showError($("accounts-error"), "");
  $("accounts-ok").hidden = true;
  try {
    await fn();
    if (okMessage) {
      $("accounts-ok").textContent = okMessage;
      $("accounts-ok").hidden = false;
    }
  } catch (err) {
    showError($("accounts-error"), err.message);
    $("accounts-error").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function accountStatus(item) {
  if (item.status === "none") return t("acc.notConnected");
  if (item.status === "rejected") return t("acc.rejected");
  if (item.status === "unreadable") return t("acc.unreadable");
  const bits = [t("acc.connected"), t("acc.since", { when: fmtWhen(item.updated_at) })];
  if (item.last_used_at) bits.push(t("dev.lastUsed", { when: fmtWhen(item.last_used_at) }));
  return bits.join(" · ");
}

async function loadAccounts() {
  const items = await api("/api/account/cookies");
  $("accounts-list").replaceChildren(...items.map((item) => {
    const li = document.createElement("li");
    const left = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = item.label;
    const state = document.createElement("span");
    state.className = item.status === "rejected" || item.status === "unreadable" ? "bad" : "muted";
    state.textContent = accountStatus(item);
    left.append(name, document.createElement("br"), state);

    const buttons = document.createElement("span");
    buttons.className = "actions";
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = ".txt,text/plain";
    picker.hidden = true;
    picker.id = `acc-file-${item.platform}`;
    picker.addEventListener("change", () => {
      const file = picker.files[0];
      picker.value = "";
      if (file) accountsAct(() => uploadCookies(item, file), t("acc.saved", { platform: item.label }));
    });
    const upload = document.createElement("button");
    upload.type = "button";
    upload.className = "secondary";
    upload.textContent = item.status === "none" ? t("acc.upload") : t("acc.replace");
    upload.addEventListener("click", () => picker.click());
    buttons.append(picker, upload);
    if (item.status !== "none") {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "quiet";
      remove.textContent = t("dev.remove");
      remove.addEventListener("click", () => accountsAct(async () => {
        await api(`/api/account/cookies/${item.platform}`, { method: "DELETE" });
        await loadAccounts();
      }, t("acc.removed", { platform: item.label })));
      buttons.append(remove);
    }
    li.append(left, buttons);
    return li;
  }));
}

async function uploadCookies(item, file) {
  if (file.size > 1024 * 1024) throw new Error(t("acc.tooBig"));
  const text = await file.text();
  await api(`/api/account/cookies/${item.platform}`, { method: "PUT", body: JSON.stringify({ text }) });
  await loadAccounts();
}

$("open-accounts").addEventListener("click", () => {
  showScreen("accounts");
  accountsAct(loadAccounts);
});

$("close-accounts").addEventListener("click", () => showScreen("app"));

// Language changed while this screen is open: repaint the list.
document.addEventListener("joyshare:prefs", () => {
  if (me && !$("accounts").hidden) accountsAct(loadAccounts);
});
