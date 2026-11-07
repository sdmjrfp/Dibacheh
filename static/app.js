/* رابط کاربری داشبورد.

   روش کار:
   - همهٔ داده‌ها در متغیر state است که از /api/state می‌آید.
   - هر تغییری به سرور فرستاده می‌شود. سرور برنامه را از نو می‌سازد و state تازه
     را برمی‌گرداند. بعد render() کل صفحه را دوباره می‌کشد. صفحه هیچ‌وقت reload نمی‌شود.
   - متن‌هایی که کاربر نوشته با textContent گذاشته می‌شوند، نه innerHTML،
     تا هیچ متنی نتواند کد اجرا کند.
*/

const CSRF = document.querySelector('meta[name="csrf-token"]').content;
const fa = Jalali.faNumber;

let state = null;
let filterStatus = "all";
let filterCategory = "";
let selectedItemId = null;
let editing = null;        // { id: شمارهٔ درس یا null برای درس جدید, type: "study" | "routine" }
let pickedSource = null;   // نتیجهٔ Browse که هنوز ذخیره نشده
let headingsCache = [];

const STATUS_LISTS = [
  ["all", "همه"],
  ["unread", "خوانده‌نشده"],
  ["reading", "در حال خواندن"],
  ["read", "خوانده‌شده"],
  ["finished", "تمام‌شده"],
];
const SESSION_STATUS = {
  unread: "خوانده‌نشده",
  reading: "نیمه‌خوانده",
  reviewing: "در حال مرور",
  finished: "تمام‌شده",
};
// ترتیب روزهای هفتهٔ ایرانی، با شمارهٔ روز در پایتون (0 = دوشنبه)
const WEEKDAYS = [[5, "شنبه"], [6, "یکشنبه"], [0, "دوشنبه"], [1, "سه‌شنبه"],
                  [2, "چهارشنبه"], [3, "پنجشنبه"], [4, "جمعه"]];

// ---------------------------------------------------------------------------
// ابزارهای کوچک
// ---------------------------------------------------------------------------

/** ساخت عنصر HTML: el("button", {class: "x", onclick: f}, "متن") */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let messageTimer = null;
function showMessage(text, isError = true) {
  const box = $("#message");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => { box.hidden = true; }, 6000);
}

/** درخواست به سرور. اگر جواب، وضعیت کامل بود، صفحه دوباره کشیده می‌شود. */
async function api(method, url, body) {
  const options = { method, headers: { "X-CSRF-Token": CSRF } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showMessage(data.error || "خطایی پیش آمد.");
    throw new Error(data.error || response.status);
  }
  if (data.items && data.plan) {
    state = data;
    render();
  }
  return data;
}

function minutesText(total) {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!hours) return `${fa(minutes)} دقیقه`;
  return minutes ? `${fa(hours)} ساعت و ${fa(minutes)} دقیقه` : `${fa(hours)} ساعت`;
}

function itemById(id) {
  return state.items.find((item) => item.id === id);
}

// ---------------------------------------------------------------------------
// کشیدن صفحه
// ---------------------------------------------------------------------------

/** کل صفحه را دوباره می‌کشد؛ هر جابه‌جایی با انیمیشن دیده می‌شود (static/motion.js). */
function render() {
  Motion.wrap(renderNow);
}

function renderNow() {
  $("#today").textContent = `امروز: ${Jalali.weekday(state.today)} ${Jalali.format(state.today)}`;
  // فقط نام پوشهٔ والت نشان داده می‌شود؛ آدرس کامل با نگه داشتن ماوس روی آن
  const vault = state.settings.vault_path;
  $("#vault-path").textContent = vault ? vault.split("/").filter(Boolean).pop() : "ثبت نشده";
  $("#vault-button").title = vault ? `مسیر والت: ${vault}\nبرای تغییر کلیک کنید` : "انتخاب پوشهٔ والت Obsidian";
  document.documentElement.dataset.theme = state.settings.theme || "light";
  document.documentElement.dataset.colorMode = state.settings.color_mode || "kind";
  // فونت و اندازهٔ فونت از تنظیمات
  const root = document.documentElement.style;
  root.setProperty("--font", `"${state.settings.font_family || "Vazirmatn"}", "Vazirmatn", system-ui, Tahoma, sans-serif`);
  root.setProperty("--font-size", `${state.settings.font_size || 16}px`);
  // رنگ کارها در تقویم، از تنظیمات
  const colors = state.settings.colors || {};
  for (const kind of ["read", "review", "routine"]) if (colors[kind]) root.setProperty(`--c-${kind}`, colors[kind]);
  renderCustomFonts();
  renderAddButtons();
  renderCategoryTabs();
  renderTabs();
  renderItems();
  renderWorkload();
  for (const warning of state.plan.warnings) showMessage(warning);
  if (editing && editing.id && $("#item-dialog").open) renderSessions();
  // دکمه‌های برگرداندن و بازگرداندن، با تعداد مرحله‌ها
  const undo = $("#undo-button");
  const redo = $("#redo-button");
  undo.disabled = !state.undo.count;
  redo.disabled = !state.undo.redo_count;
  undo.querySelector(".count").textContent = state.undo.count ? fa(state.undo.count) : "";
  redo.querySelector(".count").textContent = state.undo.redo_count ? fa(state.undo.redo_count) : "";
  undo.title = state.undo.count
    ? `برگرداندن «${state.undo.label}» · ${fa(state.undo.count)} مرحله قابل برگشت` : "تغییری برای برگرداندن نیست";
  redo.title = state.undo.redo_count
    ? `بازگرداندن «${state.undo.redo_label}» · ${fa(state.undo.redo_count)} مرحله برگشته‌اید` : "مرحله‌ای برگشته نیست";
  if (typeof renderCalendar === "function") renderCalendar();  // در calendar.js
}

/** نشانگر حجم کار منتظر: خواندن و مرور باقی‌مانده، تاریخ پایان و میانگین روزانه. */
function renderWorkload() {
  const w = state.workload;
  const box = $("#pending");
  const total = w.read_minutes + w.review_minutes;
  if (!total) {
    box.replaceChildren();
    return;
  }
  const readShare = Math.round((100 * w.read_minutes) / total);
  box.className = "workload";
  box.replaceChildren(
    el("strong", {}, `حجم کار منتظر: ${minutesText(total)}`),
    el("div", { class: "bars", title: "رنگ خواندن و رنگ مرور، به نسبت حجم هرکدام" },
      el("span", { class: "r", style: `width:${readShare}%` }),
      el("span", { class: "v", style: `width:${100 - readShare}%` })),
    el("div", {}, `خواندن ${minutesText(w.read_minutes)} · مرور ${minutesText(w.review_minutes)}`),
    w.end_date && el("div", {}, `پایان پیش‌بینی‌شدهٔ همه‌چیز: ${Jalali.format(w.end_date)}`),
    el("div", { class: "muted" },
      `۳۰ روز آینده، به‌طور میانگین هر روز ${fa(w.avg_review_next_30)} دقیقه مرور و ${fa(w.avg_read_next_30)} دقیقه مطلب جدید`),
  );
}

/** متن جلو یا عقب بودن از تاریخ هدف */
function targetText(label, info) {
  if (!info) return null;
  if (info.done) return el("span", { class: "target ahead" }, `${label}: تمام شده ✓`);
  if (info.days === null) return null;
  if (info.days === 0) return el("span", { class: "target ahead" }, `${label}: درست سر هدف`);
  const ahead = info.days > 0;
  return el("span", { class: `target ${ahead ? "ahead" : "behind"}` },
    `${label}: ${fa(Math.abs(info.days))} روز ${ahead ? "زودتر از" : "دیرتر از"} هدف`);
}

function renderTabs() {
  const counts = { all: state.items.length };
  for (const item of state.items) counts[item.status_list] = (counts[item.status_list] || 0) + 1;
  $("#status-tabs").replaceChildren(...STATUS_LISTS.map(([key, label]) =>
    el("button", {
      role: "tab",
      "aria-selected": String(filterStatus === key),
      onclick: () => { filterStatus = key; render(); },
    }, `${label} (${fa(counts[key] || 0)})`)
  ));
}

function categoryOptions(selected, emptyLabel) {
  return [
    el("option", { value: "" }, emptyLabel),
    ...state.categories.map((c) =>
      el("option", { value: c.id, selected: String(c.id) === String(selected) }, c.name)),
  ];
}

// ---------------------------------------------------------------------------
// تب‌های دسته. دوبار کلیک = تغییر نام، × = حذف، + = دستهٔ تازه، کشیدن = جابه‌جایی
// ---------------------------------------------------------------------------

let addingCategory = false;

function renderCategoryTabs() {
  const box = $("#category-tabs");
  if (box.querySelector("input:focus")) return;  // وسط تایپ نام، دوباره کشیده نشود
  const tab = (id, label, count) => {
    const selected = String(filterCategory) === String(id);
    const node = el("div", {
      class: `cat-tab${selected ? " selected" : ""}`, role: "tab", "aria-selected": String(selected),
      "data-id": id, "data-flip": `cat-${id || "all"}`,
      onclick: (e) => { if (!e.target.closest(".x")) { filterCategory = String(id); render(); } },
    }, el("span", { class: "name" }, label), el("span", { class: "count" }, fa(count)));
    return node;
  };
  const counts = new Map();
  for (const item of state.items) counts.set(item.category_id, (counts.get(item.category_id) || 0) + 1);
  const all = tab("", "همه", state.items.length);
  all.dataset.fixed = "";
  const tabs = state.categories.map((c) => {
    const node = tab(c.id, c.name, counts.get(c.id) || 0);
    node.title = "دوبار کلیک: تغییر نام · کشیدن: جابه‌جایی";
    node.addEventListener("dblclick", () => renameCategoryInline(node, c));
    node.append(el("button", {
      class: "x", title: "حذف دسته",
      onclick: () => {
        if (confirm(`دستهٔ «${c.name}» حذف شود؟ درس‌هایش می‌مانند و بدون دسته می‌شوند.`)) {
          if (String(filterCategory) === String(c.id)) filterCategory = "";
          api("DELETE", `/api/categories/${c.id}`);
        }
      },
    }, "×"));
    return node;
  });
  const plus = addingCategory
    ? el("div", { class: "cat-tab adding", "data-fixed": "" }, categoryNameInput("", async (name) => {
        addingCategory = false;
        if (name) await api("POST", "/api/categories", { name });
        else render();
      }))
    : el("button", { class: "cat-tab plus", "data-fixed": "", title: "دستهٔ جدید",
        onclick: () => { addingCategory = true; render(); $("#category-tabs input").focus(); } }, "+");
  box.replaceChildren(all, ...tabs, plus);
}

/** ورودی نام دسته: Enter = ثبت، Esc = لغو */
function categoryNameInput(value, done) {
  let finished = false;
  const input = el("input", { value, placeholder: "نام دسته", size: 10 });
  const end = (name) => { if (!finished) { finished = true; done(name); } };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") end(input.value.trim());
    if (e.key === "Escape") end("");
  });
  input.addEventListener("blur", () => end(input.value.trim()));
  return input;
}

function renameCategoryInline(node, category) {
  const input = categoryNameInput(category.name, (name) => {
    if (name && name !== category.name) api("PATCH", `/api/categories/${category.id}`, { name });
    else render();
  });
  node.replaceChildren(input);
  input.focus();
  input.select();
}

sortable($("#category-tabs"), {
  items: ".cat-tab", axis: "x",
  onDrop: (ids) => api("POST", "/api/categories/reorder", { ids: ids.filter(Boolean).map(Number) }),
});

// ---------------------------------------------------------------------------
// دکمه‌های افزودن: درس، کار روتین، نوع‌های ساخت کاربر، و «+» برای نوع تازه
// ---------------------------------------------------------------------------

function renderAddButtons() {
  $("#custom-add-buttons").replaceChildren(...state.types.map((t) =>
    el("button", {
      class: "type-button", style: `--c:${t.color}`,
      title: t.behavior === "study" ? "مثل درس، با مرور لایتنر" : "مثل کار روتین، بدون مرور",
      onclick: () => openItemDialog(null, t.behavior, null, t),
    }, `+ ${t.name}`)));
}

function typeOf(item) {
  return state.types.find((t) => t.id === item.custom_type_id) || null;
}

function renderItems() {
  const list = $("#item-list");
  const visible = state.items.filter((item) =>
    (filterStatus === "all" || item.status_list === filterStatus) &&
    (!filterCategory || String(item.category_id) === filterCategory));
  if (!visible.length) {
    list.replaceChildren(el("li", { class: "muted" }, state.items.length
      ? "درسی با این فیلتر نیست." : "هنوز درسی اضافه نشده. با دکمهٔ «+ درس» شروع کنید."));
    return;
  }
  list.replaceChildren(...visible.map(itemCard));
}

function itemCard(item) {
  const category = state.categories.find((c) => c.id === item.category_id);
  const custom = typeOf(item);
  const p = item.progress;
  const meta = [];
  if (category) meta.push(el("span", { class: "chip" }, category.name));
  if (custom) meta.push(el("span", { class: "chip typed", style: `--c:${custom.color}` }, custom.name));
  else if (item.item_type === "routine") meta.push(el("span", { class: "chip routine" }, "روتین"));
  meta.push(el("span", {}, `${fa(item.sessions.length)} جلسه`));
  meta.push(el("span", {}, `خواندن ${fa(p.read_percent)}٪`));
  if (p.reviews_total) meta.push(el("span", {}, `مرور ${fa(p.reviews_done)} از ${fa(p.reviews_total)}`));
  if (!item.is_active) {
    meta.push(el("span", {}, "غیرفعال: روی تقویم نیست"));
  } else {
    if (item.finish.read_end) meta.push(el("span", {}, `پایان خواندن: ${Jalali.formatShort(item.finish.read_end)}`));
    if (item.finish.review_end) meta.push(el("span", {}, `پایان مرور: ${Jalali.format(item.finish.review_end)}`));
  }
  if (item.pinned) {
    meta.push(el("span", { class: "pinned", title: "این جلسه‌ها روی روز خاصی مانده‌اند و اولویت صف رویشان اثر ندارد" },
      `📌 ${fa(item.pinned)} جلسه دستی جابه‌جا شده`,
      el("button", {
        class: "link", title: "همهٔ جابه‌جایی‌های دستی این درس برداشته شود",
        onclick: () => api("POST", `/api/items/${item.id}/unpin`, {}),
      }, "برگشت به چینش خودکار")));
  }
  if (item.target_date) {
    meta.push(el("span", {}, `هدف: ${Jalali.format(item.target_date)}`));
    if (item.target) {
      meta.push(targetText("خواندن", item.target.read));
      meta.push(targetText("مرور", item.target.review));
    }
  }

  const card = el("li", {
    class: `item${item.is_active ? "" : " inactive"}${item.id === selectedItemId ? " selected" : ""}`,
    "data-id": item.id, "data-flip": `item-${item.id}`,
  },
    el("span", { class: "handle", title: "برای جابه‌جایی بکشید" }, "⋮⋮"),
    el("input", {
      type: "checkbox", checked: item.is_active, title: "فعال / غیرفعال",
      onchange: (e) => api("PATCH", `/api/items/${item.id}`, { is_active: e.target.checked }),
    }),
    el("span", {
      class: "title",
      onclick: () => { selectedItemId = selectedItemId === item.id ? null : item.id; render(); },
    }, item.title),
    el("span", { class: "actions" },
      el("input", {
        type: "color", class: "swatch", value: item.display_color, title: "رنگ این منبع",
        onchange: (e) => api("PATCH", `/api/items/${item.id}`, { color: e.target.value }),
      }),
      item.source_type !== "none" && el("button", {
        class: "icon", title: "باز کردن منبع",
        onclick: () => api("POST", `/api/items/${item.id}/open`, {}),
      }, "↗"),
      el("button", { class: "icon", title: "ویرایش", onclick: () => openItemDialog(item) }, "✎"),
    ),
    el("div", { class: "progress" }, el("span", { style: `width:${p.read_percent}%` })),
    el("div", { class: "meta" }, meta),
    item.source_problem && el("div", { class: "problem" }, `⚠ ${item.source_problem}`),
  );
  return card;
}

// ---------------------------------------------------------------------------
// Drag-and-drop صف
// ---------------------------------------------------------------------------

// کشیدن کارت درس: خود کارت همراه ماوس حرکت می‌کند و بقیه کنار می‌روند (static/motion.js)
sortable($("#item-list"), {
  items: ".item", handle: ".handle", axis: "y",
  onDrop: (visibleIds, movedId) => reorderVisible(visibleIds.map(Number), Number(movedId)),
});

/** ترتیب تازهٔ کارت‌های دیده‌شده را در کل صف اعمال می‌کند.
 *  اگر فیلتری روشن است، درس‌های پنهان سر جای خودشان در صف می‌مانند. */
function reorderVisible(visibleIds, movedId) {
  const visible = new Set(visibleIds);
  const queue = [...visibleIds];
  const ids = state.items.map((item) => (visible.has(item.id) ? queue.shift() : item.id));
  state.items.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
  // movedId: درسی که کشیده شد. جابه‌جایی‌های دستی خواندنِ همین درس برداشته می‌شود
  // تا از این به بعد طبق جای تازه‌اش در صف چیده شود.
  api("POST", "/api/items/reorder", { ids, moved_id: movedId }).then((result) => {
    const item = itemById(movedId);
    if (result.released && item) {
      showMessage(`جابه‌جایی دستی ${fa(result.released)} جلسه از «${item.title}» برداشته شد تا طبق اولویت تازه چیده شود.`, false);
    }
  });
}

/** درس را درست قبل از درس مقصد در کل صف قرار می‌دهد. beforeId=null یعنی انتهای صف. */
function moveItem(movedId, beforeId) {
  const ids = state.items.map((item) => item.id).filter((id) => id !== movedId);
  if (beforeId === null) ids.push(movedId);
  else ids.splice(ids.indexOf(beforeId), 0, movedId);
  // برای حس فوری، اول خود فهرست جابه‌جا می‌شود، بعد جواب سرور تاریخ‌ها را به‌روز می‌کند
  state.items.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
  render();
  api("POST", "/api/items/reorder", { ids });
}

// ---------------------------------------------------------------------------
// ورودی تاریخ شمسی
// ---------------------------------------------------------------------------

function buildJalaliInput(holder, iso) {
  const parts = iso ? Jalali.toJalali(iso) : null;
  const year = el("input", { type: "number", min: 1300, max: 1500, value: parts ? parts.y : "", placeholder: "سال" });
  const month = el("select", {}, el("option", { value: "" }, "ماه"),
    ...Jalali.MONTHS.map((name, i) => el("option", { value: i + 1, selected: parts && parts.m === i + 1 }, name)));
  const day = el("select", {}, el("option", { value: "" }, "روز"),
    ...Array.from({ length: 31 }, (_, i) =>
      el("option", { value: i + 1, selected: parts && parts.d === i + 1 }, fa(i + 1))));
  const clear = el("button", { type: "button", class: "icon", title: "پاک کردن",
    onclick: () => { year.value = ""; month.value = ""; day.value = ""; } }, "×");
  holder.replaceChildren(year, month, day, clear);
}

/** مقدار ورودی تاریخ شمسی به شکل "2026-11-05"، یا null. */
function readJalaliInput(holder) {
  const [year, month, day] = $$("input, select", holder).map((x) => x.value);
  if (!year && !month && !day) return null;
  const iso = Jalali.fromJalali(Number(year), Number(month), Number(day));
  if (!iso) throw new Error("تاریخ شمسی نامعتبر است.");
  return iso;
}

// ---------------------------------------------------------------------------
// پنجرهٔ درس
// ---------------------------------------------------------------------------

const form = $("#item-form");
// form.elements به‌جای form: چون form.title خودِ عنوان فرم است، نه فیلد title
const fields = form.elements;

/** پنجرهٔ درس.
 *  firstDate: وقتی درس از روی یک روز تقویم اضافه می‌شود.
 *  customType: وقتی از دکمهٔ یکی از نوع‌های ساخت کاربر (مثلاً «+ پروژه») باز می‌شود. */
function openItemDialog(item, type = "study", firstDate = null, customType = null) {
  customType = customType || (item ? typeOf(item) : null);
  editing = { id: item ? item.id : null, type: item ? item.item_type : type, firstDate, customType };
  pickedSource = null;
  headingsCache = [];
  const isRoutine = editing.type === "routine";
  const typeName = customType ? customType.name : (isRoutine ? "کار روتین" : "درس");
  $("#item-dialog-title").textContent = (item ? `ویرایش ${typeName}` : `${typeName} جدید`)
    + (!item && firstDate ? ` از ${Jalali.format(firstDate)}` : "");

  const defaults = state.settings.new_item_defaults || {};
  fields.title.value = item ? item.title : "";
  fields.category_id.replaceChildren(...categoryOptions(item ? item.category_id : defaults.category_id, "بدون دسته"));
  fields.is_active.checked = item ? item.is_active : true;
  fields.color.value = item ? item.display_color : state.palette[state.items.length % state.palette.length];
  fields.session_count.value = isRoutine ? 10 : 1;
  fields.session_minutes.value = isRoutine ? 10 : (defaults.session_minutes || 60);
  fields.max_new_sessions_per_day.value = item ? item.max_new_sessions_per_day : (defaults.max_new_sessions_per_day || 1);
  fields.review_ratio.value = item && item.review_ratio ? item.review_ratio : "";
  fields.review_intervals.value = item && item.review_intervals ? item.review_intervals.join("، ") : "";
  fields.source_type.value = item ? (item.source_type === "vault" ? "file" : item.source_type) : "none";
  fields.source_url.value = item && item.source_type === "url" ? item.source_path_or_url : "";
  $("#source-path").textContent = item && ["vault", "file"].includes(item.source_type) ? item.source_path_or_url : "";
  const problem = $("#source-problem");
  problem.hidden = !(item && item.source_problem);
  problem.textContent = item && item.source_problem ? item.source_problem : "";
  fields.section_unit.value = item ? item.section_unit : "text";
  fields.range_start.value = item && item.range_start ? item.range_start : "";
  fields.range_end.value = item && item.range_end ? item.range_end : "";
  const unread = item ? item.sessions.filter((s) => s.status === "unread") : [];
  fields.resplit_count.value = unread.length || "";
  fields.resplit_minutes.value = "";

  buildJalaliInput($('.jalali-input[data-name="start_date"]'),
    item ? item.start_date : (isRoutine ? (firstDate || state.today) : null));
  buildJalaliInput($('.jalali-input[data-name="target_date"]'), item ? item.target_date : null);
  const weekdays = item && item.routine_weekdays ? item.routine_weekdays : [];
  $("#routine-weekdays").replaceChildren(...WEEKDAYS.map(([num, name]) =>
    el("label", {}, el("input", { type: "checkbox", value: num, checked: weekdays.includes(num) }), name)));

  updateDialogVisibility();
  if (item) {
    if (item.section_unit === "heading") loadHeadings(item.id);
    renderSessions();
  }
  $("#item-dialog").showModal();
}

/** نشان دادن و پنهان کردن بخش‌های فرم بر اساس نوع کار و انتخاب‌ها. */
function updateDialogVisibility() {
  const mode = editing.id ? "edit" : "create";
  $$("[data-when]", $("#item-dialog")).forEach((n) => { n.hidden = n.dataset.when !== mode; });
  $$("[data-only]", form).forEach((n) => { n.hidden = n.dataset.only !== editing.type; });
  const unit = fields.section_unit.value;
  $$("[data-unit]", form).forEach((n) => { n.hidden = !n.dataset.unit.split(" ").includes(unit); });
  const source = fields.source_type.value;
  fields.source_url.hidden = source !== "url";
  $("#browse-button").hidden = source !== "file";
  $("#source-path").hidden = source !== "file";
}

fields.section_unit.addEventListener("change", updateDialogVisibility);
fields.source_type.addEventListener("change", updateDialogVisibility);

$("#browse-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/browse", { kind: "file" });
  if (result.cancelled) return;
  pickedSource = result;
  $("#source-path").textContent = result.source_type === "vault"
    ? `${result.source_path_or_url}  (داخل والت)` : result.source_path_or_url;
  $("#source-problem").hidden = true;
});

/** اطلاعات فرم را به شکلی که سرور می‌خواهد جمع می‌کند. */
function collectForm() {
  const data = {
    title: fields.title.value,
    item_type: editing.type,
    category_id: fields.category_id.value ? Number(fields.category_id.value) : null,
    is_active: fields.is_active.checked,
    color: fields.color.value,
    section_unit: fields.section_unit.value,
    range_start: fields.range_start.value,
    range_end: fields.range_end.value,
  };
  if (editing.type === "study") {
    data.max_new_sessions_per_day = Number(fields.max_new_sessions_per_day.value);
    data.review_ratio = fields.review_ratio.value.trim();
    const intervals = fields.review_intervals.value.split(/[،,\s]+/).filter(Boolean).map(Number);
    data.review_intervals = intervals.length ? intervals : null;
    data.target_date = readJalaliInput($('.jalali-input[data-name="target_date"]'));
  } else {
    data.start_date = readJalaliInput($('.jalali-input[data-name="start_date"]'));
    data.routine_weekdays = $$("#routine-weekdays input:checked").map((x) => Number(x.value));
  }
  const source = fields.source_type.value;
  if (source === "none") {
    data.source_type = "none";
  } else if (source === "url") {
    data.source_type = "url";
    data.source_path_or_url = fields.source_url.value.trim();
  } else if (pickedSource) {
    data.source_type = pickedSource.source_type;
    data.source_path_or_url = pickedSource.source_path_or_url;
  } else if (!editing.id || !["vault", "file"].includes(itemById(editing.id).source_type)) {
    throw new Error("برای منبع فایل، اول Browse کنید و فایل را انتخاب کنید.");
  }
  if (!editing.id) {
    data.session_count = Number(fields.session_count.value);
    data.session_minutes = Number(fields.session_minutes.value);
    if (editing.firstDate) data.first_date = editing.firstDate;
    if (editing.customType) data.custom_type_id = editing.customType.id;
  }
  return data;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  let data;
  try {
    data = collectForm();
  } catch (error) {
    showMessage(error.message);
    return;
  }
  if (editing.id) await api("PATCH", `/api/items/${editing.id}`, data);
  else await api("POST", "/api/items", data);
  $("#item-dialog").close();
});

$("#close-item").addEventListener("click", () => $("#item-dialog").close());
$("#item-dialog").addEventListener("close", () => { editing = null; });

$("#resplit-button").addEventListener("click", () => {
  api("POST", `/api/items/${editing.id}/split`, {
    session_count: Number(fields.resplit_count.value),
    session_minutes: fields.resplit_minutes.value ? Number(fields.resplit_minutes.value) : null,
  });
});

$("#reset-item").addEventListener("click", () => {
  if (!confirm("همهٔ جلسه‌های این درس به حالت خوانده‌نشده برمی‌گردند و درس به انتهای صف می‌رود. سابقهٔ قبلی می‌ماند. ادامه می‌دهید؟")) return;
  api("POST", `/api/items/${editing.id}/reset`, {});
});

$("#delete-item").addEventListener("click", async () => {
  const item = itemById(editing.id);
  if (!confirm(`«${item.title}» با همهٔ جلسه‌ها و سابقه‌اش حذف شود؟ فایل منبع روی Mac دست نمی‌خورد. این کار برگشت ندارد.`)) return;
  await api("DELETE", `/api/items/${editing.id}`);
  $("#item-dialog").close();
});

// ---------------------------------------------------------------------------
// جدول جلسه‌ها (داخل پنجرهٔ درس). هر تغییر فوراً ذخیره می‌شود.
// ---------------------------------------------------------------------------

async function loadHeadings(itemId) {
  const response = await fetch(`/api/items/${itemId}/headings`);
  headingsCache = response.ok ? await response.json() : [];
  if (editing && editing.id === itemId) renderSessions();
}

function saveSession(sessionId, fields) {
  api("PATCH", `/api/sessions/${sessionId}`, fields);
}

function sectionCell(item, session) {
  const save = (key) => (e) => saveSession(session.id, { [key]: e.target.value });
  if (item.section_unit === "page" || item.section_unit === "time") {
    return el("div", { class: "range" },
      el("input", { value: session.section_start || "", dir: "ltr", onchange: save("section_start") }),
      el("span", {}, "تا"),
      el("input", { value: session.section_end || "", dir: "ltr", onchange: save("section_end") }));
  }
  if (item.section_unit === "heading") {
    const options = (selected) => [el("option", { value: "" }, "—"),
      ...headingsCache.map((h) => el("option", { value: h.text, selected: h.text === selected },
        `${"  ".repeat(h.level - 1)}${h.text}`))];
    if (!headingsCache.length) return el("span", { class: "muted" }, "عنوانی در فایل Markdown پیدا نشد.");
    return el("div", { class: "range" },
      el("select", { onchange: save("section_start") }, options(session.section_start)),
      el("span", {}, "تا"),
      el("select", { onchange: save("section_end") }, options(session.section_end)));
  }
  return el("input", { value: session.section_label || "", placeholder: "مثلاً فصل ۱", onchange: save("section_label") });
}

function renderSessions() {
  const item = itemById(editing.id);
  if (!item) return;
  $("#range-problems").replaceChildren(...item.range_problems.map((p) => el("li", {}, p)));
  $("#sessions-body").replaceChildren(...item.sessions.map((s) => {
    let status = SESSION_STATUS[s.status];
    if (s.status === "reviewing") status += ` (جعبهٔ ${fa(s.leitner_box)})`;
    if (s.status === "reading") status += ` (${fa(s.minutes_done)} دقیقه)`;
    return el("tr", { class: s.status === "unread" ? "" : "done" },
      el("td", {}, fa(s.sequence)),
      el("td", {}, status),
      el("td", {}, sectionCell(item, s)),
      el("td", {}, el("input", {
        class: "num", type: "number", min: 1, value: s.minutes,
        onchange: (e) => saveSession(s.id, { minutes: Number(e.target.value) }),
      })),
      el("td", {}, item.item_type === "routine" ? "—" : el("input", {
        class: "num", type: "number", min: 1, value: s.review_minutes_override || "",
        placeholder: "خودکار", title: "زمان مرور همین جلسه. خالی = از نسبت مرور",
        onchange: (e) => saveSession(s.id, { review_minutes_override: e.target.value }),
      })),
    );
  }));
}

// ---------------------------------------------------------------------------
// نوع کار تازه (دکمهٔ «+» کنار «+ درس» و «+ کار روتین»)
// ---------------------------------------------------------------------------

function openTypeDialog() {
  const f = $("#type-form").elements;
  f.name.value = "";
  f.behavior.value = "study";
  f.color.value = "#8b5cf6";
  $("#type-dialog").showModal();
  f.name.focus();
}

$("#type-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target.elements;
  await api("POST", "/api/types", { name: f.name.value.trim(), behavior: f.behavior.value, color: f.color.value });
  $("#type-dialog").close();
});
$("#close-type").addEventListener("click", () => $("#type-dialog").close());
$("#add-type").addEventListener("click", openTypeDialog);

// ---------------------------------------------------------------------------
// شروع
// ---------------------------------------------------------------------------

$("#add-study").addEventListener("click", () => openItemDialog(null, "study"));
$("#add-routine").addEventListener("click", () => openItemDialog(null, "routine"));
$("#vault-button").addEventListener("click", () => api("POST", "/api/browse", { kind: "vault" }));

api("GET", "/api/state");

$("#undo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/undo", {});
  if (result.undone) showMessage(`برگشت: ${result.undone}`, false);
});
$("#redo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/redo", {});
  if (result.redone) showMessage(`دوباره انجام شد: ${result.redone}`, false);
});

/** فونت‌هایی که کاربر اضافه کرده، از پوشهٔ data/fonts بار می‌شوند. */
function renderCustomFonts() {
  let style = $("#custom-font-faces");
  if (!style) {
    style = el("style", { id: "custom-font-faces" });
    document.head.append(style);
  }
  const bundled = state.bundled_fonts.flatMap((f) => [
    `@font-face { font-family: "${f.family}"; font-weight: 400; src: url("/static/vendor/fonts/${f.regular}") format("woff2"); }`,
    f.bold ? `@font-face { font-family: "${f.family}"; font-weight: 700; src: url("/static/vendor/fonts/${f.bold}") format("woff2"); }` : "",
  ]);
  const custom = (state.settings.custom_fonts || []).map((f) =>
    `@font-face { font-family: "${f.family}"; src: url("/fonts/${encodeURIComponent(f.file)}"); }`);
  const css = [...bundled, ...custom].join("\n");
  if (style.textContent !== css) style.textContent = css;
}

// ---------------------------------------------------------------------------
// جداکنندهٔ بین منابع درسی و برنامه
//
// با کشیدن جداکننده، پهنای ستون منابع عوض می‌شود. چون صفحه راست‌به‌چپ است،
// منابع سمت راست هستند: کشیدن به چپ = منابع پهن‌تر.
// اندازه فقط در همین مرورگر به خاطر سپرده می‌شود (localStorage).
// ---------------------------------------------------------------------------

const SPLIT_KEY = "dibacheh.sourcesWidth";
const SPLIT_DEFAULT = 620;
const SPLIT_MIN = 360;          // کمترین پهنای ستون منابع
const CALENDAR_MIN = 480;       // کمترین پهنای ستون برنامه

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


// ---------------------------------------------------------------------------
// تنظیمات
// ---------------------------------------------------------------------------

const settingsForm = $("#settings-form");
const sf = settingsForm.elements;
let fontsLoaded = false;
let intervalDraft = [];   // فاصله‌های لایتنر در حال ویرایش (به روز)
let chartMax = 120;       // آخرین روزِ نمودار لایتنر

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
  sf.default_category.replaceChildren(...categoryOptions(d.category_id, "بدون دسته"));
  const colors = s.colors || {};
  sf.color_read.value = colors.read || "#e5484d";
  sf.color_review.value = colors.review || "#3b82f6";
  sf.color_routine.value = colors.routine || "#f5b400";
  sf.color_mode.value = s.color_mode || "kind";
  updateColorMode();
  sf.theme.value = s.theme;
  sf.font_size.value = s.font_size;
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
        el("input", { type: "number", min: 0, max: 1440, class: "num", "data-cap": num, value: caps[num] ?? "", placeholder: "پیش‌فرض" }),
        "دقیقه"),
      el("label", {}, el("input", { type: "checkbox", "data-off": num, checked: off.includes(num) }), " تعطیل"))));

  renderTypeSettings();
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
  $("#ratio-value").textContent = `${fa(percent)}٪`;
  const reviews = intervalDraft.length;
  const each = reviewMinutesFor(60, percent);
  const total = 60 + reviews * each;
  const cap = Number(sf.default_cap_minutes.value) || 120;
  const forNew = Math.round(cap * 60 / total);
  $("#ratio-explain").replaceChildren(
    el("div", {}, `هر مرور ${fa(percent)}٪ زمان خواندن همان جلسه است و رو به بالا گرد می‌شود.`),
    el("div", {}, `مثال: جلسهٔ ۶۰ دقیقه‌ای ← هر مرور ${fa(each)} دقیقه. با ${fa(reviews)} مرور، کل وقتی که این جلسه می‌گیرد: `
      + `۶۰ + ${fa(reviews)} × ${fa(each)} = ${fa(total)} دقیقه.`),
    el("div", {}, `یعنی در بلندمدت، از سقف روزانهٔ ${fa(cap)} دقیقه حدود ${fa(forNew)} دقیقه به مطلب جدید می‌رسد و بقیه صرف مرور می‌شود.`),
    el("div", { class: "muted" }, "درس‌هایی که نسبت مرور اختصاصی دارند، از نسبت خودشان استفاده می‌کنند. برای یک جلسهٔ خاص هم می‌شود زمان مرور را دستی گذاشت."),
  );
}

sf.ratio_percent.addEventListener("input", updateRatioExplain);
sf.default_cap_minutes.addEventListener("input", updateRatioExplain);

// ---------- نمودار فاصله‌های لایتنر

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

function cumulative(intervals) {
  let sum = 0;
  return intervals.map((d) => (sum += d));
}

const CHART_STEP = 30;        // طول نمودار یک ماه یک ماه عوض می‌شود
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
  $("#chart-length-label").textContent = `${fa(months)} ماه`;
  $("#chart-length-label").title = `${fa(chartMax)} روز`;
  $("#chart-longer").disabled = chartMax + CHART_STEP > CHART_LIMIT;
  const blocked = chartMax - CHART_STEP < Math.max(CHART_STEP, lastReviewDay());
  $("#chart-shorter").disabled = blocked;
  $("#chart-shorter").title = blocked ? `مرور آخر روز ${fa(lastReviewDay())} است؛ اول آن را جلوتر بیاورید` : "یک ماه کمتر";
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
    svg("text", { x: x(chartMax), y: axisY + 46, class: "tick", "text-anchor": "middle", fill: "currentColor", "font-size": 11 }, "روز"),
    ...points.map((day, i) => svg("line", { class: "span", x1: x(i ? points[i - 1] : 0), y1: axisY, x2: x(day), y2: axisY })),
    svg("g", { class: "start" }, svg("circle", { cx: x(0), cy: axisY, r: 8 }),
      svg("text", { x: x(0), y: axisY - 16, "text-anchor": "middle", "font-size": 11, fill: "currentColor" }, "خواندن")),
    ...points.map((day, i) => svg("g", { class: "point", "data-index": i },
      svg("text", { x: x(day), y: axisY - 18 }, `مرور ${fa(i + 1)}`),
      svg("circle", { cx: x(day), cy: axisY, r: 10 }))),
  );
  box.replaceChildren(chart);
  const single = intervalDraft.length <= 1;
  $("#interval-explain").replaceChildren(...intervalDraft.map((d, i) =>
    el("li", {}, `${fa(d)} روز بعد از ${i ? `مرور ${fa(i)}` : "خواندن"}`
      + ` (یعنی روز ${fa(points[i])} بعد از خواندن) `,
      !single && el("button", {
        type: "button", class: "link danger", title: `حذف مرور ${fa(i + 1)}`,
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
  ["استاندارد", [1, 3, 7, 30]],
  ["فشرده (امتحان نزدیک)", [1, 2, 4, 7]],
  ["لایتنر کلاسیک", [1, 2, 4, 8, 16]],
  ["بلندمدت", [1, 3, 7, 14, 30, 60, 120]],
  ["سبک (مرور کم)", [3, 14, 45]],
];

function renderIntervalPresets() {
  const current = intervalDraft.join();
  $("#interval-presets").replaceChildren(...INTERVAL_PRESETS.map(([name, days]) =>
    el("button", {
      type: "button", "aria-selected": String(days.join() === current),
      title: `${days.map(fa).join("، ")} روز`,
      onclick: () => {
        intervalDraft = [...days];
        chartMax = niceChartMax(intervalDraft);
        renderIntervalChart();
      },
    }, `${name}: ${days.map(fa).join("، ")}`)));
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
  if (!state.items.length) $("#source-colors").append(el("li", { class: "muted small" }, "هنوز منبعی اضافه نشده."));
}

for (const radio of sf.color_mode) radio.addEventListener("change", updateColorMode);

function renderTypeSettings() {
  $("#type-settings").replaceChildren(...state.types.map((t) =>
    el("li", { "data-type": t.id },
      el("input", { type: "color", value: t.color, "data-field": "color" }),
      el("input", { type: "text", value: t.name, maxlength: 40, "data-field": "name" }),
      el("span", { class: "muted small" }, t.behavior === "study" ? "مثل درس، با مرور" : "مثل روتین، بدون مرور"),
      el("button", {
        type: "button", class: "danger",
        onclick: async () => {
          if (!confirm(`نوع «${t.name}» حذف شود؟ کارهای این نوع می‌مانند و درس یا روتین معمولی می‌شوند.`)) return;
          await api("DELETE", `/api/types/${t.id}`);
          renderTypeSettings();
        },
      }, "حذف"))));
  if (!state.types.length) {
    $("#type-settings").append(el("li", { class: "muted small" }, "نوع کار ساخت شما هنوز نیست. با دکمهٔ «+» کنار «+ کار روتین» بسازید."));
  }
}

let macFonts = [];   // فونت‌های نصب‌شده روی Mac؛ یک بار خوانده می‌شوند

/** کادر باز شوی فونت: همراه برنامه، اضافه‌شده، و نصب‌شده روی Mac */
function fillFontSelect(selected) {
  const custom = state.settings.custom_fonts || [];
  const bundled = [{ family: "Vazirmatn", label: "وزیرمتن" }, ...state.bundled_fonts];
  const known = new Set([...bundled, ...custom].map((f) => f.family));
  const option = (value, label) => el("option", { value, selected: value === selected }, label);
  const groups = [
    el("optgroup", { label: "فارسی، همراه برنامه" }, bundled.map((f) => option(f.family, `${f.label} (${f.family})`))),
  ];
  if (custom.length) groups.push(el("optgroup", { label: "اضافه‌شده" }, custom.map((f) => option(f.family, f.family))));
  const installed = macFonts.filter((f) => !known.has(f));
  if (installed.length) groups.push(el("optgroup", { label: "نصب‌شده روی Mac" }, installed.map((f) => option(f, f))));
  // فونت فعلی حتی اگر هنوز در فهرست نیست، از دست نرود
  if (selected && !known.has(selected) && !installed.includes(selected)) groups.unshift(option(selected, selected));
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
      el("span", { style: `font-family:"${f.family}"` }, `${f.family} — نمونهٔ متن فارسی`),
      el("button", {
        type: "button", class: "danger",
        onclick: async () => {
          await api("POST", "/api/fonts/remove", { family: f.family });
          renderFontSettings(state.settings.font_family);
        },
      }, "حذف"))));
  fillFontSelect(selected);
  if (!fontsLoaded) {
    fetch("/api/fonts").then((r) => r.json()).then((fonts) => {
      macFonts = fonts;
      fontsLoaded = true;
      fillFontSelect(sf.font_family.value);
    });
  }
}

$("#font-add").addEventListener("click", async () => {
  const result = await api("POST", "/api/fonts/add", {});
  if (result.cancelled) return;
  renderFontSettings(result.added_font);
  showMessage(`فونت «${result.added_font}» اضافه شد. برای استفاده، «ذخیره» را بزنید.`, false);
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
    colors: { read: sf.color_read.value, review: sf.color_review.value, routine: sf.color_routine.value },
    color_mode: sf.color_mode.value,
    theme: sf.theme.value,
    font_size: Number(sf.font_size.value),
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
    const t = state.types.find((x) => x.id === Number(row.dataset.type));
    const name = row.querySelector('[data-field="name"]').value.trim();
    const color = row.querySelector('[data-field="color"]').value;
    if (t && (name !== t.name || color !== t.color)) await api("PATCH", `/api/types/${t.id}`, { name, color });
  }
  // رنگ منبع‌هایی که عوض شده‌اند
  for (const row of $$("#source-colors li[data-source]")) {
    const item = itemById(Number(row.dataset.source));
    const color = row.querySelector("input").value;
    if (item && color !== item.display_color) await api("PATCH", `/api/items/${item.id}`, { color });
  }
  await api("PATCH", "/api/settings", collectSettings());
  $("#settings-dialog").close();
  showMessage("تنظیمات ذخیره شد و برنامه از نو چیده شد.", false);
});

for (const button of $$("[data-browse]", settingsForm)) {
  button.addEventListener("click", async () => {
    const result = await api("POST", "/api/browse", { kind: "folder" });
    if (!result.cancelled) sf[button.dataset.browse].value = result.path;
  });
}

$("#settings-button").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", () => $("#settings-dialog").close());
