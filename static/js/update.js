/* شمارهٔ نسخه، خبر نسخهٔ تازه، دانلود آن، و تغییرات نسخه بعد از به‌روزرسانی. */

import { $, api, el, fa, state, t } from "./core.js";
import { closeOnOutside } from "./dialogs.js";

let update = null;   // نتیجهٔ بررسی نسخهٔ تازه
let checked = false;

function language() {
  return state.settings.language || "fa";
}

/** بررسی فقط یک بار و در پس‌زمینه است. اگر اینترنت نبود، هیچ چیزی نشان داده نمی‌شود. */
async function checkForUpdate() {
  try {
    const result = await (await fetch(`/api/update/check?lang=${encodeURIComponent(language())}`)).json();
    if (!result.available) return;
    update = result;
    const button = $("#update-button");
    button.textContent = t("به‌روزرسانی به نسخهٔ {0}", fa(result.latest));
    button.hidden = false;
  } catch (error) { /* اینترنت قطع است؛ مهم نیست */ }
}

export function renderVersion() {
  $("#app-version").textContent = `v${state.version}`;
  if (checked) return;
  checked = true;
  setTimeout(checkForUpdate, 1500);   // اول صفحه کامل بالا بیاید
  showWhatsNew();
}

function megabytes(bytes) {
  return fa((bytes / 1048576).toFixed(1));
}

function openUpdateDialog() {
  $("#update-title").textContent = t("نسخهٔ تازه: {0}", fa(update.latest));
  $("#update-notes").textContent = update.notes || t("توضیحی برای این نسخه نوشته نشده است.");
  $("#update-source-note").hidden = !state.from_source;
  $("#update-size").textContent = t("حجم فایل: {0} مگابایت", megabytes(update.asset.size));
  $("#update-download").hidden = false;
  $("#update-progress").hidden = true;
  $("#update-done").hidden = true;
  $("#update-dialog").showModal();
}

async function startDownload() {
  $("#update-download").hidden = true;
  const bar = $("#update-progress");
  bar.hidden = false;
  await api("POST", "/api/update/download", { lang: language() });
  const timer = setInterval(async () => {
    const p = await (await fetch("/api/update/progress")).json();
    const percent = p.total ? Math.round((100 * p.received) / p.total) : 0;
    bar.querySelector("span").style.width = `${percent}%`;
    $("#update-progress-text").textContent = t("{0}٪ · {1} از {2} مگابایت", fa(percent), megabytes(p.received), megabytes(p.total));
    if (p.state === "downloading") return;
    clearInterval(timer);
    if (p.state === "done") {
      bar.hidden = true;
      $("#update-progress-text").textContent = "";
      $("#update-done-path").textContent = p.path;
      $("#update-done").hidden = false;
    } else {
      $("#update-progress-text").textContent = t("دانلود نشد: {0}", p.error);
      $("#update-download").hidden = false;
    }
  }, 500);
}

/** اولین اجرا بعد از به‌روزرسانی: تغییرات این نسخه. برای نصب تازه نشان داده نمی‌شود. */
async function showWhatsNew() {
  if (state.settings.last_seen_version === state.version) return;
  const upgraded = state.settings.last_seen_version || state.items.length;
  api("POST", "/api/update/seen", {});
  if (!upgraded) return;
  const log = await (await fetch("/static/changelog.json")).json();
  const notes = log[state.version];
  if (!notes) return;
  const lines = notes[language()] || notes.en || notes.fa;
  $("#whats-new-title").textContent = t("تازه‌های نسخهٔ {0}", fa(state.version));
  $("#whats-new-list").replaceChildren(...lines.map((line) => el("li", {}, line)));
  $("#whats-new-dialog").showModal();
}

$("#update-button").addEventListener("click", openUpdateDialog);
$("#update-download").addEventListener("click", startDownload);
$("#update-open").addEventListener("click", () => api("POST", "/api/update/open", {}));
$("#update-reveal").addEventListener("click", () => api("POST", "/api/update/reveal", {}));
closeOnOutside($("#update-dialog"), { closeButton: $("#close-update") });
closeOnOutside($("#whats-new-dialog"), { closeButton: $("#close-whats-new") });
