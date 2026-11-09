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

// زبان و تقویم را سرور روی <html> گذاشته است. با عوض شدنشان صفحه دوباره بار می‌شود.
const root = document.documentElement;

export const LANGUAGE = root.lang || "fa";

export const isRTL = root.dir === "rtl";

// اولین روز هفته، با شمارهٔ پایتون (0 = دوشنبه، 5 = شنبه)
export const FIRST_WEEKDAY = Number(root.dataset.firstWeekday || 5);

Jalali.configure({ calendar: root.dataset.calendar, locale: LANGUAGE });

const translations = new Map();

if (LANGUAGE !== "fa") {
  try {
    const read = async (name) => (await (await fetch(`/static/i18n/${name}.txt`)).text()).split("\n");
    const [keys, values] = await Promise.all([read("keys"), read(LANGUAGE)]);
    keys.forEach((key, i) => {
      if (values[i]) translations.set(key.replaceAll("\\n", "\n"), values[i].replaceAll("\\n", "\n"));
    });
  } catch (error) { /* بدون ترجمه: متن فارسی نشان داده می‌شود */ }
}

/** متن به زبان فعلی. متن اصلی فارسی است: t("{0} روز", n) */
export function t(text, ...args) {
  const template = translations.get(text) ?? text;
  return template.replace(/\{(\d+)\}/g, (whole, index) => (args[index] === undefined ? whole : args[index]));
}

/** متن‌های ثابت صفحه (templates/index.html) */
function translatePage() {
  if (LANGUAGE === "fa") return;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent.replace(/\s+/g, " ").trim();
    if (text && translations.has(text)) node.textContent = ` ${translations.get(text)} `;
  }
  for (const element of document.querySelectorAll("[title], [placeholder], [aria-label]")) {
    for (const name of ["title", "placeholder", "aria-label"]) {
      const value = element.getAttribute(name);
      if (value && translations.has(value)) element.setAttribute(name, translations.get(value));
    }
  }
  document.title = t(document.title);
}

translatePage();

export const fa = Jalali.faNumber;

export let state = null;

// روزهای هفته به ترتیب نمایش، با شمارهٔ روز در پایتون (0 = دوشنبه)
export const WEEKDAYS = Array.from({ length: 7 }, (_, i) => {
  const number = (FIRST_WEEKDAY + i) % 7;
  return [number, Jalali.weekdayName(number)];
});

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

/** انتخاب‌های کوچک کاربر در همین مرورگر. اگر حافظهٔ مرورگر بسته باشد، مقدار پیش‌فرض می‌ماند. */
export function getPref(name, fallback) {
  try {
    const value = localStorage.getItem(`dibacheh.${name}`);
    return value === null ? fallback : JSON.parse(value);
  } catch (error) {
    return fallback;
  }
}

export function setPref(name, value) {
  try { localStorage.setItem(`dibacheh.${name}`, JSON.stringify(value)); } catch (error) { /* حالت خصوصی */ }
}

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
    showMessage(data.error || t("خطایی پیش آمد."));
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
  if (!hours) return t("{0} دقیقه", fa(minutes));
  return minutes ? t("{0} ساعت و {1} دقیقه", fa(hours), fa(minutes)) : t("{0} ساعت", fa(hours));
}

export function itemById(id) {
  return state.items.find((item) => item.id === id);
}

export function typeOf(item) {
  return state.types.find((type) => type.id === item.custom_type_id) || null;
}

// ---------------------------------------------------------------------------
// ورودی تاریخ
// ---------------------------------------------------------------------------

export function buildJalaliInput(holder, iso) {
  const parts = iso ? Jalali.toJalali(iso) : null;
  const year = el("input", { type: "number", min: Jalali.YEARS[0], max: Jalali.YEARS[1], value: parts ? parts.y : "", placeholder: t("سال") });
  const month = el("select", {}, el("option", { value: "" }, t("ماه")),
    ...Jalali.MONTHS.map((name, i) => el("option", { value: i + 1, selected: parts && parts.m === i + 1 }, name)));
  const day = el("select", {}, el("option", { value: "" }, t("روز")),
    ...Array.from({ length: 31 }, (_, i) =>
      el("option", { value: i + 1, selected: parts && parts.d === i + 1 }, fa(i + 1))));
  const clear = el("button", { type: "button", class: "icon", title: t("پاک کردن"),
    onclick: () => { year.value = ""; month.value = ""; day.value = ""; } }, "×");
  holder.replaceChildren(year, month, day, clear);
}

/** مقدار ورودی تاریخ به شکل "2026-11-05"، یا null. */
export function readJalaliInput(holder) {
  const [year, month, day] = $$("input, select", holder).map((x) => x.value);
  if (!year && !month && !day) return null;
  const iso = Jalali.fromJalali(Number(year), Number(month), Number(day));
  if (!iso) throw new Error(t("تاریخ نامعتبر است."));
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
