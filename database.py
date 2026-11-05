"""کار با دیتابیس SQLite، migration و backup.

خود منابع (نوت، PDF، ...) اینجا ذخیره نمی‌شوند؛ فقط آدرسشان و اطلاعات برنامه‌ریزی.
برنامهٔ روزانه هم ذخیره نمی‌شود. هر بار با scheduler.build_plan از همین داده‌ها ساخته می‌شود.

تاریخ‌ها در دیتابیس به شکل متن "2026-01-03" ذخیره می‌شوند و موقع خواندن
به datetime.date تبدیل می‌شوند. فهرست‌ها (مثل فاصله‌های لایتنر) به شکل JSON ذخیره می‌شوند.
"""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
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
]

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
    "export_folder": "",
    "theme": "light",
    "font_family": "Vazirmatn",
    "font_size": 16,
    "vault_path": "",
    "backup_folder": "data/backups",
    "backup_retention": 30,
}

# ستون‌هایی که تاریخ یا JSON هستند و باید موقع خواندن و نوشتن تبدیل شوند
DATE_COLUMNS = {
    "start_date", "target_date", "read_at", "last_reviewed_on", "next_review_on",
    "read_manual_date", "review_manual_date", "date",
}
JSON_COLUMNS = {"review_intervals", "routine_weekdays"}


# ---------------------------------------------------------------------------
# اتصال و تبدیل
# ---------------------------------------------------------------------------

def connect(path=DB_PATH):
    """به دیتابیس وصل می‌شود و اگر لازم باشد جدول‌ها را می‌سازد یا به‌روز می‌کند."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn):
    """migrationهایی را که هنوز اجرا نشده‌اند اجرا می‌کند."""
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


def _to_python(row):
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
}
SESSION_FIELDS = {
    "section_label", "minutes", "minutes_done", "status", "leitner_box", "read_at",
    "last_reviewed_on", "next_review_on", "review_minutes_override",
    "read_manual_date", "review_manual_date",
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


def get_item(conn, item_id):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _to_python(row) if row else None


def list_items(conn):
    rows = conn.execute("SELECT * FROM items ORDER BY queue_position, id")
    return [_to_python(r) for r in rows]


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
    return [_to_python(r) for r in rows]


def update_session(conn, session_id, **fields):
    _update(conn, "sessions", session_id, fields, SESSION_FIELDS)


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


def add_log(conn, session_id, day, task_type, minutes, result):
    conn.execute(
        "INSERT INTO task_log (session_id, date, task_type, minutes, result) VALUES (?, ?, ?, ?, ?)",
        (session_id, day.isoformat(), task_type, minutes, result),
    )
    conn.commit()


def list_log(conn, session_id=None):
    if session_id is None:
        rows = conn.execute("SELECT * FROM task_log ORDER BY date, id")
    else:
        rows = conn.execute("SELECT * FROM task_log WHERE session_id = ? ORDER BY date, id", (session_id,))
    return [_to_python(r) for r in rows]


# ---------------------------------------------------------------------------
# ورودی موتور چینش
# ---------------------------------------------------------------------------

def load_plan_inputs(conn):
    """همهٔ داده‌هایی که scheduler.build_plan لازم دارد، به همان شکلی که می‌خواهد."""
    return {
        "items": list_items(conn),
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
    tmp.rename(target)  # فقط وقتی کپی کامل شد، با نام اصلی ذخیره می‌شود

    # فقط backupهای خود برنامه شمرده و پاک می‌شوند
    backups = sorted(folder.glob("dibacheh-????-??-??.sqlite3"))
    for old in backups[:-retention] if retention > 0 else []:
        old.unlink()
    return target
