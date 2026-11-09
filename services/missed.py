"""کارهایی که روز خودشان انجام نشده‌اند.

برنامه هر بار از نو ساخته می‌شود و گذشته را به خاطر نمی‌سپارد. برای همین یک کپی از برنامهٔ
امروز و روزهای آینده در planned_tasks نگه داشته می‌شود. وقتی روزی گذشت، هر چیزی از آن روز
که هنوز آنجا مانده و تیک نخورده، به missed_tasks می‌رود.

خود کار دست نمی‌خورد: موتور چینش خواندن و مرورِ انجام‌نشده را به روزهای بعد می‌برد.
روتین جابه‌جا نمی‌شود و فقط به‌عنوان انجام‌نشده می‌ماند.
"""

from datetime import date, timedelta

import database
from errors import NotFoundError, UserError
from i18n import _
from services import tasks as task_service

# برنامه تا چند روز جلوتر نگه داشته می‌شود؛ یعنی برنامه تا این مدت باز نشدن را هم می‌فهمد
KEEP_DAYS = 70


def roll_over(conn, today):
    """روزهای گذشته را می‌بندد: کار تیک‌نخورده انجام‌نشده ثبت می‌شود."""
    rows = conn.execute("SELECT * FROM planned_tasks WHERE date < ?", (today.isoformat(),)).fetchall()
    if not rows:
        return
    for row in rows:
        # اگر برنامه چند روز باز نشده باشد، مرورهای پیش‌بینی‌شده هنوز واقعاً موعدشان نرسیده بوده
        if row["kind"] == "review":
            session = database.get_session(conn, row["session_id"])
            if session is None or session["status"] != "reviewing" or (session["leitner_box"] or 1) != row["review_round"]:
                continue
        done = conn.execute(
            "SELECT 1 FROM task_log WHERE session_id = ? AND task_type = ? AND date = ? LIMIT 1",
            (row["session_id"], row["kind"], row["date"]),
        ).fetchone()
        if done is None:
            conn.execute(
                "INSERT OR IGNORE INTO missed_tasks (date, session_id, kind, review_round, minutes) VALUES (?, ?, ?, ?, ?)",
                (row["date"], row["session_id"], row["kind"], row["review_round"], row["minutes"]),
            )
    conn.execute("DELETE FROM planned_tasks WHERE date < ?", (today.isoformat(),))
    conn.commit()


def remember_plan(conn, plan, today):
    """برنامهٔ امروز و روزهای آینده را نگه می‌دارد. فقط اگر عوض شده باشد می‌نویسد."""
    last = today + timedelta(days=KEEP_DAYS)
    wanted = {
        (day["date"].isoformat(), task["session_id"], task["kind"], task.get("review_round") or 0, task["minutes"])
        for day in plan["days"] if day["date"] <= last for task in day["tasks"]
    }
    current = {
        (r["date"], r["session_id"], r["kind"], r["review_round"], r["minutes"])
        for r in conn.execute("SELECT * FROM planned_tasks WHERE date >= ?", (today.isoformat(),))
    }
    if wanted == current:
        return
    conn.execute("DELETE FROM planned_tasks WHERE date >= ?", (today.isoformat(),))
    conn.executemany(
        "INSERT OR IGNORE INTO planned_tasks (date, session_id, kind, review_round, minutes) VALUES (?, ?, ?, ?, ?)",
        sorted(wanted),
    )
    conn.commit()


def _is_resolved(row, session):
    """آیا این کار بعداً انجام شده؟ پس دیگر نمی‌شود دوباره «انجام شد» زد."""
    if row["kind"] == "routine":
        return session["status"] == "finished"
    if row["kind"] == "read":
        return session["status"] not in ("unread", "reading")
    if session["status"] != "reviewing":
        return True
    return (session["leitner_box"] or 1) != row["review_round"]


def list_missed(conn, today, days=120):
    """انجام‌نشده‌های اخیر، برای تقویم."""
    since = (today - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT missed_tasks.*, sessions.item_id, sessions.sequence, sessions.status, sessions.leitner_box "
        "FROM missed_tasks JOIN sessions ON sessions.id = missed_tasks.session_id "
        "WHERE missed_tasks.date >= ? ORDER BY missed_tasks.date, missed_tasks.id",
        (since,),
    ).fetchall()
    return [{
        "id": r["id"], "date": date.fromisoformat(r["date"]), "session_id": r["session_id"], "item_id": r["item_id"],
        "sequence": r["sequence"], "kind": r["kind"], "review_round": r["review_round"], "minutes": r["minutes"],
        "resolved": _is_resolved(r, r),
    } for r in rows]


def _get(conn, missed_id):
    row = conn.execute("SELECT * FROM missed_tasks WHERE id = ?", (missed_id,)).fetchone()
    if row is None:
        raise NotFoundError()
    return row


def dismiss(conn, missed_id):
    """حذف دستی: فقط از نمره و تقویم برداشته می‌شود و برنامهٔ آینده عوض نمی‌شود."""
    _get(conn, missed_id)
    conn.execute("DELETE FROM missed_tasks WHERE id = ?", (missed_id,))


def mark_done(conn, missed_id):
    """«انجام شد»: کار با تاریخ همان روز ثبت می‌شود و برنامهٔ آینده از روی آن دوباره چیده می‌شود."""
    row = _get(conn, missed_id)
    session = database.get_session(conn, row["session_id"])
    if _is_resolved(row, session):
        raise UserError(_("این کار بعداً انجام شده است."))
    day = date.fromisoformat(row["date"])
    task_service.mark_done(conn, {"session_id": row["session_id"], "kind": row["kind"], "result": "done"}, day)
    # همان کار که روزهای بعدش هم انجام‌نشده مانده، حالا انجام شده حساب می‌شود
    conn.execute(
        "DELETE FROM missed_tasks WHERE session_id = ? AND kind = ? AND review_round = ? AND date >= ?",
        (row["session_id"], row["kind"], row["review_round"], row["date"]),
    )
