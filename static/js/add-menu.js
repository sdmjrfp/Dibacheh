/* منوی «+»: انتخاب اینکه چه چیزی اضافه شود، و الگوهای آمادهٔ همان نوع. */

import { $, el, state } from "./core.js";
import { openBulkDialog, openItemDialog, openTypeDialog } from "./item-dialog.js";

const KINDS = [
  { key: "study", icon: "📖", name: "درس", about: "جلسه‌ها به ترتیب صف، با مرور لایتنر", type: "study", variant: "study" },
  { key: "routine", icon: "🔁", name: "کار روتین", about: "هر روز یا روزهای انتخابی، بدون مرور", type: "routine", variant: "study" },
  { key: "once", icon: "✅", name: "کار یک‌باره", about: "فقط یک بار انجام می‌شود، روز مشخص یا اولین جای خالی", type: "study", variant: "once" },
  { key: "project", icon: "🧩", name: "پروژه", about: "چند جلسه پشت سر هم، بدون مرور", type: "study", variant: "project" },
];

let firstDate = null;

/** firstDate: وقتی از منوی یک روز تقویم باز می‌شود. */
export function openAddMenu(date = null) {
  firstDate = date;
  $("#add-templates").hidden = true;
  $("#add-kinds").replaceChildren(
    ...KINDS.map((kind) => tile(kind.icon, kind.name, kind.about, () => chooseKind(kind), { "data-add": kind.key })),
    ...state.types.map((custom) => tile("●", custom.name,
      custom.behavior === "study" ? "مثل درس، با مرور لایتنر" : "مثل کار روتین، بدون مرور",
      () => { close(); openItemDialog(null, custom.behavior, firstDate, custom); },
      { style: `--c:${custom.color}`, class: "add-tile typed" })),
    tile("📚", "چند درس با هم", "هر خط یک درس", () => { close(); openBulkDialog(); }, { "data-add": "bulk" }),
    tile("➕", "نوع تازه", "نوع کار خودتان را با نام و رنگ دلخواه بسازید", () => { close(); openTypeDialog(); }, { "data-add": "type" }),
  );
  $("#add-dialog").showModal();
}

function tile(icon, name, about, onclick, attrs = {}) {
  return el("button", { type: "button", class: "add-tile", onclick, ...attrs },
    el("span", { class: "add-icon" }, icon),
    el("strong", {}, name),
    el("span", { class: "muted small" }, about));
}

function close() {
  $("#add-dialog").close();
}

/** اگر این نوع الگو دارد، اول الگوها پیشنهاد می‌شوند. */
function chooseKind(kind) {
  const open = (template = null) => {
    close();
    openItemDialog(null, kind.type, firstDate, null, { variant: kind.variant, template });
  };
  const templates = state.templates.filter((template) => template.kind === kind.key);
  if (!templates.length) {
    open();
    return;
  }
  $("#add-template-list").replaceChildren(
    el("button", { type: "button", id: "add-no-template", class: "add-tile", onclick: () => open() },
      el("strong", {}, "بدون الگو"), el("span", { class: "muted small" }, "خودتان همه‌چیز را تعیین کنید")),
    ...templates.map((template) => el("button", {
      type: "button", class: "add-tile", "data-template": template.id, onclick: () => open(template),
    }, el("strong", {}, template.name), el("span", { class: "muted small" }, templateSummary(template)))),
  );
  $("#add-templates").hidden = false;
}

function templateSummary(template) {
  const f = template.fields;
  const parts = [];
  if (f.session_count) parts.push(`${Jalali.faNumber(f.session_count)} جلسه`);
  if (f.session_minutes) parts.push(`${Jalali.faNumber(f.session_minutes)} دقیقه`);
  if (f.review_intervals && f.review_intervals.length) parts.push(`${Jalali.faNumber(f.review_intervals.length)} مرور`);
  return parts.join(" · ");
}

$("#add-button").addEventListener("click", () => openAddMenu());

$("#close-add").addEventListener("click", close);
