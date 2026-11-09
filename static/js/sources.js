/* ستون کارها و منابع: تب‌ها، فهرست درس‌ها، صف و نشانگر حجم کار. */

import { $, api, el, fa, itemById, minutesText, render, renderPart, showMessage, state, t, typeOf } from "./core.js";
import { openItemDialog } from "./item-dialog.js";
import { sortable } from "./motion.js";

let filterStatus = "all";

let filterCategory = "";

export let searchText = "";

export let selectedItemId = null;

const STATUS_LISTS = [
  ["all", t("همه")],
  ["unread", t("خوانده‌نشده")],
  ["reading", t("در حال خواندن")],
  ["read", t("خوانده‌شده")],
  ["finished", t("تمام‌شده")],
  ["archived", t("بایگانی")],
];

/** نشانگر حجم کار منتظر: خواندن و مرور باقی‌مانده، تاریخ پایان و میانگین روزانه. */
export function renderWorkload() {
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
    el("strong", {}, t("حجم کار منتظر: {0}", minutesText(total))),
    el("div", { class: "bars", title: t("رنگ خواندن و رنگ مرور، به نسبت حجم هرکدام") },
      el("span", { class: "r", style: `width:${readShare}%` }),
      el("span", { class: "v", style: `width:${100 - readShare}%` })),
    el("div", {}, t("خواندن {0} · مرور {1}", minutesText(w.read_minutes), minutesText(w.review_minutes))),
    w.end_date && el("div", {}, t("پایان پیش‌بینی‌شدهٔ همه‌چیز: {0}", Jalali.format(w.end_date))),
    el("div", { class: "muted" },
      t("۳۰ روز آینده، به‌طور میانگین هر روز {0} دقیقه مرور و {1} دقیقه مطلب جدید", fa(w.avg_review_next_30), fa(w.avg_read_next_30))),
  );
}

/** متن جلو یا عقب بودن از تاریخ هدف */
function targetText(label, info) {
  if (!info) return null;
  if (info.done) return el("span", { class: "target ahead" }, t("{0}: تمام شده ✓", label));
  if (info.days === null) return null;
  if (info.days === 0) return el("span", { class: "target ahead" }, t("{0}: درست سر هدف", label));
  const ahead = info.days > 0;
  return el("span", { class: `target ${ahead ? "ahead" : "behind"}` },
    t("{0}: {1} روز {2} هدف", label, fa(Math.abs(info.days)), ahead ? t("زودتر از") : t("دیرتر از")));
}

export function renderTabs() {
  const counts = { all: 0, archived: 0 };
  for (const item of state.items) {
    if (item.archived) { counts.archived += 1; continue; }
    counts.all += 1;
    counts[item.status_list] = (counts[item.status_list] || 0) + 1;
  }
  $("#status-tabs").replaceChildren(...STATUS_LISTS.map(([key, label]) =>
    el("button", {
      role: "tab",
      "aria-selected": String(filterStatus === key),
      onclick: () => { filterStatus = key; render(); },
    }, `${label} (${fa(counts[key] || 0)})`)
  ));
}

export function categoryOptions(selected, emptyLabel) {
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

let typingCategoryName = false;

export function renderCategoryTabs() {
  const box = $("#category-tabs");
  if (typingCategoryName) return;  // وسط تایپ نام، دوباره کشیده نشود
  const tab = (id, label, count) => {
    const selected = String(filterCategory) === String(id);
    const node = el("div", {
      class: `cat-tab${selected ? " selected" : ""}`, role: "tab", "aria-selected": String(selected),
      "data-id": id, "data-flip": `cat-${id || "all"}`,
      onclick: (e) => {
        // تب انتخاب‌شده دوباره کشیده نمی‌شود، وگرنه دوبار کلیک (تغییر نام) به تب حذف‌شده می‌رسد
        if (e.target.closest(".x") || selected) return;
        filterCategory = String(id);
        render();
      },
    }, el("span", { class: "name" }, label), el("span", { class: "count" }, fa(count)));
    return node;
  };
  const counts = new Map();
  for (const item of state.items) counts.set(item.category_id, (counts.get(item.category_id) || 0) + 1);
  const all = tab("", t("همه"), state.items.length);
  all.dataset.fixed = "";
  const tabs = state.categories.map((c) => {
    const node = tab(c.id, c.name, counts.get(c.id) || 0);
    node.title = t("دوبار کلیک: تغییر نام · کشیدن: جابه‌جایی");
    node.append(el("button", {
      class: "x", title: t("حذف دسته"),
      onclick: () => {
        if (confirm(t("دستهٔ «{0}» حذف شود؟ درس‌هایش می‌مانند و بدون دسته می‌شوند.", c.name))) {
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
    : el("button", { class: "cat-tab plus", "data-fixed": "", title: t("دستهٔ جدید"),
        onclick: () => { addingCategory = true; render(); $("#category-tabs input").focus(); } }, "+");
  box.replaceChildren(all, ...tabs, plus);
}

/** ورودی نام دسته: Enter = ثبت، Esc = لغو */
function categoryNameInput(value, done) {
  let finished = false;
  const input = el("input", { value, placeholder: t("نام دسته"), size: 10 });
  typingCategoryName = true;
  const end = (name) => {
    if (finished) return;
    finished = true;
    typingCategoryName = false;
    done(name);
  };
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

// روی خود نوار تب‌ها گوش می‌دهیم: کلیک اول تب‌ها را دوباره می‌کشد و تب قبلی دیگر وجود ندارد
$("#category-tabs").addEventListener("dblclick", (e) => {
  const node = e.target.closest(".cat-tab[data-id]");
  const category = node && state.categories.find((c) => String(c.id) === node.dataset.id);
  if (category) renameCategoryInline(node, category);
});

sortable($("#category-tabs"), {
  items: ".cat-tab", axis: "x",
  onDrop: (ids) => api("POST", "/api/categories/reorder", { ids: ids.filter(Boolean).map(Number) }),
});

export function renderItems() {
  const list = $("#item-list");
  const visible = state.items.filter((item) =>
    (filterStatus === "archived" ? item.archived : !item.archived) &&
    (filterStatus === "all" || filterStatus === "archived" || item.status_list === filterStatus) &&
    (!filterCategory || String(item.category_id) === filterCategory) &&
    (!searchText || searchHits(item).matched));
  // فقط اگر چیزی در فهرست عوض شده باشد، دوباره کشیده می‌شود
  const key = [visible, state.items.length, state.categories, state.types, selectedItemId, searchText];
  renderPart("items", key, () => {
    if (visible.length) {
      list.replaceChildren(...visible.map(itemCard));
    } else {
      list.replaceChildren(el("li", { class: "muted" }, state.items.length
        ? t("درسی با این فیلتر نیست.") : t("هنوز چیزی اضافه نشده. با دکمهٔ «+» شروع کنید.")));
    }
  });
}

/** حرف‌های عربی و فارسی یکی می‌شوند تا «ي» و «ی» در جست‌وجو فرق نکنند */
function normalize(text) {
  return String(text || "").toLowerCase().replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/\u200c/g, " ");
}

/** جست‌وجو در نام درس، منبع، بخش جلسه‌ها و یادداشت‌ها */
function searchHits(item) {
  const q = normalize(searchText.trim());
  if (!q) return { matched: true, sessions: [] };
  const direct = normalize(item.title).includes(q) || normalize(item.source_path_or_url).includes(q);
  const sessions = item.sessions.filter((s) =>
    normalize(s.section_text).includes(q) || normalize(s.note).includes(q));
  return { matched: direct || sessions.length > 0, sessions };
}

function itemCard(item) {
  const category = state.categories.find((c) => c.id === item.category_id);
  const custom = typeOf(item);
  const p = item.progress;
  const meta = [];
  if (category) meta.push(el("span", { class: "chip" }, category.name));
  if (custom) meta.push(el("span", { class: "chip typed", style: `--c:${custom.color}` }, custom.name));
  else if (item.item_type === "routine") meta.push(el("span", { class: "chip routine" }, t("روتین")));
  else if (item.variant === "project") meta.push(el("span", { class: "chip typed kind-project" }, t("پروژه")));
  else if (item.variant === "once") meta.push(el("span", { class: "chip typed kind-once" }, t("کار یک‌باره")));
  meta.push(el("span", {}, t("{0} جلسه", fa(item.sessions.length))));
  meta.push(el("span", {}, t("{0} {1}٪", item.variant === "study" ? t("خواندن") : t("پیشرفت"), fa(p.read_percent))));
  if (p.reviews_total) meta.push(el("span", {}, t("مرور {0} از {1}", fa(p.reviews_done), fa(p.reviews_total))));
  if (!item.is_active) {
    meta.push(el("span", {}, t("غیرفعال: روی تقویم نیست")));
  } else {
    if (item.finish.read_end) meta.push(el("span", {}, `${item.variant === "study" ? t("پایان خواندن") : t("پایان")}: ${Jalali.formatShort(item.finish.read_end)}`));
    if (item.finish.review_end) meta.push(el("span", {}, t("پایان مرور: {0}", Jalali.format(item.finish.review_end))));
  }
  for (const req of item.requires) {
    const other = itemById(req.id);
    if (!other) continue;
    const waiting = item.waiting_for.includes(other.title);
    const when = req.until === "finished" ? t("پایان مرورهای") : t("پایان خواندنِ");
    meta.push(el("span", { class: waiting ? "waiting" : "" }, `${waiting ? t("🔒 منتظر") : t("✓ بعد از")} ${when} «${other.title}»`));
  }
  if (item.pinned) {
    meta.push(el("span", { class: "pinned", title: t("این جلسه‌ها روی روز خاصی مانده‌اند و اولویت صف رویشان اثر ندارد") },
      t("📌 {0} جلسه دستی جابه‌جا شده", fa(item.pinned)),
      el("button", {
        class: "link", title: t("همهٔ جابه‌جایی‌های دستی این درس برداشته شود"),
        onclick: () => api("POST", `/api/items/${item.id}/unpin`, {}),
      }, t("برگشت به چینش خودکار"))));
  }
  if (item.target_date) {
    meta.push(el("span", {}, t("هدف: {0}", Jalali.format(item.target_date))));
    if (item.target) {
      meta.push(targetText(t("خواندن"), item.target.read));
      meta.push(targetText(t("مرور"), item.target.review));
    }
  }

  const card = el("li", {
    class: `item${item.is_active ? "" : " inactive"}${item.id === selectedItemId ? " selected" : ""}`,
    "data-id": item.id, "data-flip": `item-${item.id}`,
  },
    el("span", { class: "handle", title: t("برای جابه‌جایی بکشید") }, "⋮⋮"),
    el("input", {
      type: "checkbox", checked: item.is_active, title: t("فعال / غیرفعال"),
      onchange: (e) => api("PATCH", `/api/items/${item.id}`, { is_active: e.target.checked }),
    }),
    el("span", {
      class: "title",
      onclick: () => { selectedItemId = selectedItemId === item.id ? null : item.id; render(); },
    }, item.title),
    el("span", { class: "actions" },
      el("input", {
        type: "color", class: "swatch", value: item.display_color, title: t("رنگ این منبع"),
        onchange: (e) => api("PATCH", `/api/items/${item.id}`, { color: e.target.value }),
      }),
      item.source_type !== "none" && el("button", {
        class: "icon", title: t("باز کردن منبع"),
        onclick: () => api("POST", `/api/items/${item.id}/open`, {}),
      }, "↗"),
      el("button", { class: "icon", title: t("ویرایش"), onclick: () => openItemDialog(item) }, "✎"),
      (item.status_list === "finished" || item.archived) && el("button", {
        class: "icon", title: item.archived ? t("برگرداندن از بایگانی") : t("بایگانی"),
        onclick: () => api("POST", `/api/items/${item.id}/archive`, { archived: !item.archived }),
      }, item.archived ? "⤴" : "🗄"),
    ),
    el("div", { class: "progress" }, el("span", { style: `width:${p.read_percent}%` })),
    el("div", { class: "meta" }, meta),
    item.source_problem && el("div", { class: "problem" }, `⚠ ${item.source_problem}`),
    searchText && el("div", { class: "hits" }, searchHits(item).sessions.slice(0, 4).map((s) =>
      el("div", {}, t("جلسهٔ {0}: {1}", fa(s.sequence), [s.section_text, s.note].filter(Boolean).join(" · "))))),
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
      showMessage(t("جابه‌جایی دستی {0} جلسه از «{1}» برداشته شد تا طبق اولویت تازه چیده شود.", fa(result.released), item.title), false);
    }
  });
}

$("#item-search").addEventListener("input", (e) => { searchText = e.target.value; render(); });
