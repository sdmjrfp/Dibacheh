/* کشیدن کل صفحه. */

import { renderCalendar } from "./calendar.js";
import { $, el, fa, showMessage, state } from "./core.js";
import { editing, renderSessions } from "./item-dialog.js";
import { applyScale } from "./layout.js";
import { renderVersion } from "./update.js";
import { renderCategoryTabs, renderItems, renderTabs, renderWorkload } from "./sources.js";

// ---------------------------------------------------------------------------
// کشیدن صفحه
// ---------------------------------------------------------------------------

export function renderNow() {
  $("#today").textContent = `امروز: ${Jalali.weekday(state.today)} ${Jalali.format(state.today)}`;
  // فقط نام پوشهٔ والت نشان داده می‌شود؛ آدرس کامل با نگه داشتن ماوس روی آن
  const vault = state.settings.vault_path;
  $("#vault-path").textContent = vault ? vault.split("/").filter(Boolean).pop() : "ثبت نشده";
  $("#vault-button").title = vault ? `مسیر والت: ${vault}\nبرای تغییر کلیک کنید` : "انتخاب پوشهٔ والت Obsidian";
  document.documentElement.dataset.theme = state.settings.theme || "light";
  document.documentElement.dataset.colorMode = state.settings.color_mode || "kind";
  // فونت و اندازهٔ فونت از تنظیمات
  const root = document.documentElement.style;
  root.setProperty("--font", `"${state.settings.font_family || "Vazirmatn"}", "Vazirmatn", system-ui, Tahoma, sans-serif`);
  root.setProperty("--font-size", `${state.settings.font_size || 16}px`);
  root.setProperty("--font-weight", state.settings.font_bold ? "600" : "400");
  applyScale();
  // رنگ کارها در تقویم، از تنظیمات
  const colors = state.settings.colors || {};
  for (const kind of ["read", "review", "routine", "project", "once"]) if (colors[kind]) root.setProperty(`--c-${kind}`, colors[kind]);
  renderCustomFonts();
  renderCategoryTabs();
  renderTabs();
  renderItems();
  renderWorkload();
  for (const warning of state.plan.warnings) showMessage(warning);
  if (state.backup_problem) showMessage(state.backup_problem);
  if (state.cloud_problem) showMessage(state.cloud_problem);
  renderVersion();
  if (editing && editing.id && $("#item-dialog").open) renderSessions();
  $("#quit-button").hidden = !state.can_quit;
  // دکمه‌های برگرداندن و بازگرداندن، با تعداد مرحله‌ها
  const undo = $("#undo-button");
  const redo = $("#redo-button");
  undo.disabled = !state.undo.count;
  redo.disabled = !state.undo.redo_count;
  undo.querySelector(".count").textContent = state.undo.count ? fa(state.undo.count) : "";
  redo.querySelector(".count").textContent = state.undo.redo_count ? fa(state.undo.redo_count) : "";
  undo.title = state.undo.count
    ? `برگرداندن «${state.undo.label}» · ${fa(state.undo.count)} مرحله قابل برگشت` : "تغییری برای برگرداندن نیست";
  redo.title = state.undo.redo_count
    ? `بازگرداندن «${state.undo.redo_label}» · ${fa(state.undo.redo_count)} مرحله برگشته‌اید` : "مرحله‌ای برگشته نیست";
  renderCalendar();
}

/** فونت‌هایی که کاربر اضافه کرده، از پوشهٔ data/fonts بار می‌شوند. */
function renderCustomFonts() {
  let style = $("#custom-font-faces");
  if (!style) {
    style = el("style", { id: "custom-font-faces" });
    document.head.append(style);
  }
  const bundled = state.bundled_fonts.flatMap((f) => [
    `@font-face { font-family: "${f.family}"; font-weight: 400; src: url("/static/vendor/fonts/${f.regular}") format("woff2"); }`,
    f.bold ? `@font-face { font-family: "${f.family}"; font-weight: 700; src: url("/static/vendor/fonts/${f.bold}") format("woff2"); }` : "",
  ]);
  const custom = (state.settings.custom_fonts || []).map((f) =>
    `@font-face { font-family: "${f.family}"; src: url("/fonts/${encodeURIComponent(f.file)}"); }`);
  const css = [...bundled, ...custom].join("\n");
  if (style.textContent !== css) style.textContent = css;
}
