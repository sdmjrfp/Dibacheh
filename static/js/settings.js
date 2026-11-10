/* پنجرهٔ تنظیمات و گزارش خطا. */

import { $, $$, api, CSRF, el, fa, itemById, showMessage, state, t, WEEKDAYS } from "./core.js";
import { closeOnOutside } from "./dialogs.js";
import { createReviewEditor } from "./review-editor.js";
import { categoryOptions } from "./sources.js";

// ---------------------------------------------------------------------------
// تنظیمات
// ---------------------------------------------------------------------------

const settingsForm = $("#settings-form");

const sf = settingsForm.elements;

function openSettings() {
  const s = state.settings;
  sf.default_cap_minutes.value = s.default_cap_minutes;
  sf.cap_tolerance_minutes.value = s.cap_tolerance_minutes;
  sf.day_start_hour.value = s.day_start_hour;
  sf.review_cap_percent.value = s.review_cap_percent ?? "";
  reviewEditor.set(s.default_review_ratio, s.review_intervals);
  const d = s.new_item_defaults || {};
  sf.default_session_minutes.value = d.session_minutes || 60;
  sf.default_max_new.value = d.max_new_sessions_per_day || 1;
  sf.default_category.replaceChildren(...categoryOptions(d.category_id, t("بدون دسته")));
  const colors = s.colors || {};
  sf.color_read.value = colors.read || "#e5484d";
  sf.color_review.value = colors.review || "#3b82f6";
  sf.color_routine.value = colors.routine || "#f5b400";
  sf.color_project.value = colors.project || "#0d9488";
  sf.color_once.value = colors.once || "#db2777";
  sf.color_mode.value = s.color_mode || "kind";
  updateColorMode();
  sf.theme.value = s.theme;
  sf.font_size.value = s.font_size;
  sf.font_bold.checked = Boolean(s.font_bold);
  fillLanguages(sf.language, s.language);
  sf.calendar.value = s.calendar;
  sf.first_weekday.replaceChildren(...[5, 6, 0].map((number) =>
    el("option", { value: number, selected: number === s.first_weekday }, Jalali.weekdayName(number))));
  fillScales();
  sf.check_updates.checked = s.check_updates;
  sf.cloud_backup_folder.value = s.cloud_backup_folder;
  renderCloudBackups();
  sf.ui_scale.value = String(s.ui_scale);
  sf.vault_path.value = s.vault_path || "";
  sf.export_folder.value = s.export_folder || "";
  sf.backup_folder.value = s.backup_folder || "";
  sf.backup_retention.value = s.backup_retention;

  const caps = s.weekday_caps || {};
  const off = s.weekly_days_off || [];
  $("#weekday-settings").replaceChildren(...WEEKDAYS.map(([num, name]) =>
    el("div", { class: "wd" },
      el("strong", {}, name),
      el("span", { class: "with-unit" },
        el("input", { type: "number", min: 0, max: 1440, class: "num", "data-cap": num, value: caps[num] ?? "", placeholder: t("پیش‌فرض") }),
        t("دقیقه")),
      el("label", {}, el("input", { type: "checkbox", "data-off": num, checked: off.includes(num) }), t(" تعطیل")))));

  renderTypeSettings();
  renderTemplateSettings();
  renderBackups();
  renderFontSettings(s.font_family);
  $("#settings-dialog").showModal();
  reviewEditor.updateExplain();
  reviewEditor.refresh();
}

// ---------- نسبت مرور و فاصله‌های لایتنر: همان قطعه‌ای که پنجرهٔ درس هم دارد

const reviewEditor = createReviewEditor($("#settings-reviews"), {
  cap: () => Number(sf.default_cap_minutes.value),
  note: t("درس‌هایی که نسبت مرور اختصاصی دارند، از نسبت خودشان استفاده می‌کنند. برای یک جلسهٔ خاص هم می‌شود زمان مرور را دستی گذاشت."),
});

sf.default_cap_minutes.addEventListener("input", () => reviewEditor.updateExplain());

// ---------- نوع‌های کار و فونت‌ها

/** در رنگ‌بندی بر اساس منبع، فهرست رنگ منبع‌ها دیده می‌شود؛ وگرنه رنگ خواندن و مرور و روتین */
function updateColorMode() {
  const bySource = sf.color_mode.value === "source";
  $("#kind-colors").hidden = bySource;
  $("#source-colors").hidden = !bySource;
  $("#source-colors").replaceChildren(...state.items.map((item) =>
    el("li", { "data-source": item.id },
      el("input", { type: "color", value: item.display_color }),
      el("span", {}, item.title))));
  if (!state.items.length) $("#source-colors").append(el("li", { class: "muted small" }, t("هنوز منبعی اضافه نشده.")));
}

for (const radio of sf.color_mode) radio.addEventListener("change", updateColorMode);

export function fillLanguages(select, selected) {
  select.replaceChildren(...Object.entries(state.languages).map(([code, name]) =>
    el("option", { value: code, selected: code === selected }, name)));
}

function fillScales() {
  if (sf.ui_scale.options.length > 1) return;
  for (const percent of [50, 60, 70, 75, 80, 90, 100, 110, 125, 150, 175, 200]) {
    sf.ui_scale.append(el("option", { value: percent }, `${fa(percent)}٪`));
  }
}

function renderTemplateSettings() {
  const remove = async (template) => {
    const settings = state.settings;
    if (template.builtin) {
      await api("PATCH", "/api/settings", { hidden_templates: [...settings.hidden_templates, template.id] });
    } else {
      await api("PATCH", "/api/settings", { item_templates: settings.item_templates.filter((_, i) => i !== template.index) });
    }
    renderTemplateSettings();
  };
  $("#template-settings").replaceChildren(...state.templates.map((template) =>
    el("li", {},
      el("span", {}, template.name),
      el("button", { type: "button", class: "danger", onclick: () => remove(template) }, t("حذف")))));
  if (!state.templates.length) $("#template-settings").append(el("li", { class: "muted small" }, t("هنوز الگویی نیست.")));
  $("#templates-restore").hidden = !state.settings.hidden_templates.length;
}

$("#templates-restore").addEventListener("click", async () => {
  await api("PATCH", "/api/settings", { hidden_templates: [] });
  renderTemplateSettings();
});

/** پوشه‌های ابری پیداشده روی این کامپیوتر، با یک کلیک انتخاب می‌شوند */
async function renderCloudBackups() {
  const { folders, copies } = await (await fetch("/api/backups/cloud")).json();
  $("#cloud-found").replaceChildren(...folders.map((folder) =>
    el("button", {
      type: "button", title: folder.path,
      onclick: () => { sf.cloud_backup_folder.value = folder.path; },
    }, folder.name)));
  if (!folders.length) $("#cloud-found").append(el("span", { class: "muted small" }, t("پوشهٔ ابری‌ای روی این کامپیوتر پیدا نشد. برنامهٔ OneDrive، Google Drive، Dropbox یا iCloud را نصب کنید، یا پوشه را با Browse انتخاب کنید.")));
  $("#cloud-status").textContent = copies.length ? t("آخرین کپی: {0} · {1} نسخه", Jalali.format(copies[0].modified), fa(copies.length)) : "";
  cloudCopies = copies;
  renderBackups();
}

let cloudCopies = [];

$("#cloud-now").addEventListener("click", async () => {
  await api("PATCH", "/api/settings", { cloud_backup_folder: sf.cloud_backup_folder.value.trim() });
  const result = await api("POST", "/api/backups/cloud/now", {});
  showMessage(result.copied ? t("backup در پوشهٔ ابری کپی شد.") : t("آخرین backup از قبل در پوشهٔ ابری هست."), false);
  renderCloudBackups();
});

async function renderBackups() {
  const backups = (await (await fetch("/api/backups")).json()).concat(cloudCopies.map((copy) => ({ ...copy, cloud: true })));
  $("#backup-list").replaceChildren(...backups.map((b) =>
    el("li", {},
      el("span", {}, `${Jalali.format(b.modified)}${b.safety ? t(" (کپی قبل از برگرداندن)") : ""}${b.cloud ? t(" ☁ پوشهٔ ابری") : ""}`),
      el("span", { class: "muted small" }, t("{0} کیلوبایت", fa(Math.max(1, Math.round(b.size / 1024))))),
      el("button", {
        type: "button",
        onclick: async () => {
          if (!confirm(t("داده‌های برنامه به نسخهٔ {0} برگردد؟ یک کپی از وضعیت فعلی نگه داشته می‌شود.", Jalali.format(b.modified)))) return;
          await api("POST", "/api/backups/restore", { name: b.name, cloud: Boolean(b.cloud) });
          $("#settings-dialog").close();
          showMessage(t("backup برگردانده شد."), false);
        },
      }, t("برگرداندن")))));
  if (!backups.length) $("#backup-list").append(el("li", { class: "muted small" }, t("هنوز backupی نیست.")));
}

// گزارش خطا
$("#show-logs").addEventListener("click", async () => {
  const { lines, path } = await (await fetch("/api/logs")).json();
  const box = $("#log-box");
  box.hidden = false;
  box.value = lines.length ? lines.join("\n") : t("خطایی ثبت نشده است.");
  box.title = path;
  box.scrollTop = box.scrollHeight;
});

$("#reveal-logs").addEventListener("click", () => api("POST", "/api/logs/reveal", {}));

function reportPageError(message, source, line) {
  fetch("/api/logs/client", {
    method: "POST",
    headers: { "X-CSRF-Token": CSRF, "Content-Type": "application/json" },
    body: JSON.stringify({ message, source, line }),
  }).catch(() => {});
}

window.addEventListener("error", (e) => reportPageError(e.message, e.filename, e.lineno));

window.addEventListener("unhandledrejection", (e) => {
  if (!e.reason || !e.reason.expected) reportPageError(String(e.reason), "promise", "");
});

$("#data-export").addEventListener("click", async () => {
  const result = await api("POST", "/api/data/export", {});
  await api("POST", "/api/export/reveal", { name: result.name });
  showMessage(t("فایل داده‌ها ساخته شد: {0}", result.name), false);
});

$("#data-import").addEventListener("click", async () => {
  if (!confirm(t("داده‌های فعلی با داده‌های فایل عوض می‌شوند. یک کپی از وضعیت فعلی نگه داشته می‌شود. ادامه می‌دهید؟"))) return;
  const result = await api("POST", "/api/data/import", {});
  if (result.cancelled) return;
  $("#settings-dialog").close();
  showMessage(t("داده‌ها وارد شدند."), false);
});

function renderTypeSettings() {
  $("#type-settings").replaceChildren(...state.types.map((type) =>
    el("li", { "data-type": type.id },
      el("input", { type: "color", value: type.color, "data-field": "color" }),
      el("input", { type: "text", value: type.name, maxlength: 40, "data-field": "name" }),
      el("span", { class: "muted small" }, type.behavior === "study" ? t("مثل درس، با مرور") : t("مثل روتین، بدون مرور")),
      el("button", {
        type: "button", class: "danger",
        onclick: async () => {
          if (!confirm(t("نوع «{0}» حذف شود؟ کارهای این نوع می‌مانند و درس یا روتین معمولی می‌شوند.", type.name))) return;
          await api("DELETE", `/api/types/${type.id}`);
          renderTypeSettings();
        },
      }, t("حذف")))));
  if (!state.types.length) {
    $("#type-settings").append(el("li", { class: "muted small" }, t("نوع کار ساخت شما هنوز نیست. با منوی «+» بسازید.")));
  }
}

/** کادر باز شوی فونت: فونت‌های همراه برنامه و فونت‌هایی که کاربر اضافه کرده */
function fillFontSelect(selected) {
  const custom = state.settings.custom_fonts || [];
  const bundled = [{ family: "Vazirmatn", label: t("وزیرمتن") }, ...state.bundled_fonts];
  const known = new Set([...bundled, ...custom].map((f) => f.family));
  const option = (value, label) => el("option", { value, selected: value === selected }, label);
  const groups = [
    el("optgroup", { label: t("فارسی، همراه برنامه") }, bundled.map((f) => option(f.family, `${f.label} (${f.family})`))),
  ];
  if (custom.length) groups.push(el("optgroup", { label: t("اضافه‌شده") }, custom.map((f) => option(f.family, f.family))));
  // فونت فعلی حتی اگر در فهرست نیست (مثلاً قبلاً از فونت‌های Mac انتخاب شده)، از دست نرود
  if (selected && !known.has(selected)) groups.unshift(option(selected, selected));
  sf.font_family.replaceChildren(...groups);
  updateFontSample();
}

function updateFontSample() {
  $("#font-sample").style.fontFamily = `"${sf.font_family.value}", "Vazirmatn", sans-serif`;
}

sf.font_family.addEventListener("change", updateFontSample);

function renderFontSettings(selected = sf.font_family.value || state.settings.font_family) {
  const custom = state.settings.custom_fonts || [];
  $("#custom-font-list").replaceChildren(...custom.map((f) =>
    el("li", {},
      el("span", { style: `font-family:"${f.family}"` }, t("{0} — نمونهٔ متن فارسی", f.family)),
      el("button", {
        type: "button", class: "danger",
        onclick: async () => {
          await api("POST", "/api/fonts/remove", { family: f.family });
          renderFontSettings(state.settings.font_family);
        },
      }, t("حذف")))));
  fillFontSelect(selected);
}

$("#font-add").addEventListener("click", async () => {
  const result = await api("POST", "/api/fonts/add", {});
  if (result.cancelled) return;
  renderFontSettings(result.added_font);
  showMessage(t("فونت «{0}» اضافه شد. برای استفاده، «ذخیره» را بزنید.", result.added_font), false);
});

// ---------- ذخیره

function collectSettings() {
  const weekdayCaps = {};
  for (const input of $$("[data-cap]", settingsForm)) {
    if (input.value !== "") weekdayCaps[input.dataset.cap] = Number(input.value);
  }
  return {
    default_cap_minutes: Number(sf.default_cap_minutes.value),
    cap_tolerance_minutes: Number(sf.cap_tolerance_minutes.value),
    day_start_hour: Number(sf.day_start_hour.value),
    review_cap_percent: sf.review_cap_percent.value === "" ? null : Number(sf.review_cap_percent.value),
    default_review_ratio: reviewEditor.ratio(),
    review_intervals: reviewEditor.intervals(),
    weekday_caps: weekdayCaps,
    weekly_days_off: $$("[data-off]:checked", settingsForm).map((x) => Number(x.dataset.off)),
    new_item_defaults: {
      session_minutes: Number(sf.default_session_minutes.value),
      max_new_sessions_per_day: Number(sf.default_max_new.value),
      category_id: sf.default_category.value ? Number(sf.default_category.value) : null,
    },
    colors: {
      read: sf.color_read.value, review: sf.color_review.value, routine: sf.color_routine.value,
      project: sf.color_project.value, once: sf.color_once.value,
    },
    color_mode: sf.color_mode.value,
    theme: sf.theme.value,
    font_size: Number(sf.font_size.value),
    font_bold: sf.font_bold.checked,
    language: sf.language.value,
    calendar: sf.calendar.value,
    first_weekday: Number(sf.first_weekday.value),
    check_updates: sf.check_updates.checked,
    cloud_backup_folder: sf.cloud_backup_folder.value.trim(),
    ui_scale: sf.ui_scale.value === "auto" ? "auto" : Number(sf.ui_scale.value),
    font_family: sf.font_family.value.trim(),
    vault_path: sf.vault_path.value.trim(),
    export_folder: sf.export_folder.value.trim(),
    backup_folder: sf.backup_folder.value.trim(),
    backup_retention: Number(sf.backup_retention.value),
  };
}

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  // نام و رنگ نوع‌های کار که عوض شده‌اند
  for (const row of $$("#type-settings li[data-type]")) {
    const type = state.types.find((x) => x.id === Number(row.dataset.type));
    const name = row.querySelector('[data-field="name"]').value.trim();
    const color = row.querySelector('[data-field="color"]').value;
    if (type && (name !== type.name || color !== type.color)) await api("PATCH", `/api/types/${type.id}`, { name, color });
  }
  // رنگ منبع‌هایی که عوض شده‌اند
  for (const row of $$("#source-colors li[data-source]")) {
    const item = itemById(Number(row.dataset.source));
    const color = row.querySelector("input").value;
    if (item && color !== item.display_color) await api("PATCH", `/api/items/${item.id}`, { color });
  }
  const before = state.settings;
  const chosen = collectSettings();
  await api("PATCH", "/api/settings", chosen);
  // زبان و تقویم موقع بار شدن صفحه اعمال می‌شوند
  if (chosen.language !== before.language || chosen.calendar !== before.calendar || chosen.first_weekday !== before.first_weekday) {
    window.location.reload();
    return;
  }
  $("#settings-dialog").close();
  showMessage(t("تنظیمات ذخیره شد و برنامه از نو چیده شد."), false);
});

for (const button of $$("[data-browse]", settingsForm)) {
  button.addEventListener("click", async () => {
    const result = await api("POST", "/api/browse", { kind: "folder" });
    if (!result.cancelled) sf[button.dataset.browse].value = result.path;
  });
}

$("#settings-button").addEventListener("click", openSettings);

// ---------- بستن با کلیک بیرون پنجره، Esc یا دکمهٔ بستن: اگر چیزی عوض شده، اول می‌پرسد

/** همهٔ مقدارهای فرم، برای فهمیدن اینکه چیزی عوض شده یا نه */
function settingsSnapshot() {
  const types = $$("#type-settings li[data-type]").map((row) => [
    row.dataset.type, row.querySelector('[data-field="name"]').value, row.querySelector('[data-field="color"]').value]);
  const sources = $$("#source-colors li[data-source]").map((row) => [row.dataset.source, row.querySelector("input").value]);
  return JSON.stringify([collectSettings(), types, sources]);
}

closeOnOutside($("#settings-dialog"), {
  snapshot: settingsSnapshot, save: () => settingsForm.requestSubmit(), closeButton: $("#close-settings"),
});
