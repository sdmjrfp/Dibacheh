"""سرور محلی برنامه.

این فایل فقط صفحه‌ها و مسیرها (route) را تعریف می‌کند.
منطق اصلی در فایل‌های دیگر است:
  scheduler.py  موتور چینش برنامه
  leitner.py    قانون‌های جعبه و مرور
  database.py   کار با SQLite
  sources.py    منابع درسی و Browse
  exporter.py   ساخت خروجی HTML

اجرا:
    .venv/bin/python app.py
بعد در مرورگر به آدرس http://127.0.0.1:5000 بروید.
"""

from datetime import date, datetime

from flask import Flask, g, jsonify, render_template

import database
import scheduler

# آدرس و پورت سرور.
# 127.0.0.1 یعنی فقط خود همین Mac می‌تواند به برنامه وصل شود،
# نه گوشی یا کامپیوتر دیگری در شبکه.
HOST = "127.0.0.1"
PORT = 5000

app = Flask(__name__)
app.config["DB_PATH"] = database.DB_PATH

# تاریخ آخرین backup در همین اجرای برنامه، تا هر درخواست دوباره چک نکند
_last_backup_day = None


def get_db():
    """اتصال دیتابیس همین درخواست. در پایان درخواست بسته می‌شود."""
    if "db" not in g:
        g.db = database.connect(app.config["DB_PATH"])
    return g.db


@app.teardown_appcontext
def close_db(_error):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def today():
    """«امروز» با توجه به ساعت شروع روز در تنظیمات."""
    settings = database.get_settings(get_db())
    return scheduler.effective_today(datetime.now(), settings["day_start_hour"])


@app.before_request
def backup_once_a_day():
    """اولین درخواست هر روز، یک backup از دیتابیس می‌گیرد."""
    global _last_backup_day
    day = today()
    if _last_backup_day == day:
        return
    conn = get_db()
    settings = database.get_settings(conn)
    database.daily_backup(conn, database.backup_folder(settings), settings["backup_retention"], day)
    _last_backup_day = day


def _json_ready(value):
    """تاریخ‌ها را برای JSON به متن تبدیل می‌کند."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(_json_ready(k)): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    return value


@app.route("/")
def index():
    """صفحهٔ اصلی داشبورد."""
    return render_template("index.html")


@app.route("/api/plan")
def api_plan():
    """کل برنامه، که هر بار از نو ساخته می‌شود."""
    inputs = database.load_plan_inputs(get_db())
    plan = scheduler.build_plan(
        inputs["items"], inputs["sessions"], inputs["settings"], inputs["day_overrides"], today()
    )
    return jsonify(_json_ready(plan))


if __name__ == "__main__":
    # debug خاموش است، چون حالت debug اجازهٔ اجرای کد از راه مرورگر را می‌دهد.
    app.run(host=HOST, port=PORT, debug=False)
