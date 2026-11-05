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
PORT = 5000
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

# نام هر مسیر تغییردهنده و متنی که روی دکمهٔ برگرداندن نشان داده می‌شود
UNDO_LABELS = {
    "api_add_item": "افزودن درس",
    "api_update_item": "ویرایش درس",
    "api_split_item": "تغییر تقسیم‌بندی",
    "api_delete_item": "حذف درس",
    "api_reset_item": "برگرداندن درس",
    "api_reorder": "جابه‌جایی در صف",
    "api_update_session": "ویرایش جلسه",
    "api_move_task": "جابه‌جایی کار",
    "api_set_day": "تغییر سقف روز",
    "api_task_done": "ثبت انجام کار",
    "api_add_category": "افزودن دسته",
    "api_rename_category": "تغییر نام دسته",
    "api_delete_category": "حذف دسته",
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


@app.after_request
def forget_failed_change(response):
    # اگر تغییر به خطا خورد، چیزی عوض نشده و کپی‌اش لازم نیست
    if g.get("undo_pushed") and response.status_code >= 400 and _undo_stack:
        _undo_stack.pop()[1].close()
    return response


@app.route("/api/undo", methods=["POST"])
def api_undo():
    if not _undo_stack:
        raise UserError("تغییری برای برگرداندن نیست.")
    label, snapshot = _undo_stack.pop()
    snapshot.backup(get_db())
    snapshot.close()
    state = build_state()
    state["undone"] = label
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
        })
        items[-1]["target"] = target_status(items[-1])
    return {
        "today": now,
        "items": items,
        "categories": database.list_categories(conn),
        "settings": settings,
        "plan": plan,
        "workload": workload(plan, now),
        "history": history(conn, now),
        "day_overrides": inputs["day_overrides"],
        "undo": {"count": len(_undo_stack), "label": _undo_stack[-1][0] if _undo_stack else None},
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
    fields.setdefault("category_id", defaults.get("category_id"))
    fields.setdefault("max_new_sessions_per_day", defaults.get("max_new_sessions_per_day", 1))
    # first_date: وقتی درس از روی یک روز تقویم اضافه می‌شود
    first_date = _parse_date(data.get("first_date"))
    if fields.get("item_type") == "routine":
        fields["start_date"] = fields.get("start_date") or first_date or today()
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
        database.add_log(conn, session["id"], day, "routine", session["minutes"], "done")

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
                database.add_log(conn, session["id"], day, "read", minutes, "partial")
                return state_response()
            # اگر با این مقدار کل جلسه خوانده شد، مثل «انجام شد» ثبت می‌شود
        elif result != "done":
            raise UserError("نتیجهٔ نامعتبر.")
        updated = leitner.finish_reading(session, day, intervals)
        _save_session(conn, updated)
        database.add_log(conn, session["id"], day, "read", session["minutes"] - already, "done")

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
        database.add_log(conn, session["id"], day, "review", minutes, result)
    else:
        raise UserError("نوع کار نامعتبر است.")
    return state_response()


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
    conn = get_db()
    for key, value in _body().items():
        if key not in database.DEFAULT_SETTINGS:
            raise UserError(f"تنظیم ناشناخته: {key}")
        database.set_setting(conn, key, value)
    return state_response()


if __name__ == "__main__":
    # debug خاموش است، چون حالت debug اجازهٔ اجرای کد از راه مرورگر را می‌دهد.
    app.run(host=HOST, port=PORT, debug=False)
