/* چیدمان برنامه: اندازهٔ رابط و اینکه کارها و برنامه چطور کنار هم باشند.

   اندازه: همهٔ اندازه‌های style.css به rem هستند و rem به --ui-scale وابسته است.
   در حالت خودکار، مقیاس از پهنای پنجره می‌آید، نه رزولوشن، چون پنجره می‌تواند کوچک باشد.
   انتخاب‌های چیدمان فقط در همین مرورگر به خاطر سپرده می‌شوند.
*/

import { $, getPref, setPref, state } from "./core.js";

// پنجره از این پهنا به بالا: این مقیاس. پله‌ای است تا با کمی تغییر پنجره، همه‌چیز تکان نخورد.
const AUTO_STEPS = [[2200, 1], [1800, 0.92], [1500, 0.85], [1300, 0.8], [0, 0.75]];

export function autoScale(width) {
  return AUTO_STEPS.find(([min]) => width >= min)[1];
}

export function applyScale() {
  const chosen = state ? state.settings.ui_scale : "auto";
  const scale = chosen === "auto" ? autoScale(window.innerWidth) : chosen / 100;
  document.documentElement.style.setProperty("--ui-scale", String(scale));
}

window.addEventListener("resize", applyScale);

const LAYOUTS = ["side", "stack", "sources", "plan"];

function applyLayout(mode) {
  document.body.dataset.layout = mode;
  $("#layout-select").value = mode;
}

$("#layout-select").addEventListener("change", (e) => {
  setPref("layout", e.target.value);
  applyLayout(e.target.value);
  window.dispatchEvent(new Event("resize"));   // پهنای ستون‌ها دوباره اندازه گرفته شود
});

const saved = getPref("layout", "side");
applyLayout(LAYOUTS.includes(saved) ? saved : "side");
