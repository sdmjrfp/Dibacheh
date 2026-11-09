"""ابزارهای مشترک مسیرها: اتصال دیتابیس، خواندن درخواست و ساختن جواب."""

from datetime import date, datetime

from flask import current_app, g, jsonify, request

import config
import database
import scheduler
import undo
from errors import UserError
from i18n import _
from services import state as state_service
from services.parsing import parse_date, positive_int  # noqa: F401 (برای مسیرها)

# وضعیت backup روزانه در همین اجرای برنامه، تا هر درخواست دوباره چک نکند
backup_status = {"day": None, "problem": None, "cloud_problem": None}


def get_db():
    """اتصال دیتابیس همین درخواست. در پایان درخواست بسته می‌شود."""
    if "db" not in g:
        g.db = database.connect(current_app.config["DB_PATH"])
    return g.db


def today():
    """«امروز» با توجه به ساعت شروع روز در تنظیمات."""
    settings = database.get_settings(get_db())
    return scheduler.effective_today(datetime.now(), settings["day_start_hour"])


def json_ready(value):
    """تاریخ‌ها را برای JSON به متن تبدیل می‌کند."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(json_ready(k)): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    return value


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise UserError(_("درخواست نامعتبر است."))
    return data


def state_data():
    """وضعیت کامل با تاریخ‌های پایتونی (برای خروجی HTML)."""
    extras = {
        "undo": undo.info(), "backup_problem": backup_status["problem"], "cloud_problem": backup_status["cloud_problem"],
        "can_quit": config.CAN_QUIT, "version": config.VERSION, "from_source": not config.FROZEN,
    }
    return state_service.state_data(get_db(), today(), extras)


def build_state():
    """وضعیت برای صفحه: برنامه فقط تا چند ماه آینده فرستاده می‌شود (services/state.py)."""
    return json_ready(state_service.trim_for_page(state_data()))


def state_response():
    return jsonify(build_state())
