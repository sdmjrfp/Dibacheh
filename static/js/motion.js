/* انیمیشن‌ها و کشیدن (drag) با حرکت نرم.

   ۱) Motion.wrap(fn): هر بار که صفحه دوباره کشیده می‌شود، جای قبلی هر عنصرِ دارای
      data-flip نگه داشته می‌شود و بعد از کشیدن دوباره، عنصر از جای قبلی به جای تازه
      «سُر» می‌خورد. این روش FLIP نام دارد. پس هر جابه‌جایی، حتی کاری که موتور چینش
      از یک روز تقویم به روز دیگر برده، با انیمیشن دیده می‌شود.

   ۲) sortable(...): مرتب کردن یک فهرست با کشیدن. خودِ کارت همراه ماوس حرکت می‌کند
      و بقیهٔ کارت‌ها نرم کنار می‌روند تا جایش باز شود.

   هر دو از Web Animations API خود مرورگر استفاده می‌کنند؛ کتابخانهٔ جدا لازم نیست.
*/

export const Motion = (() => {
  const DURATION = 380;
  const EASE = "cubic-bezier(.2, .8, .2, 1)";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // جای شروع دلخواه برای یک کلید (مثلاً جای رها کردن کار کشیده‌شده)
  const overrides = new Map();

  function snapshot() {
    const rects = new Map();
    for (const node of document.querySelectorAll("[data-flip]")) {
      const r = node.getBoundingClientRect();
      if (r.width || r.height) rects.set(node.dataset.flip, r);
    }
    for (const [key, rect] of overrides) rects.set(key, rect);
    overrides.clear();
    return rects;
  }

  function play(before) {
    if (reduced) return;
    const seen = new Set();
    for (const node of document.querySelectorAll("[data-flip]")) {
      const key = node.dataset.flip;
      if (seen.has(key)) continue;  // کلید تکراری: فقط اولی
      seen.add(key);
      const now = node.getBoundingClientRect();
      if (!now.width && !now.height) continue;
      const old = before.get(key);
      if (!old) {
        // عنصر تازه: آرام ظاهر می‌شود
        if (before.size) node.animate([{ opacity: 0, transform: "scale(.96)" }, { opacity: 1, transform: "none" }],
          { duration: 260, easing: EASE });
        continue;
      }
      const dx = old.left - now.left;
      const dy = old.top - now.top;
      const sx = now.width ? old.width / now.width : 1;
      const sy = now.height ? old.height / now.height : 1;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.02 && Math.abs(sy - 1) < 0.02) continue;
      node.animate([
        { transformOrigin: "top left", transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
        { transformOrigin: "top left", transform: "none" },
      ], { duration: DURATION, easing: EASE });
    }
  }

  /** fn را اجرا می‌کند و هر جابه‌جایی را با انیمیشن نشان می‌دهد. */
  function wrap(fn) {
    const before = snapshot();
    fn();
    play(before);
  }

  return { wrap, overrides, DURATION, EASE, reduced };
})();

/**
 * مرتب کردن با کشیدن، با حرکت نرم.
 *
 *   list        عنصر فهرست
 *   options.items      selector کارت‌ها (مثلاً ".item")
 *   options.handle     selector جای گرفتن (مثلاً ".handle")؛ خالی = کل کارت
 *   options.axis       "y" برای فهرست عمودی، "x" برای تب‌های افقی (راست‌به‌چپ)
 *   options.onDrop(ids, movedId)  ترتیب تازهٔ data-id ها بعد از رها کردن، و شمارهٔ کارتی که کشیده شد
 */
export function sortable(list, options) {
  const axis = options.axis || "y";
  let drag = null;

  list.addEventListener("pointerdown", (e) => {
    const handle = options.handle ? e.target.closest(options.handle) : e.target.closest(options.items);
    if (!handle || !list.contains(handle) || e.button !== 0) return;
    if (e.target.closest("button, input, select, a")) return;  // کلیک روی دکمه‌ها کار خودش را بکند
    const card = handle.closest(options.items);
    if (!card || card.dataset.fixed !== undefined) return;
    e.preventDefault();
    const rect = card.getBoundingClientRect();
    drag = {
      card, pointerId: e.pointerId, moved: false,
      grabX: e.clientX - rect.left, grabY: e.clientY - rect.top,
      startX: e.clientX, startY: e.clientY,
      startOrder: [...list.querySelectorAll(options.items)].map((n) => n.dataset.id),
    };
    try { handle.setPointerCapture(e.pointerId); } catch (error) { /* رویداد ساختگی */ }
  });

  list.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (!drag.moved) {
      if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 4) return;
      drag.moved = true;
      drag.card.classList.add("lifted");
      document.body.classList.add("dragging-something");
    }
    // آیا باید جای کارت در فهرست عوض شود؟
    const siblings = [...list.querySelectorAll(options.items)].filter((n) => n !== drag.card && n.dataset.fixed === undefined);
    let index = 0;
    for (const s of siblings) {
      const r = s.getBoundingClientRect();
      const before = axis === "y" ? (r.top + r.height / 2 < e.clientY) : (r.left + r.width / 2 > e.clientX);  // افقی: راست‌به‌چپ
      if (before) index += 1;
    }
    const current = siblings.indexOf(drag.card.nextElementSibling);
    const currentIndex = current === -1 ? siblings.length : current;
    if (index !== currentIndex) {
      // FLIP برای بقیهٔ کارت‌ها: جای قبلی، جابه‌جایی در DOM، بعد سُر خوردن به جای تازه
      const first = new Map(siblings.map((s) => [s, s.getBoundingClientRect()]));
      const anchor = siblings[index] || null;
      list.insertBefore(drag.card, anchor ? anchor : (siblings.length ? siblings[siblings.length - 1].nextSibling : null));
      for (const s of siblings) {
        const a = first.get(s);
        const b = s.getBoundingClientRect();
        if (a.left !== b.left || a.top !== b.top) {
          s.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px)` }, { transform: "none" }],
            { duration: 220, easing: Motion.EASE });
        }
      }
    }
    // کارت همیشه درست زیر ماوس بماند
    drag.card.style.transform = "none";
    const home = drag.card.getBoundingClientRect();
    const dx = axis === "x" ? e.clientX - drag.grabX - home.left : 0;
    const dy = e.clientY - drag.grabY - home.top;
    drag.card.style.transform = `translate(${dx}px, ${dy}px) scale(1.02)`;
  });

  const finish = (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    const { card, moved, startOrder } = drag;
    drag = null;
    document.body.classList.remove("dragging-something");
    if (!moved) return;
    // کارت نرم در جای تازه‌اش می‌نشیند
    const from = card.style.transform;
    card.style.transform = "";
    card.classList.remove("lifted");
    card.animate([{ transform: from, boxShadow: "0 12px 30px rgba(0,0,0,.18)" }, { transform: "none" }],
      { duration: 260, easing: Motion.EASE });
    const order = [...list.querySelectorAll(options.items)].map((n) => n.dataset.id);
    if (order.join() !== startOrder.join()) options.onDrop(order, card.dataset.id);
  };
  list.addEventListener("pointerup", finish);
  list.addEventListener("pointercancel", finish);
}

/**
 * کشیدن یک عنصر با «سایه»ای که همراه ماوس حرکت می‌کند (برای کارهای تقویم).
 * onDrop(targetElement, ghostRect) وقتی رها شد. اگر false برگرداند، سایه به جای اول برمی‌گردد.
 */
export function dragGhost(source, e, { targetSelector, canDrop, onDrop, onClick }) {
  const start = { x: e.clientX, y: e.clientY };
  const rect = source.getBoundingClientRect();
  let ghost = null;
  let target = null;
  try { source.setPointerCapture(e.pointerId); } catch (error) { /* رویداد ساختگی */ }

  const move = (ev) => {
    if (!ghost) {
      if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < 6) return;
      ghost = source.cloneNode(true);
      ghost.classList.add("ghost");
      Object.assign(ghost.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px` });
      document.body.append(ghost);
      source.classList.add("drag-source");
      document.body.classList.add("dragging-something");
    }
    ghost.style.transform = `translate(${ev.clientX - start.x}px, ${ev.clientY - start.y}px) rotate(-1.5deg) scale(1.04)`;
    ghost.style.visibility = "hidden";  // تا elementFromPoint زیرش را ببیند
    const under = document.elementFromPoint(ev.clientX, ev.clientY);
    ghost.style.visibility = "";
    const next = under && under.closest(targetSelector);
    if (next !== target) {
      if (target) target.classList.remove("drop-target");
      target = next && canDrop(next) ? next : null;
      if (target) target.classList.add("drop-target");
    }
  };

  const up = async () => {
    source.removeEventListener("pointermove", move);
    source.removeEventListener("pointerup", up);
    source.removeEventListener("pointercancel", up);
    document.body.classList.remove("dragging-something");
    if (target) target.classList.remove("drop-target");
    if (!ghost) {
      onClick();
      return;
    }
    const ghostRect = ghost.getBoundingClientRect();
    const accepted = target ? await onDrop(target, ghostRect) : false;
    if (accepted) {
      ghost.remove();
    } else {
      // برگشت نرم به جای اول
      const back = ghost.animate([{ transform: ghost.style.transform }, { transform: "none" }],
        { duration: 260, easing: Motion.EASE });
      back.onfinish = () => ghost.remove();
    }
    source.classList.remove("drag-source");
  };

  source.addEventListener("pointermove", move);
  source.addEventListener("pointerup", up);
  source.addEventListener("pointercancel", up);
}
