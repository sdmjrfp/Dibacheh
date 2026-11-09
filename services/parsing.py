"""بررسی مقدارهای ورودی درخواست."""

from datetime import date

from errors import UserError
from i18n import _


def parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise UserError(_("تاریخ نامعتبر است."))


def positive_int(value, name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise UserError(_("{0} باید عدد باشد.", name))
    if number < 1:
        raise UserError(_("{0} باید حداقل 1 باشد.", name))
    return number
