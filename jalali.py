"""تبدیل تاریخ میلادی به شمسی در پایتون (برای خروجی HTML).

صفحهٔ اصلی برنامه از تقویم شمسی خود مرورگر استفاده می‌کند (static/jalali.js).
خروجی HTML در پایتون ساخته می‌شود، پس اینجا همان تبدیل با الگوریتم شناخته‌شدهٔ
jalaali (بر اساس جدول «سال‌های شکست» تقویم) نوشته شده است.
تست tests/test_jalali.py بررسی می‌کند که این دو برای همهٔ روزهای چند سال یکی باشند.
"""

from datetime import date, timedelta

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
           1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _div(a, b):
    return int(a / b)  # تقسیم با گرد کردن به سمت صفر، مثل الگوریتم اصلی


def _mod(a, b):
    return a - _div(a, b) * b


def _jal_cal(jy):
    """روز اول فروردین سال jy در ماه مارس، و وضعیت کبیسه."""
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return gy, march, leap


def to_jalali(day):
    """date(2026, 11, 5) → (1405, 8, 14)"""
    jy = day.year - 621
    gy, march, leap = _jal_cal(jy)
    k = (day - date(gy, 3, march)).days
    if k >= 0:
        if k <= 185:
            return jy, 1 + k // 31, k % 31 + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + k // 30, k % 30 + 1


def fa(value):
    """عدد یا متن با رقم فارسی"""
    return str(value).translate(_FA_DIGITS)


def format_date(day, weekday=False):
    """«پنجشنبه ۱۴ آبان ۱۴۰۵»"""
    y, m, d = to_jalali(day)
    text = f"{fa(d)} {MONTHS[m - 1]} {fa(y)}"
    return f"{WEEKDAYS[day.weekday()]} {text}" if weekday else text


def iso_name(day):
    """«1405-08-14» برای نام فایل"""
    y, m, d = to_jalali(day)
    return f"{y}-{m:02d}-{d:02d}"


def month_bounds(day):
    """اولین و آخرین روز (میلادی) ماه شمسی‌ای که day در آن است."""
    y, m, d = to_jalali(day)
    first = day - timedelta(days=d - 1)
    last = first
    while to_jalali(last + timedelta(days=1))[1] == m:
        last += timedelta(days=1)
    return first, last


def week_start(day):
    """شنبهٔ هفتهٔ day"""
    return day - timedelta(days=(day.weekday() - 5) % 7)
