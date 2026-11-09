"""صفحهٔ اصلی، وضعیت کامل، برگرداندن، بستن برنامه و گزارش خطا."""

import os
import threading

from flask import Blueprint, abort, current_app, jsonify, render_template, request

import config
import database
import i18n
import platform_tools
import undo
from errors import UserError
from i18n import _
from webutil import body, build_state, get_db, json_ready, parse_date, state_data, state_response

bp = Blueprint("core", __name__)


@bp.route("/")
def index():
    """صفحهٔ اصلی داشبورد."""
    settings = database.get_settings(get_db())
    language = settings["language"]
    i18n.set_language(language)
    return render_template("index.html", csrf_token=config.CSRF_TOKEN, language=language,
                           direction=i18n.LANGUAGES[language][1], calendar=settings["calendar"],
                           first_weekday=settings["first_weekday"])


@bp.route("/api/state")
def api_state():
    return state_response()


@bp.route("/api/plan")
def api_plan():
    """کل برنامه، که هر بار از نو ساخته می‌شود."""
    return jsonify(json_ready(state_data()["plan"]))


@bp.route("/api/plan/range")
def api_plan_range():
    """روزهای یک بازه از برنامه؛ برای روزهای دور که همراه وضعیت فرستاده نمی‌شوند."""
    start, end = parse_date(request.args.get("start")), parse_date(request.args.get("end"))
    if start is None or end is None:
        raise UserError(_("بازهٔ تاریخ نامعتبر است."))
    days = [d for d in state_data()["plan"]["days"] if start <= d["date"] <= end]
    return jsonify(json_ready(days))


@bp.route("/api/undo", methods=["POST"])
def api_undo():
    """یک مرحله به عقب. وضعیت فعلی در فهرست «بازگرداندن» می‌رود تا بشود دوباره جلو رفت."""
    if not undo.stack:
        raise UserError(_("تغییری برای برگرداندن نیست."))
    label, snapshot = undo.stack.pop()
    undo.redo_stack.append((label, undo.snapshot(get_db())))
    undo.restore(get_db(), snapshot)
    state = build_state()
    state["undone"] = _(label)
    return jsonify(state)


@bp.route("/api/redo", methods=["POST"])
def api_redo():
    """تغییری را که برگردانده شده بود دوباره انجام می‌دهد."""
    if not undo.redo_stack:
        raise UserError(_("تغییری برای بازگرداندن نیست."))
    label, snapshot = undo.redo_stack.pop()
    undo.stack.append((label, undo.snapshot(get_db())))
    undo.restore(get_db(), snapshot)
    state = build_state()
    state["redone"] = _(label)
    return jsonify(state)


@bp.route("/api/quit", methods=["POST"])
def api_quit():
    """نسخهٔ نصبی ویندوز و لینوکس: برنامه را می‌بندد. (روی Mac، Quit از Dock این کار را می‌کند.)"""
    if not config.CAN_QUIT:
        abort(404)
    threading.Timer(0.3, os._exit, [0]).start()   # اول جواب به صفحه برسد
    return jsonify({"ok": True})


@bp.route("/api/logs")
def api_logs():
    """200 خط آخر گزارش خطا، برای نمایش در تنظیمات."""
    path = config.log_file()
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:] if path.exists() else []
    return jsonify({"lines": lines, "path": str(path)})


@bp.route("/api/logs/reveal", methods=["POST"])
def api_logs_reveal():
    path = config.log_file()
    platform_tools.launch(platform_tools.reveal_args(path if path.exists() else path.parent.parent))
    return jsonify({"ok": True})


@bp.route("/api/logs/client", methods=["POST"])
def api_log_client_error():
    """خطای JavaScript صفحه هم در همان گزارش ثبت می‌شود."""
    data = body()
    current_app.logger.error("خطای صفحه: %s (%s:%s)", str(data.get("message"))[:500],
                     str(data.get("source"))[:200], str(data.get("line"))[:10])
    return jsonify({"ok": True})
