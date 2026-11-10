/* بستن پنجره‌ها با کلیک بیرون، Esc یا دکمهٔ بستن.
   اگر پنجره فرم دارد و چیزی عوض شده، اول می‌پرسد: ذخیره، ذخیره نشود یا ادامهٔ ویرایش. */

import { $, $$ } from "./core.js";

/** مقدار همهٔ ورودی‌های یک پنجره، به‌جز بخش‌هایی که خودشان فوراً ذخیره می‌شوند ([data-untracked]) */
export function formSnapshot(root, extra = () => null) {
  const values = $$("input, select, textarea", root)
    .filter((input) => !input.closest("[data-untracked]") && input.type !== "file")
    .map((input) => (input.type === "checkbox" || input.type === "radio" ? input.checked : input.value));
  return JSON.stringify([values, extra()]);
}

/** آیا این رویداد بیرون کادر پنجره (روی پس‌زمینهٔ تیره) بوده است؟ */
function onBackdrop(dialog, e) {
  if (e.target !== dialog) return false;
  const box = dialog.getBoundingClientRect();
  return e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
}

let pending = null;

/**
 * پنجره را بستنی می‌کند.
 * snapshot: تابعی که وضعیت فرم را برمی‌گرداند؛ اگر نباشد، پنجره بی‌پرسش بسته می‌شود.
 * save: کاری که با «ذخیره» انجام می‌شود (معمولاً ارسال فرم که خودش پنجره را می‌بندد).
 * closeButton: دکمهٔ بستن پنجره که همین مسیر را می‌رود.
 */
export function closeOnOutside(dialog, { snapshot = null, save = null, closeButton = null } = {}) {
  let baseline = "";
  const guard = {
    /** وضعیت فعلی، حالت «بدون تغییر» حساب می‌شود */
    markClean() { baseline = snapshot ? snapshot() : ""; },
    changed() { return Boolean(snapshot) && snapshot() !== baseline; },
    tryClose() {
      if (!guard.changed()) {
        dialog.close();
        return;
      }
      pending = { dialog, save };
      $("#close-confirm").showModal();
    },
  };

  // وضعیت اولیه درست بعد از باز شدن گرفته می‌شود، وقتی فرم پر شده است
  new MutationObserver(() => { if (dialog.open) guard.markClean(); })
    .observe(dialog, { attributes: true, attributeFilter: ["open"] });

  // کشیدن (مثلاً نقطهٔ نمودار) که بیرون پنجره رها شود، کلیک بیرون حساب نمی‌شود
  let pressedOutside = false;
  dialog.addEventListener("pointerdown", (e) => { pressedOutside = onBackdrop(dialog, e); });
  dialog.addEventListener("click", (e) => {
    if (pressedOutside && onBackdrop(dialog, e)) guard.tryClose();
    pressedOutside = false;
  });
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    guard.tryClose();
  });
  if (closeButton) closeButton.addEventListener("click", guard.tryClose);
  return guard;
}

$("#close-confirm-save").addEventListener("click", () => {
  $("#close-confirm").close();
  if (pending && pending.save) pending.save();
  pending = null;
});

$("#close-confirm-discard").addEventListener("click", () => {
  $("#close-confirm").close();
  if (pending) pending.dialog.close();
  pending = null;
});

$("#close-confirm-continue").addEventListener("click", () => {
  $("#close-confirm").close();
  pending = null;
});
