"""آمار و گزارش هفتگی، از روی سابقهٔ کارهای انجام‌شده (task_log)."""

from datetime import timedelta

import jalali


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

    totals = {k: sum(d[k] for d in per_day.values()) for k in ("read", "review", "routine")}
    return {"days": list(per_day.values()), "weeks": weeks, "categories": categories_out, "totals": totals}


def weekly(conn, state, week_day):
    """گزارش یک هفته (شنبه تا جمعه): چه انجام شد و چه چیزی عقب افتاده است."""
    start = jalali.week_start(week_day)
    end = start + timedelta(days=6)
    courses = {}
    totals = {"read": 0, "review": 0, "routine": 0}
    done_count = 0
    active_days = set()
    for row in _log_rows(conn, start):
        day = row["date"]
        if day > end.isoformat():
            continue
        course = courses.setdefault(row["item_id"], {"title": row["title"], "read": 0, "review": 0, "routine": 0})
        course[row["task_type"]] += row["minutes"]
        totals[row["task_type"]] += row["minutes"]
        done_count += 1
        active_days.add(day)

    # عقب‌افتاده‌ها: مرورهایی که موعدشان گذشته و هنوز انجام نشده‌اند
    titles = {item["id"]: item["title"] for item in state["items"]}
    overdue = {}
    for plan_day in state["plan"]["days"]:
        for task in plan_day["tasks"]:
            if task.get("overdue"):
                overdue[task["item_id"]] = overdue.get(task["item_id"], 0) + 1
    next_start = jalali.week_start(state["today"]) + timedelta(days=7)
    next_minutes = sum(d["total"] for d in state["plan"]["days"] if next_start <= d["date"] < next_start + timedelta(days=7))
    return {
        "start": start,
        "end": end,
        "courses": sorted(courses.values(), key=lambda c: -(c["read"] + c["review"] + c["routine"])),
        "totals": totals,
        "done_count": done_count,
        "active_days": len(active_days),
        "overdue": [{"title": titles.get(i, "؟"), "count": n} for i, n in overdue.items()],
        "next_week_minutes": next_minutes,
    }
