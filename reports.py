"""آمار و گزارش هفتگی، از روی سابقهٔ کارهای انجام‌شده (task_log)."""

from datetime import date, timedelta

import jalali
import scheduler


def _log_rows(conn, since):
    return conn.execute(
        "SELECT task_log.date, task_log.task_type, task_log.minutes, task_log.result, "
        "sessions.item_id, items.title FROM task_log "
        "JOIN sessions ON sessions.id = task_log.session_id "
        "JOIN items ON items.id = sessions.item_id "
        "WHERE task_log.date >= ? ORDER BY task_log.date",
        (since.isoformat(),),
    ).fetchall()


def stats(conn, items, categories, now, days=371):
    """داده‌های صفحهٔ آمار: کار هر روز، کار هفته‌های اخیر، و پیشرفت هر دسته."""
    per_day = {}
    for row in _log_rows(conn, now - timedelta(days=days)):
        entry = per_day.setdefault(row["date"], {"date": row["date"], "read": 0, "review": 0, "routine": 0})
        entry[row["task_type"]] += row["minutes"]

    # 12 هفتهٔ اخیر، هر هفته از شنبه
    this_week = jalali.week_start(now)
    weeks = []
    for back in range(11, -1, -1):
        start = this_week - timedelta(days=7 * back)
        week = {"start": start, "read": 0, "review": 0, "routine": 0}
        for offset in range(7):
            entry = per_day.get((start + timedelta(days=offset)).isoformat())
            if entry:
                for kind in ("read", "review", "routine"):
                    week[kind] += entry[kind]
        weeks.append(week)

    groups = {c["id"]: {"name": c["name"], "total": 0, "read": 0, "items": 0} for c in categories}
    groups[None] = {"name": "بدون دسته", "total": 0, "read": 0, "items": 0}
    for item in items:
        if item["item_type"] != "study":
            continue
        group = groups.get(item["category_id"], groups[None])
        group["items"] += 1
        for s in item["sessions"]:
            group["total"] += s["minutes"]
            group["read"] += s["minutes"] if s["status"] in ("reviewing", "finished") else (s["minutes_done"] or 0)
    categories_out = [g for g in groups.values() if g["items"]]

    # 12 ماه شمسی اخیر
    months = []
    cursor = now
    for _ in range(12):
        first, last = jalali.month_bounds(cursor)
        month = {"start": first, "read": 0, "review": 0, "routine": 0}
        for entry in per_day.values():
            if first.isoformat() <= entry["date"] <= last.isoformat():
                for kind in ("read", "review", "routine"):
                    month[kind] += entry[kind]
        months.insert(0, month)
        cursor = first - timedelta(days=1)

    totals = {k: sum(d[k] for d in per_day.values()) for k in ("read", "review", "routine")}
    return {"days": list(per_day.values()), "weeks": weeks, "months": months,
            "categories": categories_out, "totals": totals}


# پله‌های نمره: از این نمره به بالا، این عنوان
SCORE_LABELS = [(90, "عالی"), (75, "خیلی خوب"), (60, "خوب"), (40, "قابل قبول"), (0, "نیاز به تلاش بیشتر")]


def score(minutes_done, active_days, planned_minutes, work_days, reviews_done, overdue):
    """نمرهٔ ۰ تا ۱۰۰ برای یک هفته یا ماه. خروجی None یعنی چیزی برای نمره دادن نیست.

    سه بخش دارد:
      منظم بودن (۴۰): در چند روز از روزهای کاری این بازه کار کرده‌اید
      حجم کار (۴۰): چند درصد از کاری که می‌شد انجام داد، انجام شده
      مرور سر وقت (۲۰): چند درصد از مرورها عقب نیفتاده است
    """
    if work_days <= 0:
        return None
    if planned_minutes <= 0 and minutes_done <= 0:
        return None
    regularity = min(1, active_days / work_days)
    volume = 1 if planned_minutes <= 0 else min(1, minutes_done / planned_minutes)
    on_time = 1 if reviews_done + overdue == 0 else reviews_done / (reviews_done + overdue)
    parts = {"regularity": round(40 * regularity), "volume": round(40 * volume), "on_time": round(20 * on_time)}
    total = sum(parts.values())
    return {"total": total, "label": next(text for floor, text in SCORE_LABELS if total >= floor), **parts}


def period_score(state, start, end, totals, active_days, reviews_done, overdue):
    """نمرهٔ یک بازه. روزهای آینده حساب نمی‌شوند و امروز هم فقط اگر کاری در آن ثبت شده باشد."""
    today = state["today"]
    settings = state["settings"]
    overrides = state["day_overrides"]
    done = sum(totals.values())
    days = [start + timedelta(days=i) for i in range((min(end, today) - start).days + 1)]
    if today in days and today.isoformat() not in active_days:
        days.remove(today)
    work_days = [d for d in days if scheduler.day_cap(d, settings, overrides) > 0]
    # سقف روزها سقف کاری است که می‌شد کرد؛ ولی اگر همهٔ کارها تمام شده، کار کمتر عیب نیست
    capacity = sum(scheduler.day_cap(d, settings, overrides) for d in work_days)
    left = sum(d["total"] for d in state["plan"]["days"])
    planned = min(capacity, done + left)
    # روز فعال در تعطیلی هم حساب می‌شود، ولی از تعداد روزهای کاری بیشتر نمی‌شود
    return score(done, len(active_days), planned, len(work_days), reviews_done, overdue)


def period_bounds(period, day):
    """اولین و آخرین روز یک بازه. period: week، month یا all."""
    if period == "week":
        start = jalali.week_start(day)
        return start, start + timedelta(days=6)
    if period == "month":
        return jalali.month_bounds(day)
    return date(2000, 1, 1), day


def summary(conn, state, period, day):
    """خلاصهٔ یک بازه: چه انجام شد و چه چیزی عقب افتاده است."""
    start, end = period_bounds(period, day)
    courses = {}
    totals = {"read": 0, "review": 0, "routine": 0}
    done_count = 0
    active_days = set()
    first_day = None
    reviews_done = 0
    for row in _log_rows(conn, start):
        current = row["date"]
        if current > end.isoformat():
            continue
        first_day = first_day or current
        course = courses.setdefault(row["item_id"], {"title": row["title"], "read": 0, "review": 0, "routine": 0})
        course[row["task_type"]] += row["minutes"]
        totals[row["task_type"]] += row["minutes"]
        done_count += 1
        active_days.add(current)
        if row["task_type"] == "review":
            reviews_done += 1

    # عقب‌افتاده‌ها: مرورهایی که موعدشان گذشته و هنوز انجام نشده‌اند
    titles = {item["id"]: item["title"] for item in state["items"]}
    overdue = {}
    for plan_day in state["plan"]["days"]:
        for task in plan_day["tasks"]:
            if task.get("overdue"):
                overdue[task["item_id"]] = overdue.get(task["item_id"], 0) + 1
    # کار برنامه‌ریزی‌شده برای بازهٔ بعد
    if period == "all":
        next_minutes = sum(d["total"] for d in state["plan"]["days"])
    else:
        next_start, next_end = period_bounds(period, period_bounds(period, state["today"])[1] + timedelta(days=1))
        next_minutes = sum(d["total"] for d in state["plan"]["days"] if next_start <= d["date"] <= next_end)
    # عقب‌افتادگی فعلی فقط روی نمرهٔ بازهٔ جاری اثر دارد، نه هفته‌های گذشته
    current_overdue = sum(overdue.values()) if start <= state["today"] <= end else 0
    return {
        "period": period,
        "score": None if period == "all" else period_score(state, start, end, totals, active_days, reviews_done, current_overdue),
        "start": date.fromisoformat(first_day) if period == "all" and first_day else start,
        "end": end,
        "length": (end - start).days + 1,
        "courses": sorted(courses.values(), key=lambda c: -(c["read"] + c["review"] + c["routine"])),
        "totals": totals,
        "done_count": done_count,
        "active_days": len(active_days),
        "overdue": [{"title": titles.get(i, "؟"), "count": n} for i, n in overdue.items()],
        "next_minutes": next_minutes,
    }
