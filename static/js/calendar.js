import { openAddMenu } from "./add-menu.js";
import { $, $$, api, buildJalaliInput, el, fa, FIRST_WEEKDAY, getPref, isRTL, minutesText, readJalaliInput, renderPart, setPref, showMessage, state, t, typeOf, WEEKDAYS } from "./core.js";
import { openItemDialog } from "./item-dialog.js";
import { Motion, dragGhost } from "./motion.js";
import { selectedItemId } from "./sources.js";

/* تقویم هفتگی و ماهانهٔ شمسی.

   تقویم فقط برنامه‌ای را که سرور ساخته نشان می‌دهد. هر تغییری (جابه‌جایی، تعویق،
   سقف روز) به سرور فرستاده می‌شود و برنامهٔ تازه برمی‌گردد.

   تقویم عمداً هیچ گزینهٔ حذفی ندارد.
*/

let calView = "week";       // "day"، "week"، "month" یا "all"

let calAnchor = null;       // یک روز از هفته یا ماهی که نشان داده می‌شود

let orientation = getPref("orientation", "vertical");   // هر روز یک ستون، یا هر روز یک سطر

const hiddenKinds = new Set(getPref("hiddenKinds", []));   // نوع کارهایی که تیکشان برداشته شده

const KIND_LABEL = { read: t("خواندن"), review: t("مرور"), routine: t("روتین"), project: t("پروژه"), once: t("کار یک‌باره") };

/** نوع کار برای برچسب، رنگ و فیلتر. خواندنِ پروژه و کار یک‌باره نام و رنگ خودشان را دارند. */
function displayKind(kind, item) {
  return kind === "read" && item && item.variant !== "study" ? item.variant : kind;
}

// ---------------------------------------------------------------------------
// داده‌های کمکی
// ---------------------------------------------------------------------------

/** نقشهٔ تاریخ → روز برنامه */
function planDays() {
  return new Map([...farDays.entries(), ...state.plan.days.map((day) => [day.date, day])]);
}

// سرور فقط روزهای نزدیک را همراه هر جواب می‌فرستد. روزهای دورتر وقتی کاربر به آنها می‌رود
// جدا گرفته می‌شوند و با هر تغییر برنامه دور ریخته می‌شوند.
const farDays = new Map();
let farDaysFor = null;      // این روزها مال کدام نسخهٔ state هستند
let farRequest = "";        // آخرین بازهٔ درخواست‌شده

async function loadFarDays(start, end) {
  if (farDaysFor !== state) {
    farDays.clear();
    farDaysFor = state;
    farRequest = "";
  }
  const near = state.plan.days.at(-1).date;
  if (end <= near || state.plan.total_days <= state.plan.days.length) return;
  if (farDays.has(end) || farRequest === `${start}|${end}`) return;
  farRequest = `${start}|${end}`;
  const forState = state;
  const days = await (await fetch(`/api/plan/range?start=${start}&end=${end}`)).json();
  if (forState !== state) return;   // برنامه در این فاصله عوض شده است
  for (const day of days) farDays.set(day.date, day);
  renderCalendar();
}

/** نقشهٔ شمارهٔ جلسه → {item, session} */
function sessionIndex() {
  const index = new Map();
  for (const item of state.items) {
    for (const session of item.sessions) index.set(session.id, { item, session });
  }
  return index;
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

/** اولین روز هفتهٔ یک تاریخ. شروع هفته از تنظیمات می‌آید: شنبه، یکشنبه یا دوشنبه. */
export function weekStart(iso) {
  const weekday = (new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7;  // 0 = دوشنبه، مثل پایتون
  return Jalali.addDays(iso, -((weekday - FIRST_WEEKDAY + 7) % 7));
}

/** آیا این کار را می‌شود جابه‌جا کرد؟ خروجی: null یعنی بله، وگرنه دلیلش */
function whyNotMovable(task, index) {
  if (task.kind === "routine") return t("کار روتین جابه‌جا نمی‌شود؛ اگر یک روز انجام نشود، فقط همان روز از دست می‌رود.");
  const info = index.get(task.session_id);
  if (!info) return t("جلسه پیدا نشد.");
  if (task.kind === "review") {
    if (info.session.status !== "reviewing") return t("این جلسه هنوز خوانده نشده؛ خواندنش را جابه‌جا کنید تا مرورها هم با آن بروند.");
    if (!task.first_review) return t("فقط مرور بعدی این جلسه جابه‌جا می‌شود؛ مرورهای بعدی خودشان با آن جابه‌جا می‌شوند.");
  }
  return null;
}

// ---------------------------------------------------------------------------
// کشیدن کل تقویم
// ---------------------------------------------------------------------------

/** اولین و آخرین روز نمای فعلی */
function viewRange() {
  if (calView === "day") return [calAnchor, calAnchor];
  if (calView === "week") {
    const start = weekStart(calAnchor);
    return [start, Jalali.addDays(start, 6)];
  }
  if (calView === "all") return [state.today, Jalali.addDays(state.today, Math.max(state.plan.total_days, 1) - 1)];
  const { y, m } = Jalali.toJalali(calAnchor);
  const first = Jalali.fromJalali(y, m, 1);
  return [first, Jalali.addDays(first, Jalali.monthLength(y, m) - 1)];
}

/** تیک‌های راهنمای رنگ: هر نوع کار در برنامه نشان داده شود یا نه */
function renderLegend() {
  const kinds = ["read", "review", "routine"];
  for (const variant of ["project", "once"]) {
    if (state.items.some((item) => item.variant === variant)) kinds.splice(1, 0, variant);
  }
  renderPart("legend", [kinds, [...hiddenKinds]], () => {
    $("#legend-kinds").replaceChildren(...kinds.map((kind) =>
      el("label", { class: `legend-toggle kind-${kind}` },
        el("input", {
          type: "checkbox", checked: !hiddenKinds.has(kind),
          onchange: (e) => {
            if (e.target.checked) hiddenKinds.delete(kind);
            else hiddenKinds.add(kind);
            setPref("hiddenKinds", [...hiddenKinds]);
            renderCalendar();
          },
        }),
        KIND_LABEL[kind])));
  });
}

/** بزرگ‌ترین زمان کار در این نما، برای اینکه اندازهٔ هر کار نسبت به بقیه باشد */
function largestTask(context, start, end) {
  let largest = 1;
  for (const day of context.days.values()) {
    if (day.date < start || day.date > end) continue;
    for (const task of day.tasks) largest = Math.max(largest, task.minutes);
  }
  for (const entries of context.history.values()) {
    for (const entry of entries) if (entry.date >= start && entry.date <= end) largest = Math.max(largest, entry.minutes);
  }
  return largest;
}

export function renderCalendar() {
  if (!calAnchor) calAnchor = state.today;
  $("#view-day").setAttribute("aria-selected", String(calView === "day"));
  $("#view-week").setAttribute("aria-selected", String(calView === "week"));
  $("#view-month").setAttribute("aria-selected", String(calView === "month"));
  $("#view-all").setAttribute("aria-selected", String(calView === "all"));
  $("#orient-vertical").setAttribute("aria-selected", String(orientation === "vertical"));
  $("#orient-horizontal").setAttribute("aria-selected", String(orientation === "horizontal"));
  $("#orient-vertical").disabled = calView === "month";
  $("#orient-horizontal").disabled = calView === "month";
  for (const id of ["#cal-prev", "#cal-today", "#cal-next"]) $(id).hidden = calView === "all";
  renderLegend();

  const selected = state.items.find((item) => item.id === selectedItemId);
  const note = $("#selected-item-note");
  note.hidden = !selected;
  if (selected) note.textContent = t("روزهایی که «{0}» کار دارد پررنگ شده‌اند. برای برداشتن، دوباره روی نام درس کلیک کنید.", selected.title);

  const context = {
    days: planDays(), index: sessionIndex(), history: historyByDate(),
  };
  const box = $("#calendar");
  const [viewStart, viewEnd] = viewRange();
  loadFarDays(viewStart, viewEnd);
  context.largest = largestTask(context, viewStart, viewEnd);
  const draw = (fn) => renderPart("calendar", [
    calView, calAnchor, viewStart, viewEnd, orientation, [...hiddenKinds], selectedItemId, state.today, state.settings.colors, state.settings.color_mode,
    Object.entries(state.day_overrides).filter(([date]) => date >= viewStart && date <= viewEnd),
    state.types, state.history.filter((h) => h.date >= viewStart && h.date <= viewEnd),
    [...context.days.values()].filter((d) => d.date >= viewStart && d.date <= viewEnd),
    [...context.index.values()].map(({ item, session }) => [item.id, item.title, item.display_color, session.section_text, session.note, session.status]),
  ], fn);
  // راهنمای رنگ: در رنگ‌بندی بر اساس منبع، هر درس رنگ خودش را دارد
  $("#legend-source").hidden = state.settings.color_mode !== "source";
  if (calView === "day") {
    $("#cal-title").textContent = `${Jalali.weekday(calAnchor)} ${Jalali.format(calAnchor)}`;
    draw(() => box.replaceChildren(el("div", { class: `day-view ${orientation}` }, dayColumn(calAnchor, context, "cal-day day-column"))));
  } else if (calView === "week") {
    const start = weekStart(calAnchor);
    const end = Jalali.addDays(start, 6);
    $("#cal-title").textContent = t("{0} تا {1}", Jalali.formatShort(start), Jalali.format(end));
    draw(() => box.replaceChildren(weekView(start, context)));
  } else if (calView === "all") {
    $("#cal-title").textContent = t("از امروز تا {0} · {1} روز", Jalali.format(viewEnd), fa(state.plan.total_days));
    draw(() => box.replaceChildren(allView(viewStart, viewEnd, context)));
  } else {
    const { y, m } = Jalali.toJalali(calAnchor);
    $("#cal-title").textContent = `${Jalali.MONTHS[m - 1]} ${fa(y)}`;
    draw(() => box.replaceChildren(monthView(y, m, context)));
  }
}

/** کل برنامه، از امروز تا آخرین کار و آخرین مرور */
function allView(start, end, context) {
  const grid = el("div", { class: `all-days ${orientation}` });
  for (let iso = start; iso <= end; iso = Jalali.addDays(iso, 1)) {
    grid.append(dayColumn(iso, context, "cal-day all-day"));
  }
  return grid;
}

function weekView(start, context) {
  const grid = el("div", { class: `week ${orientation}` });
  for (let i = 0; i < 7; i++) {
    grid.append(dayColumn(Jalali.addDays(start, i), context, "cal-day week-day"));
  }
  return grid;
}

/** برنامه تا آخرین کار ساخته می‌شود، پس روز تعطیلِ بعد از آن در برنامه نیست و باید از تعطیلی‌ها خوانده شود. */
function isOff(iso, day) {
  return day ? day.is_off : state.day_overrides[iso] === 0;
}

function visibleTasks(day, context) {
  if (!day) return [];
  return day.tasks.filter((task) => {
    const info = context.index.get(task.session_id);
    return !hiddenKinds.has(displayKind(task.kind, info && info.item));
  });
}

function historyVisible(entry, context) {
  const info = context.index.get(entry.session_id);
  return !hiddenKinds.has(displayKind(entry.task_type, info && info.item));
}

/** اندازهٔ کار نسبت به بزرگ‌ترین کار این نما، فقط در نمای روزانه و هفتگی */
function sizeStyle(minutes, context) {
  if (calView !== "day" && calView !== "week") return null;
  return `--w:${(minutes / context.largest).toFixed(3)}`;
}

/** ستون کامل یک روز، برای نمای هفتگی و روزانه */
function dayColumn(iso, context, classes) {
  const day = context.days.get(iso);
  const column = el("div", { class: dayClasses(iso, day, classes), "data-date": iso },
    dayHeader(iso, day),
    el("div", { class: "tasks" },
      (context.history.get(iso) || []).filter((entry) => historyVisible(entry, context)).map((entry) => historyChip(entry, context)),
      visibleTasks(day, context).map((task) => taskChip(task, iso, context, false))),
  );
  if (iso >= state.today && isOff(iso, day)) column.append(el("p", { class: "muted small" }, t("تعطیل")));
  else if (iso < state.today && !context.history.has(iso)) column.append(el("p", { class: "muted small" }, t("کاری ثبت نشده")));
  else if (iso >= state.today && !day) column.append(el("p", { class: "muted small" }, t("کاری نمانده")));
  return column;
}

/** رنگ اختصاصی یک کار، یا null برای رنگ عادی نوعش (خواندن، مرور، روتین) */
function paintFor(item, kind) {
  if (!item) return null;
  if (state.settings.color_mode === "source") return item.display_color;
  // نوع کار ساخت کاربر: برای خواندن و روتینِ آن نوع؛ مرور همیشه رنگ مرور است
  const custom = typeOf(item);
  return custom && kind !== "review" ? custom.color : null;
}

function monthView(y, m, context) {
  const first = Jalali.fromJalali(y, m, 1);
  const length = Jalali.monthLength(y, m);
  const offset = Math.round((new Date(first) - new Date(weekStart(first))) / 86400000);
  const grid = el("div", { class: "month" },
    ...WEEKDAYS.map(([, name]) => el("div", { class: "month-head" }, name)));
  for (let i = 0; i < offset; i++) grid.append(el("div", { class: "month-blank" }));
  for (let d = 1; d <= length; d++) {
    const iso = Jalali.addDays(first, d - 1);
    const day = context.days.get(iso);
    const tasks = visibleTasks(day, context);
    const shown = tasks.slice(0, 5);
    const cell = el("div", {
      class: dayClasses(iso, day, "cal-day month-day"),
      "data-date": iso,
      title: t("برای دیدن کامل این هفته کلیک کنید"),
      onclick: (e) => {
        if (e.target.closest(".task")) return;
        calView = "week";
        calAnchor = iso;
        renderCalendar();
      },
    },
      el("div", { class: "month-day-head" },
        el("strong", {}, fa(d)),
        context.history.has(iso) && el("span", { class: "done-count", title: t("کارهای انجام‌شده") },
          `✓ ${fa(context.history.get(iso).length)}`),
        day && !day.is_off && el("span", { class: "muted small" }, `${fa(day.total)}/${fa(day.cap)}`),
        isOff(iso, day) && el("span", { class: "muted small" }, t("تعطیل"))),
      ...shown.map((task) => taskChip(task, iso, context, true)),
      tasks.length > shown.length && el("span", { class: "muted small" }, t("+{0} کار دیگر", fa(tasks.length - shown.length))),
    );
    grid.append(cell);
  }
  return grid;
}

function dayClasses(iso, day, base) {
  const classes = [base];
  if (iso === state.today) classes.push("today");
  if (iso < state.today) classes.push("past");
  if (isOff(iso, day)) classes.push("off");
  if (day && day.predicted) classes.push("predicted");
  if (selectedItemId && day && day.tasks.some((task) => task.item_id === selectedItemId)) classes.push("has-selected");
  return classes.join(" ");
}

function dayHeader(iso, day) {
  const header = el("button", {
    class: "day-head",
    title: iso >= state.today ? t("تغییر سقف، تعطیلی، یا اضافه کردن کار به این روز") : "",
    onclick: (e) => { if (iso >= state.today) openDayMenu(iso, day, e.currentTarget); },
  },
    el("span", { class: "weekday" }, Jalali.weekday(iso)),
    el("span", {}, Jalali.formatShort(iso)),
  );
  if (day && !day.is_off) {
    // امروز: کارهای انجام‌شده هم جزو پرشدن روز حساب می‌شوند
    const used = day.total + (day.done || 0);
    const percent = Math.min(100, Math.round((100 * used) / Math.max(day.cap, 1)));
    header.append(el("span", { class: "small muted" }, t("{0} از {1}", minutesText(used), minutesText(day.cap))));
    if (day.done) header.append(el("span", { class: "small done-count" }, t("✓ {0} انجام شد", minutesText(day.done))));
    header.append(el("span", { class: `load${used > day.cap ? " over" : ""}` }, el("span", { style: `width:${percent}%` })));
  }
  if (day && day.predicted) header.append(el("span", { class: "small muted" }, t("پیش‌بینی")));
  return header;
}

function taskChip(task, iso, context, compact) {
  const info = context.index.get(task.session_id);
  const item = info ? info.item : null;
  const session = info ? info.session : null;
  const shownKind = displayKind(task.kind, item);
  const classes = ["task", `kind-${shownKind}`];
  if (!compact && calView !== "all") classes.push("sized");
  if (selectedItemId && task.item_id === selectedItemId) classes.push("selected");
  if (selectedItemId && task.item_id !== selectedItemId) classes.push("dim");
  if (task.overdue) classes.push("overdue");
  const movable = !whyNotMovable(task, context.index);

  let label = KIND_LABEL[shownKind];
  if (task.kind === "review") label += ` ${fa(task.review_round)}`;
  if (task.partial) label += t(" (ادامه)");

  // تیک سریع فقط روی کارهای امروز. کار آینده از منوی خودش تیک می‌خورد.
  const quickTick = iso === state.today && canTick(task, iso, context) && el("input", {
    type: "checkbox", class: "tick", title: t("انجام شد"),
    onchange: () => markDone(task, "done"),
  });

  const paint = paintFor(item, task.kind);
  const size = compact ? null : sizeStyle(task.minutes, context);
  const style = [paint && `--c:${paint}`, size].filter(Boolean).join(";") || null;
  const chip = el("div", {
    class: classes.join(" "), style, "data-session": task.session_id, "data-kind": task.kind,
    "data-flip": taskKey(task),
  },
    el("div", { class: "task-title" },
      quickTick,
      task.manual && el("span", { title: t("دستی جابه‌جا شده") }, "📌 "),
      session && session.note && el("span", { title: session.note }, "📝 "),
      item ? item.title : t("؟")),
    !compact && el("div", { class: "task-meta" },
      el("span", {}, label),
      session && session.section_text && el("span", {}, session.section_text),
      el("span", {}, t("{0} دقیقه", fa(task.minutes))),
      task.overdue && el("span", { class: "error" }, t("عقب‌افتاده"))),
  );
  if (compact) chip.title = t("{0} · {1} دقیقه", label, fa(task.minutes));
  enableTaskPointer(chip, task, iso, movable);
  return chip;
}

/** کار انجام‌شده (از سابقه)، با علامت ✓ */
function historyChip(entry, context) {
  const info = context.index.get(entry.session_id);
  const title = info ? info.item.title : t("درس حذف‌شده");
  const kind = displayKind(entry.task_type, info && info.item);
  let label = KIND_LABEL[kind] || kind;
  if (entry.result === "partial") label += t(" (بخشی)");
  if (entry.result === "needs_more") label += t(" · نیاز به مرور بیشتر");
  const paint = info ? paintFor(info.item, entry.task_type) : null;
  const size = sizeStyle(entry.minutes, context);
  return el("div", {
    class: `task done kind-${kind}${size ? " sized" : ""}`, "data-flip": `h-${entry.id}`,
    style: [paint && `--c:${paint}`, size].filter(Boolean).join(";") || null,
    title: t("برای برگرداندن به حالت انجام‌نشده کلیک کنید"),
    onclick: (e) => openDoneMenu(entry, title, label, e.currentTarget),
  },
    el("div", { class: "task-title" }, "✓ ", title),
    el("div", { class: "task-meta" },
      el("span", {}, label),
      info && el("span", {}, t("جلسهٔ {0}", fa(entry.sequence))),
      el("span", {}, t("{0} دقیقه", fa(entry.minutes)))));
}

/** منوی کار انجام‌شده: برگرداندن به حالت انجام‌نشده */
function openDoneMenu(entry, title, label, anchor) {
  // هر تیک روی تیک قبلی همان جلسه سوار است، پس فقط آخرین تیک هر جلسه برمی‌گردد
  const later = state.history.some((h) => h.session_id === entry.session_id && h.id > entry.id);
  openPopover(anchor,
    el("div", { class: "pop-title" }, `✓ ${title}`),
    el("div", { class: "muted small" }, t("{0} · {1} دقیقه · {2}", label, fa(entry.minutes), Jalali.format(entry.date))),
    later
      ? el("p", { class: "muted small" }, t("بعد از این، کار دیگری از همین جلسه ثبت شده. اول آن را انجام‌نشده کنید."))
      : el("button", {
          class: "primary",
          onclick: () => { closePopover(); api("POST", "/api/tasks/undone", { log_id: entry.id }); },
        }, t("↩ انجام نشده")),
  );
}

/** آیا این کار را می‌شود امروز تیک زد؟ */
function canTick(task, iso, context) {
  if (task.kind === "routine") return iso === state.today;
  if (task.kind === "read") return true;
  // مرور: فقط مرور بعدیِ جلسه‌ای که واقعاً خوانده شده
  return !whyNotMovable(task, context.index);
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

/** کلید هر کار برای انیمیشن: همان کار در روز دیگر همان کلید را دارد و «سُر» می‌خورد */
function taskKey(task) {
  return `t-${task.kind}-${task.session_id}-${task.review_round || 0}`;
}

/** کلیک = منوی کار. کشیدن = یک کپی از کار همراه ماوس حرکت می‌کند و در روز دیگر رها می‌شود. */
function enableTaskPointer(chip, task, iso, movable) {
  chip.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("input")) return;  // کلیک روی تیک، منو باز نمی‌کند
    e.preventDefault();
    if (!movable) {
      // کاری که جابه‌جا نمی‌شود: فقط کلیک
      chip.addEventListener("pointerup", () => openTaskMenu(task, iso, chip), { once: true });
      return;
    }
    dragGhost(chip, e, {
      targetSelector: ".cal-day",
      canDrop: (cell) => cell.dataset.date >= state.today && cell.dataset.date !== iso,
      onDrop: async (cell, ghostRect) => {
        // کار از همان جایی که رها شد، به جای تازه‌اش در برنامه سُر می‌خورد
        Motion.overrides.set(taskKey(task), ghostRect);
        try {
          await moveTask(task, cell.dataset.date);
          return true;
        } catch (error) {
          Motion.overrides.clear();
          return false;
        }
      },
      onClick: () => openTaskMenu(task, iso, chip),
    });
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
  // منو از لبهٔ ابتدای عنصر باز می‌شود: راست در فارسی و عربی، چپ در بقیه
  let left = isRTL ? rect.right - width : rect.left;
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
  const blocked = whyNotMovable(task, index);
  const content = [
    el("div", { class: "pop-title" }, item.title),
    el("div", { class: "muted small" },
      t("{0}{1} · جلسهٔ {2}", KIND_LABEL[displayKind(task.kind, item)], task.kind === "review" ? ` ${fa(task.review_round)}` : "", fa(session.sequence))
      + t("{0} · {1} دقیقه · {2}", session.section_text ? ` · ${session.section_text}` : "", fa(task.minutes), Jalali.format(iso))),
  ];

  // ثبت انجام کار (همیشه با تاریخ امروز)
  if (canTick(task, iso, { index })) {
    const early = iso > state.today ? t(" (امروز، زودتر از برنامه)") : "";
    if (task.kind === "review") {
      content.push(el("div", { class: "pop-row" },
        el("button", { class: "primary", onclick: () => markDone(task, "done") }, t("✓ مرور انجام شد{0}", early)),
        el("button", { onclick: () => markDone(task, "needs_more") }, t("↺ نیاز به مرور بیشتر"))));
    } else {
      content.push(el("button", { class: "primary", onclick: () => markDone(task, "done") }, t("✓ انجام شد{0}", early)));
    }
    if (task.kind === "read") {
      const minutes = el("input", { type: "number", min: 1, max: task.minutes - 1, class: "num" });
      content.push(el("div", { class: "pop-row" }, t("فقط بخشی خواندم:"), minutes, t("دقیقه"),
        el("button", { onclick: () => minutes.value && markDone(task, "partial", Number(minutes.value)) }, t("ثبت"))));
    }
  }

  if (item.source_type !== "none") {
    content.push(el("button", { onclick: () => api("POST", `/api/items/${item.id}/open`, {}) }, t("↗ باز کردن منبع")));
  }
  if (blocked) {
    content.push(el("p", { class: "muted small" }, blocked));
  } else {
    content.push(el("button", { onclick: () => moveTask(task, Jalali.addDays(iso, 1)) }, t("به تعویق انداختن به فردا")));
    const picker = el("span", { class: "jalali-input" });
    buildJalaliInput(picker, iso);
    content.push(el("div", { class: "pop-row" }, t("انتقال به"), picker,
      el("button", {
        onclick: () => {
          try {
            const date = readJalaliInput(picker);
            if (date) moveTask(task, date);
          } catch (error) { showMessage(error.message); }
        },
      }, t("انتقال"))));
    if (task.manual) {
      content.push(el("button", { onclick: () => moveTask(task, null) }, t("برگشت به چینش خودکار")));
    }
  }
  if (item.item_type === "study" && !item.no_reviews) {
    const input = el("input", {
      type: "number", min: 1, class: "num",
      value: session.review_minutes_override || "", placeholder: t("خودکار"),
    });
    content.push(el("div", { class: "pop-row" }, t("زمان مرور این جلسه:"), input, t("دقیقه"),
      el("button", {
        onclick: () => api("PATCH", `/api/sessions/${session.id}`, { review_minutes_override: input.value })
          .then(closePopover),
      }, t("ذخیره"))));
    content.push(el("p", { class: "muted small" }, t("خالی = از نسبت مرور. روی همهٔ مرورهای این جلسه اثر دارد.")));
  }
  // یادداشت جلسه: موقع خواندن نوشته می‌شود و موقع مرور همین‌جا دیده می‌شود
  const note = el("textarea", { rows: 3, class: "wide-text", placeholder: t("یادداشت این جلسه: نکته یا سؤال…") });
  note.value = session.note || "";
  note.addEventListener("change", () => api("PATCH", `/api/sessions/${session.id}`, { note: note.value }));
  content.push(note);
  content.push(el("button", { onclick: () => { closePopover(); openItemDialog(item); } }, t("✎ ویرایش درس")));
  openPopover(anchor, ...content);
}

function openDayMenu(iso, day, anchor) {
  const override = state.day_overrides[iso];
  const capInput = el("input", { type: "number", min: 0, class: "num", value: day ? day.cap : "" });
  const setCap = (value) => api("PUT", `/api/days/${iso}`, { cap_minutes: value }).then(closePopover);

  const content = [
    el("div", { class: "pop-title" }, `${Jalali.weekday(iso)} ${Jalali.format(iso)}`),
    el("div", { class: "pop-row" }, t("سقف این روز:"), capInput, t("دقیقه"),
      el("button", { onclick: () => setCap(Number(capInput.value)) }, t("اعمال"))),
  ];
  if (!isOff(iso, day)) content.push(el("button", { onclick: () => setCap(0) }, t("تعطیل کردن این روز")));
  if (override !== undefined) content.push(el("button", { onclick: () => setCap(null) }, t("برگشت به سقف عادی")));

  // تعطیلی چندروزه: از همین روز تا تاریخ انتخابی
  const until = el("span", { class: "jalali-input" });
  buildJalaliInput(until, Jalali.addDays(iso, 6));
  const setRange = (cap) => {
    try {
      const end = readJalaliInput(until);
      if (end) api("POST", "/api/days/range", { start: iso, end, cap_minutes: cap }).then(closePopover);
    } catch (error) { showMessage(error.message); }
  };
  content.push(el("div", { class: "small" }, t("تعطیلی چندروزه، از این روز تا:")));
  content.push(el("div", { class: "pop-row" }, until));
  content.push(el("div", { class: "pop-row" },
    el("button", { onclick: () => setRange(0) }, t("تعطیل کردن بازه")),
    el("button", { onclick: () => setRange(null) }, t("برداشتن تعطیلی بازه"))));

  // کارهای روزهای بعد که می‌شود به این روز جلو آورد
  const index = sessionIndex();
  const candidates = [];
  for (const d of state.plan.days) {
    if (d.date <= iso) continue;
    for (const task of d.tasks) {
      if (!whyNotMovable(task, index)) candidates.push([task, d.date]);
      if (candidates.length >= 30) break;
    }
    if (candidates.length >= 30) break;
  }
  if (candidates.length) {
    content.push(el("div", { class: "small" }, t("جلو آوردن به این روز:")));
    content.push(el("div", { class: "pop-list" }, candidates.map(([task, date]) => {
      const info = index.get(task.session_id);
      return el("button", { class: `task-pick kind-${displayKind(task.kind, info.item)}`, onclick: () => moveTask(task, iso) },
        `${info.item.title} · ${KIND_LABEL[displayKind(task.kind, info.item)]}${task.kind === "review" ? ` ${fa(task.review_round)}` : t(" جلسهٔ {0}", fa(info.session.sequence))}`
        + t(" · {0} دقیقه · الان {1}", fa(task.minutes), Jalali.formatShort(date)));
    })));
  }
  if (calView !== "day") {
    content.push(el("button", {
      onclick: () => { closePopover(); calView = "day"; calAnchor = iso; renderCalendar(); },
    }, t("نمای روزانهٔ این روز")));
  }
  content.push(el("button", { onclick: () => openExportMenu(anchor, "day", iso) }, t("⇪ خروجی این روز")));
  content.push(el("button", { onclick: () => { closePopover(); openAddMenu(iso); } }, t("+ افزودن از این روز")));
  openPopover(anchor, ...content);
}

// ---------------------------------------------------------------------------
// خروجی HTML و اشتراک‌گذاری
// ---------------------------------------------------------------------------

function fileManager() {
  return { mac: "Finder", windows: "File Explorer" }[state.system] || t("پوشه");
}

function openExportMenu(anchor, scope = "day", date = null) {
  const choice = { scope, date: date || Jalali.addDays(state.today, 1) };  // پیش‌فرض: فردا
  const picker = el("span", { class: "jalali-input" });
  buildJalaliInput(picker, choice.date);
  const withContent = el("input", { type: "checkbox", checked: scope === "day" });
  const scopes = [["day", t("روز")], ["week", t("هفته")], ["month", t("ماه")]];
  const scopeRow = el("div", { class: "tabs" }, scopes.map(([key, label]) =>
    el("button", {
      "aria-selected": String(choice.scope === key),
      onclick: (e) => {
        choice.scope = key;
        withContent.checked = key === "day";
        $$("button", scopeRow).forEach((b) => b.setAttribute("aria-selected", "false"));
        e.currentTarget.setAttribute("aria-selected", "true");
      },
    }, label)));
  const quick = (days) => el("button", { onclick: () => buildJalaliInput(picker, Jalali.addDays(state.today, days)) },
    [t("امروز"), t("فردا"), t("پس‌فردا")][days]);

  openPopover(anchor,
    el("div", { class: "pop-title" }, t("خروجی برای خواندن روی گوشی")),
    scopeRow,
    el("div", { class: "pop-row" }, quick(0), quick(1), quick(2)),
    el("div", { class: "pop-row" }, t("روز:"), picker),
    el("p", { class: "muted small" }, t("برای هفته و ماه، هفته یا ماهی که این روز در آن است.")),
    el("label", { class: "pop-row" }, withContent, t("همراه با مطالب (نوت، صفحه‌های PDF)")),
    el("p", { class: "muted small" }, t("خروجی هفتگی و ماهانهٔ همراه با مطالب ممکن است حجیم شود.")),
    el("button", {
      class: "primary",
      onclick: async (e) => {
        let day;
        try { day = readJalaliInput(picker) || state.today; } catch (error) { showMessage(error.message); return; }
        e.currentTarget.disabled = true;
        e.currentTarget.textContent = t("در حال ساختن…");
        try {
          const result = await api("POST", "/api/export", { scope: choice.scope, date: day, with_content: withContent.checked });
          showExportResult(anchor, result);
        } catch (error) {
          closePopover();
        }
      },
    }, t("ساختن خروجی")));
}

async function showExportResult(anchor, result) {
  // فایل از قبل گرفته می‌شود تا کلیک روی «اشتراک‌گذاری» فوراً پنجرهٔ Share را باز کند
  let file = null;
  try {
    const response = await fetch(`/api/export/file/${encodeURIComponent(result.name)}`);
    file = new File([await response.blob()], result.name, { type: "text/html" });
  } catch (error) { /* اشتراک‌گذاری مستقیم ممکن نیست؛ Finder می‌ماند */ }
  const canShare = file && navigator.canShare && navigator.canShare({ files: [file] });
  const reveal = () => api("POST", "/api/export/reveal", { name: result.name });

  openPopover(anchor,
    el("div", { class: "pop-title" }, t("✓ خروجی ذخیره شد")),
    el("div", { class: "small path", dir: "ltr" }, result.path),
    el("div", { class: "muted small" }, t("حجم: {0} کیلوبایت", fa(Math.max(1, Math.round(result.size / 1024))))),
    canShare && el("button", {
      class: "primary",
      onclick: async () => {
        try {
          await navigator.share({ files: [file], title: result.name });
        } catch (error) {
          if (error.name !== "AbortError") { showMessage(t("پنجرهٔ Share باز نشد؛ فایل در {0} نشان داده می‌شود.", fileManager())); reveal(); }
        }
      },
    }, t("اشتراک‌گذاری… (تلگرام و برنامه‌های دیگر)")),
    el("button", { onclick: reveal }, t("نمایش در {0} (برای کشیدن به تلگرام)", fileManager())),
    el("button", { onclick: () => api("POST", "/api/export/open", { name: result.name }) }, t("باز کردن فایل")),
    !canShare && el("p", { class: "muted small" }, t("این مرورگر پنجرهٔ Share را برای فایل پشتیبانی نمی‌کند. فایل را از {0} به تلگرام بکشید.", fileManager())),
  );
}

// ---------------------------------------------------------------------------
// دکمه‌های بالای تقویم
// ---------------------------------------------------------------------------

function shiftCalendar(direction) {
  if (calView === "day") {
    calAnchor = Jalali.addDays(calAnchor, direction);
  } else if (calView === "week") {
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

$("#view-day").addEventListener("click", () => { calView = "day"; renderCalendar(); });

$("#view-week").addEventListener("click", () => { calView = "week"; renderCalendar(); });

$("#view-month").addEventListener("click", () => { calView = "month"; renderCalendar(); });

$("#view-all").addEventListener("click", () => { calView = "all"; renderCalendar(); });

for (const [id, value] of [["#orient-vertical", "vertical"], ["#orient-horizontal", "horizontal"]]) {
  $(id).addEventListener("click", () => {
    orientation = value;
    setPref("orientation", value);
    renderCalendar();
  });
}

$("#cal-prev").addEventListener("click", () => shiftCalendar(-1));

$("#cal-next").addEventListener("click", () => shiftCalendar(1));

$("#export-button").addEventListener("click", (e) => openExportMenu(e.currentTarget, "day"));

// پیکان‌ها در جهت خواندن زبان
$("#cal-prev").textContent = isRTL ? "→" : "←";
$("#cal-next").textContent = isRTL ? "←" : "→";

$("#cal-today").addEventListener("click", () => { calAnchor = state.today; renderCalendar(); });

