/* تبدیل و نمایش تاریخ، با تقویم شمسی یا میلادی.

   از تقویم شمسی داخلی خود مرورگر (Intl با calendar=persian) استفاده می‌شود.
   این بخشی از خود مرورگر است، پس آفلاین کار می‌کند و کتابخانهٔ جدا لازم ندارد.

   تاریخ‌ها همه‌جا به شکل متن "2026-11-05" (میلادی، مثل سرور) جابه‌جا می‌شوند.
   این فایل فقط برای نمایش و ورود تاریخ، آنها را به شمسی تبدیل می‌کند.
*/
(function () {
  // تقویم و زبان نمایش. نام Jalali مانده، ولی همهٔ تابع‌ها با تقویم انتخاب‌شده کار می‌کنند.
  let calendar = "persian";   // persian یا gregorian
  let locale = "fa";
  let longFormat, shortFormat, weekdayFormat;

  const partsFormat = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
    year: "numeric", month: "numeric", day: "numeric", timeZone: "UTC",
  });
  const PERSIAN_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const api = { MONTHS: PERSIAN_MONTHS };

  /** بعد از انتخاب زبان و تقویم صدا زده می‌شود. */
  function configure(options) {
    calendar = options.calendar === "gregorian" ? "gregorian" : "persian";
    locale = options.locale || "fa";
    const tag = `${locale === "fa" ? "fa-IR" : locale}-u-ca-${calendar === "persian" ? "persian" : "gregory"}`;
    longFormat = new Intl.DateTimeFormat(tag, { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
    shortFormat = new Intl.DateTimeFormat(tag, { month: "long", day: "numeric", timeZone: "UTC" });
    weekdayFormat = new Intl.DateTimeFormat(locale === "fa" ? "fa-IR" : locale, { weekday: "long", timeZone: "UTC" });
    if (calendar === "persian" && locale === "fa") {
      api.MONTHS = PERSIAN_MONTHS;
    } else {
      const names = new Intl.DateTimeFormat(tag, { month: "long", timeZone: "UTC" });
      api.MONTHS = Array.from({ length: 12 }, (_, i) => names.format(isoToUTC(fromJalali(calendar === "persian" ? 1405 : 2026, i + 1, 1))));
    }
    api.YEARS = calendar === "persian" ? [1300, 1500] : [1921, 2122];
  }

  function isoToUTC(iso) {
    return new Date(iso + "T00:00:00Z");
  }

  function utcToIso(date) {
    return date.toISOString().slice(0, 10);
  }

  /** "2026-11-05" → {y: 1405, m: 8, d: 14}. در تقویم میلادی: {y: 2026, m: 11, d: 5} */
  function toJalali(iso) {
    if (calendar === "gregorian") {
      const [y, m, d] = iso.split("-").map(Number);
      return { y, m, d };
    }
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
    if (calendar === "gregorian") {
      const date = new Date(Date.UTC(y, m - 1, d));
      return date.getUTCMonth() === m - 1 && date.getUTCDate() === d ? utcToIso(date) : null;
    }
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
    if (calendar === "gregorian") return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    const iso = fromJalali(y, 12, 30);
    return iso !== null && compare(toJalali(iso), { y, m: 12, d: 30 }) === 0;
  }

  function monthLength(y, m) {
    if (calendar === "gregorian") return new Date(Date.UTC(y, m, 0)).getUTCDate();
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

  /** نام روز هفته از روی شمارهٔ پایتون (0 = دوشنبه) */
  function weekdayName(number) {
    return weekdayFormat.format(isoToUTC(addDays("2024-01-01", number)));   // 2024-01-01 دوشنبه است
  }

  function addDays(iso, days) {
    return utcToIso(new Date(isoToUTC(iso).getTime() + days * 86400000));
  }

  /** عدد با رقم زبان فعلی: فقط فارسی رقم جدا دارد */
  function faNumber(n) {
    return locale === "fa" ? Number(n).toLocaleString("fa-IR", { useGrouping: false }) : String(n);
  }

  Object.assign(api, {
    configure, toJalali, fromJalali, isLeap, monthLength, format, formatShort, weekday, weekdayName, addDays, faNumber,
  });
  configure({ calendar: "persian", locale: "fa" });
  globalThis.Jalali = api;
})();
