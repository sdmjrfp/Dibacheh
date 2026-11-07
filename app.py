"""سرور محلی برنامه.

این فایل فقط صفحه‌ها و مسیرها (route) را تعریف می‌کند.
منطق اصلی در فایل‌های دیگر است:
  scheduler.py  موتور چینش برنامه
  leitner.py    قانون‌های جعبه و مرور
  database.py   کار با SQLite
  sources.py    منابع درسی و Browse
  exporter.py   ساخت خروجی HTML

هر درخواستی که چیزی را تغییر دهد، در جواب کل وضعیت تازه را برمی‌گرداند
(درس‌ها، دسته‌ها و برنامهٔ از نو ساخته‌شده)، تا صفحه بدون بارگذاری دوباره به‌روز شود.

اجرا:
    .venv/bin/python app.py
بعد در مرورگر به آدرس http://127.0.0.1:5000 بروید.
"""

import hmac
import json
import os
import secrets
import sqlite3
import subprocess
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request, send_file

import database
import leitner
import scheduler
import exporter
import sources

# آدرس و پورت سرور.
# 127.0.0.1 یعنی فقط خود همین Mac می‌تواند به برنامه وصل شود،
# نه گوشی یا کامپیوتر دیگری در شبکه.
HOST = "127.0.0.1"
# پورت را می‌شود برای امتحان عوض کرد: DIBACHEH_PORT=5001 .venv/bin/python app.py
PORT = int(os.environ.get("DIBACHEH_PORT") or 5000)
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

# توکن CSRF: هر بار که برنامه اجرا می‌شود یک رمز تصادفی تازه ساخته می‌شود.
# فقط صفحهٔ خود برنامه آن را می‌داند و همراه هر تغییر می‌فرستد.
# سایت‌های دیگری که در مرورگر باز هستند این رمز را ندارند، پس نمی‌توانند چیزی را تغییر دهند.
CSRF_TOKEN = secrets.token_urlsafe(32)

app = Flask(__name__)
# برای امتحان برنامه با یک دیتابیس جدا، بدون دست زدن به داده‌های اصلی:
#     DIBACHEH_DB=/tmp/demo.sqlite3 .venv/bin/python app.py
app.config["DB_PATH"] = os.environ.get("DIBACHEH_DB") or database.DB_PATH

# تاریخ آخرین backup در همین اجرای برنامه، تا هر درخواست دوباره چک نکند
_last_backup_day = None


# ---------------------------------------------------------------------------
# امنیت
# ---------------------------------------------------------------------------

@app.before_request
def check_security():
    # بررسی Host جلوی حمله‌ای به نام DNS rebinding را می‌گیرد،
    # که در آن یک سایت دیگر خودش را جای 127.0.0.1 جا می‌زند.
    if request.host not in ALLOWED_HOSTS:
        abort(403)
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token, CSRF_TOKEN):
            abort(403)


class UserError(Exception):
    """خطایی که متنش باید به کاربر نشان داده شود (مثلاً «عنوان خالی است»)."""


@app.errorhandler(UserError)
def handle_user_error(error):
    return jsonify({"error": str(error)}), 400


# ---------------------------------------------------------------------------
# دیتابیس و backup
# ---------------------------------------------------------------------------

def get_db():
    """اتصال دیتابیس همین درخواست. در پایان درخواست بسته می‌شود."""
    if "db" not in g:
        g.db = database.connect(app.config["DB_PATH"])
    return g.db


@app.teardown_appcontext
def close_db(_error):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def today():
    """«امروز» با توجه به ساعت شروع روز در تنظیمات."""
    settings = database.get_settings(get_db())
    return scheduler.effective_today(datetime.now(), settings["day_start_hour"])


@app.before_request
def backup_once_a_day():
    """اولین درخواست هر روز، یک backup از دیتابیس می‌گیرد."""
    global _last_backup_day
    day = today()
    if _last_backup_day == day:
        return
    conn = get_db()
    settings = database.get_settings(conn)
    database.daily_backup(conn, database.backup_folder(settings), settings["backup_retention"], day)
    _last_backup_day = day


# ---------------------------------------------------------------------------
# برگرداندن تغییرها (Undo)
#
# قبل از هر تغییر، یک کپی کامل از دیتابیس در حافظه نگه داشته می‌شود.
# «برگرداندن» آخرین کپی را سر جایش می‌گذارد. تا 20 مرحله نگه داشته می‌شود،
# و فقط تا وقتی برنامه باز است (با بستن برنامه پاک می‌شود).
# ---------------------------------------------------------------------------

UNDO_LIMIT = 20
_undo_stack = deque(maxlen=UNDO_LIMIT)  # هر عضو: (متن تغییر، کپی دیتابیس)
_redo_stack = []  # تغییرهای برگردانده‌شده؛ با هر تغییر تازه خالی می‌شود

# نام هر مسیر تغییردهنده و متنی که روی دکمهٔ برگرداندن نشان داده می‌شود
UNDO_LABELS = {
    "api_add_item": "افزودن درس",
    "api_update_item": "ویرایش درس",
    "api_split_item": "تغییر تقسیم‌بندی",
    "api_delete_item": "حذف درس",
    "api_reset_item": "برگرداندن درس",
    "api_reorder": "جابه‌جایی در صف",
    "api_unpin_item": "برگشت درس به چینش خودکار",
    "api_update_session": "ویرایش جلسه",
    "api_move_task": "جابه‌جایی کار",
    "api_set_day": "تغییر سقف روز",
    "api_task_done": "ثبت انجام کار",
    "api_task_undone": "انجام‌نشده کردن کار",
    "api_add_category": "افزودن دسته",
    "api_rename_category": "تغییر نام دسته",
    "api_delete_category": "حذف دسته",
    "api_reorder_categories": "جابه‌جایی دسته‌ها",
    "api_add_type": "ساختن نوع کار",
    "api_update_type": "ویرایش نوع کار",
    "api_delete_type": "حذف نوع کار",
    "api_add_font": "افزودن فونت",
    "api_remove_font": "حذف فونت",
    "api_settings": "تغییر تنظیمات",
}


@app.before_request
def remember_for_undo():
    if request.method == "GET" or request.endpoint not in UNDO_LABELS:
        return
    snapshot = sqlite3.connect(":memory:")
    get_db().backup(snapshot)
    if len(_undo_stack) == UNDO_LIMIT:
        _undo_stack.popleft()[1].close()  # قدیمی‌ترین کپی کنار می‌رود
    _undo_stack.append((UNDO_LABELS[request.endpoint], snapshot))
    g.undo_pushed = True
    # تغییر تازه یعنی تاریخچهٔ «بازگرداندن» دیگر معنی ندارد
    g.cleared_redo = list(_redo_stack)
    _redo_stack.clear()


@app.after_request
def forget_failed_change(response):
    # اگر تغییر به خطا خورد، چیزی عوض نشده و کپی‌اش لازم نیست
    if g.get("undo_pushed") and response.status_code >= 400 and _undo_stack:
        _undo_stack.pop()[1].close()
        _redo_stack.extend(g.get("cleared_redo", []))  # تغییر انجام نشد؛ «بازگرداندن» سر جایش برمی‌گردد
    else:
        for _, old in g.get("cleared_redo", []):
            old.close()
    return response


def _snapshot_now():
    snapshot = sqlite3.connect(":memory:")
    get_db().backup(snapshot)
    return snapshot


@app.route("/api/undo", methods=["POST"])
def api_undo():
    """یک مرحله به عقب. وضعیت فعلی در فهرست «بازگرداندن» می‌رود تا بشود دوباره جلو رفت."""
    if not _undo_stack:
        raise UserError("تغییری برای برگرداندن نیست.")
    label, snapshot = _undo_stack.pop()
    _redo_stack.append((label, _snapshot_now()))
    snapshot.backup(get_db())
    snapshot.close()
    state = build_state()
    state["undone"] = label
    return jsonify(state)


@app.route("/api/redo", methods=["POST"])
def api_redo():
    """تغییری را که برگردانده شده بود دوباره انجام می‌دهد."""
    if not _redo_stack:
        raise UserError("تغییری برای بازگرداندن نیست.")
    label, snapshot = _redo_stack.pop()
    _undo_stack.append((label, _snapshot_now()))
    snapshot.backup(get_db())
    snapshot.close()
    state = build_state()
    state["redone"] = label
    return jsonify(state)


# ---------------------------------------------------------------------------
# تبدیل‌ها
# ---------------------------------------------------------------------------

def _json_ready(value):
    """تاریخ‌ها را برای JSON به متن تبدیل می‌کند."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(_json_ready(k)): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    return value


def _parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise UserError("تاریخ نامعتبر است.")


def _positive_int(value, name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise UserError(f"{name} باید عدد باشد.")
    if number < 1:
        raise UserError(f"{name} باید حداقل 1 باشد.")
    return number


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise UserError("درخواست نامعتبر است.")
    return data


# ---------------------------------------------------------------------------
# وضعیت کامل برای صفحه
# ---------------------------------------------------------------------------

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


def state_data():
    """وضعیت کامل با تاریخ‌های پایتونی (برای خروجی HTML). build_state همین را به JSON می‌دهد."""
    conn = get_db()
    inputs = database.load_plan_inputs(conn)
    settings = inputs["settings"]
    now = today()
    plan = scheduler.build_plan(
        inputs["items"], inputs["sessions"], settings, inputs["day_overrides"], now,
        done_today=done_today(conn, now),
    )
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
            "pinned": sum(1 for x in sess if x.get("read_manual_date") or x.get("review_manual_date")),
        })
        items[-1]["target"] = target_status(items[-1])
    return {
        "today": now,
        "items": items,
        "categories": database.list_categories(conn),
        "types": database.list_types(conn),
        "palette": database.SOURCE_PALETTE,
        "bundled_fonts": sources.BUNDLED_FONTS,
        "settings": settings,
        "plan": plan,
        "workload": workload(plan, now),
        "history": history(conn, now),
        "day_overrides": inputs["day_overrides"],
        "undo": {"count": len(_undo_stack), "label": _undo_stack[-1][0] if _undo_stack else None,
                 "redo_count": len(_redo_stack), "redo_label": _redo_stack[-1][0] if _redo_stack else None},
    }


def build_state():
    return _json_ready(state_data())


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
    return [database._to_python(r) for r in rows]


def state_response():
    return jsonify(build_state())


# ---------------------------------------------------------------------------
# صفحه‌ها
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """صفحهٔ اصلی داشبورد."""
    return render_template("index.html", csrf_token=CSRF_TOKEN)


@app.route("/api/state")
def api_state():
    return state_response()


@app.route("/api/plan")
def api_plan():
    """کل برنامه، که هر بار از نو ساخته می‌شود."""
    return jsonify(build_state()["plan"])


# ---------------------------------------------------------------------------
# درس‌ها
# ---------------------------------------------------------------------------

def _item_fields(data, settings):
    """فیلدهای درس را از درخواست می‌خواند و بررسی می‌کند."""
    fields = {}
    if "title" in data:
        title = str(data["title"]).strip()
        if not title:
            raise UserError("عنوان درس خالی است.")
        fields["title"] = title
    if "item_type" in data:
        if data["item_type"] not in ("study", "routine"):
            raise UserError("نوع کار نامعتبر است.")
        fields["item_type"] = data["item_type"]
    if "category_id" in data:
        fields["category_id"] = data["category_id"] or None
    if "is_active" in data:
        fields["is_active"] = bool(data["is_active"])
    if "color" in data:
        try:
            fields["color"] = database._color(data["color"])
        except ValueError as error:
            raise UserError(str(error))
    if "max_new_sessions_per_day" in data:
        fields["max_new_sessions_per_day"] = _positive_int(data["max_new_sessions_per_day"], "سرعت")
    if "review_ratio" in data:
        ratio = data["review_ratio"] or None
        if ratio is not None:
            try:
                leitner.parse_ratio(ratio)
            except (ValueError, ZeroDivisionError):
                raise UserError("نسبت مرور نامعتبر است. مثال: 1/3 یا 0.5")
        fields["review_ratio"] = ratio
    if "review_intervals" in data:
        intervals = data["review_intervals"] or None
        if intervals is not None:
            intervals = [_positive_int(x, "فاصلهٔ لایتنر") for x in intervals]
        fields["review_intervals"] = intervals
    if "routine_weekdays" in data:
        days = data["routine_weekdays"] or None
        if days is not None:
            days = sorted({int(x) for x in days if 0 <= int(x) <= 6})
        fields["routine_weekdays"] = days or None
    for key in ("start_date", "target_date"):
        if key in data:
            fields[key] = _parse_date(data[key])
    if "section_unit" in data:
        if data["section_unit"] not in ("page", "time", "heading", "text"):
            raise UserError("نوع بخش نامعتبر است.")
        fields["section_unit"] = data["section_unit"]
    for key in ("range_start", "range_end"):
        if key in data:
            fields[key] = str(data[key]).strip() or None
    if "source_type" in data:
        if data["source_type"] not in ("vault", "file", "url", "none"):
            raise UserError("نوع منبع نامعتبر است.")
        fields["source_type"] = data["source_type"]
    if "source_path_or_url" in data:
        fields["source_path_or_url"] = str(data["source_path_or_url"] or "").strip() or None
    if fields.get("source_type") == "url" and fields.get("source_path_or_url"):
        if not sources.is_web_url(fields["source_path_or_url"]):
            raise UserError("لینک باید با http:// یا https:// شروع شود.")
    if fields.get("source_type") == "none":
        fields["source_path_or_url"] = None
    return fields


def _apply_auto_split(conn, item_id):
    """بازهٔ باقی‌ماندهٔ درس را خودکار بین جلسه‌های خوانده‌نشده تقسیم می‌کند."""
    item = database.get_item(conn, item_id)
    sessions = database.list_sessions(conn, item_id)
    kept = [s for s in sessions if s["status"] != "unread"]
    unread = [s for s in sessions if s["status"] == "unread"]
    if item["section_unit"] not in ("page", "time") or not unread:
        return
    start = item["range_start"]
    last_kept = max(kept, key=lambda s: s["sequence"], default=None)
    if last_kept and last_kept.get("section_end"):
        if item["section_unit"] == "page":
            start = str(int(last_kept["section_end"]) + 1)
        else:
            start = last_kept["section_end"]
    try:
        parts = sources.split_range(item["section_unit"], start, item["range_end"], len(unread))
    except ValueError:
        raise UserError("بازهٔ درس نامعتبر است.")
    if parts is None:
        return
    for s, (a, b) in zip(sorted(unread, key=lambda s: s["sequence"]), parts):
        database.update_session(conn, s["id"], section_start=a, section_end=b)


@app.route("/api/items", methods=["POST"])
def api_add_item():
    conn = get_db()
    data = _body()
    settings = database.get_settings(conn)
    defaults = settings["new_item_defaults"]
    count = _positive_int(data.get("session_count", 1), "تعداد جلسه")
    minutes = _positive_int(data.get("session_minutes", defaults["session_minutes"]), "زمان جلسه")
    fields = _item_fields(data, settings)
    if "title" not in fields:
        raise UserError("عنوان درس خالی است.")
    title = fields.pop("title")
    # نوع کار ساخت کاربر: رفتارش (درس یا روتین) از خود نوع می‌آید
    if data.get("custom_type_id"):
        custom = database.get_type(conn, data["custom_type_id"])
        if custom is None:
            raise UserError("نوع کار پیدا نشد.")
        fields["custom_type_id"] = custom["id"]
        fields["item_type"] = custom["behavior"]
    fields.setdefault("category_id", defaults.get("category_id"))
    fields.setdefault("max_new_sessions_per_day", defaults.get("max_new_sessions_per_day", 1))
    # first_date: وقتی درس از روی یک روز تقویم اضافه می‌شود
    first_date = _parse_date(data.get("first_date"))
    if fields.get("item_type") == "routine":
        fields["start_date"] = fields.get("start_date") or first_date or today()
    if "color" not in fields:
        used = len(database.list_items(conn))
        fields["color"] = database.SOURCE_PALETTE[used % len(database.SOURCE_PALETTE)]
    item_id = database.add_item(conn, title, count, minutes, **fields)
    _apply_auto_split(conn, item_id)
    if first_date and fields.get("item_type") != "routine":
        # جلسهٔ اول دستی به همان روز می‌رود؛ بقیهٔ جلسه‌ها پشت سرش می‌آیند
        first = database.list_sessions(conn, item_id)[0]
        database.update_session(conn, first["id"], read_manual_date=max(first_date, today()))
    return state_response()


@app.route("/api/items/<int:item_id>", methods=["PATCH"])
def api_update_item(item_id):
    conn = get_db()
    if database.get_item(conn, item_id) is None:
        abort(404)
    data = _body()
    fields = _item_fields(data, database.get_settings(conn))
    database.update_item(conn, item_id, **fields)
    if {"range_start", "range_end", "section_unit"} & set(fields):
        _apply_auto_split(conn, item_id)
    return state_response()


@app.route("/api/items/<int:item_id>/split", methods=["POST"])
def api_split_item(item_id):
    """تغییر تقسیم‌بندی: جلسه‌های انجام‌شده می‌مانند، بقیه دوباره ساخته می‌شوند."""
    conn = get_db()
    if database.get_item(conn, item_id) is None:
        abort(404)
    data = _body()
    count = _positive_int(data.get("session_count"), "تعداد جلسهٔ باقی‌مانده")
    minutes = data.get("session_minutes")
    minutes = _positive_int(minutes, "زمان جلسه") if minutes not in (None, "") else None
    _, new = scheduler.resplit_remaining(database.list_sessions(conn, item_id), count, minutes)
    database.replace_unread_sessions(conn, item_id, new)
    _apply_auto_split(conn, item_id)
    return state_response()


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def api_delete_item(item_id):
    """درس، جلسه‌ها و سابقه‌اش پاک می‌شود. فایل منبع روی Mac دست نمی‌خورد."""
    database.delete_item(get_db(), item_id)
    return state_response()


@app.route("/api/items/<int:item_id>/reset", methods=["POST"])
def api_reset_item(item_id):
    database.reset_item(get_db(), item_id)
    return state_response()


@app.route("/api/items/reorder", methods=["POST"])
def api_reorder():
    conn = get_db()
    ids = _body().get("ids")
    existing = {i["id"] for i in database.list_items(conn)}
    if not isinstance(ids, list) or set(ids) != existing or len(ids) != len(existing):
        raise UserError("ترتیب صف نامعتبر است.")
    database.reorder_items(conn, ids)
    # درسی که کاربر در صف جابه‌جا کرد، از این به بعد طبق جای تازه‌اش در صف چیده می‌شود:
    # خواندن‌هایی از همین درس که قبلاً دستی به روز خاصی برده شده بودند، آزاد می‌شوند.
    # (وگرنه کار دستی سر روز انتخابی‌اش می‌ماند و جابه‌جایی صف روی تقویم اثری نمی‌گذاشت.)
    moved = _body().get("moved_id")
    released = database.clear_manual_dates(conn, moved, reviews=False) if moved in existing else 0
    state = build_state()
    state["released"] = released
    return jsonify(state)


@app.route("/api/items/<int:item_id>/unpin", methods=["POST"])
def api_unpin_item(item_id):
    """همهٔ جابه‌جایی‌های دستی یک درس (خواندن و مرور) برداشته می‌شود و برمی‌گردد به چینش خودکار."""
    database.clear_manual_dates(get_db(), item_id)
    return state_response()


@app.route("/api/items/<int:item_id>/open", methods=["POST"])
def api_open_source(item_id):
    """منبع ثبت‌شدهٔ یک درس را باز می‌کند. آدرس از دیتابیس می‌آید، نه از مرورگر."""
    conn = get_db()
    item = database.get_item(conn, item_id)
    if item is None:
        abort(404)
    problem = sources.open_source(item, database.get_settings(conn)["vault_path"])
    if problem:
        raise UserError(problem)
    return jsonify({"ok": True})


@app.route("/api/items/<int:item_id>/headings")
def api_headings(item_id):
    conn = get_db()
    item = database.get_item(conn, item_id)
    if item is None:
        abort(404)
    return jsonify(sources.markdown_headings(item, database.get_settings(conn)["vault_path"]))


@app.route("/api/sessions/<int:session_id>", methods=["PATCH"])
def api_update_session(session_id):
    conn = get_db()
    if database.get_session(conn, session_id) is None:
        abort(404)
    data = _body()
    fields = {}
    for key in ("section_label", "section_start", "section_end"):
        if key in data:
            fields[key] = str(data[key] or "").strip() or None
    if "section_label" in fields:
        fields["section_label"] = fields["section_label"] or ""
    if "minutes" in data:
        fields["minutes"] = _positive_int(data["minutes"], "زمان جلسه")
    if "review_minutes_override" in data:
        value = data["review_minutes_override"]
        fields["review_minutes_override"] = None if value in (None, "") else _positive_int(value, "زمان مرور")
    database.update_session(conn, session_id, **fields)
    return state_response()


# ---------------------------------------------------------------------------
# تغییرات دستی در تقویم
# ---------------------------------------------------------------------------

@app.route("/api/tasks/move", methods=["POST"])
def api_move_task():
    """یک خواندن یا مرور را به روز دیگری می‌برد (جلو یا عقب).

    date خالی یعنی «برگشت به چینش خودکار».
    برنامه کار را زودتر از این روز نمی‌آورد. اگر آن روز انجام نشود، جلوتر می‌رود.
    مرورهای بعدی همان جلسه هم خودبه‌خود به همان اندازه جابه‌جا می‌شوند.
    """
    conn = get_db()
    data = _body()
    session = database.get_session(conn, data.get("session_id"))
    if session is None:
        raise UserError("جلسه پیدا نشد.")
    target = _parse_date(data.get("date"))
    if target is not None and target < today():
        raise UserError("کار را نمی‌شود به روزهای گذشته برد.")
    kind = data.get("kind")
    if kind == "read":
        if session["status"] not in ("unread", "reading"):
            raise UserError("این جلسه خوانده شده است.")
        database.update_session(conn, session["id"], read_manual_date=target)
    elif kind == "review":
        if session["status"] != "reviewing":
            raise UserError("این جلسه هنوز خوانده نشده؛ خواندنش را جابه‌جا کنید تا مرورها هم با آن بروند.")
        if target is not None and session["read_at"] and target <= session["read_at"]:
            raise UserError("مرور باید بعد از روز خواندن همان جلسه باشد.")
        database.update_session(conn, session["id"], review_manual_date=target)
    else:
        raise UserError("نوع کار نامعتبر است.")
    return state_response()


@app.route("/api/tasks/done", methods=["POST"])
def api_task_done():
    """ثبت انجام یک کار، همیشه با تاریخ امروز.

    result:
      done        انجام شد
      partial     فقط بخشی از خواندن انجام شد (minutes = دقیقهٔ خوانده‌شده)
      needs_more  مرور انجام شد ولی نیاز به مرور بیشتر دارد (برگشت به جعبهٔ 1)
    کار آینده را هم می‌شود زودتر تیک زد؛ باز هم با تاریخ امروز ثبت می‌شود.
    """
    conn = get_db()
    data = _body()
    session = database.get_session(conn, data.get("session_id"))
    if session is None:
        raise UserError("جلسه پیدا نشد.")
    item = database.get_item(conn, session["item_id"])
    settings = database.get_settings(conn)
    intervals = leitner.intervals_for(item, settings)
    day = today()
    kind = data.get("kind")
    result = data.get("result", "done")

    if kind == "routine":
        if item["item_type"] != "routine" or session["status"] == "finished":
            raise UserError("این کار روتین قبلاً ثبت شده است.")
        database.update_session(conn, session["id"], status="finished", minutes_done=session["minutes"])
        database.add_log(conn, session["id"], day, "routine", session["minutes"], "done", before=session)

    elif kind == "read":
        if session["status"] not in ("unread", "reading"):
            raise UserError("این جلسه قبلاً خوانده شده است.")
        already = session["minutes_done"] or 0
        if result == "partial":
            minutes = _positive_int(data.get("minutes"), "دقیقهٔ خوانده‌شده")
            if already + minutes < session["minutes"]:
                # بقیهٔ جلسه از فردا چیده می‌شود، نه دوباره امروز
                database.update_session(conn, session["id"], status="reading",
                                        minutes_done=already + minutes,
                                        read_manual_date=day + timedelta(days=1))
                database.add_log(conn, session["id"], day, "read", minutes, "partial", before=session)
                return state_response()
            # اگر با این مقدار کل جلسه خوانده شد، مثل «انجام شد» ثبت می‌شود
        elif result != "done":
            raise UserError("نتیجهٔ نامعتبر.")
        updated = leitner.finish_reading(session, day, intervals)
        _save_session(conn, updated)
        database.add_log(conn, session["id"], day, "read", session["minutes"] - already, "done", before=session)

    elif kind == "review":
        if session["status"] != "reviewing":
            raise UserError("این جلسه مرور منتظر ندارد.")
        minutes = leitner.review_minutes(session, item, settings)
        if result == "needs_more":
            updated = leitner.needs_more_review(session, day, intervals)
        elif result == "done":
            updated = leitner.record_review(session, day, intervals)
        else:
            raise UserError("نتیجهٔ نامعتبر.")
        _save_session(conn, updated)
        database.add_log(conn, session["id"], day, "review", minutes, result, before=session)
    else:
        raise UserError("نوع کار نامعتبر است.")
    return state_response()


@app.route("/api/tasks/undone", methods=["POST"])
def api_task_undone():
    """یک کار تیک‌خورده را به حالت انجام‌نشده برمی‌گرداند.

    جلسه دقیقاً به وضعیت قبل از همان تیک برمی‌گردد و کار دوباره وارد برنامه می‌شود.
    چون هر تیک روی تیک قبلی همان جلسه سوار است، فقط آخرین تیک هر جلسه برمی‌گردد.
    """
    conn = get_db()
    log = database.get_log(conn, _body().get("log_id"))
    if log is None:
        raise UserError("این کار در سابقه پیدا نشد.")
    logs = database.list_log(conn, log["session_id"])
    if logs[-1]["id"] != log["id"]:
        raise UserError("اول کار بعدیِ همین جلسه را انجام‌نشده کنید.")
    session = database.get_session(conn, log["session_id"])
    if session["status"] == "unread" and not session["minutes_done"]:
        raise UserError("این درس بعد از این کار به خوانده‌نشده برگردانده شده است.")
    if log.get("before_state"):
        before = json.loads(log["before_state"])
        restored = {k: (date.fromisoformat(v) if v and k in database.DATE_COLUMNS else v)
                    for k, v in before.items()}
    else:
        restored = _replay_session(conn, session, logs[:-1])
    database.update_session(conn, session["id"], **restored)
    database.delete_log(conn, log["id"])
    return state_response()


def _replay_session(conn, session, logs):
    """تیک‌هایی که قبل از ذخیره شدن وضعیت ثبت شده‌اند: جلسه از اول با سابقه‌اش بازسازی می‌شود."""
    item = database.get_item(conn, session["item_id"])
    intervals = leitner.intervals_for(item, database.get_settings(conn))
    s = leitner.reset_session(session)
    for entry in logs:
        if entry["task_type"] == "routine":
            s.update(status="finished", minutes_done=s["minutes"])
        elif entry["task_type"] == "read" and entry["result"] == "partial":
            s.update(status="reading", minutes_done=s["minutes_done"] + entry["minutes"])
        elif entry["task_type"] == "read":
            s = leitner.finish_reading(s, entry["date"], intervals)
        elif entry["result"] == "needs_more":
            s = leitner.needs_more_review(s, entry["date"], intervals)
        else:
            s = leitner.record_review(s, entry["date"], intervals)
    return {k: s.get(k) for k in database.TICK_FIELDS}


def _save_session(conn, session):
    """فیلدهای قابل ذخیرهٔ یک جلسهٔ تغییرکرده را در دیتابیس می‌نویسد."""
    fields = {k: session[k] for k in database.SESSION_FIELDS if k in session}
    database.update_session(conn, session["id"], **fields)


# ---------------------------------------------------------------------------
# خروجی HTML و اشتراک‌گذاری
# ---------------------------------------------------------------------------

def export_folder():
    return Path(database.get_settings(get_db())["export_folder"] or "~/Documents/Dibacheh Exports").expanduser()


def _export_file(name):
    """فقط فایلی که خود برنامه در پوشهٔ خروجی ساخته؛ نه هر آدرس دلخواه."""
    if not isinstance(name, str) or "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".html"):
        raise UserError("نام فایل نامعتبر است.")
    path = export_folder() / name
    if not path.is_file():
        raise UserError("فایل خروجی پیدا نشد.")
    return path


@app.route("/api/export", methods=["POST"])
def api_export():
    """خروجی روز، هفته یا ماه را می‌سازد و در پوشهٔ خروجی ذخیره می‌کند."""
    data = _body()
    scope = data.get("scope", "day")
    if scope not in ("day", "week", "month"):
        raise UserError("نوع خروجی نامعتبر است.")
    day = _parse_date(data.get("date")) or today()
    # خروجی روزانه به‌طور پیش‌فرض مطالب را هم دارد؛ هفتگی و ماهانه فقط فهرست کارها
    with_content = bool(data.get("with_content", scope == "day"))
    state = state_data()
    path = exporter.export(state, scope, day, with_content,
                           state["settings"]["vault_path"], export_folder())
    return jsonify({"name": path.name, "path": str(path), "size": path.stat().st_size})


@app.route("/api/export/file/<path:name>")
def api_export_file(name):
    """فایل خروجی را به مرورگر می‌دهد (برای پنجرهٔ Share)."""
    return send_file(_export_file(name), mimetype="text/html", as_attachment=True, download_name=name)


@app.route("/api/export/reveal", methods=["POST"])
def api_export_reveal():
    """فایل را در Finder انتخاب‌شده نشان می‌دهد تا بشود آن را به تلگرام یا هر برنامه‌ای کشید."""
    subprocess.run(["open", "-R", str(_export_file(_body().get("name")))], check=False)
    return jsonify({"ok": True})


@app.route("/api/export/open", methods=["POST"])
def api_export_open():
    subprocess.run(["open", str(_export_file(_body().get("name")))], check=False)
    return jsonify({"ok": True})


@app.route("/api/days/<day>", methods=["PUT"])
def api_set_day(day):
    """سقف یک روز خاص. 0 = تعطیل، null = برگشت به سقف عادی."""
    target = _parse_date(day)
    value = _body().get("cap_minutes")
    if value is not None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise UserError("سقف روز باید عدد باشد.")
        if value < 0:
            raise UserError("سقف روز نمی‌تواند منفی باشد.")
    database.set_day_override(get_db(), target, value)
    return state_response()


# ---------------------------------------------------------------------------
# Browse
# ---------------------------------------------------------------------------

@app.route("/api/browse", methods=["POST"])
def api_browse():
    """پنجرهٔ انتخاب فایل macOS را باز می‌کند.

    kind=file: برای منبع درس. آدرس نسبت به والت یا آدرس کامل برمی‌گردد.
    kind=vault: برای انتخاب پوشهٔ والت در تنظیمات، و همان‌جا ذخیره می‌شود.
    """
    conn = get_db()
    kind = _body().get("kind", "file")
    if kind == "folder":
        # برای پوشهٔ خروجی و backup در تنظیمات: فقط آدرس برمی‌گردد، ذخیره با دکمهٔ «ذخیره»
        path = sources.browse("folder", "یک پوشه انتخاب کنید")
        return jsonify({"cancelled": True} if path is None else {"path": path})
    if kind == "vault":
        path = sources.browse("folder", "پوشهٔ والت Obsidian را انتخاب کنید")
        if path is None:
            return jsonify({"cancelled": True})
        database.set_setting(conn, "vault_path", path)
        return state_response()
    path = sources.browse("file", "فایل منبع را انتخاب کنید")
    if path is None:
        return jsonify({"cancelled": True})
    source_type, stored = sources.classify_path(path, database.get_settings(conn)["vault_path"])
    return jsonify({"source_type": source_type, "source_path_or_url": stored})


# ---------------------------------------------------------------------------
# دسته‌ها و تنظیمات
# ---------------------------------------------------------------------------

@app.route("/api/categories", methods=["POST"])
def api_add_category():
    name = str(_body().get("name", "")).strip()
    if not name:
        raise UserError("نام دسته خالی است.")
    database.add_category(get_db(), name)
    return state_response()


@app.route("/api/categories/<int:category_id>", methods=["PATCH"])
def api_rename_category(category_id):
    name = str(_body().get("name", "")).strip()
    if not name:
        raise UserError("نام دسته خالی است.")
    database.rename_category(get_db(), category_id, name)
    return state_response()


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def api_delete_category(category_id):
    database.delete_category(get_db(), category_id)
    return state_response()


@app.route("/api/settings", methods=["PATCH"])
def api_settings():
    """چند تنظیم را با هم ذخیره می‌کند. هر مقدار اول بررسی می‌شود؛ اگر یکی نامعتبر بود، هیچ‌کدام ذخیره نمی‌شود."""
    conn = get_db()
    cleaned = {}
    for key, value in _body().items():
        try:
            cleaned[key] = database.clean_setting(key, value)
        except ValueError as error:
            raise UserError(str(error))
    for key, value in cleaned.items():
        database.set_setting(conn, key, value)
    return state_response()


FONT_SUFFIXES = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}


@app.route("/api/fonts/add", methods=["POST"])
def api_add_font():
    """یک فایل فونت را با Browse انتخاب می‌کند و کپی‌اش را در data/fonts می‌گذارد."""
    conn = get_db()
    path = sources.browse("file", "فایل فونت را انتخاب کنید (ttf، otf، woff یا woff2)")
    if path is None:
        return jsonify({"cancelled": True})
    source = Path(path)
    if source.suffix.lower() not in FONT_SUFFIXES:
        raise UserError("این فایل فونت نیست. فقط ttf، otf، woff و woff2.")
    try:
        family = sources.font_family_name(source)
        family = database.clean_setting("font_family", family)
    except Exception:
        raise UserError("نام این فونت خوانده نشد.")
    database.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    target = database.FONTS_DIR / source.name
    target.write_bytes(source.read_bytes())
    fonts = [f for f in database.get_settings(conn)["custom_fonts"] if f["family"] != family]
    fonts.append({"family": family, "file": target.name})
    database.set_setting(conn, "custom_fonts", fonts)
    state = build_state()
    state["added_font"] = family
    return jsonify(state)


@app.route("/api/fonts/remove", methods=["POST"])
def api_remove_font():
    conn = get_db()
    family = _body().get("family")
    settings = database.get_settings(conn)
    fonts = [f for f in settings["custom_fonts"] if f["family"] != family]
    database.set_setting(conn, "custom_fonts", fonts)
    if settings["font_family"] == family:
        database.set_setting(conn, "font_family", "Vazirmatn")
    return state_response()


@app.route("/fonts/<name>")
def serve_font(name):
    """فایل فونت‌های اضافه‌شده، فقط از پوشهٔ data/fonts."""
    path = database.FONTS_DIR / Path(name).name
    if path.suffix.lower() not in FONT_SUFFIXES or not path.is_file():
        abort(404)
    return send_file(path, mimetype=FONT_SUFFIXES[path.suffix.lower()])


# ---------------------------------------------------------------------------
# نوع‌های کار ساخت کاربر
# ---------------------------------------------------------------------------

def _type_fields(data):
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 40:
        raise UserError("نام نوع کار باید بین 1 تا 40 حرف باشد.")
    try:
        color = database._color(data.get("color", "#8b5cf6"))
    except ValueError as error:
        raise UserError(str(error))
    return name, color


@app.route("/api/types", methods=["POST"])
def api_add_type():
    data = _body()
    name, color = _type_fields(data)
    behavior = data.get("behavior", "study")
    if behavior not in ("study", "routine"):
        raise UserError("رفتار نوع کار نامعتبر است.")
    database.add_type(get_db(), name, behavior, color)
    return state_response()


@app.route("/api/types/<int:type_id>", methods=["PATCH"])
def api_update_type(type_id):
    if database.get_type(get_db(), type_id) is None:
        abort(404)
    name, color = _type_fields(_body())
    database.update_type(get_db(), type_id, name, color)
    return state_response()


@app.route("/api/types/<int:type_id>", methods=["DELETE"])
def api_delete_type(type_id):
    database.delete_type(get_db(), type_id)
    return state_response()


@app.route("/api/categories/reorder", methods=["POST"])
def api_reorder_categories():
    conn = get_db()
    ids = _body().get("ids")
    existing = {c["id"] for c in database.list_categories(conn)}
    if not isinstance(ids, list) or set(ids) != existing:
        raise UserError("ترتیب دسته‌ها نامعتبر است.")
    database.reorder_categories(conn, ids)
    return state_response()


if __name__ == "__main__":
    # debug خاموش است، چون حالت debug اجازهٔ اجرای کد از راه مرورگر را می‌دهد.
    app.run(host=HOST, port=PORT, debug=False)
