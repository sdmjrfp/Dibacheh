"""کارهای تقویم: جابه‌جایی، ثبت انجام‌شده و برگرداندن به انجام‌نشده."""

import json
from datetime import date, timedelta

import database
import leitner
from errors import UserError
from i18n import _
from services.parsing import parse_date, positive_int


def move_task(conn, data, day):
    """یک خواندن یا مرور را به روز دیگری می‌برد (جلو یا عقب).

    date خالی یعنی «برگشت به چینش خودکار».
    برنامه کار را زودتر از این روز نمی‌آورد. اگر آن روز انجام نشود، جلوتر می‌رود.
    مرورهای بعدی همان جلسه هم خودبه‌خود به همان اندازه جابه‌جا می‌شوند.
    """
    session = database.get_session(conn, data.get("session_id"))
    if session is None:
        raise UserError(_("جلسه پیدا نشد."))
    target = parse_date(data.get("date"))
    if target is not None and target < day:
        raise UserError(_("کار را نمی‌شود به روزهای گذشته برد."))
    kind = data.get("kind")
    if kind == "read":
        if session["status"] not in ("unread", "reading"):
            raise UserError(_("این جلسه خوانده شده است."))
        database.update_session(conn, session["id"], read_manual_date=target)
    elif kind == "review":
        if session["status"] != "reviewing":
            raise UserError(_("این جلسه هنوز خوانده نشده؛ خواندنش را جابه‌جا کنید تا مرورها هم با آن بروند."))
        if target is not None and session["read_at"] and target <= session["read_at"]:
            raise UserError(_("مرور باید بعد از روز خواندن همان جلسه باشد."))
        database.update_session(conn, session["id"], review_manual_date=target)
    else:
        raise UserError(_("نوع کار نامعتبر است."))


def mark_done(conn, data, day):
    """ثبت انجام یک کار، همیشه با تاریخ امروز.

    result:
      done        انجام شد
      partial     فقط بخشی از خواندن انجام شد (minutes = دقیقهٔ خوانده‌شده)
      needs_more  مرور انجام شد ولی نیاز به مرور بیشتر دارد (برگشت به جعبهٔ 1)
    کار آینده را هم می‌شود زودتر تیک زد؛ باز هم با تاریخ امروز ثبت می‌شود.
    """
    session = database.get_session(conn, data.get("session_id"))
    if session is None:
        raise UserError(_("جلسه پیدا نشد."))
    item = database.get_item(conn, session["item_id"])
    settings = database.get_settings(conn)
    intervals = leitner.intervals_for(item, settings)
    kind = data.get("kind")
    result = data.get("result", "done")

    if kind == "routine":
        if item["item_type"] != "routine" or session["status"] == "finished":
            raise UserError(_("این کار روتین قبلاً ثبت شده است."))
        database.update_session(conn, session["id"], status="finished", minutes_done=session["minutes"])
        database.add_log(conn, session["id"], day, "routine", session["minutes"], "done", before=session)

    elif kind == "read":
        if session["status"] not in ("unread", "reading"):
            raise UserError(_("این جلسه قبلاً خوانده شده است."))
        already = session["minutes_done"] or 0
        if result == "partial":
            minutes = positive_int(data.get("minutes"), _("دقیقهٔ خوانده‌شده"))
            if already + minutes < session["minutes"]:
                # بقیهٔ جلسه از فردا چیده می‌شود، نه دوباره امروز
                database.update_session(conn, session["id"], status="reading",
                                        minutes_done=already + minutes,
                                        read_manual_date=day + timedelta(days=1))
                database.add_log(conn, session["id"], day, "read", minutes, "partial", before=session)
                return
            # اگر با این مقدار کل جلسه خوانده شد، مثل «انجام شد» ثبت می‌شود
        elif result != "done":
            raise UserError(_("نتیجهٔ نامعتبر."))
        updated = leitner.finish_reading(session, day, intervals)
        _save_session(conn, updated)
        database.add_log(conn, session["id"], day, "read", session["minutes"] - already, "done", before=session)

    elif kind == "review":
        if session["status"] != "reviewing":
            raise UserError(_("این جلسه مرور منتظر ندارد."))
        minutes = leitner.review_minutes(session, item, settings)
        if result == "needs_more":
            updated = leitner.needs_more_review(session, day, intervals)
        elif result == "done":
            updated = leitner.record_review(session, day, intervals)
        else:
            raise UserError(_("نتیجهٔ نامعتبر."))
        _save_session(conn, updated)
        database.add_log(conn, session["id"], day, "review", minutes, result, before=session)
    else:
        raise UserError(_("نوع کار نامعتبر است."))


def mark_undone(conn, log_id):
    """یک کار تیک‌خورده را به حالت انجام‌نشده برمی‌گرداند.

    جلسه دقیقاً به وضعیت قبل از همان تیک برمی‌گردد و کار دوباره وارد برنامه می‌شود.
    چون هر تیک روی تیک قبلی همان جلسه سوار است، فقط آخرین تیک هر جلسه برمی‌گردد.
    """
    log = database.get_log(conn, log_id)
    if log is None:
        raise UserError(_("این کار در سابقه پیدا نشد."))
    logs = database.list_log(conn, log["session_id"])
    if logs[-1]["id"] != log["id"]:
        raise UserError(_("اول کار بعدیِ همین جلسه را انجام‌نشده کنید."))
    session = database.get_session(conn, log["session_id"])
    if session["status"] == "unread" and not session["minutes_done"]:
        raise UserError(_("این درس بعد از این کار به خوانده‌نشده برگردانده شده است."))
    if log.get("before_state"):
        before = json.loads(log["before_state"])
        restored = {k: (date.fromisoformat(v) if v and k in database.DATE_COLUMNS else v)
                    for k, v in before.items()}
    else:
        restored = _replay_session(conn, session, logs[:-1])
    item = database.get_item(conn, session["item_id"])
    if restored.get("status") == "reviewing" and item.get("no_reviews"):
        restored["status"] = "finished"   # مرورهای این درس حذف شده‌اند
    database.update_session(conn, session["id"], **restored)
    database.delete_log(conn, log["id"])


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
