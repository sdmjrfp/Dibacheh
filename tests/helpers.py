"""ابزارهای کوچک برای ساختن دادهٔ تست موتور چینش.

برای خوانایی، شناسهٔ جلسه‌ها متنی است: "A1" یعنی جلسهٔ 1 از درس A.
"""

from datetime import date, timedelta

# روز 1 سناریوها. (3 ژانویهٔ 2026 شنبه است.)
DAY1 = date(2026, 1, 3)


def d(n):
    """تاریخ روز n ام سناریو. d(1) همان DAY1 است."""
    return DAY1 + timedelta(days=n - 1)


def item(item_id, queue, **extra):
    data = {
        "id": item_id,
        "title": f"درس {item_id}",
        "item_type": "study",
        "queue_position": queue,
        "is_active": True,
        "max_new_sessions_per_day": 1,
        "review_ratio": None,
        "review_intervals": None,
    }
    data.update(extra)
    return data


def sessions(item_id, count, minutes, **extra):
    """count جلسهٔ خوانده‌نشده با شناسه‌های A1، A2، ..."""
    result = []
    for i in range(1, count + 1):
        s = {
            "id": f"{item_id}{i}",
            "item_id": item_id,
            "sequence": i,
            "minutes": minutes,
            "minutes_done": 0,
            "status": "unread",
            "leitner_box": 0,
            "read_at": None,
            "last_reviewed_on": None,
            "next_review_on": None,
            "review_minutes_override": None,
            "read_manual_date": None,
            "review_manual_date": None,
        }
        s.update(extra)
        result.append(s)
    return result


def settings(**extra):
    data = {
        "default_cap_minutes": 120,
        "cap_tolerance_minutes": 30,
        "default_review_ratio": "1/3",
        "review_intervals": [1, 3, 7, 30],
    }
    data.update(extra)
    return data


def table(plan, start=DAY1):
    """برنامه را به شکل جدول ساده برمی‌گرداند:
    {شمارهٔ روز: ["خواندن A1", "مرور B1", ...]}
    """
    names = {"read": "خواندن", "review": "مرور", "routine": "روتین"}
    result = {}
    for day in plan["days"]:
        n = (day["date"] - start).days + 1
        result[n] = [f'{names[t["kind"]]} {t["session_id"]}' for t in day["tasks"]]
    return result


def totals(plan, start=DAY1):
    return {(day["date"] - start).days + 1: day["total"] for day in plan["days"]}


def day_of(plan, session_id, kind, start=DAY1):
    """همهٔ روزهایی که یک کار از یک جلسه در آنها آمده است."""
    return [
        (day["date"] - start).days + 1
        for day in plan["days"]
        for t in day["tasks"]
        if t["session_id"] == session_id and t["kind"] == kind
    ]


def all_tasks(plan):
    """همهٔ کارهای برنامه، بدون توجه به روز (برای بررسی «هیچ کاری گم نشد»)."""
    return sorted(
        (t["kind"], t["session_id"], t.get("review_round", 0))
        for day in plan["days"]
        for t in day["tasks"]
    )
