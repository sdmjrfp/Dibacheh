/* ویرایشگر مرور: اسلایدر نسبت مرور، فاصله‌های آماده و نمودار لایتنر.

   تنظیمات کلی و پنجرهٔ هر درس همین یک قطعه را به کار می‌برند تا شکل و رفتارشان یکی بماند.
   فاصله‌ها روی نمودار جابه‌جا می‌شوند: روز صفر (خواندن) یک طرف است و زمان به طرف دیگر جلو می‌رود.
*/

import { el, fa, t } from "./core.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

const CHART_STEP = 30;    // طول نمودار یک ماه یک ماه عوض می‌شود
const CHART_LIMIT = 3650;

// فاصله‌های آماده. بعد از انتخاب، باز هم می‌شود نقطه‌ها را روی نمودار جابه‌جا کرد.
const PRESETS = () => [
  [t("استاندارد"), [1, 3, 7, 30]],
  [t("فشرده (امتحان نزدیک)"), [1, 2, 4, 7]],
  [t("لایتنر کلاسیک"), [1, 2, 4, 8, 16]],
  [t("بلندمدت"), [1, 3, 7, 14, 30, 60, 120]],
  [t("سبک (مرور کم)"), [3, 14, 45]],
];

export function ratioToPercent(text) {
  const value = String(text || "1/3").trim();
  const [a, b] = value.includes("/") ? value.split("/").map(Number) : [Number(value), 1];
  return Math.round((100 * a) / (b || 1)) || 33;
}

export function percentToRatio(percent) {
  // یک‌سوم و دوسوم دقیق نگه داشته می‌شوند تا گرد کردن درست باشد
  if (percent === 33) return "1/3";
  if (percent === 67) return "2/3";
  return `${percent}/100`;
}

function reviewMinutesFor(minutes, percent) {
  const [a, b] = percentToRatio(percent).split("/").map(Number);
  return Math.ceil((minutes * a) / b);
}

function cumulative(intervals) {
  let sum = 0;
  return intervals.map((d) => (sum += d));
}

/** طول پیشنهادی نمودار: کمی بیشتر از آخرین مرور، مضربی از یک ماه */
function niceChartMax(intervals) {
  const last = cumulative(intervals).at(-1) || 30;
  return Math.max(60, Math.ceil((last * 1.25) / CHART_STEP) * CHART_STEP);
}

/**
 * root: جایی که ویرایشگر در آن ساخته می‌شود.
 * options.cap(): سقف روزانه برای توضیح نسبت مرور
 * options.note: جملهٔ پایانی توضیح نسبت مرور (در تنظیمات کلی)
 * options.onChange(): بعد از هر تغییر
 */
export function createReviewEditor(root, options = {}) {
  let intervals = [1, 3, 7, 30];
  let chartMax = 120;

  const ratioInput = el("input", { type: "range", min: 5, max: 100, step: 1, class: "ratio-input", "aria-label": t("زمان مرور") });
  const ratioValue = el("output", { class: "big-number ratio-value" });
  const ratioExplain = el("div", { class: "explain ratio-explain" });
  const presets = el("div", { class: "presets interval-presets" });
  const chartBox = el("div", { class: "interval-chart" });
  const lengthLabel = el("span", { class: "chart-length-label" });
  const longer = el("button", { type: "button", class: "icon chart-longer", title: t("یک ماه بیشتر") }, "+");
  const shorter = el("button", { type: "button", class: "icon chart-shorter", title: t("یک ماه کمتر") }, "−");
  const addButton = el("button", { type: "button", class: "interval-add" }, t("+ یک مرور دیگر"));
  const removeButton = el("button", { type: "button", class: "interval-remove" }, t("− حذف یک مرور"));
  const explain = el("ol", { class: "explain interval-explain" });

  root.classList.add("review-editor");
  root.replaceChildren(
    el("h4", {}, t("زمان مرور")),
    el("div", { class: "slider-row" }, ratioInput, ratioValue),
    ratioExplain,
    el("h4", {}, t("فاصله‌های لایتنر")),
    el("p", { class: "muted small" }, t("هر نقطه یک مرور است. نقطه‌ها را به چپ و راست بکشید. برای حذف یک مرور خاص، × کنارش در فهرست پایین را بزنید.")),
    presets,
    el("div", { class: "interval-wrap" }, chartBox, el("div", { class: "chart-length" }, longer, lengthLabel, shorter)),
    el("div", { class: "pop-row" }, addButton, removeButton),
    explain,
  );

  const lastReviewDay = () => cumulative(intervals).at(-1) || 0;
  const changed = () => { if (options.onChange) options.onChange(); };

  function updateRatioExplain() {
    const percent = Number(ratioInput.value);
    ratioValue.textContent = t("{0}٪", fa(percent));
    const each = reviewMinutesFor(60, percent);
    const total = 60 + intervals.length * each;
    const cap = (options.cap && options.cap()) || 120;
    ratioExplain.replaceChildren(
      el("div", {}, t("هر مرور {0}٪ زمان خواندن همان جلسه است و رو به بالا گرد می‌شود.", fa(percent))),
      el("div", {}, t("مثال: جلسهٔ ۶۰ دقیقه‌ای ← هر مرور {0} دقیقه. با {1} مرور، کل وقتی که این جلسه می‌گیرد: ", fa(each), fa(intervals.length))
        + t("۶۰ + {0} × {1} = {2} دقیقه.", fa(intervals.length), fa(each), fa(total))),
      el("div", {}, t("یعنی در بلندمدت، از سقف روزانهٔ {0} دقیقه حدود {1} دقیقه به مطلب جدید می‌رسد و بقیه صرف مرور می‌شود.", fa(cap), fa(Math.round((cap * 60) / total)))),
      options.note ? el("div", { class: "muted" }, options.note) : "",
    );
  }

  function geometry() {
    const width = Math.max(chartBox.clientWidth, 400);
    const pad = 36;
    const x = (day) => width - pad - (width - 2 * pad) * Math.sqrt(day / chartMax);
    const dayAt = (px) => {
      const frac = Math.min(1, Math.max(0, (width - pad - px) / (width - 2 * pad)));
      return Math.round(chartMax * frac * frac);
    };
    return { width, x, dayAt };
  }

  function removeInterval(index) {
    if (intervals.length <= 1) return;
    // با حذف یک مرور، مرورهای بعدی سر روز خودشان می‌مانند
    const points = cumulative(intervals).filter((_, j) => j !== index);
    intervals = points.map((p, j) => p - (j ? points[j - 1] : 0));
    render();
    changed();
  }

  function render() {
    const { width, x } = geometry();
    const axisY = 70;
    const points = cumulative(intervals);
    // برچسب‌های محور؛ انتهای نمودار همیشه برچسب دارد
    const ticks = [1, 3, 7, 14, 30, 60, 90, 180, 365, 730, 1825].filter((d) => d < chartMax * 0.85).concat(chartMax);
    chartBox.replaceChildren(svg("svg", { viewBox: `0 0 ${width} 130` },
      svg("line", { class: "axis", x1: x(0), y1: axisY, x2: x(chartMax), y2: axisY }),
      ...ticks.map((d) => svg("g", { class: "tick" },
        svg("line", { x1: x(d), y1: axisY + 8, x2: x(d), y2: axisY + 14 }),
        svg("text", { x: x(d), y: axisY + 28 }, fa(d)))),
      svg("text", { x: x(chartMax), y: axisY + 46, class: "tick", "text-anchor": "middle", fill: "currentColor", "font-size": 11 }, t("روز")),
      ...points.map((day, i) => svg("line", { class: "span", x1: x(i ? points[i - 1] : 0), y1: axisY, x2: x(day), y2: axisY })),
      svg("g", { class: "start" }, svg("circle", { cx: x(0), cy: axisY, r: 8 }),
        svg("text", { x: x(0), y: axisY - 16, "text-anchor": "middle", "font-size": 11, fill: "currentColor" }, t("خواندن"))),
      ...points.map((day, i) => svg("g", { class: "point", "data-index": i },
        svg("text", { x: x(day), y: axisY - 18 }, t("مرور {0}", fa(i + 1))),
        svg("circle", { cx: x(day), cy: axisY, r: 10 }))),
    ));
    const single = intervals.length <= 1;
    explain.replaceChildren(...intervals.map((d, i) =>
      el("li", {}, t("{0} روز بعد از {1}", fa(d), i ? t("مرور {0}", fa(i)) : t("خواندن"))
        + t(" (یعنی روز {0} بعد از خواندن) ", fa(points[i])),
        !single && el("button", {
          type: "button", class: "link danger", title: t("حذف مرور {0}", fa(i + 1)),
          onclick: () => removeInterval(i),
        }, "×"))));
    removeButton.disabled = single;
    lengthLabel.textContent = t("{0} ماه", fa(chartMax / CHART_STEP));
    lengthLabel.title = t("{0} روز", fa(chartMax));
    longer.disabled = chartMax + CHART_STEP > CHART_LIMIT;
    const blocked = chartMax - CHART_STEP < Math.max(CHART_STEP, lastReviewDay());
    shorter.disabled = blocked;
    shorter.title = blocked ? t("مرور آخر روز {0} است؛ اول آن را جلوتر بیاورید", fa(lastReviewDay())) : t("یک ماه کمتر");
    const current = intervals.join();
    presets.replaceChildren(...PRESETS().map(([name, days]) => el("button", {
      type: "button", "aria-selected": String(days.join() === current), title: t("{0} روز", days.map(fa).join(t("، "))),
      onclick: () => {
        intervals = [...days];
        chartMax = niceChartMax(intervals);
        render();
        changed();
      },
    }, `${name}: ${days.map(fa).join(t("، "))}`)));
    updateRatioExplain();
  }

  // کشیدن نقطه‌ها روی نمودار
  let dragIndex = null;
  chartBox.addEventListener("pointerdown", (e) => {
    const point = e.target.closest(".point");
    if (!point || root.classList.contains("off")) return;
    e.preventDefault();
    dragIndex = Number(point.dataset.index);
    try { chartBox.setPointerCapture(e.pointerId); } catch (error) { /* رویداد ساختگی */ }
    point.classList.add("active");
  });
  chartBox.addEventListener("pointermove", (e) => {
    if (dragIndex === null) return;
    const { width, dayAt } = geometry();
    const rect = chartBox.getBoundingClientRect();
    const points = cumulative(intervals);
    const low = (dragIndex ? points[dragIndex - 1] : 0) + 1;
    const high = dragIndex < points.length - 1 ? points[dragIndex + 1] - 1 : chartMax;
    // فقط همین مرور جابه‌جا می‌شود؛ مرورهای بعدی سر روز خودشان می‌مانند
    points[dragIndex] = Math.min(high, Math.max(low, dayAt((e.clientX - rect.left) * (width / rect.width))));
    intervals = points.map((p, i) => p - (i ? points[i - 1] : 0));
    render();
    chartBox.querySelector(`.point[data-index="${dragIndex}"]`).classList.add("active");
  });
  const stop = () => {
    if (dragIndex === null) return;
    dragIndex = null;
    chartBox.querySelectorAll(".point.active").forEach((n) => n.classList.remove("active"));
    changed();
  };
  chartBox.addEventListener("pointerup", stop);
  chartBox.addEventListener("pointercancel", stop);
  chartBox.addEventListener("dblclick", (e) => {
    const point = e.target.closest(".point");
    if (point) removeInterval(Number(point.dataset.index));
  });

  addButton.addEventListener("click", () => {
    intervals.push(Math.min((intervals.at(-1) || 1) * 2, 365));
    // اگر مرور آخر از انتهای نمودار رد شد، نمودار بلندتر می‌شود
    chartMax = Math.max(chartMax, Math.ceil(lastReviewDay() / CHART_STEP) * CHART_STEP);
    render();
    changed();
  });
  removeButton.addEventListener("click", () => removeInterval(intervals.length - 1));
  longer.addEventListener("click", () => { chartMax += CHART_STEP; render(); });
  shorter.addEventListener("click", () => { chartMax -= CHART_STEP; render(); });
  ratioInput.addEventListener("input", () => { updateRatioExplain(); changed(); });

  return {
    /** مقدارهای شروع: نسبت به شکل متن («1/3») و فهرست فاصله‌ها */
    set(ratioText, days) {
      ratioInput.value = ratioToPercent(ratioText);
      intervals = [...days];
      chartMax = niceChartMax(intervals);
      render();
    },
    percent: () => Number(ratioInput.value),
    ratio: () => percentToRatio(Number(ratioInput.value)),
    intervals: () => [...intervals],
    refresh: render,
    updateExplain: updateRatioExplain,
    /** بدون مرور: ویرایشگر خاموش و کم‌رنگ می‌شود، ولی مقدارها می‌مانند */
    setEnabled(on) {
      root.classList.toggle("off", !on);
      for (const control of root.querySelectorAll("input, button")) control.disabled = !on;
      if (on) render();
    },
  };
}
