// Each person's own look: the name at the top, lettering, colors and language.
// Kept in this browser for instant loading, and saved to the account so it follows you.
// Loaded in <head>, so the right colors and font are in place before anything is drawn.
const PREF_KEY = "joyshare_prefs";
const FONT_CHOICES = ["unbounded", "syne", "warp", "glitch", "mono", "fredoka", "bangers", "audiowide", "win"];
const THEME_CHOICES = ["void", "acid", "sunset", "zine", "clay", "win95", "comic", "vapor"];
// Each look comes with lettering that suits it. Picking a look switches to it; you can still change it after.
const THEME_FONT = { void: "unbounded", acid: "warp", sunset: "syne", zine: "mono", clay: "fredoka", win95: "win", comic: "bangers", vapor: "audiowide" };

const prefs = { name: "", font: "unbounded", theme: "void", lang: "" };
let defaultName = "joyshare";
let prefsSignedIn = false;

try { Object.assign(prefs, JSON.parse(localStorage.getItem(PREF_KEY) || "{}")); } catch { /* private window */ }
if (!["en", "es"].includes(prefs.lang)) prefs.lang = (navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en";
if (!FONT_CHOICES.includes(prefs.font)) prefs.font = "unbounded";
if (!THEME_CHOICES.includes(prefs.theme)) prefs.theme = "void";

function brandName() {
  return prefs.name || defaultName;
}

function applyPrefs() {
  const root = document.documentElement;
  root.dataset.theme = prefs.theme;
  root.dataset.font = prefs.font;
  LANG = prefs.lang;
  // The server reads this cookie to answer in the same language (also for live progress updates).
  document.cookie = `joyshare_lang=${prefs.lang}; path=/; max-age=31536000; samesite=lax`;
  document.title = brandName();
  if (!document.body) return; // called once from <head> before the page exists
  document.getElementById("brand").textContent = brandName();
  document.getElementById("ticker").textContent = t("ticker").repeat(8);
  document.getElementById("lang-toggle").textContent = prefs.lang === "es" ? "🇲🇽 ES" : "🇺🇸 EN";
  for (const b of document.querySelectorAll("[data-font]")) b.setAttribute("aria-pressed", String(b.dataset.font === prefs.font));
  for (const b of document.querySelectorAll("[data-theme-pick]")) b.setAttribute("aria-pressed", String(b.dataset.themePick === prefs.theme));
  translatePage();
  document.dispatchEvent(new CustomEvent("joyshare:prefs"));
}

let saveTimer = null;
function setPrefs(changes) {
  Object.assign(prefs, changes);
  try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* private window */ }
  applyPrefs();
  if (!prefsSignedIn) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/auth/prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: prefs.name, font: prefs.font, theme: prefs.theme, lang: prefs.lang }),
    }).catch(() => { /* saved locally; the account copy catches up next time */ });
  }, 500);
}

// Called after sign-in: the account's saved look wins over this browser's copy.
function adoptAccountPrefs(status) {
  defaultName = status.app_name || defaultName;
  prefsSignedIn = Boolean(status.signed_in);
  const saved = status.prefs;
  if (saved) {
    prefs.name = saved.name === defaultName ? "" : saved.name;
    prefs.font = saved.font;
    prefs.theme = saved.theme;
    if (saved.lang) prefs.lang = saved.lang;
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* private window */ }
  }
  applyPrefs();
}

applyPrefs(); // colors and font right away

document.addEventListener("DOMContentLoaded", () => {
  const $id = (id) => document.getElementById(id);
  applyPrefs();

  $id("lang-toggle").addEventListener("click", () => setPrefs({ lang: prefs.lang === "es" ? "en" : "es" }));
  for (const b of document.querySelectorAll("[data-font]")) {
    b.addEventListener("click", () => setPrefs({ font: b.dataset.font }));
  }
  for (const b of document.querySelectorAll("[data-theme-pick]")) {
    b.addEventListener("click", () => setPrefs({ theme: b.dataset.themePick, font: THEME_FONT[b.dataset.themePick] }));
  }

  const panel = $id("style-panel"), nameInput = $id("style-name");
  $id("open-style").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      nameInput.value = prefs.name;
      nameInput.placeholder = defaultName;
      panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
      nameInput.focus();
    }
  });
  nameInput.addEventListener("input", () => setPrefs({ name: nameInput.value.replace(/\s+/g, " ").trim().slice(0, 24) }));
  $id("close-style").addEventListener("click", () => { panel.hidden = true; });
});
