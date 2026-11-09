/* پنجرهٔ اولین اجرا: زبان و تقویم. */

import { $, api, state } from "./core.js";
import { fillLanguages } from "./settings.js";

const form = $("#setup-form");

function browserLanguage() {
  const wanted = (navigator.language || "en").slice(0, 2).toLowerCase();
  return state.languages[wanted] ? wanted : "en";
}

/** فقط برای نصب تازه. کاربری که از قبل داده دارد، همان فارسی و شمسی می‌ماند. */
export function showSetupIfNeeded() {
  if (state.settings.setup_done || state.items.length || $("#setup-dialog").open) return;
  const language = browserLanguage();
  fillLanguages(form.elements.language, language);
  form.elements.calendar.value = language === "fa" ? "persian" : "gregorian";
  $("#setup-dialog").showModal();
}

form.elements.language.addEventListener("change", (e) => {
  form.elements.calendar.value = e.target.value === "fa" ? "persian" : "gregorian";
});

// این انتخاب لازم است، پس Esc پنجره را نمی‌بندد
$("#setup-dialog").addEventListener("cancel", (e) => e.preventDefault());

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const language = form.elements.language.value;
  const calendar = form.elements.calendar.value;
  const usesPersianScript = ["fa", "ar"].includes(language);
  await api("POST", "/api/setup", {
    language,
    calendar,
    first_weekday: calendar === "persian" ? 5 : 0,
    font_family: usesPersianScript ? "Vazirmatn" : "Noto Sans",
  });
  window.location.reload();
});
