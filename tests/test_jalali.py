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


def test_every_day_for_ten_years_round_trips():
    expr = """(() => {
      let iso = "2020-01-01", bad = [];
      for (let i = 0; i < 3653; i++) {
        const j = Jalali.toJalali(iso);
        if (Jalali.fromJalali(j.y, j.m, j.d) !== iso) bad.push(iso);
        iso = Jalali.addDays(iso, 1);
      }
      return bad;
    })()"""
    assert run_js(expr) == []
