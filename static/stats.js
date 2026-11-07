/* پنجرهٔ گزارش: خلاصهٔ هفته، نمودار ۱۲ هفتهٔ اخیر، نقشهٔ فعالیت سالانه و پیشرفت دسته‌ها.

   نمودارها با SVG ساده کشیده می‌شوند و به کتابخانه و اینترنت نیاز ندارند.
   رنگ خواندن، مرور و روتین همان رنگ‌های تقویم است.
*/

const KINDS = [["read", "خواندن"], ["review", "مرور"], ["routine", "روتین"]];
let reportWeek = null;   // یک روز از هفتهٔ نمایش‌داده‌شده

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

function weeklySection(w, data) {
  const t = w.totals;
  const total = t.read + t.review + t.routine;
  const isThisWeek = weekStart(state.today) === w.start;
  return el("section", { class: "stats-section" },
    el("div", { class: "panel-head" },
      el("h3", {}, `هفتهٔ ${Jalali.formatShort(w.start)} تا ${Jalali.format(w.end)}`),
      el("span", { class: "spacer" }),
      el("button", { type: "button", class: "icon", title: "هفتهٔ قبل", onclick: () => openStats(Jalali.addDays(w.start, -7)) }, "→"),
      el("button", { type: "button", class: "icon", title: "هفتهٔ بعد", disabled: isThisWeek, onclick: () => openStats(Jalali.addDays(w.start, 7)) }, "←"),
      el("button", {
        type: "button",
        onclick: async () => {
          const result = await api("POST", "/api/export/report", { week: w.start });
          await api("POST", "/api/export/reveal", { name: result.name });
          showMessage(`گزارش ذخیره شد: ${result.name}`, false);
        },
      }, "⇪ خروجی گزارش")),
    el("div", { class: "stat-row" },
      statTile(minutesText(total), "زمان مطالعه"),
      statTile(fa(w.done_count), "کار انجام‌شده"),
      statTile(`${fa(w.active_days)} از ۷`, "روز فعال"),
      statTile(minutesText(w.next_week_minutes), "برنامهٔ هفتهٔ بعد")),
    w.courses.length
      ? el("table", { class: "sessions" },
          el("thead", {}, el("tr", {}, ...["درس", "خواندن", "مرور", "روتین"].map((h) => el("th", {}, h)))),
          el("tbody", {}, w.courses.map((c) => el("tr", {},
            el("td", {}, c.title), el("td", {}, fa(c.read)), el("td", {}, fa(c.review)), el("td", {}, fa(c.routine))))))
      : el("p", { class: "muted" }, "در این هفته کاری ثبت نشده."),
    w.overdue.length
      ? el("p", {}, `عقب‌افتاده: ${w.overdue.map((o) => `${o.title} (${fa(o.count)})`).join("، ")}`)
      : el("p", { class: "muted small" }, "کار عقب‌افتاده‌ای نیست."),
  );
}

/** نمودار ستونی انباشته: زمان هر هفته به تفکیک نوع کار */
function weeksChart(weeks) {
  const W = 720, H = 200, top = 12, bottom = 26, left = 8, right = 44;
  const plot = H - top - bottom;
  const max = Math.max(60, ...weeks.map((w) => w.read + w.review + w.routine));
  const nice = Math.ceil(max / 60) * 60;
  const y = (m) => top + plot - (plot * m) / nice;
  const slot = (W - left - right) / weeks.length;
  const barW = Math.min(30, slot - 8);
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "bars-chart", role: "img", "aria-label": "زمان مطالعهٔ ۱۲ هفتهٔ اخیر" });
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
      [Jalali.formatShort(w.start), "شروع هفته"],
      ...KINDS.map(([kind, label]) => [`${fa(w[kind])} دقیقه`, label]),
    ]);
    chart.append(group);
    if (i % 3 === 0) {
      chart.append(svg("text", { class: "axis-text", x: x + barW / 2, y: H - 8, "text-anchor": "middle" }, Jalali.formatShort(w.start)));
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

async function openStats(week = null) {
  reportWeek = week;
  const url = week ? `/api/stats?week=${week}` : "/api/stats";
  const data = await (await fetch(url)).json();
  const hasWork = data.days.length > 0;
  $("#stats-body").replaceChildren(
    weeklySection(data.weekly, data),
    el("section", { class: "stats-section" },
      el("h3", {}, "زمان مطالعهٔ ۱۲ هفتهٔ اخیر"),
      hasWork ? weeksChart(data.weeks) : el("p", { class: "muted" }, "بعد از ثبت اولین کار، نمودار اینجا می‌آید."),
      chartLegend(),
      el("details", {}, el("summary", { class: "small" }, "نمایش به شکل جدول"),
        el("table", { class: "sessions" },
          el("thead", {}, el("tr", {}, ...["شروع هفته", "خواندن", "مرور", "روتین"].map((h) => el("th", {}, h)))),
          el("tbody", {}, data.weeks.map((w) => el("tr", {},
            el("td", {}, Jalali.format(w.start)), el("td", {}, fa(w.read)), el("td", {}, fa(w.review)), el("td", {}, fa(w.routine)))))))),
    el("section", { class: "stats-section" }, el("h3", {}, "نقشهٔ فعالیت یک سال اخیر"), activityMap(data.days)),
    data.categories.length
      ? el("section", { class: "stats-section" }, el("h3", {}, "پیشرفت خواندن هر دسته"), categoriesSection(data.categories))
      : "",
  );
  if (!$("#stats-dialog").open) $("#stats-dialog").showModal();
}

$("#stats-button").addEventListener("click", () => openStats());
$("#close-stats").addEventListener("click", () => $("#stats-dialog").close());
