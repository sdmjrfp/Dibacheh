"""تست تبدیل تاریخ شمسی در static/jalali.js، از جمله سال کبیسه.

این تست فایل جاوااسکریپت را با Node اجرا می‌کند. اگر Node نصب نباشد، رد می‌شود (skip).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JALALI_JS = Path(__file__).resolve().parent.parent / "static" / "jalali.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node نصب نیست")


def run_js(expression):
    code = f"require({json.dumps(str(JALALI_JS))}); console.log(JSON.stringify({expression}));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("iso, jalali", [
    ("2024-03-20", [1403, 1, 1]),
    ("2024-03-19", [1402, 12, 29]),   # 1402 کبیسه نیست
    ("2025-03-20", [1403, 12, 30]),   # 1403 کبیسه است
    ("2025-03-21", [1404, 1, 1]),
    ("2021-03-20", [1399, 12, 30]),   # 1399 کبیسه است
    ("2026-03-21", [1405, 1, 1]),
    ("2026-11-05", [1405, 8, 14]),
    ("2029-03-20", [1408, 1, 1]),
])
def test_gregorian_to_jalali(iso, jalali):
    result = run_js(f"Jalali.toJalali({json.dumps(iso)})")
    assert [result["y"], result["m"], result["d"]] == jalali


def test_jalali_to_gregorian_round_trip():
    assert run_js("Jalali.fromJalali(1403, 12, 30)") == "2025-03-20"
    assert run_js("Jalali.fromJalali(1405, 8, 14)") == "2026-11-05"
    assert run_js("Jalali.fromJalali(1404, 7, 1)") == "2025-09-23"


def test_leap_years_and_month_lengths():
    assert run_js("[1399, 1403, 1408].map(Jalali.isLeap)") == [True, True, True]
    assert run_js("[1400, 1402, 1404].map(Jalali.isLeap)") == [False, False, False]
    assert run_js("[Jalali.monthLength(1403,12), Jalali.monthLength(1404,12), "
                  "Jalali.monthLength(1404,1), Jalali.monthLength(1404,7)]") == [30, 29, 31, 30]


def test_invalid_date_gives_null():
    assert run_js("Jalali.fromJalali(1404, 12, 30)") is None   # 1404 کبیسه نیست


def walk_days(start, count):
    """همهٔ روزها از start را در مرورگر (Node) تبدیل می‌کند."""
    return run_js(f"""(() => {{
      let iso = {json.dumps(start)}, days = [], bad = [];
      for (let i = 0; i < {count}; i++) {{
        const j = Jalali.toJalali(iso);
        days.push([j.y, j.m, j.d]);
        if (Jalali.fromJalali(j.y, j.m, j.d) !== iso) bad.push(iso);
        iso = Jalali.addDays(iso, 1);
      }}
      return {{days, bad}};
    }})()""")


def test_python_and_browser_agree_on_every_day_the_app_accepts():
    """jalali.py (برای خروجی) و jalali.js (برای صفحه) باید برای همهٔ روزها یکی باشند.

    بازه همان بازه‌ای است که کادر تاریخ می‌پذیرد: سال ۱۳۰۰ تا ۱۵۰۰ (js/core.js).
    بیرون از آن، در سال ۱۵۰۳، دو الگوریتم یک سال با هم فرق دارند.
    """
    from datetime import date, timedelta

    import jalali
    start = date(1921, 3, 21)   # ۱ فروردین ۱۳۰۰
    count = (date(2122, 3, 21) - start).days   # تا پایان ۱۵۰۰
    assert jalali.to_jalali(start) == (1300, 1, 1)
    assert jalali.to_jalali(start + timedelta(days=count - 1))[0] == 1500
    browser = walk_days(start.isoformat(), count)
    assert browser["bad"] == []   # هر روز، رفت و برگشت به همان روز می‌رسد
    python = [list(jalali.to_jalali(start + timedelta(days=i))) for i in range(count)]
    assert python == browser["days"]


def test_python_jalali_helpers():
    from datetime import date

    import jalali
    assert jalali.format_date(date(2026, 11, 5), weekday=True) == "پنجشنبه ۱۴ آبان ۱۴۰۵"
    assert jalali.iso_name(date(2025, 3, 20)) == "1403-12-30"
    assert jalali.month_bounds(date(2026, 11, 5)) == (date(2026, 10, 23), date(2026, 11, 21))
    assert jalali.week_start(date(2026, 11, 5)) == date(2026, 10, 31)


def test_digits_of_numbers_and_version_text():
    assert run_js('[Jalali.faNumber(1405), Jalali.faNumber("1.3.0"), Jalali.faNumber("12.5")]') == ["۱۴۰۵", "۱.۳.۰", "۱۲.۵"]


def test_gregorian_mode_in_browser():
    expr = """(() => {
      Jalali.configure({calendar: "gregorian", locale: "en"});
      return [Jalali.toJalali("2026-11-05"), Jalali.fromJalali(2026, 2, 30), Jalali.fromJalali(2024, 2, 29),
              Jalali.monthLength(2024, 2), Jalali.monthLength(2026, 2), Jalali.isLeap(2024), Jalali.MONTHS[0],
              Jalali.weekdayName(0), Jalali.faNumber(5), Jalali.format("2026-11-05")];
    })()"""
    assert run_js(expr) == [{"y": 2026, "m": 11, "d": 5}, None, "2024-02-29", 29, 28, True, "January", "Monday", "5", "November 5, 2026"]
