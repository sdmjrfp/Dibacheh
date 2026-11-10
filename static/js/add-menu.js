/* منوی «+»: انتخاب اینکه چه چیزی اضافه شود، و الگوهای آمادهٔ همان نوع. */

import { $, el, state, t } from "./core.js";
import { closeOnOutside } from "./dialogs.js";
import { openBulkDialog, openItemDialog, openTypeDialog } from "./item-dialog.js";

const KINDS = [
  { key: "study", icon: "📖", name: t("درس"), about: t("جلسه‌ها به ترتیب صف، با مرور لایتنر"), type: "study", variant: "study" },
  { key: "routine", icon: "🔁", name: t("کار روتین"), about: t("هر روز یا روزهای انتخابی، بدون مرور"), type: "routine", variant: "study" },
  { key: "once", icon: "✅", name: t("کار یک‌باره"), about: t("فقط یک بار انجام می‌شود، روز مشخص یا اولین جای خالی"), type: "study", variant: "once" },
  { key: "project", icon: "🧩", name: t("پروژه"), about: t("چند جلسه پشت سر هم، بدون مرور"), type: "study", variant: "project" },
];

let firstDate = null;

/** firstDate: وقتی از منوی یک روز تقویم باز می‌شود. */
export function openAddMenu(date = null) {
  firstDate = date;
  $("#add-templates").hidden = true;
  $("#add-kinds").replaceChildren(
    ...KINDS.map((kind) => tile(kind.icon, kind.name, kind.about, () => chooseKind(kind), { "data-add": kind.key })),
    ...state.types.map((custom) => tile("●", custom.name,
      custom.behavior === "study" ? t("مثل درس، با مرور لایتنر") : t("مثل کار روتین، بدون مرور"),
      () => { close(); openItemDialog(null, custom.behavior, firstDate, custom); },
      { style: `--c:${custom.color}`, class: "add-tile typed" })),
    tile("📚", t("چند درس با هم"), t("هر خط یک درس"), () => { close(); openBulkDialog(); }, { "data-add": "bulk" }),
    tile("➕", t("نوع تازه"), t("نوع کار خودتان را با نام و رنگ دلخواه بسازید"), () => { close(); openTypeDialog(); }, { "data-add": "type" }),
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
      el("strong", {}, t("بدون الگو")), el("span", { class: "muted small" }, t("خودتان همه‌چیز را تعیین کنید"))),
    ...templates.map((template) => el("button", {
      type: "button", class: "add-tile", "data-template": template.id, onclick: () => open(template),
    }, el("strong", {}, template.name), el("span", { class: "muted small" }, templateSummary(template)))),
  );
  $("#add-templates").hidden = false;
}

function templateSummary(template) {
  const f = template.fields;
  const parts = [];
  if (f.session_count) parts.push(t("{0} جلسه", Jalali.faNumber(f.session_count)));
  if (f.session_minutes) parts.push(t("{0} دقیقه", Jalali.faNumber(f.session_minutes)));
  if (f.review_intervals && f.review_intervals.length) parts.push(t("{0} مرور", Jalali.faNumber(f.review_intervals.length)));
  return parts.join(" · ");
}

$("#add-button").addEventListener("click", () => openAddMenu());

closeOnOutside($("#add-dialog"), { closeButton: $("#close-add") });
