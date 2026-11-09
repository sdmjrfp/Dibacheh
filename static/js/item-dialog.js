/* پنجرهٔ درس، نوع کار تازه و افزودن گروهی. */

import { $, $$, api, buildJalaliInput, el, fa, itemById, readJalaliInput, showMessage, state, t, typeOf, WEEKDAYS } from "./core.js";
import { categoryOptions } from "./sources.js";

export let editing = null;

        // { id: شمارهٔ درس یا null برای درس جدید, type: "study" | "routine" }
let pickedSource = null;

   // نتیجهٔ Browse که هنوز ذخیره نشده
let headingsCache = [];

const SESSION_STATUS = {
  unread: t("خوانده‌نشده"),
  reading: t("نیمه‌خوانده"),
  reviewing: t("در حال مرور"),
  finished: t("تمام‌شده"),
};

// ---------------------------------------------------------------------------
// پنجرهٔ درس
// ---------------------------------------------------------------------------

const form = $("#item-form");

// form.elements به‌جای form: چون form.title خودِ عنوان فرم است، نه فیلد title
const fields = form.elements;

/** پنجرهٔ درس.
 *  firstDate: وقتی درس از روی یک روز تقویم اضافه می‌شود.
 *  customType: وقتی از دکمهٔ یکی از نوع‌های ساخت کاربر (مثلاً «+ پروژه») باز می‌شود. */
export function openItemDialog(item, type = "study", firstDate = null, customType = null, { variant = "study", template = null } = {}) {
  customType = customType || (item ? typeOf(item) : null);
  editing = {
    id: item ? item.id : null, type: item ? item.item_type : type, firstDate, customType,
    variant: item ? item.variant : variant,
  };
  pickedSource = null;
  headingsCache = [];
  const isRoutine = editing.type === "routine";
  const variantName = { once: t("کار یک‌باره"), project: t("پروژه") }[editing.variant];
  const typeName = customType ? customType.name : (variantName || (isRoutine ? t("کار روتین") : t("درس")));
  $("#item-dialog-title").textContent = (item ? t("ویرایش {0}", typeName) : t("{0} جدید", typeName))
    + (!item && firstDate ? t(" از {0}", Jalali.format(firstDate)) : "");

  const defaults = state.settings.new_item_defaults || {};
  fields.title.value = item ? item.title : "";
  fields.category_id.replaceChildren(...categoryOptions(item ? item.category_id : defaults.category_id, t("بدون دسته")));
  fields.is_active.checked = item ? item.is_active : true;
  fields.color.value = item ? item.display_color : state.palette[state.items.length % state.palette.length];
  fields.session_count.value = isRoutine ? 10 : 1;
  buildJalaliInput($('.jalali-input[data-name="once_date"]'), !item && editing.variant === "once" ? firstDate : null);
  fields.session_minutes.value = isRoutine ? 10 : (defaults.session_minutes || 60);
  fields.max_new_sessions_per_day.value = item ? item.max_new_sessions_per_day : (defaults.max_new_sessions_per_day || 1);
  fields.review_ratio.value = item && item.review_ratio ? item.review_ratio : "";
  fields.review_intervals.value = item && item.review_intervals ? item.review_intervals.join(t("، ")) : "";
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

  editing.requires = item ? item.requires.map((r) => ({ ...r })) : [];
  editing.sections = null;
  renderRequires();
  renderTemplateSelect();
  $("#outline-box").hidden = true;
  fields.session_count.disabled = false;
  updateDialogVisibility();
  if (template) applyTemplate(template);
  if (item && ["vault", "file"].includes(item.source_type)) {
    fetch(`/api/items/${item.id}/outline`).then((r) => r.json()).then((r) => {
      if (editing && editing.id === item.id) showOutline(r.outline);
    });
  }
  if (item) {
    if (item.section_unit === "heading") loadHeadings(item.id);
    renderSessions(true);
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
  // کاری که مرور ندارد (پروژه، کار یک‌باره، یا درسی که مرورهایش حذف شده)
  const current = editing.id ? itemById(editing.id) : null;
  const noReviews = editing.variant !== "study" || Boolean(current && current.no_reviews);
  $$("[data-variant]", form).forEach((n) => { n.hidden = n.dataset.variant !== editing.variant || Boolean(current); });
  $$("[data-sessions]", form).forEach((n) => { n.hidden = n.hidden || editing.variant === "once"; });
  $$("[data-reviews]", form).forEach((n) => { n.hidden = n.hidden || noReviews; });
  const canHaveReviews = Boolean(current) && editing.type === "study" && editing.variant === "study";
  $("#remove-reviews").hidden = !canHaveReviews || noReviews;
  $("#restore-reviews").hidden = !canHaveReviews || !noReviews;
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
    ? t("{0}  (داخل والت)", result.source_path_or_url) : result.source_path_or_url;
  $("#source-problem").hidden = true;
  showOutline(result.outline);
});

// ---------- ساختن جلسه‌ها از ساختار فایل

/** عنوان‌های نوت یا فصل‌های PDF در یک سطح، به شکل فهرست بخش‌ها */
function outlineSections(outline, level) {
  const entries = outline.entries.filter((e) => e.level === level);
  if (outline.unit === "heading") return entries.map((e) => ({ title: e.title, start: e.title, end: e.title }));
  return entries.map((e, i) => {
    const next = entries[i + 1];
    const end = next ? Math.max(e.page, next.page - 1) : outline.pages;
    return { title: e.title, start: String(e.page), end: String(end) };
  });
}

function showOutline(outline) {
  const box = $("#outline-box");
  box.hidden = !outline;
  if (!outline) return;
  const levels = [...new Set(outline.entries.map((e) => e.level))].sort();
  const count = (level) => outline.entries.filter((e) => e.level === level).length;
  const select = el("select", {}, levels.map((l) =>
    el("option", { value: l }, t("سطح {0}: {1} {2}", fa(l), fa(count(l)), outline.unit === "heading" ? t("عنوان") : t("فصل")))));
  const status = el("span", { class: "muted" });
  const apply = async () => {
    const sections = outlineSections(outline, Number(select.value));
    fields.section_unit.value = outline.unit;
    updateDialogVisibility();
    if (editing.id) {
      await api("POST", `/api/items/${editing.id}/split`, { sections, section_unit: outline.unit });
      status.textContent = t("جلسه‌های خوانده‌نشده با {0} بخش عوض شدند.", fa(sections.length));
    } else {
      editing.sections = sections;
      fields.session_count.value = sections.length;
      fields.session_count.disabled = true;
      status.textContent = t("{0} جلسه ساخته می‌شود.", fa(sections.length));
    }
  };
  box.replaceChildren(
    el("div", {}, outline.unit === "heading" ? t("این نوت عنوان دارد. می‌شود هر عنوان یک جلسه باشد.") : t("این PDF فهرست مطالب دارد. می‌شود هر فصل یک جلسه باشد.")),
    el("div", { class: "pop-row" }, select,
      el("button", { type: "button", onclick: apply }, t("ساختن جلسه‌ها از فایل")), status));
}

// ---------- وابستگی‌ها

function renderRequires() {
  const list = editing.requires;
  $("#requires-list").replaceChildren(...list.map((req, i) => {
    const other = itemById(req.id);
    return el("li", {},
      el("span", {}, t("بعد از {0} «{1}»", req.until === "finished" ? t("پایان مرورهای") : t("پایان خواندن"), other ? other.title : t("؟"))),
      el("button", { type: "button", class: "danger", onclick: () => { list.splice(i, 1); renderRequires(); } }, t("حذف")));
  }));
  const taken = new Set(list.map((r) => r.id));
  const options = state.items.filter((i) => i.item_type === "study" && i.id !== editing.id && !taken.has(i.id));
  $("#requires-item").replaceChildren(...options.map((i) => el("option", { value: i.id }, i.title)));
  $("#requires-add").disabled = !options.length;
}

$("#requires-add").addEventListener("click", () => {
  const id = Number($("#requires-item").value);
  if (!id) return;
  editing.requires.push({ id, until: $("#requires-until").value });
  renderRequires();
});

// ---------- الگوها

/** نوع فعلی پنجره به زبان الگوها */
function templateKind() {
  if (editing.variant !== "study") return editing.variant;
  return editing.type === "routine" ? "routine" : "study";
}

function renderTemplateSelect() {
  const templates = state.templates.filter((template) => template.kind === templateKind());
  $("#template-select").replaceChildren(el("option", { value: "" }, templates.length ? t("از روی الگو…") : t("الگویی ذخیره نشده")),
    ...templates.map((template) => el("option", { value: template.id }, template.name)));
}

function applyTemplate(template) {
  const f = template.fields;
  if (f.session_count) fields.session_count.value = f.session_count;
  if (f.session_minutes) fields.session_minutes.value = f.session_minutes;
  if (f.max_new_sessions_per_day) fields.max_new_sessions_per_day.value = f.max_new_sessions_per_day;
  fields.review_ratio.value = f.review_ratio || "";
  fields.review_intervals.value = (f.review_intervals || []).join(t("، "));
  fields.section_unit.value = f.section_unit || "text";
  if (f.category_id !== undefined) fields.category_id.value = f.category_id || "";
  if (f.color) fields.color.value = f.color;
  const weekdays = f.routine_weekdays || [];
  $$("#routine-weekdays input").forEach((box) => { box.checked = weekdays.includes(Number(box.value)); });
  updateDialogVisibility();
}

$("#template-select").addEventListener("change", (e) => {
  const template = state.templates.find((item) => item.id === e.target.value);
  if (template) applyTemplate(template);
});

$("#template-save").addEventListener("click", async () => {
  const name = prompt(t("نام الگو:"));
  if (!name || !name.trim()) return;
  const intervals = fields.review_intervals.value.split(/[،,\s]+/).filter(Boolean).map(Number);
  const template = {
    name: name.trim(),
    kind: templateKind(),
    fields: {
      session_count: Number(fields.session_count.value),
      session_minutes: Number(fields.session_minutes.value),
      max_new_sessions_per_day: Number(fields.max_new_sessions_per_day.value),
      review_ratio: fields.review_ratio.value.trim(),
      review_intervals: intervals,
      section_unit: fields.section_unit.value,
      category_id: fields.category_id.value ? Number(fields.category_id.value) : null,
      routine_weekdays: $$("#routine-weekdays input:checked").map((x) => Number(x.value)),
    },
  };
  await api("PATCH", "/api/settings", { item_templates: [...(state.settings.item_templates || []), template] });
  renderTemplateSelect();
  showMessage(t("الگوی «{0}» ذخیره شد.", template.name), false);
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
  if (!editing.id) data.variant = editing.variant;
  if (editing.type === "study") {
    data.max_new_sessions_per_day = Number(fields.max_new_sessions_per_day.value);
    data.review_ratio = fields.review_ratio.value.trim();
    const intervals = fields.review_intervals.value.split(/[،,\s]+/).filter(Boolean).map(Number);
    data.review_intervals = intervals.length ? intervals : null;
    data.target_date = readJalaliInput($('.jalali-input[data-name="target_date"]'));
    data.requires = editing.requires;
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
    throw new Error(t("برای منبع فایل، اول Browse کنید و فایل را انتخاب کنید."));
  }
  if (!editing.id) {
    data.session_count = editing.variant === "once" ? 1 : Number(fields.session_count.value);
    data.session_minutes = Number(fields.session_minutes.value);
    if (editing.firstDate) data.first_date = editing.firstDate;
    if (editing.variant === "once") data.first_date = readJalaliInput($('.jalali-input[data-name="once_date"]'));
    if (editing.customType) data.custom_type_id = editing.customType.id;
    if (editing.sections) data.sections = editing.sections;
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
  if (!confirm(t("همهٔ جلسه‌های این درس به حالت خوانده‌نشده برمی‌گردند و درس به انتهای صف می‌رود. سابقهٔ قبلی می‌ماند. ادامه می‌دهید؟"))) return;
  api("POST", `/api/items/${editing.id}/reset`, {});
});

$("#remove-reviews").addEventListener("click", async () => {
  const item = itemById(editing.id);
  if (!confirm(t("همهٔ مرورهای «{0}» حذف شود؟ جلسه‌ها از این به بعد با خواندن تمام می‌شوند و سابقهٔ کارهای انجام‌شده می‌ماند.", item.title))) return;
  await api("DELETE", `/api/items/${editing.id}/reviews`);
  updateDialogVisibility();
});

$("#restore-reviews").addEventListener("click", async () => {
  await api("POST", `/api/items/${editing.id}/reviews`, {});
  updateDialogVisibility();
});

$("#delete-item").addEventListener("click", async () => {
  const item = itemById(editing.id);
  if (!confirm(t("«{0}» با همهٔ جلسه‌ها و سابقه‌اش حذف شود؟ فایل منبع روی کامپیوتر دست نمی‌خورد. این کار برگشت ندارد.", item.title))) return;
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
      el("span", {}, t("تا")),
      el("input", { value: session.section_end || "", dir: "ltr", onchange: save("section_end") }));
  }
  if (item.section_unit === "heading") {
    const options = (selected) => [el("option", { value: "" }, "—"),
      ...headingsCache.map((h) => el("option", { value: h.text, selected: h.text === selected },
        `${"  ".repeat(h.level - 1)}${h.text}`))];
    if (!headingsCache.length) return el("span", { class: "muted" }, t("عنوانی در فایل Markdown پیدا نشد."));
    return el("div", { class: "range" },
      el("select", { onchange: save("section_start") }, options(session.section_start)),
      el("span", {}, t("تا")),
      el("select", { onchange: save("section_end") }, options(session.section_end)));
  }
  return el("input", { value: session.section_label || "", placeholder: t("مثلاً فصل ۱"), onchange: save("section_label") });
}

let sessionsKey = "";

export function renderSessions(force = false) {
  const item = itemById(editing.id);
  if (!item) return;
  // وقتی چیزی در جدول عوض نشده، دوباره کشیده نمی‌شود تا فوکوس فیلد از بین نرود
  const key = JSON.stringify([item.id, item.sessions, item.range_problems, item.section_unit, headingsCache]);
  if (!force && key === sessionsKey) return;
  sessionsKey = key;
  $("#range-problems").replaceChildren(...item.range_problems.map((p) => el("li", {}, p)));
  $("#sessions-body").replaceChildren(...item.sessions.map((s) => {
    let status = SESSION_STATUS[s.status];
    if (s.status === "reviewing") status += t(" (جعبهٔ {0})", fa(s.leitner_box));
    if (s.status === "reading") status += t(" ({0} دقیقه)", fa(s.minutes_done));
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
        placeholder: t("خودکار"), title: t("زمان مرور همین جلسه. خالی = از نسبت مرور"),
        onchange: (e) => saveSession(s.id, { review_minutes_override: e.target.value }),
      })),
      el("td", {}, el("input", {
        value: s.note || "", placeholder: t("یادداشت…"),
        onchange: (e) => saveSession(s.id, { note: e.target.value }),
      })),
    );
  }));
}

// ---------------------------------------------------------------------------
// نوع کار تازه (از منوی «+»)
// ---------------------------------------------------------------------------

export function openTypeDialog() {
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

$("#quit-button").addEventListener("click", async () => {
  if (!confirm(t("برنامه بسته شود؟"))) return;
  await api("POST", "/api/quit", {});
  document.body.replaceChildren(el("p", { class: "quit-note" }, t("برنامه بسته شد. می‌توانید این صفحه را ببندید.")));
});

// ---------------------------------------------------------------------------
// افزودن گروهی و جست‌وجو
// ---------------------------------------------------------------------------

export function openBulkDialog() {
  const f = $("#bulk-form").elements;
  f.text.value = "";
  f.category_id.replaceChildren(...categoryOptions("", t("بدون دسته")));
  f.custom_type_id.replaceChildren(el("option", { value: "" }, t("درس")),
    ...state.types.map((type) => el("option", { value: type.id }, type.name)));
  $("#bulk-dialog").showModal();
}

$("#bulk-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target.elements;
  await api("POST", "/api/items/bulk", {
    text: f.text.value,
    category_id: f.category_id.value ? Number(f.category_id.value) : null,
    custom_type_id: f.custom_type_id.value ? Number(f.custom_type_id.value) : null,
  });
  $("#bulk-dialog").close();
});

$("#close-bulk").addEventListener("click", () => $("#bulk-dialog").close());
