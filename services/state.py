"""ساختن وضعیت کامل برنامه برای صفحه و خروجی."""

from datetime import timedelta

import database
import i18n
import leitner
import platform_tools
import scheduler
import sources
from i18n import _

# برنامه چند روز جلوتر همراه هر جواب به صفحه فرستاده می‌شود. روزهای دورتر با
# درخواست جدا (/api/plan/range) گرفته می‌شوند.
PAGE_PLAN_DAYS = 70


def item_status(sessions):
    """لیستی که درس در آن قرار می‌گیرد."""
    if not sessions:
        return "unread"
    statuses = {s["status"] for s in sessions}
    started = any(s["status"] != "unread" or (s["minutes_done"] or 0) > 0 for s in sessions)
    if not started:
        return "unread"
    if statuses & {"unread", "reading"}:
        return "reading"
    if "reviewing" in statuses:
        return "read"
    return "finished"


def item_progress(item, sessions, settings):
    """درصد خواندن و تعداد مرورهای انجام‌شده."""
    intervals = leitner.intervals_for(item, settings)
    total_minutes = sum(s["minutes"] for s in sessions) or 1
    read_minutes = sum(
        s["minutes"] if s["status"] in ("reviewing", "finished") else (s["minutes_done"] or 0)
        for s in sessions
    )
    reviews_done = 0
    for s in sessions:
        if s["status"] == "finished":
            reviews_done += len(intervals)
        elif s["status"] == "reviewing":
            reviews_done += max(0, (s["leitner_box"] or 1) - 1)
    return {
        "read_percent": round(100 * read_minutes / total_minutes),
        "reviews_done": reviews_done,
        "reviews_total": len(intervals) * len(sessions) if item["item_type"] == "study" else 0,
    }


def state_data(conn, now, extras):
    """وضعیت کامل با تاریخ‌های پایتونی. extras: چیزهایی که از لایهٔ وب می‌آید (undo و ...)."""
    inputs = database.load_plan_inputs(conn)
    settings = inputs["settings"]
    plan = scheduler.build_plan(
        inputs["items"], inputs["sessions"], settings, inputs["day_overrides"], now,
        done_today=done_today(conn, now),
    )
    mark_first_reviews(plan)
    sessions_by_item = {}
    for s in inputs["sessions"]:
        sessions_by_item.setdefault(s["item_id"], []).append(s)

    items = []
    for item in inputs["items"]:
        sess = sessions_by_item.get(item["id"], [])
        for s in sess:
            s["section_text"] = sources.section_text(item, s)
        finish = plan["items"].get(item["id"], {"read_end": None, "review_end": None})
        items.append({
            **item,
            "sessions": sess,
            "status_list": item_status(sess),
            "progress": item_progress(item, sess, settings),
            "finish": finish if item["is_active"] else {"read_end": None, "review_end": None},
            "source_problem": sources.check_source(item, settings["vault_path"]),
            "range_problems": sources.check_ranges(item, sess),
            # چند جلسه از این درس دستی به روز خاصی برده شده‌اند (📌)
            # رنگ منبع: انتخاب کاربر، وگرنه یک رنگ ثابت از فهرست رنگ‌ها
            "display_color": item.get("color") or database.SOURCE_PALETTE[item["id"] % len(database.SOURCE_PALETTE)],
            "waiting_for": waiting_for(item, inputs["items"], sessions_by_item),
            "pinned": sum(1 for x in sess if x.get("read_manual_date") or x.get("review_manual_date")),
        })
        items[-1]["target"] = target_status(items[-1])
    return {
        "today": now,
        "items": items,
        "categories": database.list_categories(conn),
        "types": database.list_types(conn),
        "templates": templates(settings),
        "palette": database.SOURCE_PALETTE,
        "system": platform_tools.system(),
        "bundled_fonts": [{**f, "label": _(f["label"])} for f in sources.BUNDLED_FONTS],
        "languages": {code: name for code, (name, _direction) in i18n.LANGUAGES.items()},
        "settings": settings,
        "plan": plan,
        "workload": workload(plan, now),
        "history": history(conn, now),
        "day_overrides": inputs["day_overrides"],
        **extras,
    }


def templates(settings):
    """الگوهای منوی «+»: الگوهای آمادهٔ حذف‌نشده و الگوهای خود کاربر."""
    hidden = set(settings["hidden_templates"])
    builtin = [{**t, "name": _(t["name"]), "builtin": True} for t in database.BUILTIN_TEMPLATES if t["id"] not in hidden]
    own = [{"id": f"own-{i}", "index": i, "kind": t.get("kind", "study"), "name": t["name"], "fields": t["fields"], "builtin": False}
           for i, t in enumerate(settings["item_templates"])]
    return builtin + own


def waiting_for(item, items, sessions_by_item):
    """نام پیش‌نیازهایی که هنوز تمام نشده‌اند و این درس منتظرشان است."""
    titles = {i["id"]: i for i in items}
    names = []
    for req in item.get("requires") or []:
        other = titles.get(req["id"])
        if other is None or not other["is_active"]:
            continue
        status = item_status(sessions_by_item.get(other["id"], []))
        finished = status == "finished" if req["until"] == "finished" else status in ("read", "finished")
        if not finished:
            names.append(other["title"])
    return names


def done_today(conn, now):
    """کارهای امروز که قبلاً تیک خورده‌اند، برای اینکه موتور سقف و سرعت امروز را دوباره پر نکند."""
    rows = conn.execute(
        "SELECT task_log.session_id, task_log.task_type, task_log.minutes, sessions.item_id "
        "FROM task_log JOIN sessions ON sessions.id = task_log.session_id WHERE task_log.date = ?",
        (now.isoformat(),),
    ).fetchall()
    read_sessions = {}
    for r in rows:
        if r["task_type"] == "read":
            read_sessions.setdefault(r["item_id"], set()).add(r["session_id"])
    return {
        "minutes": sum(r["minutes"] for r in rows),
        "new_reads": {item_id: len(ids) for item_id, ids in read_sessions.items()},
    }


def target_status(item):
    """جلو یا عقب بودن درس نسبت به تاریخ هدف، جداگانه برای پایان خواندن و پایان مرور.

    days مثبت = چند روز زودتر از هدف تمام می‌شود، منفی = چند روز دیرتر.
    done = این بخش از قبل تمام شده است.
    """
    target = item.get("target_date")
    if not target or not item["is_active"]:
        return None
    status = item["status_list"]
    result = {}
    for key, end, finished in (
        ("read", item["finish"]["read_end"], status in ("read", "finished")),
        ("review", item["finish"]["review_end"], status == "finished"),
    ):
        if end is None:
            result[key] = {"done": finished, "days": None}
        else:
            result[key] = {"done": False, "days": (target - end).days}
    return result


def workload(plan, now):
    """نشانگر حجم کار منتظر: چقدر خواندن و مرور مانده و میانگین 30 روز آینده."""
    read = review = 0
    next_read = next_review = 0
    last_day = None
    horizon = now + timedelta(days=30)
    for day in plan["days"]:
        for task in day["tasks"]:
            if task["kind"] == "routine":
                continue
            last_day = day["date"]
            if task["kind"] == "read":
                read += task["minutes"]
            else:
                review += task["minutes"]
            if day["date"] < horizon:
                if task["kind"] == "read":
                    next_read += task["minutes"]
                else:
                    next_review += task["minutes"]
    return {
        "read_minutes": read,
        "review_minutes": review,
        "end_date": last_day,
        "avg_read_next_30": round(next_read / 30),
        "avg_review_next_30": round(next_review / 30),
    }


def history(conn, now, days=120):
    """کارهای انجام‌شدهٔ گذشته (و امروز)، برای نمایش در تقویم."""
    since = (now - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT task_log.*, sessions.item_id, sessions.sequence FROM task_log "
        "JOIN sessions ON sessions.id = task_log.session_id "
        "WHERE task_log.date >= ? ORDER BY task_log.date, task_log.id",
        (since,),
    )
    return [database.row_to_dict(r) for r in rows]


def mark_first_reviews(plan):
    """اولین مرور هر جلسه در برنامه علامت می‌خورد؛ فقط همین مرور جابه‌جا می‌شود."""
    seen = set()
    for day in plan["days"]:
        for task in day["tasks"]:
            if task["kind"] == "review" and task["session_id"] not in seen:
                seen.add(task["session_id"])
                task["first_review"] = True


def trim_for_page(state):
    """برنامه‌ای که به صفحه می‌رود به روزهای نزدیک محدود می‌شود تا هر جواب کم‌حجم بماند."""
    plan = state["plan"]
    last = state["today"] + timedelta(days=PAGE_PLAN_DAYS)
    near = [d for d in plan["days"] if d["date"] <= last]
    return {**state, "plan": {**plan, "days": near, "total_days": len(plan["days"])}}
