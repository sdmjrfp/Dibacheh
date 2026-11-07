"""موتور چینش برنامه.

این فایل به Flask یا SQLite وابسته نیست تا جدا تست شود.

تابع اصلی build_plan است. «خالص» است: همان ورودی همیشه همان خروجی را می‌دهد،
و خودش ساعت سیستم یا دیتابیس را نمی‌خواند. «امروز» را لایهٔ بیرونی می‌دهد.

برنامهٔ آینده هیچ‌جا ذخیره نمی‌شود. هر بار که چیزی تغییر کند، کل برنامه
از روی وضعیت فعلی درس‌ها و جلسه‌ها دوباره ساخته می‌شود.

ترتیب کار برای هر روز:
  1. سقف روز
  2. کارهای روتین همان روز
  3. کارهایی که کاربر دستی به این روز (یا قبل‌تر) منتقل کرده
  4. مرورهای موعدرسیده، به ترتیب تاریخ خواندن
  5. جلسه‌های جدید، به ترتیب صف درس‌ها
  6. برای هر خواندن یا مروری که چیده شد، مرور بعدی‌اش در حافظه پیش‌بینی می‌شود
     (فرض: مرور موفق است).
"""

import heapq
from datetime import timedelta

import leitner

DEFAULT_SETTINGS = {
    "default_cap_minutes": 120,
    "cap_tolerance_minutes": 30,
    "default_review_ratio": "1/3",
    "review_intervals": [1, 3, 7, 30],
    # کلید: شمارهٔ روز هفته در پایتون (0=دوشنبه ... 5=شنبه، 6=یکشنبه)
    "weekday_caps": {},
    "weekly_days_off": [],
    "day_start_hour": 4,
    # None یعنی خاموش. عدد یعنی حداکثر چند درصد سقف روز به مرور می‌رسد.
    "review_cap_percent": None,
}


# ---------------------------------------------------------------------------
# تابع‌های کمکی کوچک
# ---------------------------------------------------------------------------

def effective_today(now, day_start_hour):
    """«امروز» با توجه به ساعت شروع روز.

    اگر روز ساعت 4 شروع شود، ساعت 1 بامداد هنوز جزو روز قبل است.
    """
    return (now - timedelta(hours=day_start_hour)).date()


def day_cap(day, settings, day_overrides):
    """سقف دقیقهٔ یک روز. صفر یعنی تعطیل.

    ترتیب اولویت: تغییر همان روز، تعطیلی هفتگی، سقف روز هفته، سقف پیش‌فرض.
    """
    if day in day_overrides:
        return day_overrides[day]
    weekday = day.weekday()
    days_off = {int(d) for d in settings.get("weekly_days_off") or []}
    if weekday in days_off:
        return 0
    weekday_caps = {int(k): v for k, v in (settings.get("weekday_caps") or {}).items()}
    if weekday_caps.get(weekday) is not None:
        return weekday_caps[weekday]
    return settings["default_cap_minutes"]


class _Day:
    """کارهای یک روز در حال چیدن، و قانون «آیا این کار جا می‌شود؟»."""

    def __init__(self, date, cap, tolerance, already_done=0):
        self.date = date
        self.cap = cap
        self.tolerance = tolerance
        self.tasks = []
        # دقیقه‌هایی که امروز قبلاً انجام و تیک خورده، از سقف امروز کم می‌شود
        self.done = already_done
        self.used = already_done

    def fits(self, minutes):
        # جلسهٔ خیلی بزرگ (بیشتر از سقف + اضافه‌سقف) فقط در روز کاملاً خالی می‌آید.
        if minutes > self.cap + self.tolerance:
            return not self.tasks and self.used == 0
        if self.used + minutes <= self.cap:
            return True
        # اضافه‌سقف: فقط وقتی روز هنوز جای خالی دارد، و جمع از سقف + 30 بیشتر نشود.
        return self.used < self.cap and self.used + minutes <= self.cap + self.tolerance

    def add(self, task):
        self.tasks.append(task)
        self.used += task["minutes"]


# ---------------------------------------------------------------------------
# آماده کردن ورودی
# ---------------------------------------------------------------------------

def _make_state(session, item, settings):
    """یک کپی کاری از جلسه برای شبیه‌سازی. دادهٔ اصلی دست نمی‌خورد."""
    intervals = leitner.intervals_for(item, settings)
    st = {
        "id": session["id"],
        "item_id": item["id"],
        "seq": session["sequence"],
        "queue": item["queue_position"],
        "max_new": item.get("max_new_sessions_per_day") or 1,
        "intervals": intervals,
        "review_min": leitner.review_minutes(session, item, settings),
        "manual_read": session.get("read_manual_date"),
        "manual_review": session.get("review_manual_date"),
        "partial": False,
    }
    status = session["status"]
    if status in ("unread", "reading"):
        done = session.get("minutes_done") or 0
        st["phase"] = "read"
        st["read_left"] = max(session["minutes"] - done, 1)
        st["partial"] = done > 0
        st["read_day"] = None
    elif status == "reviewing" and intervals:
        st["phase"] = "review"
        st["box"] = leitner.clamp_box(session.get("leitner_box") or 1, intervals)
        st["read_day"] = session.get("read_at")
        st["last_day"] = session.get("last_reviewed_on") or session.get("read_at")
    else:
        st["phase"] = "done"
    return st


def _due(st, today):
    """تاریخ مرور بعدی یک جلسه در شبیه‌سازی."""
    if st["last_day"] is None:
        return today
    due = st["last_day"] + timedelta(days=st["intervals"][st["box"] - 1])
    # مرور هرگز قبل از خواندن همان جلسه نمی‌آید.
    if st["read_day"] is not None and due <= st["read_day"]:
        due = st["read_day"] + timedelta(days=1)
    return due


def routine_calendar(item, count, today):
    """روزهای یک کار روتین: {تاریخ: شمارهٔ جلسه}.

    از تاریخ شروع، count روز پشت‌سرهم. اگر کاربر فقط بعضی روزهای هفته را
    انتخاب کرده باشد (routine_weekdays)، فقط همان روزها شمرده می‌شوند.
    روز ازدست‌رفته یا تعطیل هم یکی از همین روزهاست و جبران نمی‌شود.
    """
    start = item.get("start_date") or today
    weekdays = {int(w) for w in item.get("routine_weekdays") or []}
    result = {}
    day = start
    seq = 1
    while seq <= count:
        if not weekdays or day.weekday() in weekdays:
            result[day] = seq
            seq += 1
        day += timedelta(days=1)
    return result


def _review_key(st):
    """ترتیب مرورها: تاریخ خواندن، بعد جای درس در صف، بعد شمارهٔ جلسه."""
    read_day = st["read_day"].toordinal() if st["read_day"] else 0
    return (read_day, st["queue"], st["seq"], st["id"])


# ---------------------------------------------------------------------------
# تابع اصلی
# ---------------------------------------------------------------------------

def build_plan(items, sessions, settings, day_overrides, today, horizon_days=3650,
               done_today=None):
    """کل برنامه را از امروز تا پایان کارها می‌سازد.

    ورودی‌ها:
        items          فهرست dict درس‌ها و کارهای روتین
        sessions       فهرست dict جلسه‌ها
        settings       dict تنظیمات (کلیدهای جاافتاده از DEFAULT_SETTINGS خوانده می‌شوند)
        day_overrides  dict از تاریخ به سقف آن روز (صفر = تعطیل)
        today          datetime.date
        done_today     کارهایی که امروز قبلاً تیک خورده‌اند (اختیاری):
                       {"minutes": جمع دقیقه‌ها، "new_reads": {item_id: تعداد جلسهٔ جدید}}
                       تا سقف امروز و سرعت درس‌ها دوباره پر نشود.

    خروجی، یک dict:
        days      فهرست روزها. هر روز: date، cap، is_off، predicted، total، tasks
        items     برای هر درس: read_end (پایان خواندن) و review_end (پایان مرور)
        pending_minutes  جمع زمان خواندن و مرورهای باقی‌مانده (بدون روتین)
        warnings  فهرست هشدارها
    """
    settings = {**DEFAULT_SETTINGS, **settings}
    done_today = done_today or {}
    tolerance = settings["cap_tolerance_minutes"]
    review_cap_percent = settings.get("review_cap_percent")

    # فقط درس‌های فعال وارد برنامه می‌شوند.
    active = {it["id"]: it for it in items if it.get("is_active", True)}
    routines = sorted(
        (it for it in active.values() if it.get("item_type") == "routine"),
        key=lambda it: (it["queue_position"], it["id"]),
    )
    routine_sessions = {}  # item_id -> {sequence: session}
    states = []
    for s in sessions:
        item = active.get(s["item_id"])
        if item is None:
            continue
        if item.get("item_type") == "routine":
            routine_sessions.setdefault(item["id"], {})[s["sequence"]] = s
            continue
        st = _make_state(s, item, settings)
        if st["phase"] != "done":
            states.append(st)

    # تقویم هر کار روتین و آخرین روز همهٔ روتین‌ها
    routine_dates = {}
    routine_last_day = today
    for it in routines:
        cal = routine_calendar(it, len(routine_sessions.get(it["id"], {})), today)
        routine_dates[it["id"]] = cal
        if cal:
            routine_last_day = max(routine_last_day, max(cal))

    # صف خواندن هر درس، به ترتیب شمارهٔ جلسه
    reads_by_item = {}
    for st in sorted(states, key=lambda x: x["seq"]):
        if st["phase"] == "read":
            reads_by_item.setdefault(st["item_id"], []).append(st)
    item_order = sorted(reads_by_item, key=lambda i: (active[i]["queue_position"], i))
    manual_reads = [st for st in states if st["phase"] == "read" and st["manual_read"]]

    # وابستگی درس‌ها: برای هر درس چند خواندن و چند کار دیگر مانده، و آخرین بار کی انجام شده
    open_reads = {}
    open_all = {}
    for st in states:
        open_all[st["item_id"]] = open_all.get(st["item_id"], 0) + 1
        if st["phase"] == "read":
            open_reads[st["item_id"]] = open_reads.get(st["item_id"], 0) + 1
    last_read_on = {}
    last_work_on = {}
    for s in sessions:
        if s.get("read_at"):
            last_read_on[s["item_id"]] = max(s["read_at"], last_read_on.get(s["item_id"], s["read_at"]))
        work = s.get("last_reviewed_on") or s.get("read_at")
        if work:
            last_work_on[s["item_id"]] = max(work, last_work_on.get(s["item_id"], work))

    def waiting_for_prerequisite(item_id, date):
        """درس وابسته از روز بعد از تمام شدن پیش‌نیازش شروع می‌شود.

        پیش‌نیاز غیرفعال نادیده گرفته می‌شود تا درس برای همیشه گیر نکند.
        """
        for req in active[item_id].get("requires") or []:
            other = req["id"]
            if other not in active:
                continue
            if req.get("until") == "finished":
                if open_all.get(other, 0) > 0 or last_work_on.get(other, date - timedelta(days=1)) >= date:
                    return True
            elif open_reads.get(other, 0) > 0 or last_read_on.get(other, date - timedelta(days=1)) >= date:
                return True
        return False

    # مرورها در یک heap بر اساس تاریخ موعد نگه داشته می‌شوند تا محاسبه سریع باشد.
    review_heap = []
    manual_reviews = []

    def schedule_review(st):
        if st["manual_review"] is not None:
            manual_reviews.append(st)
        else:
            heapq.heappush(review_heap, (_due(st, today).toordinal(), _review_key(st), st["id"], st))

    for st in states:
        if st["phase"] == "review":
            schedule_review(st)

    remaining = len(states)
    days = []
    finish = {}  # item_id -> {"read_end", "review_end"}
    pending_minutes = 0
    warnings = []

    def place(day, st, kind, minutes):
        nonlocal remaining, pending_minutes
        task = {
            "kind": kind,
            "session_id": st["id"],
            "item_id": st["item_id"],
            "minutes": minutes,
            "manual": False,
            "overdue": False,
            "partial": False,
        }
        info = finish.setdefault(st["item_id"], {"read_end": None, "review_end": None})
        pending_minutes += minutes
        if kind == "read":
            task["manual"] = st["manual_read"] is not None
            task["partial"] = st["partial"]
            info["read_end"] = day.date
            open_reads[st["item_id"]] -= 1
            last_read_on[st["item_id"]] = day.date
            last_work_on[st["item_id"]] = day.date
            # بعد از خواندن، جلسه وارد جعبهٔ 1 می‌شود.
            st.update(phase="review", box=1, read_day=day.date, last_day=day.date,
                      manual_read=None, manual_review=None, partial=False)
            if st["intervals"]:
                schedule_review(st)
            else:
                st["phase"] = "done"
                remaining -= 1
                open_all[st["item_id"]] -= 1
        else:
            task["manual"] = st["manual_review"] is not None
            task["review_round"] = st["box"]
            task["overdue"] = _due(st, today) < today if st["manual_review"] is None else False
            info["review_end"] = day.date
            last_work_on[st["item_id"]] = day.date
            if st["box"] >= len(st["intervals"]):
                st["phase"] = "done"
                remaining -= 1
                open_all[st["item_id"]] -= 1
            else:
                st.update(box=st["box"] + 1, last_day=day.date, manual_review=None)
                schedule_review(st)
        day.add(task)

    offset = 0
    for offset in range(horizon_days):
        date = today + timedelta(days=offset)
        if remaining == 0 and date > routine_last_day:
            break

        cap = day_cap(date, settings, day_overrides)
        day = _Day(date, cap, tolerance, done_today.get("minutes", 0) if date == today else 0)
        if cap > 0:
            # item_id -> تعداد جلسهٔ جدید امروز (با احتساب جلسه‌هایی که امروز تیک خورده‌اند)
            new_today = dict(done_today.get("new_reads", {})) if date == today else {}

            # 2. کارهای روتین همین تاریخ. روز ازدست‌رفته منتقل نمی‌شود.
            for it in routines:
                seq = routine_dates[it["id"]].get(date)
                rs = routine_sessions.get(it["id"], {}).get(seq)
                if rs is not None and rs["status"] != "finished":
                    day.add({
                        "kind": "routine", "session_id": rs["id"], "item_id": it["id"],
                        "minutes": rs["minutes"], "manual": False, "overdue": False,
                        "partial": False,
                    })

            # 3. کارهایی که دستی به امروز یا قبل‌تر منتقل شده‌اند.
            manual = []
            for st in manual_reads:
                if st["phase"] == "read" and st["manual_read"] <= date:
                    manual.append((st["manual_read"], 1, (0, st["queue"], st["seq"], st["id"]), st))
            for st in manual_reviews:
                read_ok = st["read_day"] is None or st["read_day"] < date
                if st["manual_review"] <= date and read_ok:
                    manual.append((st["manual_review"], 0, _review_key(st), st))
            manual.sort(key=lambda m: (m[0], m[1], m[2]))
            for _, is_read, _, st in manual:
                if is_read:
                    if day.fits(st["read_left"]):
                        place(day, st, "read", st["read_left"])
                        new_today[st["item_id"]] = new_today.get(st["item_id"], 0) + 1
                elif day.fits(st["review_min"]):
                    manual_reviews.remove(st)
                    place(day, st, "review", st["review_min"])

            # 4. مرورهای موعدرسیده و عقب‌افتاده
            due_today = []
            while review_heap and review_heap[0][0] <= date.toordinal():
                due_today.append(heapq.heappop(review_heap))
            due_today.sort(key=lambda r: r[1])
            review_limit = None
            if review_cap_percent is not None:
                review_limit = cap * review_cap_percent // 100
            review_used = sum(t["minutes"] for t in day.tasks if t["kind"] == "review")
            reviews_left = False
            for entry in due_today:
                st = entry[3]
                minutes = st["review_min"]
                if review_limit is not None and review_used + minutes > review_limit:
                    ok = False
                else:
                    ok = day.fits(minutes)
                if ok:
                    place(day, st, "review", minutes)
                    review_used += minutes
                else:
                    reviews_left = True
                    heapq.heappush(review_heap, entry)  # فردا دوباره امتحان می‌شود

            # 5. جلسه‌های جدید. مرور همیشه اول است، مگر سقف مرور روشن باشد.
            if not reviews_left or review_limit is not None:
                for item_id in item_order:
                    if waiting_for_prerequisite(item_id, date):
                        continue  # کار دستی این درس همچنان در مرحلهٔ 3 می‌آید
                    queue = reads_by_item[item_id]
                    # جلسه‌های خوانده‌شده را از ابتدای صف بردار (فقط برای سرعت)
                    while queue and queue[0]["phase"] != "read":
                        queue.pop(0)
                    count = new_today.get(item_id, 0)
                    for st in queue:
                        if st["phase"] != "read":
                            continue
                        # جلسه‌ای که دستی جابه‌جا شده، جلسه‌های بعدی همان درس را نگه می‌دارد.
                        if st["manual_read"] is not None:
                            break
                        if count >= st["max_new"] or not day.fits(st["read_left"]):
                            break  # جلسه‌های بعدی همین درس نباید جلو بزنند
                        place(day, st, "read", st["read_left"])
                        count += 1
                    new_today[item_id] = count

        days.append({
            "date": date,
            "cap": cap,
            "is_off": cap == 0,
            "predicted": date > today,
            "total": day.used - day.done,   # فقط کارهای چیده‌شده
            "done": day.done,               # دقیقه‌های انجام‌شدهٔ امروز
            "tasks": day.tasks,
        })
    else:
        if remaining > 0:
            warnings.append(
                f"برنامه تا {horizon_days} روز بعد تمام نشد. "
                "ممکن است سقف روزها خیلی کم باشد یا همهٔ روزها تعطیل باشند."
            )

    # درسی که هیچ کاری در برنامه ندارد، تاریخ پایان ندارد.
    for item_id in active:
        finish.setdefault(item_id, {"read_end": None, "review_end": None})

    return {
        "days": days,
        "items": finish,
        "pending_minutes": pending_minutes,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# تغییر تقسیم‌بندی یک درس
# ---------------------------------------------------------------------------

def resplit_remaining(sessions, new_count, minutes_each=None):
    """جلسه‌های خوانده‌نشدهٔ یک درس را دوباره تقسیم می‌کند.

    جلسه‌های شروع‌شده یا خوانده‌شده دست نمی‌خورند.
    اگر minutes_each داده نشود، کل زمان باقی‌مانده بین new_count جلسه پخش می‌شود.
    خروجی: (جلسه‌های دست‌نخورده، فهرست dict جلسه‌های جدید بدون id)
    """
    kept = [s for s in sessions if s["status"] != "unread"]
    unread = [s for s in sessions if s["status"] == "unread"]
    total = sum(s["minutes"] for s in unread)
    if minutes_each is None:
        base, extra = divmod(total, new_count) if new_count else (0, 0)
        sizes = [base + (1 if i < extra else 0) for i in range(new_count)]
    else:
        sizes = [minutes_each] * new_count
    start = max((s["sequence"] for s in kept), default=0)
    new = [
        {
            "sequence": start + i + 1,
            "section_label": "",
            "minutes": m,
            "minutes_done": 0,
            "status": "unread",
            "leitner_box": 0,
        }
        for i, m in enumerate(sizes)
    ]
    return kept, new
