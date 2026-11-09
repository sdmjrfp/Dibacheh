/* پنجرهٔ تنظیمات و گزارش خطا. */

import { $, $$, api, CSRF, el, fa, itemById, showMessage, state, t, WEEKDAYS } from "./core.js";
import { categoryOptions } from "./sources.js";

// ---------------------------------------------------------------------------
// تنظیمات
// ---------------------------------------------------------------------------

const settingsForm = $("#settings-form");

const sf = settingsForm.elements;

let intervalDraft = [];

   // فاصله‌های لایتنر در حال ویرایش (به روز)
let chartMax = 120;

       // آخرین روزِ نمودار لایتنر

function openSettings() {
  const s = state.settings;
  sf.default_cap_minutes.value = s.default_cap_minutes;
  sf.cap_tolerance_minutes.value = s.cap_tolerance_minutes;
  sf.day_start_hour.value = s.day_start_hour;
  sf.review_cap_percent.value = s.review_cap_percent ?? "";
  sf.ratio_percent.value = ratioToPercent(s.default_review_ratio);
  intervalDraft = [...s.review_intervals];
  chartMax = niceChartMax(intervalDraft);
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
  updateRatioExplain();
  renderIntervalChart();
}

// ---------- نسبت مرور (اسلایدر)

function ratioToPercent(text) {
  const value = String(text || "1/3").trim();
  const [a, b] = value.includes("/") ? value.split("/").map(Number) : [Number(value), 1];
  return Math.round((100 * a) / (b || 1)) || 33;
}

function percentToRatio(percent) {
  // یک‌سوم و دوسوم دقیق نگه داشته می‌شوند تا گرد کردن درست باشد
  if (percent === 33) return "1/3";
  if (percent === 67) return "2/3";
  return `${percent}/100`;
}

function reviewMinutesFor(minutes, percent) {
  const ratio = percentToRatio(percent);
  const [a, b] = ratio.split("/").map(Number);
  return Math.ceil((minutes * a) / b);
}

function updateRatioExplain() {
  const percent = Number(sf.ratio_percent.value);
  $("#ratio-value").textContent = t("{0}٪", fa(percent));
  const reviews = intervalDraft.length;
  const each = reviewMinutesFor(60, percent);
  const total = 60 + reviews * each;
  const cap = Number(sf.default_cap_minutes.value) || 120;
  const forNew = Math.round(cap * 60 / total);
  $("#ratio-explain").replaceChildren(
    el("div", {}, t("هر مرور {0}٪ زمان خواندن همان جلسه است و رو به بالا گرد می‌شود.", fa(percent))),
    el("div", {}, t("مثال: جلسهٔ ۶۰ دقیقه‌ای ← هر مرور {0} دقیقه. با {1} مرور، کل وقتی که این جلسه می‌گیرد: ", fa(each), fa(reviews))
      + t("۶۰ + {0} × {1} = {2} دقیقه.", fa(reviews), fa(each), fa(total))),
    el("div", {}, t("یعنی در بلندمدت، از سقف روزانهٔ {0} دقیقه حدود {1} دقیقه به مطلب جدید می‌رسد و بقیه صرف مرور می‌شود.", fa(cap), fa(forNew))),
    el("div", { class: "muted" }, t("درس‌هایی که نسبت مرور اختصاصی دارند، از نسبت خودشان استفاده می‌کنند. برای یک جلسهٔ خاص هم می‌شود زمان مرور را دستی گذاشت.")),
  );
}

sf.ratio_percent.addEventListener("input", updateRatioExplain);

sf.default_cap_minutes.addEventListener("input", updateRatioExplain);

// ---------- نمودار فاصله‌های لایتنر

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

function cumulative(intervals) {
  let sum = 0;
  return intervals.map((d) => (sum += d));
}

const CHART_STEP = 30;

        // طول نمودار یک ماه یک ماه عوض می‌شود
const CHART_LIMIT = 3650;

function lastReviewDay() {
  return cumulative(intervalDraft).at(-1) || 0;
}

/** طول پیشنهادی نمودار: کمی بیشتر از آخرین مرور، مضربی از یک ماه */
function niceChartMax(intervals) {
  const last = cumulative(intervals).at(-1) || 30;
  return Math.max(60, Math.ceil((last * 1.25) / CHART_STEP) * CHART_STEP);
}

/** اگر مرور آخر از انتهای نمودار رد شد، نمودار بلندتر می‌شود؛ کوتاه‌تر را خود کاربر انتخاب می‌کند */
function fitChart() {
  chartMax = Math.max(chartMax, Math.ceil(lastReviewDay() / CHART_STEP) * CHART_STEP);
}

function renderChartLength() {
  const months = chartMax / CHART_STEP;
  $("#chart-length-label").textContent = t("{0} ماه", fa(months));
  $("#chart-length-label").title = t("{0} روز", fa(chartMax));
  $("#chart-longer").disabled = chartMax + CHART_STEP > CHART_LIMIT;
  const blocked = chartMax - CHART_STEP < Math.max(CHART_STEP, lastReviewDay());
  $("#chart-shorter").disabled = blocked;
  $("#chart-shorter").title = blocked ? t("مرور آخر روز {0} است؛ اول آن را جلوتر بیاورید", fa(lastReviewDay())) : t("یک ماه کمتر");
}

function removeInterval(index) {
  if (intervalDraft.length <= 1) return;
  // با حذف یک مرور، مرورهای بعدی سر روز خودشان می‌مانند
  const points = cumulative(intervalDraft).filter((_, j) => j !== index);
  intervalDraft = points.map((p, j) => p - (j ? points[j - 1] : 0));
  renderIntervalChart();
}

/** محور زمان: روز صفر (خواندن) سمت راست است و زمان به چپ جلو می‌رود.
 *  مقیاس جذری است تا فاصله‌های کوتاه (۱ و ۳ روز) هم جا داشته باشند. */
function chartGeometry() {
  const box = $("#interval-chart");
  const width = Math.max(box.clientWidth, 400);
  const pad = 36;
  const x = (day) => width - pad - (width - 2 * pad) * Math.sqrt(day / chartMax);
  const dayAt = (px) => {
    const frac = Math.min(1, Math.max(0, (width - pad - px) / (width - 2 * pad)));
    return Math.round(chartMax * frac * frac);
  };
  return { width, x, dayAt };
}

function renderIntervalChart() {
  const box = $("#interval-chart");
  const { width, x } = chartGeometry();
  const axisY = 70;
  const points = cumulative(intervalDraft);
  // برچسب‌های محور؛ انتهای نمودار همیشه برچسب دارد و برچسب خیلی نزدیک به آن حذف می‌شود
  const ticks = [1, 3, 7, 14, 30, 60, 90, 180, 365, 730, 1825]
    .filter((d) => d < chartMax * 0.85).concat(chartMax);
  const chart = svg("svg", { viewBox: `0 0 ${width} 130` },
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
  );
  box.replaceChildren(chart);
  const single = intervalDraft.length <= 1;
  $("#interval-explain").replaceChildren(...intervalDraft.map((d, i) =>
    el("li", {}, t("{0} روز بعد از {1}", fa(d), i ? t("مرور {0}", fa(i)) : t("خواندن"))
      + t(" (یعنی روز {0} بعد از خواندن) ", fa(points[i])),
      !single && el("button", {
        type: "button", class: "link danger", title: t("حذف مرور {0}", fa(i + 1)),
        onclick: () => removeInterval(i),
      }, "×"))));
  $("#interval-remove").disabled = single;
  renderChartLength();
  updateRatioExplain();
  renderIntervalPresets();
}

(function setupIntervalChart() {
  const box = $("#interval-chart");
  let dragIndex = null;
  box.addEventListener("pointerdown", (e) => {
    const point = e.target.closest(".point");
    if (!point) return;
    e.preventDefault();
    dragIndex = Number(point.dataset.index);
    try { box.setPointerCapture(e.pointerId); } catch (error) { /* رویداد ساختگی */ }
    point.classList.add("active");
  });
  box.addEventListener("pointermove", (e) => {
    if (dragIndex === null) return;
    const { dayAt } = chartGeometry();
    const rect = box.getBoundingClientRect();
    const scale = chartGeometry().width / rect.width;
    const points = cumulative(intervalDraft);
    const low = (dragIndex ? points[dragIndex - 1] : 0) + 1;
    const high = dragIndex < points.length - 1 ? points[dragIndex + 1] - 1 : chartMax;
    const day = Math.min(high, Math.max(low, dayAt((e.clientX - rect.left) * scale)));
    // فقط همین مرور جابه‌جا می‌شود؛ مرورهای بعدی سر روز خودشان می‌مانند
    points[dragIndex] = day;
    intervalDraft = points.map((p, i) => p - (i ? points[i - 1] : 0));
    renderIntervalChart();
    box.querySelector(`.point[data-index="${dragIndex}"]`).classList.add("active");
  });
  const stop = () => {
    if (dragIndex === null) return;
    dragIndex = null;
    box.querySelectorAll(".point.active").forEach((n) => n.classList.remove("active"));
  };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  box.addEventListener("dblclick", (e) => {
    const point = e.target.closest(".point");
    if (point) removeInterval(Number(point.dataset.index));
  });
})();

$("#interval-add").addEventListener("click", () => {
  const last = intervalDraft.at(-1) || 1;
  intervalDraft.push(Math.min(last * 2, 365));
  fitChart();
  renderIntervalChart();
});

$("#interval-remove").addEventListener("click", () => removeInterval(intervalDraft.length - 1));

$("#chart-longer").addEventListener("click", () => { chartMax += CHART_STEP; renderIntervalChart(); });

$("#chart-shorter").addEventListener("click", () => { chartMax -= CHART_STEP; renderIntervalChart(); });

// فاصله‌های آماده. بعد از انتخاب، باز هم می‌شود نقطه‌ها را روی نمودار جابه‌جا کرد.
const INTERVAL_PRESETS = [
  [t("استاندارد"), [1, 3, 7, 30]],
  [t("فشرده (امتحان نزدیک)"), [1, 2, 4, 7]],
  [t("لایتنر کلاسیک"), [1, 2, 4, 8, 16]],
  [t("بلندمدت"), [1, 3, 7, 14, 30, 60, 120]],
  [t("سبک (مرور کم)"), [3, 14, 45]],
];

function renderIntervalPresets() {
  const current = intervalDraft.join();
  $("#interval-presets").replaceChildren(...INTERVAL_PRESETS.map(([name, days]) =>
    el("button", {
      type: "button", "aria-selected": String(days.join() === current),
      title: t("{0} روز", days.map(fa).join(t("، "))),
      onclick: () => {
        intervalDraft = [...days];
        chartMax = niceChartMax(intervalDraft);
        renderIntervalChart();
      },
    }, `${name}: ${days.map(fa).join(t("، "))}`)));
}

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
    default_review_ratio: percentToRatio(Number(sf.ratio_percent.value)),
    review_intervals: intervalDraft,
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

$("#close-settings").addEventListener("click", () => $("#settings-dialog").close());
