/* جداکنندهٔ بین منابع درسی و برنامه. */

import { $ } from "./core.js";

// ---------------------------------------------------------------------------
// جداکنندهٔ بین منابع درسی و برنامه
//
// با کشیدن جداکننده، پهنای ستون منابع عوض می‌شود. چون صفحه راست‌به‌چپ است،
// منابع سمت راست هستند: کشیدن به چپ = منابع پهن‌تر.
// اندازه فقط در همین مرورگر به خاطر سپرده می‌شود (localStorage).
// ---------------------------------------------------------------------------

const SPLIT_KEY = "dibacheh.sourcesWidth";

const SPLIT_DEFAULT = 620;

const SPLIT_MIN = 360;

          // کمترین پهنای ستون منابع
const CALENDAR_MIN = 480;

       // کمترین پهنای ستون برنامه

function setSourcesWidth(width, save = true) {
  const layout = $(".layout");
  const max = layout.clientWidth - CALENDAR_MIN;
  const clamped = Math.round(Math.max(SPLIT_MIN, Math.min(width, max)));
  layout.style.setProperty("--sources-width", `${clamped}px`);
  $("#splitter").setAttribute("aria-valuenow", clamped);
  if (save) {
    try { localStorage.setItem(SPLIT_KEY, String(clamped)); } catch (e) { /* حالت خصوصی مرورگر */ }
  }
}

function currentSourcesWidth() {
  return $(".sources").getBoundingClientRect().width;
}

(function setupSplitter() {
  const splitter = $("#splitter");
  let saved = null;
  try { saved = Number(localStorage.getItem(SPLIT_KEY)); } catch (e) { /* بدون حافظه */ }
  setSourcesWidth(saved || SPLIT_DEFAULT, false);

  splitter.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    splitter.setPointerCapture(e.pointerId);
    splitter.classList.add("active");
    document.body.classList.add("resizing");
  });
  splitter.addEventListener("pointermove", (e) => {
    if (!splitter.classList.contains("active")) return;
    // لبهٔ راست ستون منابع ثابت است؛ پهنا = فاصلهٔ آن تا جای ماوس
    const right = $(".sources").getBoundingClientRect().right;
    setSourcesWidth(right - e.clientX, false);
  });
  const stop = () => {
    if (!splitter.classList.contains("active")) return;
    splitter.classList.remove("active");
    document.body.classList.remove("resizing");
    setSourcesWidth(currentSourcesWidth());
  };
  splitter.addEventListener("pointerup", stop);
  splitter.addEventListener("pointercancel", stop);
  splitter.addEventListener("dblclick", () => setSourcesWidth(SPLIT_DEFAULT));
  // با صفحه‌کلید هم کار می‌کند: کلیدهای چپ و راست
  splitter.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 80 : 20;
    if (e.key === "ArrowLeft") setSourcesWidth(currentSourcesWidth() + step);
    else if (e.key === "ArrowRight") setSourcesWidth(currentSourcesWidth() - step);
    else return;
    e.preventDefault();
  });
  // اگر پنجره کوچک شد، ستون برنامه از حداقل کمتر نشود
  window.addEventListener("resize", () => setSourcesWidth(currentSourcesWidth(), false));
})();
