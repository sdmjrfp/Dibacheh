"""کار با دیتابیس SQLite، migration و backup.

خود منابع (نوت، PDF، ...) اینجا ذخیره نمی‌شوند؛ فقط آدرسشان و اطلاعات برنامه‌ریزی.
برنامهٔ روزانه هم ذخیره نمی‌شود. هر بار با scheduler.build_plan از همین داده‌ها ساخته می‌شود.

تاریخ‌ها در دیتابیس به شکل متن "2026-01-03" ذخیره می‌شوند و موقع خواندن
به datetime.date تبدیل می‌شوند. فهرست‌ها (مثل فاصله‌های لایتنر) به شکل JSON ذخیره می‌شوند.
"""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import platform_tools

PROJECT_DIR = platform_tools.app_home()
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "dibacheh.sqlite3"

# ---------------------------------------------------------------------------
# Migration
#
# هر بار که ساختار جدول‌ها عوض شود، یک مورد جدید به انتهای این فهرست اضافه کنید.
# موارد قبلی را هرگز تغییر ندهید. SQLite شمارهٔ آخرین نسخهٔ اجراشده را در
# PRAGMA user_version نگه می‌دارد، پس هر migration فقط یک بار اجرا می‌شود
# و داده‌های قبلی کاربر از بین نمی‌روند.
# ---------------------------------------------------------------------------

MIGRATIONS = [
    # نسخهٔ 1: جدول‌های اولیه
    """
    CREATE TABLE categories (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE items (
        id                        INTEGER PRIMARY KEY,
        title                     TEXT NOT NULL,
        category_id               INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        item_type                 TEXT NOT NULL DEFAULT 'study',   -- study یا routine
        source_type               TEXT NOT NULL DEFAULT 'none',    -- vault، file، url، none
        source_path_or_url        TEXT,
        queue_position            INTEGER NOT NULL,
        is_active                 INTEGER NOT NULL DEFAULT 1,
        max_new_sessions_per_day  INTEGER NOT NULL DEFAULT 1,
        review_ratio              TEXT,       -- خالی = از تنظیمات
        review_intervals          TEXT,       -- JSON، خالی = از تنظیمات
        start_date                TEXT,       -- فقط برای کار روتین
        routine_weekdays          TEXT,       -- JSON، خالی = همهٔ روزها
        target_date               TEXT,       -- تاریخ هدف اختیاری
        created_at                TEXT NOT NULL
    );

    CREATE TABLE sessions (
        id                       INTEGER PRIMARY KEY,
        item_id                  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        sequence                 INTEGER NOT NULL,
        section_label            TEXT NOT NULL DEFAULT '',
        minutes                  INTEGER NOT NULL,
        minutes_done             INTEGER NOT NULL DEFAULT 0,
        status                   TEXT NOT NULL DEFAULT 'unread',
        leitner_box              INTEGER NOT NULL DEFAULT 0,
        read_at                  TEXT,
        last_reviewed_on         TEXT,
        next_review_on           TEXT,
        review_minutes_override  INTEGER,
        read_manual_date         TEXT,
        review_manual_date       TEXT
    );
    CREATE INDEX sessions_by_item ON sessions(item_id, sequence);

    CREATE TABLE day_overrides (
        date         TEXT PRIMARY KEY,
        cap_minutes  INTEGER NOT NULL      -- صفر = تعطیل
    );

    CREATE TABLE task_log (
        id          INTEGER PRIMARY KEY,
        session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        date        TEXT NOT NULL,
        task_type   TEXT NOT NULL,         -- read یا review
        minutes     INTEGER NOT NULL,
        result      TEXT NOT NULL          -- done، partial، needs_more
    );

    CREATE TABLE settings (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL               -- JSON
    );
    """,
    # نسخهٔ 2: مشخص کردن بخش هر جلسه
    #   section_unit: page (بازهٔ صفحهٔ PDF)، time (بازهٔ زمانی ویدیو)،
    #                 heading (عنوان‌های Markdown)، text (متن آزاد)
    #   range_start / range_end: کل بازهٔ درس، مثلاً صفحهٔ 1 تا 150
    #   section_start / section_end: بازهٔ هر جلسه
    """
    ALTER TABLE items ADD COLUMN section_unit TEXT NOT NULL DEFAULT 'text';
    ALTER TABLE items ADD COLUMN range_start TEXT;
    ALTER TABLE items ADD COLUMN range_end TEXT;
    ALTER TABLE sessions ADD COLUMN section_start TEXT;
    ALTER TABLE sessions ADD COLUMN section_end TEXT;
    """,
    # نسخهٔ 3: نوع‌های کار که خود کاربر می‌سازد (مثلاً «پروژه» یا «تمرین»)
    #   behavior: study (مثل درس، با مرور لایتنر) یا routine (مثل کار روتین، بدون مرور)
    """
    CREATE TABLE item_types (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        behavior    TEXT NOT NULL DEFAULT 'study',
        color       TEXT NOT NULL DEFAULT '#8b5cf6',
        sort_order  INTEGER NOT NULL DEFAULT 0
    );
    ALTER TABLE items ADD COLUMN custom_type_id INTEGER REFERENCES item_types(id) ON DELETE SET NULL;
    """,
    # نسخهٔ 4: رنگ اختصاصی هر منبع، و وضعیت جلسه قبل از هر تیک (برای «انجام نشده»)
    """
    ALTER TABLE items ADD COLUMN color TEXT;
    ALTER TABLE task_log ADD COLUMN before_state TEXT;
    """,
    # نسخهٔ 5: وابستگی درس‌ها، یادداشت جلسه، بایگانی
    #   until: read (بعد از پایان خواندن پیش‌نیاز) یا finished (بعد از پایان مرورهایش)
    """
    CREATE TABLE item_dependencies (
        item_id        INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        depends_on_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        until          TEXT NOT NULL DEFAULT 'read',
        PRIMARY KEY (item_id, depends_on_id)
    );
    ALTER TABLE sessions ADD COLUMN note TEXT NOT NULL DEFAULT '';
    ALTER TABLE items ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
    """,
    # نسخهٔ 6: گزارش‌ها با زیاد شدن سابقه کند نشوند
    """
    CREATE INDEX task_log_by_date ON task_log(date);
    CREATE INDEX task_log_by_session ON task_log(session_id, id);
    """,
    # نسخهٔ 7: کار بدون مرور، و گونهٔ کار
    #   no_reviews: جلسه با خواندن تمام می‌شود (پروژه، کار یک‌باره، یا درسی که مرورهایش حذف شده)
    #   variant: study، project یا once. برچسب و رنگ کار را مشخص می‌کند
    """
    ALTER TABLE items ADD COLUMN no_reviews INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE items ADD COLUMN variant TEXT NOT NULL DEFAULT 'study';
    """,
]

# رنگ‌های پیش‌فرض منبع‌ها؛ هر منبع تازه رنگ بعدی را می‌گیرد و بعداً قابل تغییر است
SOURCE_PALETTE = ["#e5484d", "#3b82f6", "#f5b400", "#10b981", "#8b5cf6", "#f97316",
                  "#ec4899", "#14b8a6", "#84cc16", "#6366f1", "#a16207", "#06b6d4"]

# مقدار پیش‌فرض تنظیمات. فقط تنظیم‌هایی که کاربر عوض کند در جدول settings ذخیره می‌شوند.
DEFAULT_SETTINGS = {
    "default_cap_minutes": 120,
    "cap_tolerance_minutes": 30,
    "default_review_ratio": "1/3",
    "review_intervals": [1, 3, 7, 30],
    "weekday_caps": {},          # {"5": 90} یعنی شنبه 90 دقیقه (0=دوشنبه ... 6=یکشنبه)
    "weekly_days_off": [],
    "day_start_hour": 4,
    "new_item_defaults": {"session_minutes": 60, "max_new_sessions_per_day": 1, "category_id": None},
    "review_cap_percent": None,  # None = خاموش
    "export_folder": "~/Documents/Dibacheh Exports",
    "theme": "light",
    "font_family": "Vazirmatn",
    "font_size": 16,
    "vault_path": "",
    "backup_folder": "data/backups",
    "backup_retention": 30,
    # رنگ کارها در تقویم. پیش‌فرض: روتین زرد، مرور آبی، خواندن قرمز
    "colors": {"read": "#e5484d", "review": "#3b82f6", "routine": "#f5b400"},
    # رنگ‌بندی تقویم: kind = بر اساس خواندن و مرور و روتین، source = بر اساس رنگ خود منبع
    "color_mode": "kind",
    # فونت‌هایی که کاربر اضافه کرده: [{"family": "...", "file": "..."}]؛ فایل‌ها در data/fonts
    "custom_fonts": [],
    # الگوهای درس: [{"name": "...", "fields": {...}}]
    "item_templates": [],
}

FONTS_DIR = DATA_DIR / "fonts"

# ستون‌هایی که تاریخ یا JSON هستند و باید موقع خواندن و نوشتن تبدیل شوند
DATE_COLUMNS = {
    "start_date", "target_date", "read_at", "last_reviewed_on", "next_review_on",
    "read_manual_date", "review_manual_date", "date",
}
JSON_COLUMNS = {"review_intervals", "routine_weekdays"}


# ---------------------------------------------------------------------------
# اتصال و تبدیل
# ---------------------------------------------------------------------------

class Connection(sqlite3.Connection):
    """اتصال دیتابیس که می‌تواند چند تغییر را یک کار حساب کند.

    داخل database.transaction()، دستور commit تابع‌های این فایل کاری نمی‌کند،
    تا همهٔ تغییرها با هم ذخیره شوند یا هیچ‌کدام.
    """

    transaction_depth = 0

    def commit(self):
        if self.transaction_depth == 0:
            super().commit()

    def commit_now(self):
        super().commit()


@contextmanager
def transaction(conn):
    """همهٔ تغییرهای داخل این بلوک با هم ذخیره می‌شوند؛ اگر خطا پیش بیاید، هیچ‌کدام."""
    begin_transaction(conn)
    try:
        yield
    except BaseException:
        end_transaction(conn, success=False)
        raise
    end_transaction(conn, success=True)


def begin_transaction(conn):
    conn.transaction_depth += 1


def end_transaction(conn, success):
    conn.transaction_depth -= 1
    if conn.transaction_depth == 0:
        if success:
            conn.commit_now()
        else:
            conn.rollback()


def connect(path=DB_PATH):
    """به دیتابیس وصل می‌شود و اگر لازم باشد جدول‌ها را می‌سازد یا به‌روز می‌کند."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


# مرورگر گاهی چند درخواست را هم‌زمان می‌فرستد. این قفل نمی‌گذارد دو درخواست
# با هم جدول‌ها را بسازند (وگرنه دومی خطای «table already exists» می‌گیرد).
_migrate_lock = threading.Lock()


def migrate(conn):
    """migrationهایی را که هنوز اجرا نشده‌اند اجرا می‌کند."""
    with _migrate_lock:
        # نسخه داخل قفل خوانده می‌شود، تا اگر درخواست دیگری همین الان migration را تمام کرده، دوباره اجرا نشود
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS, start=1):
            if number <= version:
                continue
            # همهٔ تغییرهای یک migration با هم انجام می‌شوند یا هیچ‌کدام
            try:
                conn.executescript(f"BEGIN; {script} PRAGMA user_version = {number}; COMMIT;")
            except sqlite3.Error:
                conn.rollback()
                raise


def row_to_dict(row):
    """یک سطر دیتابیس را به dict با تاریخ و فهرست واقعی تبدیل می‌کند."""
    data = dict(row)
    for key, value in data.items():
        if value is None:
            continue
        if key in DATE_COLUMNS:
            data[key] = date.fromisoformat(value)
        elif key in JSON_COLUMNS:
            data[key] = json.loads(value)
    if "is_active" in data:
        data["is_active"] = bool(data["is_active"])
    if "archived" in data:
        data["archived"] = bool(data["archived"])
    if "no_reviews" in data:
        data["no_reviews"] = bool(data["no_reviews"])
    return data


def _to_db(key, value):
    """یک مقدار پایتون را به شکل قابل ذخیره در دیتابیس درمی‌آورد."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if key in JSON_COLUMNS:
        return json.dumps(value)
    if isinstance(value, bool):
        return int(value)
    return value


def _update(conn, table, row_id, fields, allowed):
    """فیلدهای مجاز یک سطر را تغییر می‌دهد. نام ستون‌ها فقط از فهرست allowed می‌آید."""
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"فیلد ناشناخته: {', '.join(sorted(unknown))}")
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = [_to_db(k, v) for k, v in fields.items()]
    conn.execute(f"UPDATE {table} SET {columns} WHERE id = ?", [*values, row_id])
    conn.commit()


# ---------------------------------------------------------------------------
# تنظیمات
# ---------------------------------------------------------------------------

def get_settings(conn):
    """همهٔ تنظیمات: پیش‌فرض‌ها، با مقدارهایی که کاربر عوض کرده."""
    result = json.loads(json.dumps(DEFAULT_SETTINGS))  # کپی کامل
    for row in conn.execute("SELECT key, value FROM settings"):
        result[row["key"]] = json.loads(row["value"])
    return result


def _int_in(value, low, high, name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} باید عدد باشد.")
    if not low <= number <= high:
        raise ValueError(f"{name} باید بین {low} و {high} باشد.")
    return number


def clean_setting(key, value):
    """یک تنظیم را بررسی می‌کند و مقدار درست‌شده‌اش را برمی‌گرداند. مقدار نامعتبر → ValueError.

    این بررسی جلوی مقدارهایی را می‌گیرد که موتور چینش را خراب می‌کنند (مثل فاصلهٔ لایتنر صفر).
    """
    if key not in DEFAULT_SETTINGS:
        raise ValueError(f"تنظیم ناشناخته: {key}")
    if key == "default_cap_minutes":
        return _int_in(value, 0, 1440, "سقف پیش‌فرض")
    if key == "cap_tolerance_minutes":
        return _int_in(value, 0, 600, "مقدار مجاز بیشتر از سقف")
    if key == "default_review_ratio":
        from fractions import Fraction
        try:
            ratio = Fraction(str(value).strip())
        except (ValueError, ZeroDivisionError):
            raise ValueError("نسبت مرور نامعتبر است. مثال: 1/3 یا 0.5")
        if ratio <= 0:
            raise ValueError("نسبت مرور باید بیشتر از صفر باشد.")
        return str(value).strip()
    if key == "review_intervals":
        if not isinstance(value, list) or not 1 <= len(value) <= 20:
            raise ValueError("فاصله‌های لایتنر باید بین 1 تا 20 عدد باشند.")
        return [_int_in(v, 1, 3650, "فاصلهٔ لایتنر") for v in value]
    if key == "weekday_caps":
        if not isinstance(value, dict):
            raise ValueError("سقف روزهای هفته نامعتبر است.")
        return {str(_int_in(k, 0, 6, "روز هفته")): _int_in(v, 0, 1440, "سقف روز هفته")
                for k, v in value.items() if v not in (None, "")}
    if key == "weekly_days_off":
        return sorted({_int_in(v, 0, 6, "روز تعطیل") for v in (value or [])})
    if key == "day_start_hour":
        return _int_in(value, 0, 23, "ساعت شروع روز")
    if key == "new_item_defaults":
        value = value or {}
        category = value.get("category_id")
        return {
            "session_minutes": _int_in(value.get("session_minutes", 60), 1, 1440, "زمان جلسهٔ پیش‌فرض"),
            "max_new_sessions_per_day": _int_in(value.get("max_new_sessions_per_day", 1), 1, 50, "سرعت پیش‌فرض"),
            "category_id": int(category) if category not in (None, "") else None,
        }
    if key == "review_cap_percent":
        return None if value in (None, "") else _int_in(value, 1, 100, "سقف زمان مرور")
    if key == "theme":
        if value not in ("light", "dark"):
            raise ValueError("حالت نمایش نامعتبر است.")
        return value
    if key == "font_family":
        name = str(value or "").strip() or "Vazirmatn"
        # فقط حرف، عدد، فاصله و خط تیره، چون این نام مستقیم در CSS قرار می‌گیرد
        if len(name) > 80 or not re.fullmatch(r"[\w \-.]+", name):
            raise ValueError("نام فونت نامعتبر است.")
        return name
    if key == "font_size":
        return _int_in(value, 10, 32, "اندازهٔ فونت")
    if key == "backup_retention":
        return _int_in(value, 1, 365, "تعداد backup")
    if key == "colors":
        if not isinstance(value, dict):
            raise ValueError("رنگ‌ها نامعتبرند.")
        result = dict(DEFAULT_SETTINGS["colors"])
        for kind in result:
            if kind in value:
                result[kind] = clean_color(value[kind])
        return result
    if key == "color_mode":
        if value not in ("kind", "source"):
            raise ValueError("نوع رنگ‌بندی نامعتبر است.")
        return value
    if key == "item_templates":
        if not isinstance(value, list):
            raise ValueError("فهرست الگوها نامعتبر است.")
        allowed = {"session_count", "session_minutes", "max_new_sessions_per_day", "review_ratio",
                   "review_intervals", "section_unit", "category_id", "item_type", "custom_type_id", "color"}
        result = []
        for template in value:
            name = str(template.get("name", "")).strip()
            if not name or len(name) > 60:
                raise ValueError("نام الگو باید بین 1 تا 60 حرف باشد.")
            fields = template.get("fields") or {}
            result.append({"name": name, "fields": {k: v for k, v in fields.items() if k in allowed}})
        return result
    if key == "custom_fonts":
        if not isinstance(value, list):
            raise ValueError("فهرست فونت‌ها نامعتبر است.")
        return [{"family": clean_setting("font_family", f["family"]), "file": Path(str(f["file"])).name}
                for f in value]
    # آدرس‌ها: vault_path، export_folder، backup_folder
    return str(value or "").strip()


def clean_color(value):
    """رنگ به شکل #rrggbb"""
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", text):
        raise ValueError("رنگ باید به شکل #rrggbb باشد.")
    return text


def set_setting(conn, key, value):
    if key not in DEFAULT_SETTINGS:
        raise ValueError(f"تنظیم ناشناخته: {key}")
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# دسته‌ها
# ---------------------------------------------------------------------------

def list_categories(conn):
    rows = conn.execute("SELECT * FROM categories ORDER BY sort_order, id")
    return [dict(r) for r in rows]


def add_category(conn, name):
    next_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories").fetchone()[0]
    cur = conn.execute("INSERT INTO categories (name, sort_order) VALUES (?, ?)", (name, next_order))
    conn.commit()
    return cur.lastrowid


def rename_category(conn, category_id, name):
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
    conn.commit()


def reorder_categories(conn, category_ids):
    conn.executemany("UPDATE categories SET sort_order = ? WHERE id = ?",
                     [(n, cid) for n, cid in enumerate(category_ids, start=1)])
    conn.commit()


# ---------------------------------------------------------------------------
# نوع‌های کار ساخت کاربر
# ---------------------------------------------------------------------------

def list_types(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM item_types ORDER BY sort_order, id")]


def get_type(conn, type_id):
    row = conn.execute("SELECT * FROM item_types WHERE id = ?", (type_id,)).fetchone()
    return dict(row) if row else None


def add_type(conn, name, behavior, color):
    order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM item_types").fetchone()[0]
    cur = conn.execute("INSERT INTO item_types (name, behavior, color, sort_order) VALUES (?, ?, ?, ?)",
                       (name, behavior, color, order))
    conn.commit()
    return cur.lastrowid


def update_type(conn, type_id, name, color):
    """نام و رنگ عوض می‌شود. رفتار (با مرور یا بدون مرور) بعد از ساخت ثابت است،
    چون درس‌های قبلی همین نوع با همان رفتار ساخته شده‌اند."""
    conn.execute("UPDATE item_types SET name = ?, color = ? WHERE id = ?", (name, color, type_id))
    conn.commit()


def delete_type(conn, type_id):
    """نوع حذف می‌شود؛ درس‌هایش می‌مانند و درس یا روتین معمولی می‌شوند."""
    conn.execute("DELETE FROM item_types WHERE id = ?", (type_id,))
    conn.commit()


def delete_category(conn, category_id):
    """دسته حذف می‌شود؛ درس‌هایش بدون دسته می‌مانند."""
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# درس‌ها و جلسه‌ها
# ---------------------------------------------------------------------------

ITEM_FIELDS = {
    "title", "category_id", "item_type", "source_type", "source_path_or_url",
    "is_active", "max_new_sessions_per_day", "review_ratio", "review_intervals",
    "start_date", "routine_weekdays", "target_date",
    "section_unit", "range_start", "range_end", "custom_type_id", "color", "archived",
    "no_reviews", "variant",
}
SESSION_FIELDS = {
    "section_label", "section_start", "section_end", "minutes", "minutes_done", "status", "leitner_box", "read_at",
    "last_reviewed_on", "next_review_on", "review_minutes_override",
    "read_manual_date", "review_manual_date", "note",
}


def add_item(conn, title, session_count, session_minutes, now=None, **fields):
    """درس یا کار روتین جدید می‌سازد و جلسه‌هایش را هم می‌سازد.

    درس جدید به انتهای صف می‌رود.
    """
    unknown = set(fields) - ITEM_FIELDS
    if unknown:
        raise ValueError(f"فیلد ناشناخته: {', '.join(sorted(unknown))}")
    now = now or datetime.now()
    queue = conn.execute("SELECT COALESCE(MAX(queue_position), 0) + 1 FROM items").fetchone()[0]
    data = {"title": title, "queue_position": queue, "created_at": now.isoformat(timespec="seconds")}
    data.update(fields)
    columns = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO items ({columns}) VALUES ({marks})",
        [_to_db(k, v) for k, v in data.items()],
    )
    item_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO sessions (item_id, sequence, minutes) VALUES (?, ?, ?)",
        [(item_id, n, session_minutes) for n in range(1, session_count + 1)],
    )
    conn.commit()
    return item_id


def list_dependencies(conn):
    """{شمارهٔ درس: [{"id": پیش‌نیاز، "until": "read" یا "finished"}]}"""
    result = {}
    for row in conn.execute("SELECT * FROM item_dependencies"):
        result.setdefault(row["item_id"], []).append({"id": row["depends_on_id"], "until": row["until"]})
    return result


def set_dependencies(conn, item_id, requires):
    conn.execute("DELETE FROM item_dependencies WHERE item_id = ?", (item_id,))
    conn.executemany("INSERT INTO item_dependencies (item_id, depends_on_id, until) VALUES (?, ?, ?)",
                     [(item_id, r["id"], r["until"]) for r in requires])
    conn.commit()


def set_day_range(conn, start, end, cap_minutes):
    """سقف یک بازهٔ چندروزه. cap_minutes=0 تعطیل، None برگشت به حالت عادی."""
    day = start
    while day <= end:
        if cap_minutes is None:
            conn.execute("DELETE FROM day_overrides WHERE date = ?", (day.isoformat(),))
        else:
            conn.execute("INSERT INTO day_overrides (date, cap_minutes) VALUES (?, ?) "
                         "ON CONFLICT(date) DO UPDATE SET cap_minutes = excluded.cap_minutes",
                         (day.isoformat(), cap_minutes))
        day += timedelta(days=1)
    conn.commit()


def get_item(conn, item_id):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_items(conn):
    rows = conn.execute("SELECT * FROM items ORDER BY queue_position, id")
    return [row_to_dict(r) for r in rows]


def update_item(conn, item_id, **fields):
    _update(conn, "items", item_id, fields, ITEM_FIELDS)


def delete_item(conn, item_id):
    """درس، جلسه‌ها و سابقه‌اش را پاک می‌کند. فایل منبع روی Mac دست نمی‌خورد."""
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()


def reorder_items(conn, item_ids):
    """ترتیب جدید صف را ذخیره می‌کند (برای drag-and-drop)."""
    conn.executemany(
        "UPDATE items SET queue_position = ? WHERE id = ?",
        [(position, item_id) for position, item_id in enumerate(item_ids, start=1)],
    )
    conn.commit()


def list_sessions(conn, item_id=None):
    if item_id is None:
        rows = conn.execute("SELECT * FROM sessions ORDER BY item_id, sequence")
    else:
        rows = conn.execute("SELECT * FROM sessions WHERE item_id = ? ORDER BY sequence", (item_id,))
    return [row_to_dict(r) for r in rows]


def get_session(conn, session_id):
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_dict(row) if row else None


def update_session(conn, session_id, **fields):
    _update(conn, "sessions", session_id, fields, SESSION_FIELDS)


def clear_manual_dates(conn, item_id, reads=True, reviews=True):
    """جابه‌جایی‌های دستی جلسه‌های یک درس را برمی‌دارد. خروجی: تعداد جلسه‌های آزادشده."""
    columns = [c for c, on in (("read_manual_date", reads), ("review_manual_date", reviews)) if on]
    where = " OR ".join(f"{c} IS NOT NULL" for c in columns)
    count = conn.execute(f"SELECT COUNT(*) FROM sessions WHERE item_id = ? AND ({where})", (item_id,)).fetchone()[0]
    conn.execute(f"UPDATE sessions SET {', '.join(f'{c} = NULL' for c in columns)} WHERE item_id = ?", (item_id,))
    conn.commit()
    return count


def replace_unread_sessions(conn, item_id, new_sessions):
    """جلسه‌های خوانده‌نشدهٔ درس را با فهرست تازه عوض می‌کند (تغییر تقسیم‌بندی).

    جلسه‌های شروع‌شده یا خوانده‌شده و سابقه‌شان دست نمی‌خورند.
    هر جلسهٔ تازه یک dict با sequence، minutes و در صورت نیاز بخش است.
    """
    conn.execute("DELETE FROM sessions WHERE item_id = ? AND status = 'unread'", (item_id,))
    for s in new_sessions:
        conn.execute(
            "INSERT INTO sessions (item_id, sequence, minutes, section_label, section_start, section_end) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, s["sequence"], s["minutes"], s.get("section_label") or "",
             s.get("section_start"), s.get("section_end")),
        )
    conn.commit()


def reset_item(conn, item_id):
    """درس را به لیست خوانده‌نشده برمی‌گرداند و به انتهای صف می‌برد.

    زمان و بخش جلسه‌ها می‌ماند و سابقهٔ قبلی در task_log حفظ می‌شود.
    """
    conn.execute(
        "UPDATE sessions SET status = 'unread', leitner_box = 0, minutes_done = 0, read_at = NULL, "
        "last_reviewed_on = NULL, next_review_on = NULL, read_manual_date = NULL, "
        "review_manual_date = NULL WHERE item_id = ?",
        (item_id,),
    )
    queue = conn.execute("SELECT COALESCE(MAX(queue_position), 0) + 1 FROM items").fetchone()[0]
    conn.execute("UPDATE items SET queue_position = ?, archived = 0 WHERE id = ?", (queue, item_id))
    conn.commit()


# ---------------------------------------------------------------------------
# سقف روزها و سابقه
# ---------------------------------------------------------------------------

def set_day_override(conn, day, cap_minutes):
    """سقف یک روز خاص را عوض می‌کند. cap_minutes=None یعنی برگشت به حالت عادی."""
    if cap_minutes is None:
        conn.execute("DELETE FROM day_overrides WHERE date = ?", (day.isoformat(),))
    else:
        conn.execute(
            "INSERT INTO day_overrides (date, cap_minutes) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET cap_minutes = excluded.cap_minutes",
            (day.isoformat(), cap_minutes),
        )
    conn.commit()


def get_day_overrides(conn):
    rows = conn.execute("SELECT date, cap_minutes FROM day_overrides")
    return {date.fromisoformat(r["date"]): r["cap_minutes"] for r in rows}


# ستون‌هایی از جلسه که با تیک زدن عوض می‌شوند
TICK_FIELDS = ("status", "minutes_done", "leitner_box", "read_at", "last_reviewed_on",
               "next_review_on", "read_manual_date", "review_manual_date")


def add_log(conn, session_id, day, task_type, minutes, result, before=None):
    """یک کار انجام‌شده را ثبت می‌کند. before: جلسه قبل از این تیک، برای «انجام نشده»."""
    snapshot = None
    if before is not None:
        snapshot = json.dumps({k: _to_db(k, before.get(k)) for k in TICK_FIELDS})
    conn.execute(
        "INSERT INTO task_log (session_id, date, task_type, minutes, result, before_state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, day.isoformat(), task_type, minutes, result, snapshot),
    )
    conn.commit()


def get_log(conn, log_id):
    row = conn.execute("SELECT * FROM task_log WHERE id = ?", (log_id,)).fetchone()
    return row_to_dict(row) if row else None


def delete_log(conn, log_id):
    conn.execute("DELETE FROM task_log WHERE id = ?", (log_id,))
    conn.commit()


def list_log(conn, session_id=None):
    if session_id is None:
        rows = conn.execute("SELECT * FROM task_log ORDER BY date, id")
    else:
        rows = conn.execute("SELECT * FROM task_log WHERE session_id = ? ORDER BY date, id", (session_id,))
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# ورودی موتور چینش
# ---------------------------------------------------------------------------

def load_plan_inputs(conn):
    """همهٔ داده‌هایی که scheduler.build_plan لازم دارد، به همان شکلی که می‌خواهد."""
    items = list_items(conn)
    requires = list_dependencies(conn)
    for item in items:
        item["requires"] = requires.get(item["id"], [])
    return {
        "items": items,
        "sessions": list_sessions(conn),
        "settings": get_settings(conn),
        "day_overrides": get_day_overrides(conn),
    }


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def backup_folder(settings):
    """پوشهٔ backup. آدرس نسبی نسبت به پوشهٔ پروژه حساب می‌شود."""
    folder = Path(settings.get("backup_folder") or "data/backups").expanduser()
    return folder if folder.is_absolute() else PROJECT_DIR / folder


class BackupError(Exception):
    """کپی دیتابیس سالم نبود."""


def integrity_problem(path):
    """سلامت یک فایل دیتابیس را بررسی می‌کند. خروجی: None یعنی سالم، وگرنه متن مشکل."""
    try:
        other = sqlite3.connect(_read_only_uri(path), uri=True)
        try:
            result = other.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            other.close()
    except sqlite3.Error as error:
        return str(error)
    return None if result == "ok" else result


def daily_backup(conn, folder, retention, today):
    """اگر امروز هنوز backup گرفته نشده، یک نسخه می‌گیرد و نسخه‌های قدیمی را پاک می‌کند.

    از SQLite Backup API استفاده می‌شود، که حتی وقتی برنامه در حال کار است
    کپی سالم و کامل می‌دهد (کپی معمولی فایل ممکن است نیمه‌کاره باشد).
    خروجی: آدرس فایل backup امروز، یا None اگر از قبل وجود داشت.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"dibacheh-{today.isoformat()}.sqlite3"
    if target.exists():
        return None
    tmp = target.with_suffix(".tmp")
    dest = sqlite3.connect(tmp)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    # backup خراب نباید جای نسخه‌های سالم را بگیرد و باعث پاک شدن قدیمی‌ترها شود
    problem = integrity_problem(tmp)
    if problem:
        tmp.unlink()
        raise BackupError(problem)
    tmp.rename(target)  # فقط وقتی کپی کامل و سالم شد، با نام اصلی ذخیره می‌شود

    # فقط backupهای خود برنامه شمرده و پاک می‌شوند
    backups = sorted(folder.glob("dibacheh-????-??-??.sqlite3"))
    for old in backups[:-retention] if retention > 0 else []:
        old.unlink()
    return target


def list_backups(folder):
    """فهرست backupها، تازه‌ترین اول."""
    folder = Path(folder)
    if not folder.exists():
        return []
    files = sorted(folder.glob("dibacheh-*.sqlite3"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size": f.stat().st_size,
             "modified": datetime.fromtimestamp(f.stat().st_mtime).date(),
             "safety": "before" in f.name} for f in files]


def _read_only_uri(path):
    """آدرس فقط‌خواندنی فایل دیتابیس؛ as_uri فاصله و حرف فارسی و مسیر ویندوز را درست می‌کند."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def check_database_file(path):
    """آیا این فایل واقعاً دیتابیس دیباچه است و از نسخهٔ تازه‌تر برنامه نیست؟ خطا → ValueError"""
    try:
        other = sqlite3.connect(_read_only_uri(path), uri=True)
        try:
            version = other.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in other.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            other.close()
    except sqlite3.Error:
        raise ValueError("این فایل دیتابیس معتبری نیست.")
    if integrity_problem(path):
        raise ValueError("این فایل دیتابیس خراب است.")
    if not {"items", "sessions", "settings"} <= tables:
        raise ValueError("این فایل دیتابیس دیباچه نیست.")
    if version > len(MIGRATIONS):
        raise ValueError("این فایل با نسخهٔ تازه‌تری از برنامه ساخته شده است.")


def safety_copy(conn, folder, now):
    """قبل از جایگزینی داده‌ها، یک کپی جدا می‌گیرد. فقط 5 نسخهٔ آخر از این نوع می‌ماند."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"dibacheh-before-restore-{now.strftime('%Y-%m-%d-%H%M%S')}.sqlite3"
    dest = sqlite3.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    for old in sorted(folder.glob("dibacheh-before-restore-*.sqlite3"))[:-5]:
        old.unlink()
    return target


def replace_database(conn, path):
    """دادهٔ دیتابیس فعلی را با یک فایل دیگر عوض می‌کند و به آخرین ساختار می‌رساند."""
    source = sqlite3.connect(_read_only_uri(path), uri=True)
    try:
        source.backup(conn)
    finally:
        source.close()
    migrate(conn)
