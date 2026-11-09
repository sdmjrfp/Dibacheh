"""مسیرهای کارهای تقویم و سقف روزها."""

from flask import Blueprint

import database
from errors import UserError
from i18n import _
from services import missed
from services import tasks as task_service
from webutil import body, get_db, parse_date, state_response, today

bp = Blueprint("tasks", __name__)


@bp.route("/api/tasks/move", methods=["POST"])
def api_move_task():
    task_service.move_task(get_db(), body(), today())
    return state_response()


@bp.route("/api/tasks/done", methods=["POST"])
def api_task_done():
    task_service.mark_done(get_db(), body(), today())
    return state_response()


@bp.route("/api/tasks/undone", methods=["POST"])
def api_task_undone():
    task_service.mark_undone(get_db(), body().get("log_id"))
    return state_response()


@bp.route("/api/missed/<int:missed_id>", methods=["DELETE"])
def api_missed_dismiss(missed_id):
    missed.dismiss(get_db(), missed_id)
    return state_response()


@bp.route("/api/missed/<int:missed_id>/done", methods=["POST"])
def api_missed_done(missed_id):
    missed.mark_done(get_db(), missed_id)
    return state_response()


@bp.route("/api/days/range", methods=["POST"])
def api_set_day_range():
    """تعطیلی چندروزه: همهٔ روزهای بازه با هم. cap_minutes=null یعنی برداشتن تعطیلی."""
    data = body()
    start, end = parse_date(data.get("start")), parse_date(data.get("end"))
    if start is None or end is None or end < start:
        raise UserError(_("بازهٔ تاریخ نامعتبر است."))
    if (end - start).days > 366:
        raise UserError(_("بازه نمی‌تواند بیشتر از یک سال باشد."))
    database.set_day_range(get_db(), start, end, data.get("cap_minutes", 0))
    return state_response()


@bp.route("/api/days/<day>", methods=["PUT"])
def api_set_day(day):
    """سقف یک روز خاص. 0 = تعطیل، null = برگشت به سقف عادی."""
    target = parse_date(day)
    value = body().get("cap_minutes")
    if value is not None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise UserError(_("سقف روز باید عدد باشد."))
        if value < 0:
            raise UserError(_("سقف روز نمی‌تواند منفی باشد."))
    database.set_day_override(get_db(), target, value)
    return state_response()
