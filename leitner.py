"""قانون‌های جعبه‌های لایتنر و زمان‌بندی مرور.

همهٔ تابع‌های این فایل «خالص» هستند: فقط ورودی می‌گیرند و خروجی می‌دهند،
و به دیتابیس یا ساعت سیستم دست نمی‌زنند. برای همین راحت تست می‌شوند.

هر «جلسه» (session) یک dict است با کلیدهایی مثل:
    minutes, status, leitner_box, read_at, last_reviewed_on, next_review_on,
    review_minutes_override, read_manual_date, review_manual_date
تاریخ‌ها از نوع datetime.date هستند.

معنی جعبه:
    0          هنوز خوانده نشده
    1 تا n     n = تعداد فاصله‌ها. جعبهٔ k یعنی مرور بعدی، مرور شمارهٔ k است.
"""

import math
from datetime import timedelta
from fractions import Fraction

DEFAULT_INTERVALS = [1, 3, 7, 30]
DEFAULT_RATIO = Fraction(1, 3)


# ---------------------------------------------------------------------------
# خواندن تنظیمات
# ---------------------------------------------------------------------------

def parse_ratio(value):
    """نسبت مرور را به کسر تبدیل می‌کند. ورودی می‌تواند "1/3"، 0.5 یا Fraction باشد."""
    if value is None or value == "":
        return DEFAULT_RATIO
    if isinstance(value, Fraction):
        return value
    # Fraction خودش "1/3" و "0.5" را می‌فهمد.
    # limit_denominator جلوی کسرهای عجیب مثل 0.1 = 3602879701896397/36028797018963968 را می‌گیرد.
    return Fraction(str(value)).limit_denominator(1000)


def intervals_for(item, settings):
    """فاصله‌های لایتنر یک درس: اول فاصلهٔ اختصاصی درس، وگرنه تنظیم کلی."""
    custom = item.get("review_intervals")
    if custom:
        return list(custom)
    return list(settings.get("review_intervals") or DEFAULT_INTERVALS)


def ratio_for(item, settings):
    """نسبت مرور یک درس: اول نسبت اختصاصی درس، وگرنه تنظیم کلی."""
    if item.get("review_ratio") not in (None, ""):
        return parse_ratio(item["review_ratio"])
    return parse_ratio(settings.get("default_review_ratio"))


def review_minutes(session, item, settings):
    """زمان هر مرور این جلسه.

    اگر کاربر برای این جلسه زمان مرور اختصاصی گذاشته باشد، همان استفاده می‌شود.
    وگرنه زمان خواندن ضربدر نسبت مرور، رو به بالا گرد می‌شود (مثلاً 50 × 1/3 = 17).
    """
    override = session.get("review_minutes_override")
    if override is not None:
        return override
    return math.ceil(session["minutes"] * ratio_for(item, settings))


# ---------------------------------------------------------------------------
# تاریخ مرور بعدی
# ---------------------------------------------------------------------------

def next_review_date(session, intervals):
    """تاریخ مرور بعدی یک جلسه که در حال مرور است.

    = آخرین خواندن یا مرور + فاصلهٔ جعبهٔ فعلی.
    چون هر بار از روی فاصله‌ها حساب می‌شود، اگر کاربر فاصله‌ها را عوض کند،
    تاریخ همهٔ مرورها خودبه‌خود با فاصلهٔ جدید حساب می‌شود.
    اگر جعبه از تعداد فاصله‌های جدید بیشتر باشد، آخرین جعبه حساب می‌شود.
    """
    if session.get("review_manual_date"):
        return session["review_manual_date"]
    last = session.get("last_reviewed_on") or session.get("read_at")
    if last is None:
        return None
    box = clamp_box(session.get("leitner_box") or 1, intervals)
    return last + timedelta(days=intervals[box - 1])


def clamp_box(box, intervals):
    """جعبه را بین 1 و تعداد فاصله‌ها نگه می‌دارد."""
    return max(1, min(box, len(intervals)))


# ---------------------------------------------------------------------------
# ثبت کارهای انجام‌شده (هر تابع یک نسخهٔ جدید از جلسه برمی‌گرداند)
# ---------------------------------------------------------------------------

def finish_reading(session, day, intervals):
    """پایان خواندن در روز day: جلسه به جعبهٔ 1 می‌رود."""
    s = dict(session)
    s["minutes_done"] = s["minutes"]
    s["read_at"] = day
    s["last_reviewed_on"] = None
    s["read_manual_date"] = None
    s["review_manual_date"] = None
    if not intervals:
        # بدون فاصلهٔ مرور، جلسه با خواندن تمام می‌شود
        s["leitner_box"] = 0
        s["status"] = "finished"
        s["next_review_on"] = None
        return s
    s["leitner_box"] = 1
    s["status"] = "reviewing"
    s["next_review_on"] = day + timedelta(days=intervals[0])
    return s


def record_review(session, day, intervals):
    """مرور موفق در روز day.

    اگر آخرین جعبه بود، جلسه تمام می‌شود.
    وگرنه به جعبهٔ بعد می‌رود و فاصلهٔ بعدی از همین روز واقعی حساب می‌شود
    (پس مرور دیرهنگام جعبه‌اش را از دست نمی‌دهد).
    """
    s = dict(session)
    box = clamp_box(s.get("leitner_box") or 1, intervals)
    s["last_reviewed_on"] = day
    s["review_manual_date"] = None
    if box >= len(intervals):
        s["leitner_box"] = box
        s["status"] = "finished"
        s["next_review_on"] = None
        return s
    s["leitner_box"] = box + 1
    s["status"] = "reviewing"
    s["next_review_on"] = day + timedelta(days=intervals[box])
    return s


def needs_more_review(session, day, intervals):
    """«نیاز به مرور بیشتر»: جلسه به جعبهٔ 1 برمی‌گردد و مرور بعدی فردا (فاصلهٔ اول) است."""
    s = dict(session)
    s["leitner_box"] = 1
    s["status"] = "reviewing"
    s["last_reviewed_on"] = day
    s["review_manual_date"] = None
    s["next_review_on"] = day + timedelta(days=intervals[0])
    return s


def reset_session(session):
    """برگرداندن جلسه به حالت خوانده‌نشده. زمان و بخش جلسه می‌ماند."""
    s = dict(session)
    s.update(
        status="unread",
        leitner_box=0,
        minutes_done=0,
        read_at=None,
        last_reviewed_on=None,
        next_review_on=None,
        read_manual_date=None,
        review_manual_date=None,
    )
    return s
