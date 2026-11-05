/* تقویم هفتگی و ماهانهٔ شمسی.

   این فایل بعد از app.js بار می‌شود و از ابزارهای آن (state، el، api، ...) استفاده می‌کند.
   تقویم فقط برنامه‌ای را که سرور ساخته نشان می‌دهد. هر تغییری (جابه‌جایی، تعویق،
   سقف روز) به سرور فرستاده می‌شود و برنامهٔ تازه برمی‌گردد.

   تقویم عمداً هیچ گزینهٔ حذفی ندارد.
*/

let calView = "week";     // "week" یا "month"
let calAnchor = null;     // یک روز از هفته یا ماهی که نشان داده می‌شود

const KIND_LABEL = { read: "خواندن", review: "مرور", routine: "روتین" };

// ---------------------------------------------------------------------------
// داده‌های کمکی
// ---------------------------------------------------------------------------

/** نقشهٔ تاریخ → روز برنامه */
function planDays() {
  return new Map(state.plan.days.map((day) => [day.date, day]));
}

/** نقشهٔ شمارهٔ جلسه → {item, session} */
function sessionIndex() {
  const index = new Map();
  for (const item of state.items) {
    for (const session of item.sessions) index.set(session.id, { item, session });
  }
  return index;
}

/** اولین روزی که هر جلسه مرور دارد. فقط همین مرور قابل جابه‌جایی است. */
function firstReviewDates() {
  const first = new Map();
  for (const day of state.plan.days) {
    for (const t of day.tasks) {
      if (t.kind === "review" && !first.has(t.session_id)) first.set(t.session_id, day.date);
    }
  }
  return first;
}

/** نقشهٔ تاریخ → کارهای انجام‌شدهٔ آن روز (از سابقه) */
function historyByDate() {
  const map = new Map();
  for (const entry of state.history) {
    if (!map.has(entry.date)) map.set(entry.date, []);
    map.get(entry.date).push(entry);
  }
  return map;
}

/** شنبهٔ هفتهٔ یک روز (هفتهٔ ایرانی از شنبه شروع می‌شود) */
function weekStart(iso) {
  const weekday = new Date(iso + "T00:00:00Z").getUTCDay();  // 0 = یکشنبه ... 6 = شنبه
  return Jalali.addDays(iso, -((weekday + 1) % 7));
}

/** آیا این کار را می‌شود جابه‌جا کرد؟ خروجی: null یعنی بله، وگرنه دلیلش */
function whyNotMovable(task, date, index, firstReviews) {
  if (task.kind === "routine") return "کار روتین جابه‌جا نمی‌شود؛ اگر یک روز انجام نشود، فقط همان روز از دست می‌رود.";
  const info = index.get(task.session_id);
  if (!info) return "جلسه پیدا نشد.";
  if (task.kind === "review") {
    if (info.session.status !== "reviewing") return "این جلسه هنوز خوانده نشده؛ خواندنش را جابه‌جا کنید تا مرورها هم با آن بروند.";
    if (firstReviews.get(task.session_id) !== date) return "فقط مرور بعدی این جلسه جابه‌جا می‌شود؛ مرورهای بعدی خودشان با آن جابه‌جا می‌شوند.";
  }
  return null;
}

// ---------------------------------------------------------------------------
// کشیدن کل تقویم
// ---------------------------------------------------------------------------

function renderCalendar() {
  if (!calAnchor) calAnchor = state.today;
  $("#view-week").setAttribute("aria-selected", String(calView === "week"));
  $("#view-month").setAttribute("aria-selected", String(calView === "month"));

  const selected = state.items.find((item) => item.id === selectedItemId);
  const note = $("#selected-item-note");
  note.hidden = !selected;
  if (selected) note.textContent = `روزهایی که «${selected.title}» کار دارد پررنگ شده‌اند. برای برداشتن، دوباره روی نام درس کلیک کنید.`;

  const context = {
    days: planDays(), index: sessionIndex(), firstReviews: firstReviewDates(), history: historyByDate(),
  };
  const box = $("#calendar");
  if (calView === "week") {
    const start = weekStart(calAnchor);
    const end = Jalali.addDays(start, 6);
    $("#cal-title").textContent = `${Jalali.formatShort(start)} تا ${Jalali.format(end)}`;
    box.replaceChildren(weekView(start, context));
  } else {
    const { y, m } = Jalali.toJalali(calAnchor);
    $("#cal-title").textContent = `${Jalali.MONTHS[m - 1]} ${fa(y)}`;
    box.replaceChildren(monthView(y, m, context));
  }
}

function weekView(start, context) {
  const grid = el("div", { class: "week" });
  for (let i = 0; i < 7; i++) {
    const iso = Jalali.addDays(start, i);
    const day = context.days.get(iso);
    const column = el("div", { class: dayClasses(iso, day, "cal-day week-day"), "data-date": iso },
      dayHeader(iso, day),
      el("div", { class: "tasks" },
        (context.history.get(iso) || []).map((entry) => historyChip(entry, context)),
        day ? day.tasks.map((t) => taskChip(t, iso, context, false)) : []),
    );
    if (iso < state.today && !context.history.has(iso)) column.append(el("p", { class: "muted small" }, "کاری ثبت نشده"));
    else if (iso >= state.today && !day) column.append(el("p", { class: "muted small" }, "کاری نمانده"));
    else if (day.is_off) column.append(el("p", { class: "muted small" }, "تعطیل"));
    grid.append(column);
  }
  return grid;
}

function monthView(y, m, context) {
  const first = Jalali.fromJalali(y, m, 1);
  const length = Jalali.monthLength(y, m);
  const offset = Math.round((new Date(first) - new Date(weekStart(first))) / 86400000);
  const grid = el("div", { class: "month" },
    ...["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
      .map((name) => el("div", { class: "month-head" }, name)));
  for (let i = 0; i < offset; i++) grid.append(el("div", { class: "month-blank" }));
  for (let d = 1; d <= length; d++) {
    const iso = Jalali.addDays(first, d - 1);
    const day = context.days.get(iso);
    const tasks = day ? day.tasks : [];
    const shown = tasks.slice(0, 5);
    const cell = el("div", {
      class: dayClasses(iso, day, "cal-day month-day"),
      "data-date": iso,
      title: "برای دیدن کامل این هفته کلیک کنید",
      onclick: (e) => {
        if (e.target.closest(".task")) return;
        calView = "week";
        calAnchor = iso;
        renderCalendar();
      },
    },
      el("div", { class: "month-day-head" },
        el("strong", {}, fa(d)),
        context.history.has(iso) && el("span", { class: "done-count", title: "کارهای انجام‌شده" },
          `✓ ${fa(context.history.get(iso).length)}`),
        day && !day.is_off && el("span", { class: "muted small" }, `${fa(day.total)}/${fa(day.cap)}`),
        day && day.is_off && el("span", { class: "muted small" }, "تعطیل")),
      ...shown.map((t) => taskChip(t, iso, context, true)),
      tasks.length > shown.length && el("span", { class: "muted small" }, `+${fa(tasks.length - shown.length)} کار دیگر`),
    );
    grid.append(cell);
  }
  return grid;
}

function dayClasses(iso, day, base) {
  const classes = [base];
  if (iso === state.today) classes.push("today");
  if (iso < state.today) classes.push("past");
  if (day && day.is_off) classes.push("off");
  if (day && day.predicted) classes.push("predicted");
  if (selectedItemId && day && day.tasks.some((t) => t.item_id === selectedItemId)) classes.push("has-selected");
  return classes.join(" ");
}

function dayHeader(iso, day) {
  const header = el("button", {
    class: "day-head",
    title: iso >= state.today ? "تغییر سقف، تعطیلی، یا اضافه کردن کار به این روز" : "",
    onclick: (e) => { if (iso >= state.today) openDayMenu(iso, day, e.currentTarget); },
  },
    el("span", { class: "weekday" }, Jalali.weekday(iso)),
    el("span", {}, Jalali.formatShort(iso)),
  );
  if (day && !day.is_off) {
    // امروز: کارهای انجام‌شده هم جزو پرشدن روز حساب می‌شوند
    const used = day.total + (day.done || 0);
    const percent = Math.min(100, Math.round((100 * used) / Math.max(day.cap, 1)));
    header.append(el("span", { class: "small muted" }, `${minutesText(used)} از ${minutesText(day.cap)}`));
    if (day.done) header.append(el("span", { class: "small done-count" }, `✓ ${minutesText(day.done)} انجام شد`));
    header.append(el("span", { class: `load${used > day.cap ? " over" : ""}` }, el("span", { style: `width:${percent}%` })));
  }
  if (day && day.predicted) header.append(el("span", { class: "small muted" }, "پیش‌بینی"));
  return header;
}

function taskChip(task, iso, context, compact) {
  const info = context.index.get(task.session_id);
  const item = info ? info.item : null;
  const session = info ? info.session : null;
  const classes = ["task", `kind-${task.kind}`];
  if (selectedItemId && task.item_id === selectedItemId) classes.push("selected");
  if (selectedItemId && task.item_id !== selectedItemId) classes.push("dim");
  if (task.overdue) classes.push("overdue");
  const movable = !whyNotMovable(task, iso, context.index, context.firstReviews);

  let label = KIND_LABEL[task.kind];
  if (task.kind === "review") label += ` ${fa(task.review_round)}`;
  if (task.partial) label += " (ادامه)";

  // تیک سریع فقط روی کارهای امروز. کار آینده از منوی خودش تیک می‌خورد.
  const quickTick = iso === state.today && canTick(task, iso, context) && el("input", {
    type: "checkbox", class: "tick", title: "انجام شد",
    onchange: () => markDone(task, "done"),
  });

  const chip = el("div", { class: classes.join(" "), "data-session": task.session_id, "data-kind": task.kind },
    el("div", { class: "task-title" },
      quickTick,
      task.manual && el("span", { title: "دستی جابه‌جا شده" }, "📌 "),
      item ? item.title : "؟"),
    !compact && el("div", { class: "task-meta" },
      el("span", {}, label),
      session && session.section_text && el("span", {}, session.section_text),
      el("span", {}, `${fa(task.minutes)} دقیقه`),
      task.overdue && el("span", { class: "error" }, "عقب‌افتاده")),
  );
  if (compact) chip.title = `${label} · ${fa(task.minutes)} دقیقه`;
  enableTaskPointer(chip, task, iso, movable);
  return chip;
}

/** کار انجام‌شده (از سابقه)، با علامت ✓ */
function historyChip(entry, context) {
  const info = context.index.get(entry.session_id);
  const title = info ? info.item.title : "درس حذف‌شده";
  const kind = entry.task_type;
  let label = KIND_LABEL[kind] || kind;
  if (entry.result === "partial") label += " (بخشی)";
  if (entry.result === "needs_more") label += " · نیاز به مرور بیشتر";
  return el("div", { class: `task done kind-${kind}`, title: "انجام شد. برای برگرداندن اشتباه، از دکمهٔ «برگرداندن» استفاده کنید." },
    el("div", { class: "task-title" }, "✓ ", title),
    el("div", { class: "task-meta" },
      el("span", {}, label),
      info && el("span", {}, `جلسهٔ ${fa(entry.sequence)}`),
      el("span", {}, `${fa(entry.minutes)} دقیقه`)));
}

/** آیا این کار را می‌شود امروز تیک زد؟ */
function canTick(task, iso, context) {
  if (task.kind === "routine") return iso === state.today;
  if (task.kind === "read") return true;
  // مرور: فقط مرور بعدیِ جلسه‌ای که واقعاً خوانده شده
  return !whyNotMovable(task, iso, context.index, context.firstReviews);
}

function markDone(task, result, minutes) {
  closePopover();
  const body = { session_id: task.session_id, kind: task.kind, result };
  if (minutes !== undefined) body.minutes = minutes;
  return api("POST", "/api/tasks/done", body);
}

// ---------------------------------------------------------------------------
// کشیدن کار به روز دیگر، یا کلیک برای باز کردن منو
// ---------------------------------------------------------------------------

function enableTaskPointer(chip, task, iso, movable) {
  let start = null;
  let dragging = false;
  let target = null;

  chip.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("input")) return;  // کلیک روی تیک، منو باز نمی‌کند
    start = { x: e.clientX, y: e.clientY };
    dragging = false;
    chip.setPointerCapture(e.pointerId);
  });
  chip.addEventListener("pointermove", (e) => {
    if (!start || !movable) return;
    if (!dragging && Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) return;
    dragging = true;
    chip.classList.add("dragging");
    $$(".drop-target").forEach((n) => n.classList.remove("drop-target"));
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const cell = under && under.closest(".cal-day");
    target = cell && cell.dataset.date >= state.today && cell.dataset.date !== iso ? cell.dataset.date : null;
    if (target) cell.classList.add("drop-target");
  });
  chip.addEventListener("pointerup", (e) => {
    if (!start) return;
    start = null;
    chip.classList.remove("dragging");
    $$(".drop-target").forEach((n) => n.classList.remove("drop-target"));
    if (dragging) {
      if (target) moveTask(task, target);
    } else {
      openTaskMenu(task, iso, chip);
    }
    e.stopPropagation();
  });
}

function moveTask(task, date) {
  return api("POST", "/api/tasks/move", { session_id: task.session_id, kind: task.kind, date }).then(closePopover);
}

// ---------------------------------------------------------------------------
// منوی کوچک (popover)
// ---------------------------------------------------------------------------

function openPopover(anchor, ...content) {
  const pop = $("#popover");
  pop.replaceChildren(...content);
  pop.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const width = pop.offsetWidth;
  // در صفحهٔ راست‌به‌چپ، منو از لبهٔ راست عنصر باز می‌شود
  let left = rect.right - width;
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - pop.offsetHeight - 4);
  pop.style.left = `${left + window.scrollX}px`;
  pop.style.top = `${top + window.scrollY}px`;
}

function closePopover() {
  $("#popover").hidden = true;
}

document.addEventListener("pointerdown", (e) => {
  if (!$("#popover").hidden && !e.target.closest("#popover")) closePopover();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePopover(); });

function openTaskMenu(task, iso, anchor) {
  const index = sessionIndex();
  const info = index.get(task.session_id);
  if (!info) return;
  const { item, session } = info;
  const blocked = whyNotMovable(task, iso, index, firstReviewDates());
  const content = [
    el("div", { class: "pop-title" }, item.title),
    el("div", { class: "muted small" },
      `${KIND_LABEL[task.kind]}${task.kind === "review" ? ` ${fa(task.review_round)}` : ""} · جلسهٔ ${fa(session.sequence)}`
      + `${session.section_text ? ` · ${session.section_text}` : ""} · ${fa(task.minutes)} دقیقه · ${Jalali.format(iso)}`),
  ];

  // ثبت انجام کار (همیشه با تاریخ امروز)
  if (canTick(task, iso, { index, firstReviews: firstReviewDates() })) {
    const early = iso > state.today ? " (امروز، زودتر از برنامه)" : "";
    if (task.kind === "review") {
      content.push(el("div", { class: "pop-row" },
        el("button", { class: "primary", onclick: () => markDone(task, "done") }, `✓ مرور انجام شد${early}`),
        el("button", { onclick: () => markDone(task, "needs_more") }, "↺ نیاز به مرور بیشتر")));
    } else {
      content.push(el("button", { class: "primary", onclick: () => markDone(task, "done") }, `✓ انجام شد${early}`));
    }
    if (task.kind === "read") {
      const minutes = el("input", { type: "number", min: 1, max: task.minutes - 1, class: "num" });
      content.push(el("div", { class: "pop-row" }, "فقط بخشی خواندم:", minutes, "دقیقه",
        el("button", { onclick: () => minutes.value && markDone(task, "partial", Number(minutes.value)) }, "ثبت")));
    }
  }

  if (item.source_type !== "none") {
    content.push(el("button", { onclick: () => api("POST", `/api/items/${item.id}/open`, {}) }, "↗ باز کردن منبع"));
  }
  if (blocked) {
    content.push(el("p", { class: "muted small" }, blocked));
  } else {
    content.push(el("button", { onclick: () => moveTask(task, Jalali.addDays(iso, 1)) }, "به تعویق انداختن به فردا"));
    const picker = el("span", { class: "jalali-input" });
    buildJalaliInput(picker, iso);
    content.push(el("div", { class: "pop-row" }, "انتقال به", picker,
      el("button", {
        onclick: () => {
          try {
            const date = readJalaliInput(picker);
            if (date) moveTask(task, date);
          } catch (error) { showMessage(error.message); }
        },
      }, "انتقال")));
    if (task.manual) {
      content.push(el("button", { onclick: () => moveTask(task, null) }, "برگشت به چینش خودکار"));
    }
  }
  if (item.item_type === "study") {
    const input = el("input", {
      type: "number", min: 1, class: "num",
      value: session.review_minutes_override || "", placeholder: "خودکار",
    });
    content.push(el("div", { class: "pop-row" }, "زمان مرور این جلسه:", input, "دقیقه",
      el("button", {
        onclick: () => api("PATCH", `/api/sessions/${session.id}`, { review_minutes_override: input.value })
          .then(closePopover),
      }, "ذخیره")));
    content.push(el("p", { class: "muted small" }, "خالی = از نسبت مرور. روی همهٔ مرورهای این جلسه اثر دارد."));
  }
  content.push(el("button", { onclick: () => { closePopover(); openItemDialog(item); } }, "✎ ویرایش درس"));
  openPopover(anchor, ...content);
}

function openDayMenu(iso, day, anchor) {
  const override = state.day_overrides[iso];
  const capInput = el("input", { type: "number", min: 0, class: "num", value: day ? day.cap : "" });
  const setCap = (value) => api("PUT", `/api/days/${iso}`, { cap_minutes: value }).then(closePopover);

  const content = [
    el("div", { class: "pop-title" }, `${Jalali.weekday(iso)} ${Jalali.format(iso)}`),
    el("div", { class: "pop-row" }, "سقف این روز:", capInput, "دقیقه",
      el("button", { onclick: () => setCap(Number(capInput.value)) }, "اعمال")),
  ];
  if (!day || !day.is_off) content.push(el("button", { onclick: () => setCap(0) }, "تعطیل کردن این روز"));
  if (override !== undefined) content.push(el("button", { onclick: () => setCap(null) }, "برگشت به سقف عادی"));

  // کارهای روزهای بعد که می‌شود به این روز جلو آورد
  const index = sessionIndex();
  const firstReviews = firstReviewDates();
  const candidates = [];
  for (const d of state.plan.days) {
    if (d.date <= iso) continue;
    for (const t of d.tasks) {
      if (!whyNotMovable(t, d.date, index, firstReviews)) candidates.push([t, d.date]);
      if (candidates.length >= 30) break;
    }
    if (candidates.length >= 30) break;
  }
  if (candidates.length) {
    content.push(el("div", { class: "small" }, "جلو آوردن به این روز:"));
    content.push(el("div", { class: "pop-list" }, candidates.map(([t, date]) => {
      const info = index.get(t.session_id);
      return el("button", { class: `task-pick kind-${t.kind}`, onclick: () => moveTask(t, iso) },
        `${info.item.title} · ${KIND_LABEL[t.kind]}${t.kind === "review" ? ` ${fa(t.review_round)}` : ` جلسهٔ ${fa(info.session.sequence)}`}`
        + ` · ${fa(t.minutes)} دقیقه · الان ${Jalali.formatShort(date)}`);
    })));
  }
  content.push(el("div", { class: "pop-row" },
    el("button", { onclick: () => { closePopover(); openItemDialog(null, "study", iso); } }, "+ درس جدید از این روز"),
    el("button", { onclick: () => { closePopover(); openItemDialog(null, "routine", iso); } }, "+ کار روتین از این روز")));
  openPopover(anchor, ...content);
}

// ---------------------------------------------------------------------------
// دکمه‌های بالای تقویم
// ---------------------------------------------------------------------------

function shiftCalendar(direction) {
  if (calView === "week") {
    calAnchor = Jalali.addDays(calAnchor, 7 * direction);
  } else {
    let { y, m } = Jalali.toJalali(calAnchor);
    m += direction;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    calAnchor = Jalali.fromJalali(y, m, 1);
  }
  renderCalendar();
}

$("#view-week").addEventListener("click", () => { calView = "week"; renderCalendar(); });
$("#view-month").addEventListener("click", () => { calView = "month"; renderCalendar(); });
$("#cal-prev").addEventListener("click", () => shiftCalendar(-1));
$("#cal-next").addEventListener("click", () => shiftCalendar(1));
$("#cal-today").addEventListener("click", () => { calAnchor = state.today; renderCalendar(); });

// اگر state قبل از بار شدن این فایل رسیده باشد
if (state) renderCalendar();
