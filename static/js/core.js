/* ابزارهای مشترک: وضعیت برنامه، ساختن عنصر، درخواست به سرور، ورودی تاریخ. */

import { Motion } from "./motion.js";

/* رابط کاربری داشبورد.

   روش کار:
   - همهٔ داده‌ها در متغیر state است که از /api/state می‌آید.
   - هر تغییری به سرور فرستاده می‌شود. سرور برنامه را از نو می‌سازد و state تازه
     را برمی‌گرداند. بعد render() کل صفحه را دوباره می‌کشد. صفحه هیچ‌وقت reload نمی‌شود.
   - متن‌هایی که کاربر نوشته با textContent گذاشته می‌شوند، نه innerHTML،
     تا هیچ متنی نتواند کد اجرا کند.
*/

export const CSRF = document.querySelector('meta[name="csrf-token"]').content;

export const fa = Jalali.faNumber;

export let state = null;

// ترتیب روزهای هفتهٔ ایرانی، با شمارهٔ روز در پایتون (0 = دوشنبه)
export const WEEKDAYS = [[5, "شنبه"], [6, "یکشنبه"], [0, "دوشنبه"], [1, "سه‌شنبه"],
                  [2, "چهارشنبه"], [3, "پنجشنبه"], [4, "جمعه"]];

// ---------------------------------------------------------------------------
// ابزارهای کوچک
// ---------------------------------------------------------------------------

/** ساخت عنصر HTML: el("button", {class: "x", onclick: f}, "متن") */
export function el(tag, attrs = {}, ...children) {
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

export const $ = (selector, root = document) => root.querySelector(selector);

export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let messageTimer = null;

export function showMessage(text, isError = true) {
  const box = $("#message");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => { box.hidden = true; }, 6000);
}

/** درخواست به سرور. اگر جواب، وضعیت کامل بود، صفحه دوباره کشیده می‌شود. */
export async function api(method, url, body) {
  const options = { method, headers: { "X-CSRF-Token": CSRF } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showMessage(data.error || "خطایی پیش آمد.");
    const error = new Error(data.error || response.status);
    error.expected = true;   // به کاربر نشان داده شد و در گزارش خطا ثبت نمی‌شود
    throw error;
  }
  if (data.items && data.plan) {
    state = data;
    render();
  }
  return data;
}

export function minutesText(total) {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!hours) return `${fa(minutes)} دقیقه`;
  return minutes ? `${fa(hours)} ساعت و ${fa(minutes)} دقیقه` : `${fa(hours)} ساعت`;
}

export function itemById(id) {
  return state.items.find((item) => item.id === id);
}

export function typeOf(item) {
  return state.types.find((t) => t.id === item.custom_type_id) || null;
}

// ---------------------------------------------------------------------------
// ورودی تاریخ شمسی
// ---------------------------------------------------------------------------

export function buildJalaliInput(holder, iso) {
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
export function readJalaliInput(holder) {
  const [year, month, day] = $$("input, select", holder).map((x) => x.value);
  if (!year && !month && !day) return null;
  const iso = Jalali.fromJalali(Number(year), Number(month), Number(day));
  if (!iso) throw new Error("تاریخ شمسی نامعتبر است.");
  return iso;
}

// render.js کل صفحه را می‌کشد. اینجا فقط صدا زده می‌شود تا این فایل به بقیه وابسته نباشد.
let renderer = () => {};

export function setRenderer(fn) {
  renderer = fn;
}

/** کل صفحه را دوباره می‌کشد؛ هر جابه‌جایی با انیمیشن دیده می‌شود (motion.js). */
export function render() {
  Motion.wrap(renderer);
}

/** بخشی از صفحه را فقط وقتی دوباره می‌کشد که داده‌اش عوض شده باشد.
 *  این کار سریع‌تر است و فوکوس و جای تایپ کاربر را به هم نمی‌زند. */
const lastParts = new Map();

export function renderPart(name, key, draw) {
  const text = JSON.stringify(key);
  if (lastParts.get(name) === text) return;
  lastParts.set(name, text);
  draw();
}
