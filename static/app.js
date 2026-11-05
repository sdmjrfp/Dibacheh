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

function render() {
  $("#today").textContent = `امروز: ${Jalali.weekday(state.today)} ${Jalali.format(state.today)}`;
  // فقط نام پوشهٔ والت نشان داده می‌شود؛ آدرس کامل با نگه داشتن ماوس روی آن
  const vault = state.settings.vault_path;
  $("#vault-path").textContent = vault ? vault.split("/").filter(Boolean).pop() : "ثبت نشده";
  $("#vault-button").title = vault ? `مسیر والت: ${vault}\nبرای تغییر کلیک کنید` : "انتخاب پوشهٔ والت Obsidian";
  document.documentElement.dataset.theme = state.settings.theme || "light";
  renderTabs();
  renderCategoryFilter();
  renderItems();
  renderWorkload();
  for (const warning of state.plan.warnings) showMessage(warning);
  if (editing && editing.id && $("#item-dialog").open) renderSessions();
  const undo = $("#undo-button");
  undo.disabled = !state.undo.count;
  undo.title = state.undo.count
    ? `برگرداندن: ${state.undo.label} (${fa(state.undo.count)} مرحله قابل برگشت)` : "تغییری برای برگرداندن نیست";
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
    el("div", { class: "bars", title: "سبز: خواندن · آبی: مرور" },
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

function renderCategoryFilter() {
  $("#category-filter").replaceChildren(...categoryOptions(filterCategory, "همهٔ دسته‌ها"));
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
  const p = item.progress;
  const meta = [];
  if (category) meta.push(el("span", { class: "chip" }, category.name));
  if (item.item_type === "routine") meta.push(el("span", { class: "chip routine" }, "روتین"));
  meta.push(el("span", {}, `${fa(item.sessions.length)} جلسه`));
  meta.push(el("span", {}, `خواندن ${fa(p.read_percent)}٪`));
  if (p.reviews_total) meta.push(el("span", {}, `مرور ${fa(p.reviews_done)} از ${fa(p.reviews_total)}`));
  if (!item.is_active) {
    meta.push(el("span", {}, "غیرفعال: روی تقویم نیست"));
  } else {
    if (item.finish.read_end) meta.push(el("span", {}, `پایان خواندن: ${Jalali.formatShort(item.finish.read_end)}`));
    if (item.finish.review_end) meta.push(el("span", {}, `پایان مرور: ${Jalali.format(item.finish.review_end)}`));
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
    "data-id": item.id,
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
  enableDrag(card);
  return card;
}

// ---------------------------------------------------------------------------
// Drag-and-drop صف
// ---------------------------------------------------------------------------

// کشیدن با رویدادهای pointer انجام می‌شود (نه drag-and-drop خود HTML)،
// چون ساده‌تر و در همهٔ مرورگرها یکسان است.
let drag = null;   // { id, card, target } در حین کشیدن

function enableDrag(card) {
  const handle = $(".handle", card);
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    drag = { id: Number(card.dataset.id), card, target: undefined };
    card.classList.add("dragging");
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag) return;
    $$(".drop-before").forEach((n) => n.classList.remove("drop-before"));
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const target = under && under.closest(".item");
    if (target && target !== drag.card) {
      target.classList.add("drop-before");
      drag.target = Number(target.dataset.id);
    } else if (under && under.closest("#item-list") && !target) {
      drag.target = null;  // پایین فهرست: انتهای صف
    } else {
      drag.target = undefined;  // بیرون فهرست: لغو
    }
  });
  handle.addEventListener("pointerup", () => {
    if (!drag) return;
    const { id, target } = drag;
    drag.card.classList.remove("dragging");
    $$(".drop-before").forEach((n) => n.classList.remove("drop-before"));
    drag = null;
    if (target !== undefined && target !== id) moveItem(id, target);
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

/** پنجرهٔ درس. firstDate: وقتی درس از روی یک روز تقویم اضافه می‌شود. */
function openItemDialog(item, type = "study", firstDate = null) {
  editing = { id: item ? item.id : null, type: item ? item.item_type : type, firstDate };
  pickedSource = null;
  headingsCache = [];
  const isRoutine = editing.type === "routine";
  $("#item-dialog-title").textContent = item
    ? (isRoutine ? "ویرایش کار روتین" : "ویرایش درس")
    : (isRoutine ? "کار روتین جدید" : "درس جدید")
      + (firstDate ? ` از ${Jalali.format(firstDate)}` : "");

  const defaults = state.settings.new_item_defaults || {};
  fields.title.value = item ? item.title : "";
  fields.category_id.replaceChildren(...categoryOptions(item ? item.category_id : defaults.category_id, "بدون دسته"));
  fields.is_active.checked = item ? item.is_active : true;
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
// دسته‌ها
// ---------------------------------------------------------------------------

function renderCategoryDialog() {
  $("#category-list").replaceChildren(...state.categories.map((c) =>
    el("li", {},
      el("input", {
        value: c.name,
        onchange: (e) => api("PATCH", `/api/categories/${c.id}`, { name: e.target.value }).then(renderCategoryDialog),
      }),
      el("button", {
        class: "danger",
        onclick: () => {
          if (confirm(`دستهٔ «${c.name}» حذف شود؟ درس‌هایش بدون دسته می‌مانند.`)) {
            api("DELETE", `/api/categories/${c.id}`).then(renderCategoryDialog);
          }
        },
      }, "حذف"))));
}

$("#manage-categories").addEventListener("click", () => {
  renderCategoryDialog();
  $("#category-dialog").showModal();
});
$("#close-categories").addEventListener("click", () => $("#category-dialog").close());
$("#category-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("POST", "/api/categories", { name: e.target.name.value });
  e.target.reset();
  renderCategoryDialog();
});

// ---------------------------------------------------------------------------
// شروع
// ---------------------------------------------------------------------------

$("#category-filter").addEventListener("change", (e) => { filterCategory = e.target.value; render(); });
$("#add-study").addEventListener("click", () => openItemDialog(null, "study"));
$("#add-routine").addEventListener("click", () => openItemDialog(null, "routine"));
$("#vault-button").addEventListener("click", () => api("POST", "/api/browse", { kind: "vault" }));

api("GET", "/api/state");

$("#undo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/undo", {});
  if (result.undone) showMessage(`برگشت: ${result.undone}`, false);
});
