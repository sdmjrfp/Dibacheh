/* جداکنندهٔ بین منابع درسی و برنامه. */

import { $, isRTL } from "./core.js";

// ---------------------------------------------------------------------------
// جداکنندهٔ بین منابع درسی و برنامه
//
// با کشیدن جداکننده، پهنای ستون منابع عوض می‌شود. چون صفحه راست‌به‌چپ است،
// منابع سمت راست هستند: کشیدن به چپ = منابع پهن‌تر.
// اندازه فقط در همین مرورگر به خاطر سپرده می‌شود (localStorage).
// ---------------------------------------------------------------------------

const SPLIT_KEY = "dibacheh.sourcesWidth";

// پیش‌فرض: سهمی از پهنای برنامه، تا در هر اندازهٔ پنجره ستون برنامه جا داشته باشد
const SPLIT_SHARE = 0.3;

const SPLIT_MIN = 300;       // کمترین پهنای ستون منابع

const CALENDAR_MIN = 420;    // کمترین پهنای ستون برنامه

function defaultWidth() {
  return $(".layout").clientWidth * SPLIT_SHARE;
}

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
  setSourcesWidth(saved || defaultWidth(), false);

  splitter.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    splitter.setPointerCapture(e.pointerId);
    splitter.classList.add("active");
    document.body.classList.add("resizing");
  });
  splitter.addEventListener("pointermove", (e) => {
    if (!splitter.classList.contains("active")) return;
    // لبهٔ راست ستون منابع ثابت است؛ پهنا = فاصلهٔ آن تا جای ماوس
    const box = $(".sources").getBoundingClientRect();
    setSourcesWidth(isRTL ? box.right - e.clientX : e.clientX - box.left, false);
  });
  const stop = () => {
    if (!splitter.classList.contains("active")) return;
    splitter.classList.remove("active");
    document.body.classList.remove("resizing");
    setSourcesWidth(currentSourcesWidth());
  };
  splitter.addEventListener("pointerup", stop);
  splitter.addEventListener("pointercancel", stop);
  splitter.addEventListener("dblclick", () => {
    try { localStorage.removeItem(SPLIT_KEY); } catch (e) { /* بدون حافظه */ }
    setSourcesWidth(defaultWidth(), false);
  });
  // با صفحه‌کلید هم کار می‌کند: کلیدهای چپ و راست
  splitter.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 80 : 20;
    const wider = isRTL ? "ArrowLeft" : "ArrowRight";
    const narrower = isRTL ? "ArrowRight" : "ArrowLeft";
    if (e.key === wider) setSourcesWidth(currentSourcesWidth() + step);
    else if (e.key === narrower) setSourcesWidth(currentSourcesWidth() - step);
    else return;
    e.preventDefault();
  });
  // اگر پنجره کوچک شد، ستون برنامه از حداقل کمتر نشود
  window.addEventListener("resize", () => {
    if (document.body.dataset.layout !== "side") return;
    let width = null;
    try { width = Number(localStorage.getItem(SPLIT_KEY)); } catch (e) { /* بدون حافظه */ }
    setSourcesWidth(width || defaultWidth(), false);
  });
})();
