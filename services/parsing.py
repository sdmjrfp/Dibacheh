"""بررسی مقدارهای ورودی درخواست."""

from datetime import date

from errors import UserError


def parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise UserError("تاریخ نامعتبر است.")


def positive_int(value, name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise UserError(f"{name} باید عدد باشد.")
    if number < 1:
        raise UserError(f"{name} باید حداقل 1 باشد.")
    return number
