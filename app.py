"""سرور محلی برنامه: ساختن Flask، قانون‌های هر درخواست، و اجرا.

این فایل نقطهٔ شروع است. بقیه:
  routes/       مسیرهای وب، به تفکیک بخش
  services/     منطق برنامه، بدون وابستگی به وب
  scheduler.py  موتور چینش برنامه
  leitner.py    قانون‌های جعبه و مرور
  database.py   کار با SQLite
  sources.py    منابع درسی
  exporter.py   ساخت خروجی HTML
  reports.py    آمار و گزارش

هر درخواستی که چیزی را تغییر دهد، در جواب کل وضعیت تازه را برمی‌گرداند
(درس‌ها، دسته‌ها و برنامهٔ از نو ساخته‌شده)، تا صفحه بدون بارگذاری دوباره به‌روز شود.

اجرا:
    .venv/bin/python app.py
بعد در مرورگر به آدرس http://127.0.0.1:5000 بروید.
"""

import hmac
import logging
import mimetypes
import os
import sys
import threading
import urllib.request

from flask import Flask, abort, g, jsonify, request
from waitress import serve
from werkzeug.exceptions import HTTPException

import config
import database
import i18n
import jalali
import platform_tools
import undo
import webutil
from errors import NotFoundError, UserError
from i18n import _
from routes import core, data, items, settings, tasks, update
from webutil import get_db, today

# ویندوز گاهی نوع فایل .js را اشتباه می‌دهد و مرورگر module را اجرا نمی‌کند
mimetypes.add_type("text/javascript", ".js")

app = Flask(__name__, template_folder=str(config.RESOURCE_DIR / "templates"),
            static_folder=str(config.RESOURCE_DIR / "static"))
# برای امتحان برنامه با یک دیتابیس جدا، بدون دست زدن به داده‌های اصلی:
#     DIBACHEH_DB=/tmp/demo.sqlite3 .venv/bin/python app.py
app.config["DB_PATH"] = os.environ.get("DIBACHEH_DB") or database.DB_PATH

for module in (core, items, tasks, data, settings, update):
    app.register_blueprint(module.bp)


# ---------------------------------------------------------------------------
# امنیت
# ---------------------------------------------------------------------------

@app.before_request
def use_language():
    """زبان و تقویم این درخواست، از تنظیمات."""
    if request.endpoint == "static":
        return
    settings_now = database.get_settings(get_db())
    i18n.set_language(settings_now["language"])
    jalali.configure(settings_now["calendar"], settings_now["first_weekday"])


@app.before_request
def check_security():
    # بررسی Host جلوی حمله‌ای به نام DNS rebinding را می‌گیرد،
    # که در آن یک سایت دیگر خودش را جای 127.0.0.1 جا می‌زند.
    if request.host not in config.ALLOWED_HOSTS:
        abort(403)
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token, config.CSRF_TOKEN):
            abort(403)


@app.errorhandler(platform_tools.BrowseUnavailable)
def handle_browse_unavailable(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """خطای پیش‌بینی‌نشده در گزارش خطا ثبت می‌شود و صفحه یک پیام قابل فهم می‌گیرد."""
    if isinstance(error, HTTPException):
        return error
    app.logger.exception("خطا در %s %s", request.method, request.path)
    return jsonify({"error": _("خطای پیش‌بینی‌نشده‌ای پیش آمد. جزئیات در «گزارش خطا» در تنظیمات هست.")}), 500


@app.errorhandler(UserError)
def handle_user_error(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(NotFoundError)
def handle_not_found(_error):
    return jsonify({"error": _("پیدا نشد.")}), 404


@app.teardown_appcontext
def close_db(_error):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.before_request
def backup_once_a_day():
    """اولین درخواست هر روز، یک backup از دیتابیس می‌گیرد."""
    status = webutil.backup_status
    day = today()
    if status["day"] == day:
        return
    conn = get_db()
    settings_now = database.get_settings(conn)
    try:
        database.daily_backup(conn, config.backups_dir(settings_now), settings_now["backup_retention"], day)
    except database.BackupError as error:
        app.logger.error("backup سالم نبود: %s", error)
        status["problem"] = _("backup امروز سالم نبود و ذخیره نشد: {0}", error)
    else:
        status["problem"] = None
    status["day"] = day
    if settings_now["cloud_backup_folder"]:
        # پوشهٔ ابری می‌تواند کند باشد، پس برنامه منتظرش نمی‌ماند
        threading.Thread(target=copy_to_cloud, args=(config.backups_dir(settings_now), settings_now), daemon=True).start()


def copy_to_cloud(folder, settings_now):
    status = webutil.backup_status
    try:
        database.copy_backup_to_cloud(folder, settings_now["cloud_backup_folder"], settings_now["backup_retention"])
        status["cloud_problem"] = None
    except OSError as error:
        app.logger.warning("کپی backup در پوشهٔ ابری نشد: %s", error)
        status["cloud_problem"] = _("backup امروز در پوشهٔ ابری کپی نشد: {0}", error)


@app.before_request
def remember_for_undo():
    """قبل از هر تغییر یک کپی برای «برگرداندن»، و شروع یک تراکنش."""
    view = (request.endpoint or "").rsplit(".", 1)[-1]
    if request.method == "GET" or view not in undo.UNDO_LABELS:
        return
    undo.stack.append((undo.UNDO_LABELS[view], undo.snapshot(get_db())))
    g.undo_pushed = True
    # همهٔ تغییرهای این درخواست با هم ذخیره می‌شوند یا هیچ‌کدام
    database.begin_transaction(get_db())
    g.in_transaction = True
    # تغییر تازه یعنی تاریخچهٔ «بازگرداندن» دیگر معنی ندارد
    g.cleared_redo = list(undo.redo_stack)
    undo.redo_stack.clear()


@app.after_request
def finish_change(response):
    """اگر تغییر موفق بود ذخیره می‌شود؛ وگرنه همه‌چیز به حالت قبل برمی‌گردد."""
    failed = response.status_code >= 400
    if g.pop("in_transaction", False):
        database.end_transaction(get_db(), success=not failed)
    if g.get("undo_pushed") and failed and undo.stack:
        undo.stack.pop()
        undo.redo_stack.extend(g.get("cleared_redo", []))  # «بازگرداندن» سر جایش برمی‌گردد
    return response


# ---------------------------------------------------------------------------
# اجرا
# ---------------------------------------------------------------------------

def _already_running():
    """آیا دیباچه همین حالا روی این پورت باز است؟"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{config.HOST}:{config.PORT}/", timeout=2) as response:
            return b'name="csrf-token"' in response.read()
    except OSError:
        return False


def _open_page():
    platform_tools.launch(platform_tools.open_args(f"http://{config.HOST}:{config.PORT}/"))


def _start_desktop():
    """نسخهٔ نصبی ویندوز و لینوکس: صفحه را هم خودش باز می‌کند.

    خروجی True یعنی برنامه از قبل باز بود و فقط صفحه باز شد.
    """
    if _already_running():
        _open_page()
        return True
    threading.Timer(1.0, _open_page).start()
    return False


def main():
    if sys.stdout is None or sys.stderr is None:   # برنامهٔ ویندوزی بدون پنجرهٔ کنسول
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    config.setup_logging()
    if config.CAN_QUIT and not os.environ.get("DIBACHEH_NO_LAUNCH") and _start_desktop():
        return
    try:
        # waitress سرور کوچک و پایدار است؛ debug خود Flask هم خاموش می‌ماند.
        serve(app, host=config.HOST, port=config.PORT, threads=8)
    except OSError as error:
        logging.getLogger().error("سرور اجرا نشد (پورت %s): %s", config.PORT, error)
        print(f"Port {config.PORT} is in use: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
