/* تبدیل تاریخ میلادی و شمسی.

   از تقویم شمسی داخلی خود مرورگر (Intl با calendar=persian) استفاده می‌شود.
   این بخشی از خود مرورگر است، پس آفلاین کار می‌کند و کتابخانهٔ جدا لازم ندارد.

   تاریخ‌ها همه‌جا به شکل متن "2026-11-05" (میلادی، مثل سرور) جابه‌جا می‌شوند.
   این فایل فقط برای نمایش و ورود تاریخ، آنها را به شمسی تبدیل می‌کند.
*/
(function () {
  const partsFormat = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
    year: "numeric", month: "numeric", day: "numeric", timeZone: "UTC",
  });
  const longFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
  const shortFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    month: "long", day: "numeric", timeZone: "UTC",
  });
  const weekdayFormat = new Intl.DateTimeFormat("fa-IR", { weekday: "long", timeZone: "UTC" });

  const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];

  function isoToUTC(iso) {
    return new Date(iso + "T00:00:00Z");
  }

  function utcToIso(date) {
    return date.toISOString().slice(0, 10);
  }

  /** "2026-11-05" → {y: 1405, m: 8, d: 14} */
  function toJalali(iso) {
    const result = {};
    for (const part of partsFormat.formatToParts(isoToUTC(iso))) {
      if (part.type === "year") result.y = parseInt(part.value, 10);
      if (part.type === "month") result.m = parseInt(part.value, 10);
      if (part.type === "day") result.d = parseInt(part.value, 10);
    }
    return result;
  }

  function compare(a, b) {
    return (a.y - b.y) || (a.m - b.m) || (a.d - b.d);
  }

  /** {1405, 8, 14} → "2026-11-05". برای تاریخ نامعتبر null برمی‌گرداند. */
  function fromJalali(y, m, d) {
    // تخمین اولیه: اول فروردین حدود 21 مارس است. بعد روزبه‌روز اصلاح می‌شود.
    const dayOfYear = (m <= 6 ? (m - 1) * 31 : 186 + (m - 7) * 30) + (d - 1);
    let guess = new Date(Date.UTC(y + 621, 2, 21 + dayOfYear));
    const target = { y, m, d };
    for (let i = 0; i < 10; i++) {
      const diff = compare(toJalali(utcToIso(guess)), target);
      if (diff === 0) return utcToIso(guess);
      guess = new Date(guess.getTime() + (diff < 0 ? 1 : -1) * 86400000);
    }
    return null;
  }

  function isLeap(y) {
    const iso = fromJalali(y, 12, 30);
    return iso !== null && compare(toJalali(iso), { y, m: 12, d: 30 }) === 0;
  }

  function monthLength(y, m) {
    if (m <= 6) return 31;
    if (m <= 11) return 30;
    return isLeap(y) ? 30 : 29;
  }

  /** "۱۴ آبان ۱۴۰۵" */
  function format(iso) {
    return iso ? longFormat.format(isoToUTC(iso)) : "";
  }

  /** "۱۴ آبان" */
  function formatShort(iso) {
    return iso ? shortFormat.format(isoToUTC(iso)) : "";
  }

  function weekday(iso) {
    return weekdayFormat.format(isoToUTC(iso));
  }

  function addDays(iso, days) {
    return utcToIso(new Date(isoToUTC(iso).getTime() + days * 86400000));
  }

  /** عدد با رقم فارسی */
  function faNumber(n) {
    return Number(n).toLocaleString("fa-IR", { useGrouping: false });
  }

  globalThis.Jalali = {
    MONTHS, toJalali, fromJalali, isLeap, monthLength, format, formatShort, weekday,
    addDays, faNumber,
  };
})();
