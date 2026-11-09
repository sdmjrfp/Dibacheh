import { weekStart } from "./calendar.js";
import { $, api, el, fa, minutesText, showMessage, state } from "./core.js";
import { svg } from "./settings.js";

/* پنجرهٔ گزارش: خلاصهٔ هفته، نمودار ۱۲ هفتهٔ اخیر، نقشهٔ فعالیت سالانه و پیشرفت دسته‌ها.

   نمودارها با SVG ساده کشیده می‌شوند و به کتابخانه و اینترنت نیاز ندارند.
   رنگ خواندن، مرور و روتین همان رنگ‌های تقویم است.
*/

const KINDS = [["read", "خواندن"], ["review", "مرور"], ["routine", "روتین"]];

let reportPeriod = "week";

  // week، month یا all
let reportDate = null;

      // یک روز از بازهٔ نمایش‌داده‌شده

/** یک راهنمای کوچک برای مقدار هر مستطیل نمودار */
function chartTip() {
  let tip = $("#chart-tip");
  if (!tip) {
    tip = el("div", { id: "chart-tip", class: "chart-tip", hidden: true });
    $("#stats-dialog").append(tip);
  }
  return tip;
}

function attachTip(node, lines) {
  const show = (x, y) => {
    const tip = chartTip();
    tip.replaceChildren(...lines.map(([value, label]) =>
      el("div", {}, el("strong", {}, value), label ? ` ${label}` : "")));
    tip.hidden = false;
    tip.style.left = `${Math.max(8, Math.min(x + 12, window.innerWidth - tip.offsetWidth - 8))}px`;
    tip.style.top = `${y + 14}px`;
  };
  node.setAttribute("tabindex", "0");
  node.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
  node.addEventListener("pointerleave", () => { chartTip().hidden = true; });
  node.addEventListener("focus", () => { const r = node.getBoundingClientRect(); show(r.left, r.bottom); });
  node.addEventListener("blur", () => { chartTip().hidden = true; });
}

function statTile(value, label) {
  return el("div", { class: "stat-tile" }, el("div", { class: "stat-value" }, value), el("div", { class: "muted small" }, label));
}

/** عنوان بازه، و یک روز از بازهٔ قبل و بعد */
function periodInfo(w) {
  if (w.period === "week") {
    return {
      title: `هفتهٔ ${Jalali.formatShort(w.start)} تا ${Jalali.format(w.end)}`,
      previous: Jalali.addDays(w.start, -1), next: Jalali.addDays(w.end, 1), nextLabel: "برنامهٔ هفتهٔ بعد",
    };
  }
  if (w.period === "month") {
    const { y, m } = Jalali.toJalali(w.start);
    return {
      title: `${Jalali.MONTHS[m - 1]} ${fa(y)}`,
      previous: Jalali.addDays(w.start, -1), next: Jalali.addDays(w.end, 1), nextLabel: "برنامهٔ ماه بعد",
    };
  }
  return { title: `از ${Jalali.format(w.start)} تا امروز`, nextLabel: "کار باقی‌مانده" };
}

/** نمرهٔ این بازه، با سهم هر بخش */
function scoreCard(score) {
  const part = (label, value, max) => el("div", { class: "score-part" },
    el("span", { class: "small" }, `${label}: ${fa(value)} از ${fa(max)}`),
    el("div", { class: "progress" }, el("span", { style: `width:${Math.round((100 * value) / max)}%` })));
  return el("div", { class: "score-card" },
    el("div", { class: "score-total" }, el("strong", {}, fa(score.total)), el("span", { class: "muted small" }, `از ${fa(100)}`), el("span", {}, score.label)),
    el("div", { class: "score-parts" },
      part("منظم بودن", score.regularity, 40),
      part("حجم کار", score.volume, 40),
      part("مرور سر وقت", score.on_time, 20)));
}

function summarySection(w) {
  const t = w.totals;
  const total = t.read + t.review + t.routine;
  const info = periodInfo(w);
  const reachedNow = !info.next || info.next > state.today;
  return el("section", { class: "stats-section" },
    el("div", { class: "panel-head" },
      el("h3", {}, info.title),
      el("span", { class: "spacer" }),
      info.previous && el("button", { type: "button", class: "icon", title: "قبلی", onclick: () => openStats(w.period, info.previous) }, "→"),
      info.previous && el("button", { type: "button", class: "icon", title: "بعدی", disabled: reachedNow, onclick: () => openStats(w.period, info.next) }, "←"),
      el("button", {
        type: "button",
        onclick: async () => {
          const result = await api("POST", "/api/export/report", { period: w.period, date: reportDate });
          await api("POST", "/api/export/reveal", { name: result.name });
          showMessage(`گزارش ذخیره شد: ${result.name}`, false);
        },
      }, "⇪ خروجی گزارش")),
    w.score && scoreCard(w.score),
    el("div", { class: "stat-row" },
      statTile(minutesText(total), "زمان مطالعه"),
      statTile(fa(w.done_count), "کار انجام‌شده"),
      statTile(w.period === "all" ? fa(w.active_days) : `${fa(w.active_days)} از ${fa(w.length)}`, "روز فعال"),
      statTile(minutesText(w.next_minutes), info.nextLabel)),
    w.courses.length
      ? el("table", { class: "sessions" },
          el("thead", {}, el("tr", {}, ...["درس", "خواندن", "مرور", "روتین"].map((h) => el("th", {}, h)))),
          el("tbody", {}, w.courses.map((c) => el("tr", {},
            el("td", {}, c.title), el("td", {}, fa(c.read)), el("td", {}, fa(c.review)), el("td", {}, fa(c.routine))))))
      : el("p", { class: "muted" }, "در این بازه کاری ثبت نشده."),
    w.overdue.length
      ? el("p", {}, `عقب‌افتاده: ${w.overdue.map((o) => `${o.title} (${fa(o.count)})`).join("، ")}`)
      : el("p", { class: "muted small" }, "کار عقب‌افتاده‌ای نیست."),
  );
}

/** نمودار ستونی انباشته: زمان هر هفته یا ماه به تفکیک نوع کار */
function stackedChart(weeks, name, label, every) {
  const W = 720, H = 200, top = 12, bottom = 26, left = 8, right = 44;
  const plot = H - top - bottom;
  const max = Math.max(60, ...weeks.map((w) => w.read + w.review + w.routine));
  const nice = Math.ceil(max / 60) * 60;
  const y = (m) => top + plot - (plot * m) / nice;
  const slot = (W - left - right) / weeks.length;
  const barW = Math.min(30, slot - 8);
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "bars-chart", role: "img", "aria-label": `زمان مطالعهٔ ۱۲ ${name} اخیر` });
  for (const m of [nice / 2, nice]) {
    chart.append(svg("line", { class: "grid", x1: left, x2: W - right, y1: y(m), y2: y(m) }),
      svg("text", { class: "axis-text", x: W - right + 6, y: y(m) + 4, "text-anchor": "end" }, `${fa(Math.round(m / 60))} ساعت`));
  }
  chart.append(svg("line", { class: "baseline", x1: left, x2: W - right, y1: y(0), y2: y(0) }));
  // زمان از راست به چپ جلو می‌رود، مثل تقویم راست‌به‌چپ
  weeks.forEach((w, i) => {
    const x = W - right - slot * (i + 1) + (slot - barW) / 2;
    const group = svg("g", { class: "bar" });
    let base = 0;
    for (const [kind] of KINDS) {
      if (!w[kind]) continue;
      const y1 = y(base + w[kind]);
      const height = Math.max(y(base) - y1 - 2, 1);   // ۲ پیکسل فاصله بین تکه‌ها
      group.append(svg("rect", { x, y: y1, width: barW, height, rx: 3, fill: `var(--c-${kind})` }));
      base += w[kind];
    }
    // ناحیهٔ لمس بزرگ‌تر از خود ستون
    group.append(svg("rect", { x: x - 4, y: top, width: barW + 8, height: plot, fill: "transparent" }));
    attachTip(group, [
      [label(w), ""],
      ...KINDS.map(([kind, label]) => [`${fa(w[kind])} دقیقه`, label]),
    ]);
    chart.append(group);
    if (i % every === 0) {
      chart.append(svg("text", { class: "axis-text", x: x + barW / 2, y: H - 8, "text-anchor": "middle" }, label(w)));
    }
  });
  return chart;
}

function chartLegend() {
  return el("div", { class: "chart-legend" }, KINDS.map(([kind, label]) =>
    el("span", {}, el("i", { style: `background:var(--c-${kind})` }), label)));
}

/** نقشهٔ فعالیت: هر خانه یک روز، هر ستون یک هفته، پررنگ‌تر یعنی مطالعهٔ بیشتر */
function activityMap(days) {
  const minutes = new Map(days.map((d) => [d.date, d.read + d.review + d.routine]));
  const values = [...minutes.values()].filter(Boolean).sort((a, b) => a - b);
  const quantile = (q) => values[Math.floor((values.length - 1) * q)] || 0;
  const steps = [quantile(0.25), quantile(0.5), quantile(0.75)];
  const level = (m) => (!m ? 0 : 1 + steps.filter((s) => m > s).length);
  const cell = 13, gap = 3, weeks = 53, labelH = 16;
  const W = weeks * (cell + gap), H = labelH + 7 * (cell + gap);
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "heat-chart", role: "img", "aria-label": "نقشهٔ فعالیت یک سال اخیر" });
  const firstWeek = Jalali.addDays(weekStart(state.today), -7 * (weeks - 1));
  let lastMonth = null;
  for (let w = 0; w < weeks; w++) {
    const x = W - (w + 1) * (cell + gap);   // هفتهٔ قدیمی سمت راست
    const start = Jalali.addDays(firstWeek, 7 * w);
    const month = Jalali.toJalali(start).m;
    if (month !== lastMonth && w < weeks - 1) {
      chart.append(svg("text", { class: "axis-text", x: x + cell, y: 11, "text-anchor": "end" }, Jalali.MONTHS[month - 1]));
      lastMonth = month;
    }
    for (let d = 0; d < 7; d++) {
      const iso = Jalali.addDays(start, d);
      if (iso > state.today) continue;
      const value = minutes.get(iso) || 0;
      const rect = svg("rect", { x, y: labelH + d * (cell + gap), width: cell, height: cell, rx: 3, class: `heat l${level(value)}` });
      attachTip(rect, [[value ? minutesText(value) : "بدون مطالعه", ""], [Jalali.format(iso), ""]]);
      chart.append(rect);
    }
  }
  return el("div", { class: "heat-wrap" }, chart,
    el("div", { class: "chart-legend" }, "کمتر",
      ...[0, 1, 2, 3, 4].map((l) => el("i", { class: `heat-key l${l}` })), "بیشتر"));
}

function categoriesSection(categories) {
  return el("div", { class: "cat-progress" }, categories.map((c) => {
    const percent = c.total ? Math.round((100 * c.read) / c.total) : 0;
    return el("div", { class: "cat-row" },
      el("span", {}, c.name),
      el("div", { class: "progress" }, el("span", { style: `width:${percent}%` })),
      el("span", { class: "muted small" }, `${fa(percent)}٪ · ${fa(c.items)} درس`));
  }));
}

/** نمودار با جدول همان داده‌ها */
function chartSection(rows, name, label, every, hasWork) {
  return el("section", { class: "stats-section" },
    el("h3", {}, `زمان مطالعهٔ ۱۲ ${name} اخیر`),
    hasWork ? stackedChart(rows, name, label, every) : el("p", { class: "muted" }, "بعد از ثبت اولین کار، نمودار اینجا می‌آید."),
    chartLegend(),
    el("details", {}, el("summary", { class: "small" }, "نمایش به شکل جدول"),
      el("table", { class: "sessions" },
        el("thead", {}, el("tr", {}, ...[name, "خواندن", "مرور", "روتین"].map((h) => el("th", {}, h)))),
        el("tbody", {}, rows.map((r) => el("tr", {},
          el("td", {}, label(r)), el("td", {}, fa(r.read)), el("td", {}, fa(r.review)), el("td", {}, fa(r.routine))))))));
}

function monthLabel(row) {
  return Jalali.MONTHS[Jalali.toJalali(row.start).m - 1];
}

function renderReportTabs() {
  const tabs = [["week", "هفتگی"], ["month", "ماهانه"], ["all", "کلی"]];
  $("#report-tabs").replaceChildren(...tabs.map(([key, label]) =>
    el("button", { type: "button", role: "tab", "aria-selected": String(reportPeriod === key), onclick: () => openStats(key) }, label)));
}

/** گزارش یک بازه را باز می‌کند. date: یک روز از بازه؛ خالی یعنی بازهٔ فعلی. */
async function openStats(period = reportPeriod, date = null) {
  reportPeriod = period;
  reportDate = date;
  const query = new URLSearchParams({ period });
  if (date) query.set("date", date);
  const data = await (await fetch(`/api/stats?${query}`)).json();
  const hasWork = data.days.length > 0;
  const sections = [summarySection(data.summary)];
  if (period === "week") {
    sections.push(chartSection(data.weeks, "هفته", (w) => Jalali.formatShort(w.start), 3, hasWork));
  } else if (period === "month") {
    sections.push(chartSection(data.months, "ماه", monthLabel, 1, hasWork));
  } else {
    sections.push(el("section", { class: "stats-section" }, el("h3", {}, "نقشهٔ فعالیت یک سال اخیر"), activityMap(data.days)));
    if (data.categories.length) {
      sections.push(el("section", { class: "stats-section" }, el("h3", {}, "پیشرفت خواندن هر دسته"), categoriesSection(data.categories)));
    }
  }
  renderReportTabs();
  $("#stats-body").replaceChildren(...sections);
  if (!$("#stats-dialog").open) $("#stats-dialog").showModal();
}

$("#stats-button").addEventListener("click", () => openStats("week"));

$("#close-stats").addEventListener("click", () => $("#stats-dialog").close());
